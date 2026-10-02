"""Scan-driven temporal state regressions over the owner-scoped product API."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import twf.discovery.product_service as product_module
from twf.auth import create_user
from twf.config.settings import Settings
from twf.discovery.domain import (
    DiscoveryLifecycleState,
    DiscoveryObservation,
    DiscoveryObservationKind,
    EvaluationCoverage,
    InstrumentIdentity,
    RevisionRef,
    ScanComparabilityDescriptor,
)
from twf.discovery.temporal import RunAdmission, TemporalStore
from twf.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from twf.infrastructure.discovery import (
    DiscoveryComparisonScopeRecord,
    DiscoveryEpisodeRecord,
    DiscoveryObservationRecord,
    DiscoveryProjectionCheckpointRecord,
    DiscoveryScanAdmissionRecord,
)
from twf.infrastructure.identity import User
from twf.main import create_app

ORIGIN = "https://web.example"
PASSWORD = "test-only-strong-password"


@pytest.fixture
def temporal_client() -> Iterator[TestClient]:
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    engine = create_database_engine(Settings())
    with session_scope(create_session_factory(engine)) as session:
        create_user(session, "temporal-alice", "Temporal Alice", PASSWORD)
        create_user(session, "temporal-bob", "Temporal Bob", PASSWORD)
        session.commit()
    with TestClient(
        create_app(Settings(cors_origins=(ORIGIN,)), engine_factory=lambda _: engine)
    ) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "temporal-alice", "password": PASSWORD},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 200
        yield client


def payload(**changes: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "universe": ["RELIANCE"],
        "provider": "internal",
        "profile": "RELATIVE_VOLUME",
        "horizon": "5d",
        "intent": "MOMENTUM",
        "include_llm": False,
        "context_mode": "partial",
    }
    result.update(changes)
    return result


def run(client: TestClient, **changes: Any) -> dict[str, Any]:
    response = client.post(
        "/api/v1/discovery/scans",
        json=payload(**changes),
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def test_present_absent_and_null_absent_relevance(
    temporal_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = run(temporal_client)
    candidate_id = first["candidates"][0]["candidate_id"]
    original = product_module.synthetic_fixture

    def no_match(symbol: str, progression: int = 0) -> product_module.SyntheticInstrumentFixture:
        return replace(original(symbol, progression), relative_volume=Decimal("0.20"))

    monkeypatch.setattr(product_module, "synthetic_fixture", no_match)
    second = run(temporal_client)
    assert second["candidates"] == []
    detail = temporal_client.get(f"/api/v1/discovery/candidates/{candidate_id}").json()
    assert detail["lifecycle"] == "STALE"
    assert [item["kind"] for item in detail["observations"]][:2] == [
        "ABSENT",
        "PRESENT",
    ]
    absent = detail["observations"][0]
    assert absent["relevance_score"] is None
    assert absent["relevance_band"] is None
    assert absent["reason"] == "not-rediscovered"

    monkeypatch.setattr(product_module, "synthetic_fixture", original)
    recovered = run(temporal_client)
    assert recovered["candidates"][0]["candidate_id"] == candidate_id
    current = temporal_client.get(f"/api/v1/discovery/candidates/{candidate_id}").json()
    assert current["lifecycle"] == "CURRENT"
    assert [item["kind"] for item in current["observations"]][:3] == [
        "PRESENT",
        "ABSENT",
        "PRESENT",
    ]


def test_repeated_absence_stays_nonterminal(
    temporal_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = run(temporal_client)
    candidate_id = first["candidates"][0]["candidate_id"]
    original = product_module.synthetic_fixture

    def no_match(symbol: str, progression: int = 0) -> product_module.SyntheticInstrumentFixture:
        return replace(original(symbol, progression), relative_volume=Decimal("0.20"))

    monkeypatch.setattr(product_module, "synthetic_fixture", no_match)
    run(temporal_client, idempotency_key="first-absence")
    run(temporal_client, idempotency_key="second-absence")
    detail = temporal_client.get(f"/api/v1/discovery/candidates/{candidate_id}").json()
    assert detail["lifecycle"] == "STALE"
    assert [item["kind"] for item in detail["observations"]][:2] == [
        "ABSENT",
        "ABSENT",
    ]
    assert all(item["relevance_score"] is None for item in detail["observations"][:2])


def test_terminal_owner_fence_requires_a_new_linked_episode(
    temporal_client: TestClient,
) -> None:
    first = run(temporal_client)
    original = first["candidates"][0]
    dismissed = temporal_client.post(
        "/api/v1/discovery/candidates/{}/lifecycle".format(original["candidate_id"]),
        json={
            "action": "DISMISS",
            "revision": original["revision"],
            "reason": "temporal-owner-fence-test",
        },
        headers={"Origin": ORIGIN},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["lifecycle"] == "REJECTED"
    second = run(temporal_client, idempotency_key="after-owner-fence")
    successor = second["candidates"][0]
    assert successor["candidate_id"] != original["candidate_id"]
    detail = temporal_client.get(
        "/api/v1/discovery/candidates/{}".format(successor["candidate_id"])
    ).json()
    assert detail["previous_episode_id"] == original["episode_id"]
    assert detail["lifecycle"] == "NEW"


def test_explicit_scan_closes_elapsed_window_and_present_opens_successor(
    temporal_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = run(temporal_client)
    original = first["candidates"][0]
    app = cast(FastAPI, temporal_client.app)
    with session_scope(app.state.session_factory) as session:
        episode = session.scalar(
            select(DiscoveryEpisodeRecord).where(
                DiscoveryEpisodeRecord.id == UUID(original["episode_id"])
            )
        )
        assert episode is not None
        stored = dict(episode.payload["episode"])
        stored["window"] = {
            **stored["window"],
            "ends_at": "2000-01-01T00:00:00+00:00",
        }
        episode.payload = {**episode.payload, "episode": stored}
        session.commit()

    original_fixture = product_module.synthetic_fixture

    def no_match(symbol: str, progression: int = 0) -> product_module.SyntheticInstrumentFixture:
        return replace(original_fixture(symbol, progression), relative_volume=Decimal("0.20"))

    monkeypatch.setattr(product_module, "synthetic_fixture", no_match)
    run(temporal_client, idempotency_key="elapsed-absence")
    closed = temporal_client.get(
        "/api/v1/discovery/candidates/{}".format(original["candidate_id"])
    ).json()
    assert closed["lifecycle"] == "EXPIRED"
    assert any(item.get("event_type") == "WINDOW_CLOSURE" for item in closed["transitions"])

    monkeypatch.setattr(product_module, "synthetic_fixture", original_fixture)
    successor = run(temporal_client, idempotency_key="elapsed-successor")["candidates"][0]
    assert successor["candidate_id"] != original["candidate_id"]
    successor_detail = temporal_client.get(
        "/api/v1/discovery/candidates/{}".format(successor["candidate_id"])
    ).json()
    assert successor_detail["previous_episode_id"] == original["episode_id"]
    assert successor_detail["lifecycle"] == "NEW"


def test_universe_exclusion_is_not_evaluated_and_lifecycle_neutral(
    temporal_client: TestClient,
) -> None:
    first = run(temporal_client)
    candidate_id = first["candidates"][0]["candidate_id"]
    before = first["candidates"][0]["lifecycle"]
    second = run(temporal_client, universe=["MCX"])
    temporal = temporal_client.get(
        f"/api/v1/discovery/candidates/{candidate_id}/observations",
        params={"limit": 20},
    )
    assert temporal.status_code == 200
    body = temporal.json()
    assert body["items"][0]["kind"] == "NOT_EVALUATED"
    assert body["items"][0]["coverage"] == "NOT_REQUESTED"
    assert body["items"][0]["relevance_score"] is None
    current = temporal_client.get(f"/api/v1/discovery/candidates/{candidate_id}").json()
    assert current["lifecycle"] == before
    as_scanned = temporal_client.get(
        f"/api/v1/discovery/scans/{second['summary']['run_id']}/temporal",
        params={"mode": "as_scanned"},
    ).json()
    assert {item["observation"]["kind"] for item in as_scanned["items"]} == {
        "PRESENT",
        "NOT_EVALUATED",
    }


def test_run_views_keep_historical_observation_separate_from_current_state(
    temporal_client: TestClient,
) -> None:
    first = run(temporal_client)
    run(temporal_client)
    run_id = first["summary"]["run_id"]
    scanned = temporal_client.get(
        f"/api/v1/discovery/scans/{run_id}/temporal",
        params={"mode": "as_scanned"},
    ).json()
    current = temporal_client.get(
        f"/api/v1/discovery/scans/{run_id}/temporal",
        params={"mode": "current_state"},
    ).json()
    assert scanned["items"][0]["candidate"] is None
    assert scanned["items"][0]["observation"]["lifecycle_after"] == "NEW"
    assert current["items"][0]["candidate"]["lifecycle"] == "CURRENT"
    assert current["items"][0]["candidate"]["temporal"]["total_count"] == 2


def test_idempotent_run_replay_and_hot_cold_pagination(temporal_client: TestClient) -> None:
    configured = temporal_client.get("/api/v1/discovery/settings").json()
    configured["hot_observation_count"] = 5
    response = temporal_client.put(
        "/api/v1/discovery/settings", json=configured, headers={"Origin": ORIGIN}
    )
    assert response.status_code == 200
    request = payload(idempotency_key="stable-temporal-replay")
    first_response = temporal_client.post(
        "/api/v1/discovery/scans", json=request, headers={"Origin": ORIGIN}
    )
    second_response = temporal_client.post(
        "/api/v1/discovery/scans", json=request, headers={"Origin": ORIGIN}
    )
    assert first_response.status_code == second_response.status_code == 201
    first = first_response.json()
    assert second_response.json()["summary"]["run_id"] == first["summary"]["run_id"]
    candidate_id = first["candidates"][0]["candidate_id"]
    for index in range(6):
        run(temporal_client, idempotency_key=f"hot-window-{index}")
    page = temporal_client.get(
        f"/api/v1/discovery/candidates/{candidate_id}/observations",
        params={"limit": 3, "offset": 5},
    ).json()
    assert page["total"] == 7
    assert len(page["items"]) == 2
    assert all(not item["is_hot"] for item in page["items"])
    with session_scope(cast(FastAPI, temporal_client.app).state.session_factory) as session:
        count = session.scalar(select(func.count()).select_from(DiscoveryObservationRecord))
        assert count == 7
        episode = session.scalar(
            select(DiscoveryEpisodeRecord).where(
                DiscoveryEpisodeRecord.candidate_id == UUID(candidate_id)
            )
        )
        assert episode is not None
        episode.state = DiscoveryLifecycleState.REJECTED.value
        rebuilt = TemporalStore(session, episode.user_id).rebuild_projection(episode)
        assert rebuilt == DiscoveryLifecycleState.CURRENT
        checkpoint = session.get(DiscoveryProjectionCheckpointRecord, episode.id)
        assert checkpoint is not None
        assert checkpoint.through_sequence == 7
        assert checkpoint.prefix_digest


def test_late_result_is_historical_and_projection_rebuild_is_deterministic(
    temporal_client: TestClient,
) -> None:
    first = run(temporal_client)
    candidate_id = UUID(first["candidates"][0]["candidate_id"])
    app = cast(FastAPI, temporal_client.app)
    with session_scope(app.state.session_factory) as session:
        owner_id = session.scalar(select(User.id).where(User.username == "temporal-alice"))
        assert owner_id is not None
        episode = session.scalar(
            select(DiscoveryEpisodeRecord).where(
                DiscoveryEpisodeRecord.candidate_id == candidate_id
            )
        )
        assert episode is not None and episode.comparison_scope_id is not None
        instrument = InstrumentIdentity.model_validate(episode.payload["episode"]["instrument"])
        newer = RunAdmission(uuid4(), episode.comparison_scope_id, 3, "ADMITTED", False)
        older = RunAdmission(uuid4(), episode.comparison_scope_id, 2, "ADMITTED", False)
        store = TemporalStore(session, owner_id)
        observation_time = episode.updated_at.replace(tzinfo=UTC)
        store.append_observation(
            admission=newer,
            instrument=instrument,
            kind=DiscoveryObservationKind.ABSENT,
            coverage=EvaluationCoverage.EVALUATED,
            reason="newer-authoritative-absence",
            observed_at=observation_time,
            source_data_time=observation_time,
            source_sample_key="newer-source",
            episode=episode,
        )
        late = store.append_observation(
            admission=older,
            instrument=instrument,
            kind=DiscoveryObservationKind.PRESENT,
            coverage=EvaluationCoverage.EVALUATED,
            reason="older-completed-late",
            observed_at=observation_time,
            source_data_time=observation_time,
            source_sample_key="older-source",
            episode=episode,
            scan_match_id=uuid4(),
            relevance_score=Decimal("0.81"),
        )
        session.flush()
        assert episode.state == DiscoveryLifecycleState.STALE.value
        late_value = DiscoveryObservation.model_validate(late.payload["observation"])
        assert late_value.reason == "late-observation-quarantined"
        assert late_value.novelty.value == "NOVEL"

        changed_model = RunAdmission(uuid4(), episode.comparison_scope_id, 4, "ADMITTED", False)
        changed_model_run = changed_model.run_id
        store.append_observation(
            admission=changed_model,
            instrument=instrument,
            kind=DiscoveryObservationKind.PRESENT,
            coverage=EvaluationCoverage.EVALUATED,
            reason="new-score-series",
            observed_at=observation_time,
            source_data_time=observation_time,
            source_sample_key="score-series-v3",
            episode=episode,
            scan_match_id=uuid4(),
            relevance_score=Decimal("0.77"),
            relevance_policy=RevisionRef(id="deterministic-relevance-v3", version="3"),
        )
        incomplete = RunAdmission(uuid4(), episode.comparison_scope_id, 5, "ADMITTED", False)
        store.append_observation(
            admission=incomplete,
            instrument=instrument,
            kind=DiscoveryObservationKind.NOT_EVALUATED,
            coverage=EvaluationCoverage.PARTIAL_FAILURE,
            reason="provider-partial-failure",
            observed_at=observation_time,
            source_data_time=None,
            source_sample_key=None,
            episode=episode,
        )
        summary = store.summary(episode, 5)
        assert summary is not None
        assert summary.latest_observation_kind == DiscoveryObservationKind.NOT_EVALUATED
        assert summary.latest_attempted_run_id == incomplete.run_id
        assert summary.latest_comparable_run_id == changed_model_run
        assert summary.relevance_model == "deterministic-relevance-v3@3"
        assert summary.relevance_delta is None
        assert episode.state == DiscoveryLifecycleState.CURRENT.value

        episode.state = DiscoveryLifecycleState.REJECTED.value
        rebuilt = store.rebuild_projection(episode)
        assert rebuilt == DiscoveryLifecycleState.CURRENT
        assert episode.state == DiscoveryLifecycleState.CURRENT.value
        rebuilt_summary = store.summary(episode, 5)
        assert rebuilt_summary is not None
        assert rebuilt_summary.latest_comparable_run_id == changed_model_run
        assert rebuilt_summary.latest_attempted_run_id == incomplete.run_id
        session.commit()


def test_temporal_records_and_owner_boundaries_are_durable(temporal_client: TestClient) -> None:
    result = run(temporal_client)
    run_id = UUID(result["summary"]["run_id"])
    with session_scope(cast(FastAPI, temporal_client.app).state.session_factory) as session:
        admission = session.get(DiscoveryScanAdmissionRecord, run_id)
        assert admission is not None and admission.status == "FINALIZED"
        assert admission.result_digest
        observation = session.scalar(
            select(DiscoveryObservationRecord).where(DiscoveryObservationRecord.run_id == run_id)
        )
        assert observation is not None
        assert observation.user_id == admission.user_id
        assert observation.scope_id == admission.scope_id
    temporal_client.post("/api/v1/auth/logout", json={}, headers={"Origin": ORIGIN})
    login = temporal_client.post(
        "/api/v1/auth/login",
        json={"username": "temporal-bob", "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert login.status_code == 200
    assert temporal_client.get(f"/api/v1/discovery/scans/{run_id}/temporal").status_code == 404


def test_duplicate_source_sample_cannot_manufacture_confirmation(
    temporal_client: TestClient,
) -> None:
    first = run(temporal_client)
    candidate_id = UUID(first["candidates"][0]["candidate_id"])
    app = cast(FastAPI, temporal_client.app)
    with session_scope(app.state.session_factory) as session:
        episode = session.scalar(
            select(DiscoveryEpisodeRecord).where(
                DiscoveryEpisodeRecord.candidate_id == candidate_id
            )
        )
        assert episode is not None and episode.comparison_scope_id is not None
        prior = session.scalar(
            select(DiscoveryObservationRecord).where(
                DiscoveryObservationRecord.episode_id == episode.id
            )
        )
        assert prior is not None and prior.source_sample_key is not None
        prior_value = DiscoveryObservation.model_validate(prior.payload["observation"])
        instrument = InstrumentIdentity.model_validate(episode.payload["episode"]["instrument"])
        row = TemporalStore(session, episode.user_id).append_observation(
            admission=RunAdmission(uuid4(), episode.comparison_scope_id, 2, "ADMITTED", False),
            instrument=instrument,
            kind=DiscoveryObservationKind.PRESENT,
            coverage=EvaluationCoverage.EVALUATED,
            reason="same-provider-sample-redelivered",
            observed_at=prior_value.observed_at,
            source_data_time=prior_value.source_data_time,
            source_sample_key=prior.source_sample_key,
            episode=episode,
            scan_match_id=uuid4(),
            relevance_score=prior_value.relevance_score,
            relevance_band=prior_value.relevance_band,
            relevance_policy=prior_value.relevance_policy,
        )
        value = DiscoveryObservation.model_validate(row.payload["observation"])
        assert value.novelty.value == "DUPLICATE"
        assert episode.state == DiscoveryLifecycleState.NEW.value
        assert episode.payload["temporal"]["distinct_present_count"] == 1
        session.commit()


def test_profile_and_provider_semantics_use_distinct_comparison_scopes(
    temporal_client: TestClient,
) -> None:
    internal = run(temporal_client, idempotency_key="internal-relative")
    momentum = run(
        temporal_client,
        profile="MOMENTUM",
        idempotency_key="internal-momentum",
    )
    tradingview = run(
        temporal_client,
        provider="tradingview-synthetic",
        idempotency_key="tradingview-relative",
    )
    candidate_ids = {
        internal["candidates"][0]["candidate_id"],
        momentum["candidates"][0]["candidate_id"],
        tradingview["candidates"][0]["candidate_id"],
    }
    assert len(candidate_ids) == 3
    app = cast(FastAPI, temporal_client.app)
    with session_scope(app.state.session_factory) as session:
        rows = tuple(
            session.scalars(
                select(DiscoveryEpisodeRecord).where(
                    DiscoveryEpisodeRecord.candidate_id.in_(
                        tuple(UUID(value) for value in candidate_ids)
                    )
                )
            )
        )
        assert len(rows) == 3
        assert len({row.comparison_scope_id for row in rows}) == 3


def test_projection_persistence_failure_rolls_back_and_closes_admission(
    temporal_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = run(temporal_client)
    candidate_id = UUID(first["candidates"][0]["candidate_id"])
    app = cast(FastAPI, temporal_client.app)
    with session_scope(app.state.session_factory) as session:
        episode = session.scalar(
            select(DiscoveryEpisodeRecord).where(
                DiscoveryEpisodeRecord.candidate_id == candidate_id
            )
        )
        assert episode is not None and episode.comparison_scope_id is not None
        scope = session.get(DiscoveryComparisonScopeRecord, episode.comparison_scope_id)
        assert scope is not None
        descriptor = ScanComparabilityDescriptor.model_validate(scope.descriptor)
        store = TemporalStore(session, episode.user_id)
        admission = store.admit_run(
            descriptor,
            run_id=uuid4(),
            request_key="forced-projection-failure",
            request_digest="1" * 64,
            as_of=episode.updated_at.replace(tzinfo=UTC),
            payload={"test": "projection-failure"},
        )
        episode = session.get(DiscoveryEpisodeRecord, episode.id)
        assert episode is not None
        instrument = InstrumentIdentity.model_validate(episode.payload["episode"]["instrument"])
        before = session.scalar(
            select(func.count())
            .select_from(DiscoveryObservationRecord)
            .where(DiscoveryObservationRecord.episode_id == episode.id)
        )

        def fail_projection(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("forced projection persistence failure")

        monkeypatch.setattr(TemporalStore, "apply_projection", fail_projection)
        with pytest.raises(RuntimeError, match="forced projection"):
            store.append_observation(
                admission=admission,
                instrument=instrument,
                kind=DiscoveryObservationKind.ABSENT,
                coverage=EvaluationCoverage.EVALUATED,
                reason="forced-failure",
                observed_at=episode.updated_at.replace(tzinfo=UTC),
                source_data_time=episode.updated_at.replace(tzinfo=UTC),
                source_sample_key="forced-failure-sample",
                episode=episode,
            )
        failed = session.get(DiscoveryScanAdmissionRecord, admission.run_id)
        assert failed is not None and failed.status == "FAILED"
        after = session.scalar(
            select(func.count())
            .select_from(DiscoveryObservationRecord)
            .where(DiscoveryObservationRecord.episode_id == episode.id)
        )
        assert after == before
        preserved = session.get(DiscoveryEpisodeRecord, episode.id)
        assert preserved is not None and preserved.state == DiscoveryLifecycleState.NEW.value


def test_logical_rollover_is_restart_safe_and_cold_core_reconstructs(
    temporal_client: TestClient,
) -> None:
    configured = temporal_client.get("/api/v1/discovery/settings").json()
    configured["hot_observation_count"] = 5
    assert (
        temporal_client.put(
            "/api/v1/discovery/settings", json=configured, headers={"Origin": ORIGIN}
        ).status_code
        == 200
    )
    first = run(temporal_client, idempotency_key="restart-rollover-0")
    candidate_id = first["candidates"][0]["candidate_id"]
    for index in range(8):
        run(temporal_client, idempotency_key=f"restart-rollover-{index + 1}")
    before = temporal_client.get(
        f"/api/v1/discovery/candidates/{candidate_id}/observations",
        params={"limit": 4, "offset": 5},
    ).json()
    assert before["total"] == 9
    assert len(before["items"]) == 4
    assert all(item["is_hot"] is False for item in before["items"])

    app = cast(FastAPI, temporal_client.app)
    with session_scope(app.state.session_factory) as session:
        episode = session.scalar(
            select(DiscoveryEpisodeRecord).where(
                DiscoveryEpisodeRecord.candidate_id == UUID(candidate_id)
            )
        )
        assert episode is not None
        episode.state = DiscoveryLifecycleState.REJECTED.value
        rebuilt = TemporalStore(session, episode.user_id).rebuild_projection(episode)
        assert rebuilt == DiscoveryLifecycleState.CURRENT
        session.commit()

    after = temporal_client.get(
        f"/api/v1/discovery/candidates/{candidate_id}/observations",
        params={"limit": 4, "offset": 5},
    ).json()
    assert [(item["observation_id"], item["kind"]) for item in after["items"]] == [
        (item["observation_id"], item["kind"]) for item in before["items"]
    ]
