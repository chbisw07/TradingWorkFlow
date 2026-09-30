"""Integrated Sprint-2 product regressions over the real owner-scoped API."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from twf.auth import create_user
from twf.config.settings import Settings
from twf.discovery.product_service import identity, market_series
from twf.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from twf.infrastructure.discovery import (
    DiscoveryEpisodeRecord,
    DiscoverySnapshotRecord,
    ScanMatchRecord,
    ScanRunRecord,
)
from twf.main import create_app

ORIGIN = "https://web.example"
PASSWORD = "test-only-strong-password"


@pytest.fixture
def product_client() -> Iterator[TestClient]:
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    engine = create_database_engine(Settings())
    with session_scope(create_session_factory(engine)) as session:
        create_user(session, "alice", "Alice", PASSWORD)
        create_user(session, "bob", "Bob", PASSWORD)
        session.commit()
    with TestClient(
        create_app(Settings(cors_origins=(ORIGIN,)), engine_factory=lambda _: engine)
    ) as client:
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"username": "alice", "password": PASSWORD},
                headers={"Origin": ORIGIN},
            ).status_code
            == 200
        )
        yield client


def post(client: TestClient, path: str, payload: dict[str, Any]) -> Any:
    response = client.post(path, json=payload, headers={"Origin": ORIGIN})
    assert response.status_code in {200, 201}, response.text
    return response.json()


def scan_payload(**changes: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "universe": ["RELIANCE", "TCS"],
        "provider": "internal",
        "profile": "RELATIVE_VOLUME",
        "horizon": "5d",
        "intent": "MOMENTUM",
        "include_llm": False,
        "context_mode": "partial",
    }
    payload.update(changes)
    return payload


def test_internal_scan_context_candidates_and_history(product_client: TestClient) -> None:
    result = post(product_client, "/api/v1/discovery/scans", scan_payload())
    assert result["summary"]["provider"] == "internal"
    assert result["summary"]["match_count"] == 2
    assert result["summary"]["candidate_count"] == 2
    assert result["market_context"]["availability"] == "PARTIAL"
    assert any(item["availability"] == "MISSING" for item in result["market_context"]["dimensions"])
    assert {item["lifecycle"] for item in result["candidates"]} == {"NEW"}
    assert all(item["relevance_explanation"]["contributions"] for item in result["candidates"])
    tolerance = result["candidates"][0]["tolerance"]
    assert tolerance["state"] == "WITHIN"
    assert {item["dimension"] for item in tolerance["dimensions"]} == {
        "price",
        "volume",
        "market",
        "sector",
        "time_decay",
    }
    assert tolerance["envelope"]["policy"] == {
        "id": "candidate-tolerance-v1",
        "version": "1",
    }
    assert (
        product_client.get("/api/v1/discovery/scans").json()[0]["run_id"]
        == result["summary"]["run_id"]
    )
    candidates = product_client.get("/api/v1/discovery/candidates").json()
    assert candidates["total"] == 2 and len(candidates["items"]) == 2


def test_scan_history_archive_restore_and_owner_isolation(
    product_client: TestClient,
) -> None:
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE", "TCS"], context_mode="healthy"),
    )
    summary = result["summary"]
    run_id = summary["run_id"]
    assert summary["universe"] == ["RELIANCE", "TCS"]
    assert summary["context_mode"] == "healthy"

    archived = product_client.post(
        f"/api/v1/discovery/scans/{run_id}/archive",
        headers={"Origin": ORIGIN},
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert product_client.get("/api/v1/discovery/scans").json() == []
    past = product_client.get("/api/v1/discovery/scans", params={"include_archived": "true"}).json()
    assert len(past) == 1 and past[0]["run_id"] == run_id

    with session_scope(cast(FastAPI, product_client.app).state.session_factory) as session:
        stored = session.get(ScanRunRecord, UUID(run_id))
        assert stored is not None and stored.archived_at is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(ScanMatchRecord)
                .where(ScanMatchRecord.run_id == UUID(run_id))
            )
            == summary["match_count"]
        )

    assert product_client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN}).status_code == 200
    assert (
        product_client.post(
            "/api/v1/auth/login",
            json={"username": "bob", "password": PASSWORD},
            headers={"Origin": ORIGIN},
        ).status_code
        == 200
    )
    assert (
        product_client.get("/api/v1/discovery/scans", params={"include_archived": "true"}).json()
        == []
    )
    denied = product_client.post(
        f"/api/v1/discovery/scans/{run_id}/restore",
        headers={"Origin": ORIGIN},
    )
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "SCAN_NOT_FOUND"

    assert product_client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN}).status_code == 200
    assert (
        product_client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": PASSWORD},
            headers={"Origin": ORIGIN},
        ).status_code
        == 200
    )
    restored = product_client.post(
        f"/api/v1/discovery/scans/{run_id}/restore",
        headers={"Origin": ORIGIN},
    )
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert product_client.get("/api/v1/discovery/scans").json()[0]["run_id"] == run_id


def test_synthetic_fixture_is_realistic_deterministic_and_varied(
    product_client: TestClient,
) -> None:
    universe = ["RELIANCE", "MCX", "HDFCBANK", "INFY", "BSE", "NIFTY", "BANKNIFTY"]
    result = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=universe))
    matched = {item["symbol"] for item in result["matches"]}
    assert {"RELIANCE", "MCX", "INFY", "NIFTY"} <= matched
    assert {"HDFCBANK", "BSE", "BANKNIFTY"}.isdisjoint(matched)
    closes = {item["key_metrics"]["close"] for item in result["matches"]}
    assert len(closes) >= 3 and "100" not in closes
    explanations = {tuple(item["why_matched"]) for item in result["matches"]}
    assert len(explanations) >= 2
    relevance = {item["relevance"]["value"] for item in result["candidates"]}
    coverage = {item["relevance"]["coverage"] for item in result["candidates"]}
    assert len(relevance) >= 2 and len(coverage) >= 2
    nifty = next(item for item in result["candidates"] if item["instrument"]["symbol"] == "NIFTY")
    assert nifty["instrument"]["segment"] == "INDEX"
    assert identity("BANKNIFTY").segment == "INDEX"
    assert identity("RELIANCE").segment == "EQ"

    at = datetime(2026, 9, 30, tzinfo=UTC)
    assert market_series(identity("RELIANCE"), at, 0) == market_series(identity("RELIANCE"), at, 0)


def test_second_snapshot_promotes_current_and_history_is_immutable(
    product_client: TestClient,
) -> None:
    first = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["RELIANCE"]))
    second = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["RELIANCE"]))
    candidate = second["candidates"][0]
    assert candidate["candidate_id"] == first["candidates"][0]["candidate_id"]
    assert candidate["lifecycle"] == "CURRENT"
    assert candidate["relevance"]["value"] != first["candidates"][0]["relevance"]["value"]
    detail = product_client.get(f"/api/v1/discovery/candidates/{candidate['candidate_id']}").json()
    assert [item["sequence"] for item in detail["snapshots"]] == [1, 2]
    assert detail["snapshots"][0]["snapshot_id"] != detail["snapshots"][1]["snapshot_id"]
    with session_scope(cast(FastAPI, product_client.app).state.session_factory) as session:
        rows = tuple(
            session.scalars(
                select(DiscoverySnapshotRecord).order_by(DiscoverySnapshotRecord.sequence)
            )
        )
        assert len(rows) == 2 and rows[0].payload != rows[1].payload


@pytest.mark.parametrize(
    ("mode", "availability", "lifecycle"),
    [
        ("healthy", "COMPLETE", "CURRENT"),
        ("partial", "PARTIAL", "CURRENT"),
        ("stale", "STALE", "STALE"),
        ("unavailable", "UNAVAILABLE", "STALE"),
    ],
)
def test_context_degradation_is_explicit(
    product_client: TestClient, mode: str, availability: str, lifecycle: str
) -> None:
    post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["INFY"]))
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["INFY"], context_mode=mode),
    )
    assert result["market_context"]["availability"] == availability
    assert result["candidates"][0]["lifecycle"] == lifecycle


def test_no_match_and_provider_status(product_client: TestClient) -> None:
    result = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["NOMATCH"]))
    assert result["summary"]["match_count"] == 0
    assert result["matches"] == [] and result["candidates"] == []
    status = product_client.get("/api/v1/discovery/status").json()
    assert [item["id"] for item in status] == ["internal", "tradingview-synthetic"]
    assert status[0]["last_success_at"] is not None


def test_multi_provider_merges_evidence_with_distinct_lineage(product_client: TestClient) -> None:
    first = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["RELIANCE"]))
    second = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], provider="tradingview-synthetic"),
    )
    assert first["candidates"][0]["candidate_id"] == second["candidates"][0]["candidate_id"]
    assert set(second["candidates"][0]["provider_sources"]) >= {"twf-native", "tradingview"}
    detail = product_client.get(
        f"/api/v1/discovery/candidates/{second['candidates'][0]['candidate_id']}"
    ).json()
    assert len(detail["snapshots"]) == 2
    assert detail["snapshots"][1]["source_data_time"] is None


def test_llm_is_optional_grounded_and_has_no_authority(product_client: TestClient) -> None:
    defaults = product_client.get("/api/v1/discovery/settings").json()
    assert defaults["llm_enabled"] is False
    disabled = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["BEL"]))
    candidate = disabled["candidates"][0]
    response = product_client.post(
        f"/api/v1/discovery/candidates/{candidate['candidate_id']}/explain",
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "LLM_DISABLED"
    defaults["llm_enabled"] = True
    updated = product_client.put(
        "/api/v1/discovery/settings", json=defaults, headers={"Origin": ORIGIN}
    )
    assert updated.status_code == 200 and updated.json()["revision"] == 1
    before = product_client.get(f"/api/v1/discovery/candidates/{candidate['candidate_id']}").json()
    explanation = post(
        product_client,
        f"/api/v1/discovery/candidates/{candidate['candidate_id']}/explain",
        {},
    )
    after = product_client.get(f"/api/v1/discovery/candidates/{candidate['candidate_id']}").json()
    assert explanation["grounding"] == "GROUNDED"
    assert "no lifecycle or trading authority" in explanation["narrative"]
    assert before["lifecycle"] == after["lifecycle"]
    assert before["relevance"] == after["relevance"]


def test_terminal_episode_is_not_resurrected(product_client: TestClient) -> None:
    result = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["KAYNES"]))
    candidate = result["candidates"][0]
    dismissed = post(
        product_client,
        f"/api/v1/discovery/candidates/{candidate['candidate_id']}/lifecycle",
        {"action": "DISMISS", "revision": candidate["revision"], "reason": "user-review"},
    )
    assert dismissed["lifecycle"] == "REJECTED"
    again = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["KAYNES"]))
    renewed = again["candidates"][0]
    assert renewed["candidate_id"] != candidate["candidate_id"]
    detail = product_client.get(f"/api/v1/discovery/candidates/{renewed['candidate_id']}").json()
    assert detail["previous_episode_id"] == candidate["episode_id"]


def test_owner_isolation_and_restart_persistence(product_client: TestClient) -> None:
    result = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["HAL"]))
    candidate_id = result["candidates"][0]["candidate_id"]
    engine = cast(FastAPI, product_client.app).state.database_engine
    assert product_client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN}).status_code == 200
    assert (
        product_client.post(
            "/api/v1/auth/login",
            json={"username": "bob", "password": PASSWORD},
            headers={"Origin": ORIGIN},
        ).status_code
        == 200
    )
    assert product_client.get("/api/v1/discovery/candidates").json()["total"] == 0
    assert product_client.get(f"/api/v1/discovery/candidates/{candidate_id}").status_code == 404
    product_client.close()
    with TestClient(
        create_app(Settings(cors_origins=(ORIGIN,)), engine_factory=lambda _: engine)
    ) as restarted:
        assert (
            restarted.post(
                "/api/v1/auth/login",
                json={"username": "alice", "password": PASSWORD},
                headers={"Origin": ORIGIN},
            ).status_code
            == 200
        )
        detail = restarted.get(f"/api/v1/discovery/candidates/{candidate_id}")
        assert detail.status_code == 200 and detail.json()["snapshot_count"] == 1


def test_settings_cas_and_input_bounds(product_client: TestClient) -> None:
    defaults = product_client.get("/api/v1/discovery/settings").json()
    defaults["low_max"] = "0.55"
    assert (
        product_client.put(
            "/api/v1/discovery/settings", json=defaults, headers={"Origin": ORIGIN}
        ).status_code
        == 200
    )
    stale = product_client.put(
        "/api/v1/discovery/settings", json=defaults, headers={"Origin": ORIGIN}
    )
    assert stale.status_code == 409
    too_many = scan_payload(universe=[f"SYM{i}" for i in range(21)])
    assert (
        product_client.post(
            "/api/v1/discovery/scans", json=too_many, headers={"Origin": ORIGIN}
        ).status_code
        == 422
    )


def test_schema_and_rows_are_owner_scoped(product_client: TestClient) -> None:
    post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["RELIANCE"]))
    with session_scope(cast(FastAPI, product_client.app).state.session_factory) as session:
        episodes = tuple(session.scalars(select(DiscoveryEpisodeRecord)))
        assert len(episodes) == 1
        assert episodes[0].snapshot_count == 1
        assert episodes[0].payload["episode"]["owner_id"] == str(episodes[0].user_id)


def test_same_symbol_keeps_intent_and_horizon_lifecycles_distinct(
    product_client: TestClient,
) -> None:
    first = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["TCS"], intent="MOMENTUM", horizon="5d"),
    )["candidates"][0]
    second = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["TCS"], intent="BREAKOUT", horizon="5d"),
    )["candidates"][0]
    third = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["TCS"], intent="MOMENTUM", horizon="15d"),
    )["candidates"][0]
    assert len({first["candidate_id"], second["candidate_id"], third["candidate_id"]}) == 3
    assert {
        (first["intent"], first["horizon"]),
        (second["intent"], second["horizon"]),
        (third["intent"], third["horizon"]),
    } == {
        ("MOMENTUM", "5d"),
        ("BREAKOUT", "5d"),
        ("MOMENTUM", "15d"),
    }
    first_volume = next(
        item for item in first["tolerance"]["dimensions"] if item["dimension"] == "volume"
    )
    third_volume = next(
        item for item in third["tolerance"]["dimensions"] if item["dimension"] == "volume"
    )
    assert float(first_volume["threshold"]) == 1.0
    assert float(third_volume["threshold"]) == 0.9


def test_owner_lifecycle_actions_are_revisioned_and_audited(product_client: TestClient) -> None:
    item = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["SBIN"]))[
        "candidates"
    ][0]
    defunct = post(
        product_client,
        f"/api/v1/discovery/candidates/{item['candidate_id']}/lifecycle",
        {"action": "MARK_DEFUNCT", "revision": item["revision"], "reason": "evidence-deteriorated"},
    )
    assert defunct["lifecycle"] == "DEFUNCT"
    recovered = post(
        product_client,
        f"/api/v1/discovery/candidates/{item['candidate_id']}/lifecycle",
        {"action": "RECOVER", "revision": defunct["revision"], "reason": "fresh-evidence"},
    )
    assert recovered["lifecycle"] == "CURRENT"
    assert [(row["from_state"], row["to_state"]) for row in recovered["transitions"]] == [
        ("NEW", "DEFUNCT"),
        ("DEFUNCT", "CURRENT"),
    ]
    stale = product_client.post(
        f"/api/v1/discovery/candidates/{item['candidate_id']}/lifecycle",
        json={"action": "DISMISS", "revision": item["revision"], "reason": "stale-tab"},
        headers={"Origin": ORIGIN},
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "REVISION_CONFLICT"


def test_nonconfigured_llm_provider_degrades_without_breaking_scan(
    product_client: TestClient,
) -> None:
    configured = product_client.get("/api/v1/discovery/settings").json()
    configured.update({"llm_enabled": True, "llm_provider": "openai"})
    assert (
        product_client.put(
            "/api/v1/discovery/settings", json=configured, headers={"Origin": ORIGIN}
        ).status_code
        == 200
    )
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["WIPRO"], include_llm=True),
    )
    candidate = result["candidates"][0]
    assert candidate["lifecycle"] == "NEW"
    unavailable = product_client.post(
        f"/api/v1/discovery/candidates/{candidate['candidate_id']}/explain",
        headers={"Origin": ORIGIN},
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "LLM_UNAVAILABLE"
    detail = product_client.get(f"/api/v1/discovery/candidates/{candidate['candidate_id']}").json()
    assert detail["explanations"] == []
