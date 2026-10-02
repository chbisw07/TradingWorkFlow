"""Integrated Sprint-2 product regressions over the real owner-scoped API."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
from twf.discovery.dhan_credentials import (
    DhanCredentialCapture,
    DhanCredentialState,
    DhanCredentialStatus,
)
from twf.discovery.domain import SourceMode, SourceReference
from twf.discovery.market_data import (
    DHAN_IDENTITY,
    MarketDataErrorCode,
    MarketDataFailure,
)
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
        "provider": "synthetic",
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
    assert result["summary"]["provider"] == "synthetic"
    assert result["summary"]["match_count"] == 1
    assert result["summary"]["candidate_count"] == 1
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
    assert candidates["total"] == 1 and len(candidates["items"]) == 1


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
    assert matched == {"RELIANCE", "MCX"}
    assert {"HDFCBANK", "INFY", "BSE", "NIFTY", "BANKNIFTY"}.isdisjoint(matched)
    closes = {item["key_metrics"]["close"] for item in result["matches"]}
    assert len(closes) == 2 and "100" not in closes
    explanations = {tuple(item["why_matched"]) for item in result["matches"]}
    assert len(explanations) >= 2
    relevance = {item["relevance"]["value"] for item in result["candidates"]}
    coverage = {item["relevance"]["coverage"] for item in result["candidates"]}
    assert len(relevance) >= 2 and len(coverage) >= 2
    assert identity("NIFTY").segment == "INDEX"
    assert identity("BANKNIFTY").segment == "INDEX"
    assert identity("RELIANCE").segment == "EQ"

    at = datetime(2026, 9, 30, tzinfo=UTC)
    assert market_series(identity("RELIANCE"), at, 0) == market_series(identity("RELIANCE"), at, 0)


def test_u1_profiles_have_distinct_matches_and_authoritative_reasons(
    product_client: TestClient,
) -> None:
    cases = (
        ("RELATIVE_VOLUME", "MCX", ("Relative volume", "Positive 10-day momentum")),
        ("MOMENTUM", "MCX", ("Positive 10-day momentum", "RSI")),
        ("BREAKOUT_WITH_VOLUME", "RELIANCE", ("Upside breakout", "Relative volume")),
        ("PULLBACK_IN_UPTREND", "INFY", ("50-day trend", "One-day pullback")),
        ("TREND_CONTINUATION", "NIFTY", ("50-day trend", "RSI")),
    )
    reason_sets: set[tuple[str, ...]] = set()
    for profile, symbol, expected_fragments in cases:
        result = post(
            product_client,
            "/api/v1/discovery/scans",
            scan_payload(profile=profile, universe=[symbol]),
        )
        assert result["summary"]["match_count"] == 1
        reasons = tuple(result["matches"][0]["why_matched"])
        assert all(any(fragment in reason for reason in reasons) for fragment in expected_fragments)
        reason_sets.add(reasons)
    assert len(reason_sets) == len(cases)


def test_u1_directional_intent_requires_supporting_evidence(
    product_client: TestClient,
) -> None:
    bullish = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(
            profile="MOMENTUM",
            universe=["MCX"],
            intent="POSITIONAL_LONG",
            horizon="5d",
        ),
    )
    assert bullish["summary"]["candidate_count"] == 1
    assert all(
        item["polarity"] == "POSITIVE"
        for item in product_client.get(
            f"/api/v1/discovery/candidates/{bullish['candidates'][0]['candidate_id']}"
        ).json()["snapshots"][0]["evidence"]
        if item["category"] == "PROVIDER_SCAN"
    )
    assert (
        post(
            product_client,
            "/api/v1/discovery/scans",
            scan_payload(
                profile="MOMENTUM",
                universe=["MCX"],
                intent="POSITIONAL_SHORT",
                horizon="5d",
            ),
        )["summary"]["candidate_count"]
        == 0
    )

    bearish = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(
            profile="MOMENTUM",
            universe=["BSE"],
            intent="POSITIONAL_SHORT",
            horizon="5d",
        ),
    )
    assert bearish["summary"]["candidate_count"] == 1
    assert (
        post(
            product_client,
            "/api/v1/discovery/scans",
            scan_payload(
                profile="MOMENTUM",
                universe=["BSE"],
                intent="POSITIONAL_LONG",
                horizon="5d",
            ),
        )["summary"]["candidate_count"]
        == 0
    )

    upside = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(
            profile="BREAKOUT_WITH_VOLUME",
            universe=["RELIANCE"],
            intent="POSITIONAL_LONG",
            horizon="5d",
        ),
    )
    downside = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(
            profile="BREAKOUT_WITH_VOLUME",
            universe=["BANKNIFTY"],
            intent="POSITIONAL_SHORT",
            horizon="5d",
        ),
    )
    assert upside["summary"]["candidate_count"] == 1
    assert downside["summary"]["candidate_count"] == 1
    assert "Upside breakout" in upside["matches"][0]["why_matched"][0]
    assert "Downside breakdown" in downside["matches"][0]["why_matched"][0]


def test_u1_intent_horizon_and_profile_compatibility(product_client: TestClient) -> None:
    valid = (
        scan_payload(intent="INTRADAY_LONG", horizon="intraday"),
        scan_payload(intent="INTRADAY_SHORT", horizon="1d"),
        scan_payload(intent="POSITIONAL_LONG", horizon="5d"),
        scan_payload(intent="POSITIONAL_SHORT", horizon="15d"),
    )
    for payload in valid:
        assert (
            product_client.post(
                "/api/v1/discovery/scans", json=payload, headers={"Origin": ORIGIN}
            ).status_code
            == 201
        )

    invalid = (
        scan_payload(intent="INTRADAY_LONG", horizon="5d"),
        scan_payload(intent="POSITIONAL_LONG", horizon="intraday"),
        scan_payload(
            profile="PULLBACK_IN_UPTREND",
            intent="POSITIONAL_SHORT",
            horizon="5d",
        ),
    )
    for payload in invalid:
        response = product_client.post(
            "/api/v1/discovery/scans", json=payload, headers={"Origin": ORIGIN}
        )
        assert response.status_code == 422


def test_u1_fixture_profiles_are_differentiated_and_relevance_discriminates(
    product_client: TestClient,
) -> None:
    universe = ["RELIANCE", "MCX", "HDFCBANK", "INFY", "BSE", "NIFTY", "BANKNIFTY", "TCS"]
    result_sets: dict[str, set[str]] = {}
    for profile in (
        "RELATIVE_VOLUME",
        "MOMENTUM",
        "BREAKOUT_WITH_VOLUME",
        "PULLBACK_IN_UPTREND",
        "TREND_CONTINUATION",
    ):
        result = post(
            product_client,
            "/api/v1/discovery/scans",
            scan_payload(profile=profile, universe=universe, context_mode="healthy"),
        )
        result_sets[profile] = {item["symbol"] for item in result["matches"]}
    assert len({frozenset(items) for items in result_sets.values()}) >= 4
    assert result_sets["BREAKOUT_WITH_VOLUME"] == {"RELIANCE"}
    assert result_sets["PULLBACK_IN_UPTREND"] == {"INFY"}
    assert "MCX" in result_sets["RELATIVE_VOLUME"]
    assert "NIFTY" in result_sets["TREND_CONTINUATION"]

    scored = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(profile="TREND_CONTINUATION", universe=universe, context_mode="healthy"),
    )["candidates"]
    values = [float(item["relevance"]["value"]) for item in scored]
    assert len(set(values)) >= 2
    assert min(values) < max(values) < 1


def test_u1_lineage_tracks_origin_and_latest_scan(product_client: TestClient) -> None:
    first = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["RELIANCE"]))
    second = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["RELIANCE"]))
    candidate = second["candidates"][0]
    assert candidate["originating_scan_run_id"] == first["summary"]["run_id"]
    assert candidate["latest_scan_run_id"] == second["summary"]["run_id"]
    assert candidate["originating_scan_run_id"] != candidate["latest_scan_run_id"]


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
    post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["RELIANCE"]))
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], context_mode=mode),
    )
    assert result["market_context"]["availability"] == availability
    assert result["candidates"][0]["lifecycle"] == lifecycle


def test_no_match_and_provider_status(product_client: TestClient) -> None:
    result = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["NOMATCH"]))
    assert result["summary"]["match_count"] == 0
    assert result["matches"] == [] and result["candidates"] == []
    status = product_client.get("/api/v1/discovery/status").json()
    assert [item["id"] for item in status] == [
        "dhan",
        "internal-scanner-v0",
        "tapetide",
    ]
    assert status[0]["role"] == "MARKET_DATA"
    assert status[1]["role"] == "SCANNER"
    assert status[2]["role"] == "MARKET_INTELLIGENCE"
    assert status[1]["last_success_at"] is not None


def test_legacy_internal_alias_normalizes_to_synthetic(product_client: TestClient) -> None:
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], provider="internal"),
    )
    assert result["summary"]["provider"] == "synthetic"
    assert result["matches"][0]["provider"] == "twf-native"


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
        scan_payload(universe=["RELIANCE"], intent="MOMENTUM", horizon="5d"),
    )["candidates"][0]
    second = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], intent="BREAKOUT", horizon="5d"),
    )["candidates"][0]
    third = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], intent="MOMENTUM", horizon="15d"),
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


def test_u2_match_admission_reconciles_and_explains_exclusions(
    product_client: TestClient,
) -> None:
    directional = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(
            profile="MOMENTUM",
            universe=["MCX", "BSE"],
            intent="POSITIONAL_LONG",
            horizon="5d",
        ),
    )
    admission = directional["admission"]
    assert admission["match_count"] == admission["admitted_count"] + admission["excluded_count"]
    assert len(admission["decisions"]) == admission["match_count"]
    assert {item["reason"] for item in admission["decisions"]} == {"ADMITTED"}

    blocked = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(
            profile="MOMENTUM",
            universe=["MCX"],
            context_mode="partial",
            context_policy="REQUIRE_COMPLETE",
        ),
    )
    assert blocked["summary"]["match_count"] == 1
    assert blocked["summary"]["candidate_count"] == 0
    assert blocked["admission"]["decisions"][0]["reason"] == "EXCLUDED_CONTEXT_POLICY"


def test_u2_synthetic_provider_contract_is_deterministic(product_client: TestClient) -> None:
    payload = scan_payload(
        profile="MOMENTUM",
        universe=["MCX"],
        context_mode="healthy",
    )
    first = post(product_client, "/api/v1/discovery/scans", payload)
    second = post(product_client, "/api/v1/discovery/scans", payload)
    assert first["matches"][0]["why_matched"] == second["matches"][0]["why_matched"]
    assert first["matches"][0]["raw_reasons"] == second["matches"][0]["raw_reasons"]
    assert second["matches"][0]["provider"] == "twf-native"


def test_u2_optional_context_is_not_required_or_lifecycle_degrading(
    product_client: TestClient,
) -> None:
    first = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(
            universe=["RELIANCE"],
            context_mode="unavailable",
            context_policy="OPTIONAL",
        ),
    )
    second = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(
            universe=["RELIANCE"],
            context_mode="unavailable",
            context_policy="OPTIONAL",
        ),
    )
    assert first["summary"]["context_policy"] == "OPTIONAL"
    assert second["candidates"][0]["lifecycle"] == "CURRENT"
    explanation = second["candidates"][0]["relevance_explanation"]
    factors = {item["factor"] for item in explanation["contributions"]}
    assert "market-context" not in factors
    assert "market-context" not in explanation["missing"]


def test_u2_candidate_attention_order_is_stable_and_bounded(
    product_client: TestClient,
) -> None:
    post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(
            profile="TREND_CONTINUATION",
            universe=["RELIANCE", "MCX", "INFY", "NIFTY", "TCS"],
            context_mode="healthy",
        ),
    )
    first = product_client.get(
        "/api/v1/discovery/candidates", params={"limit": 3, "offset": 0}
    ).json()
    second = product_client.get(
        "/api/v1/discovery/candidates", params={"limit": 3, "offset": 0}
    ).json()
    assert len(first["items"]) <= 3
    assert [item["candidate_id"] for item in first["items"]] == [
        item["candidate_id"] for item in second["items"]
    ]
    scores = [float(item["relevance"]["value"] or 0) for item in first["items"]]
    assert scores == sorted(scores, reverse=True)
    assert all(item["profile"] == "TREND_CONTINUATION" for item in first["items"])
    assert all(item["lifecycle_reason"] for item in first["items"])


def test_u2_snapshots_keep_current_evidence_without_cross_snapshot_duplication(
    product_client: TestClient,
) -> None:
    first = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], profile="BREAKOUT_WITH_VOLUME"),
    )
    second = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], profile="BREAKOUT_WITH_VOLUME"),
    )
    assert first["candidates"][0]["candidate_id"] == second["candidates"][0]["candidate_id"]
    detail = product_client.get(
        f"/api/v1/discovery/candidates/{second['candidates'][0]['candidate_id']}"
    ).json()
    evidence_sets = [
        {item["evidence_id"] for item in snapshot["evidence"]} for snapshot in detail["snapshots"]
    ]
    assert len(evidence_sets) == 2
    assert evidence_sets[0].isdisjoint(evidence_sets[1])
    assert detail["snapshots"][1]["lifecycle_reason"] == "comparable-observation"


@pytest.mark.parametrize("context_mode", ["healthy", "partial", "unavailable", "stale"])
def test_u2_optional_context_never_changes_required_score_or_coverage(
    product_client: TestClient, context_mode: str
) -> None:
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(
            universe=["RELIANCE"],
            context_mode=context_mode,
            context_policy="OPTIONAL",
        ),
    )
    assert result["summary"]["candidate_count"] == 1
    candidate = result["candidates"][0]
    explanation = candidate["relevance_explanation"]
    assert {item["factor"] for item in explanation["contributions"]} == {
        "provider-scan",
        "price",
        "technical",
    }
    assert explanation["coverage"] == "0.940723321145283268671926364"
    assert explanation["score"] == "0.9299706044326655158838757395"
    assert "market-context" not in explanation["missing"]
    assert candidate["lifecycle"] == "NEW"


@pytest.mark.parametrize(
    ("context_policy", "context_mode", "admitted", "context_value"),
    [
        ("REQUIRE_COMPLETE", "healthy", True, "1"),
        ("REQUIRE_COMPLETE", "partial", False, None),
        ("REQUIRE_COMPLETE", "unavailable", False, None),
        ("ALLOW_PARTIAL", "healthy", True, "1"),
        ("ALLOW_PARTIAL", "partial", True, "0.50"),
        ("ALLOW_PARTIAL", "unavailable", True, "0"),
    ],
)
def test_u2_context_policy_admission_and_coverage_matrix(
    product_client: TestClient,
    context_policy: str,
    context_mode: str,
    admitted: bool,
    context_value: str | None,
) -> None:
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(
            universe=["RELIANCE"],
            context_mode=context_mode,
            context_policy=context_policy,
        ),
    )
    assert bool(result["candidates"]) is admitted
    assert result["admission"]["match_count"] == 1
    assert result["admission"]["admitted_count"] == int(admitted)
    assert result["admission"]["excluded_count"] == int(not admitted)
    if not admitted:
        assert result["admission"]["decisions"][0]["reason"] == "EXCLUDED_CONTEXT_POLICY"
        return
    contribution = next(
        item
        for item in result["candidates"][0]["relevance_explanation"]["contributions"]
        if item["factor"] == "market-context"
    )
    assert contribution["value"] == context_value


def test_u2_same_symbol_distinct_intents_keep_distinct_active_episodes(
    product_client: TestClient,
) -> None:
    legacy = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], intent="MOMENTUM"),
    )
    positional = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], intent="POSITIONAL_LONG"),
    )
    assert legacy["candidates"][0]["candidate_id"] != positional["candidates"][0]["candidate_id"]
    page = product_client.get("/api/v1/discovery/candidates", params={"limit": 10}).json()
    same_symbol = [item for item in page["items"] if item["instrument"]["symbol"] == "RELIANCE"]
    assert len(same_symbol) == 2
    assert {item["intent"] for item in same_symbol} == {"MOMENTUM", "POSITIONAL_LONG"}


def test_u2h_historical_scan_detail_is_read_only_and_owner_scoped(
    product_client: TestClient,
) -> None:
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE", "MCX"], context_mode="healthy"),
    )
    run_id = result["summary"]["run_id"]
    candidate_id = result["candidates"][0]["candidate_id"]
    before = product_client.get(f"/api/v1/discovery/candidates/{candidate_id}").json()

    detail = product_client.get(f"/api/v1/discovery/scans/{run_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["summary"] == result["summary"]
    assert {item["match_id"]: item for item in payload["matches"]} == {
        item["match_id"]: item for item in result["matches"]
    }
    assert payload["market_context"] == result["market_context"]
    assert product_client.get(f"/api/v1/discovery/candidates/{candidate_id}").json() == before

    assert product_client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN}).status_code == 200
    assert (
        product_client.post(
            "/api/v1/auth/login",
            json={"username": "bob", "password": PASSWORD},
            headers={"Origin": ORIGIN},
        ).status_code
        == 200
    )
    denied = product_client.get(f"/api/v1/discovery/scans/{run_id}")
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "SCAN_NOT_FOUND"


def test_u2h_legacy_profile_is_derived_without_rewriting_history(
    product_client: TestClient,
) -> None:
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], profile="BREAKOUT_WITH_VOLUME"),
    )
    candidate_id = result["candidates"][0]["candidate_id"]
    engine = cast(FastAPI, product_client.app).state.database_engine
    with session_scope(create_session_factory(engine)) as session:
        episode = session.scalar(
            select(DiscoveryEpisodeRecord).where(
                DiscoveryEpisodeRecord.candidate_id == UUID(candidate_id)
            )
        )
        assert episode is not None
        snapshot = session.scalar(
            select(DiscoverySnapshotRecord).where(DiscoverySnapshotRecord.episode_id == episode.id)
        )
        assert snapshot is not None
        original_snapshot = dict(snapshot.payload)
        snapshot.payload = {
            key: value for key, value in snapshot.payload.items() if key != "profile"
        }
        session.commit()

    recovered = product_client.get(f"/api/v1/discovery/candidates/{candidate_id}").json()
    assert recovered["profile"] == "BREAKOUT_WITH_VOLUME"
    assert recovered["profile_lineage"] == "ORIGINATING_SCAN"
    assert recovered["legacy_profile"] is True

    with session_scope(create_session_factory(engine)) as session:
        snapshot = session.scalar(
            select(DiscoverySnapshotRecord).where(
                DiscoverySnapshotRecord.episode_id == UUID(recovered["episode_id"])
            )
        )
        episode = session.get(DiscoveryEpisodeRecord, UUID(recovered["episode_id"]))
        assert snapshot is not None and episode is not None
        assert "profile" not in snapshot.payload
        lineage = dict(episode.payload.get("scan_lineage", {}))
        lineage.pop("originating_scan_run_id", None)
        lineage.pop("latest_scan_run_id", None)
        lineage.pop("profile", None)
        episode.payload = {**episode.payload, "scan_lineage": lineage}
        session.commit()

    fallback = product_client.get(f"/api/v1/discovery/candidates/{candidate_id}").json()
    assert fallback["profile"] is None
    assert fallback["profile_lineage"] == "LEGACY_UNAVAILABLE"
    assert fallback["legacy_profile"] is True
    assert original_snapshot["profile"] == "BREAKOUT_WITH_VOLUME"


def test_u2h_current_relevance_precedes_legacy_score_without_mutation(
    product_client: TestClient,
) -> None:
    created = [
        post(product_client, "/api/v1/discovery/scans", scan_payload(universe=[symbol]))
        for symbol in ("RELIANCE", "MCX", "KAYNES")
    ]
    candidate_ids = [item["candidates"][0]["candidate_id"] for item in created]
    target_scores = {
        candidate_ids[0]: ("0.84", "deterministic-relevance-v2", "2"),
        candidate_ids[1]: ("0.82", "deterministic-relevance-v2", "2"),
        candidate_ids[2]: ("1.00", "deterministic-relevance-v1", "1"),
    }
    engine = cast(FastAPI, product_client.app).state.database_engine
    with session_scope(create_session_factory(engine)) as session:
        episodes = tuple(
            session.scalars(
                select(DiscoveryEpisodeRecord).where(
                    DiscoveryEpisodeRecord.candidate_id.in_(
                        tuple(UUID(value) for value in candidate_ids)
                    )
                )
            )
        )
        for episode in episodes:
            snapshot = session.scalar(
                select(DiscoverySnapshotRecord).where(
                    DiscoverySnapshotRecord.episode_id == episode.id
                )
            )
            assert snapshot is not None
            score, policy_id, version = target_scores[str(episode.candidate_id)]
            payload = dict(snapshot.payload)
            stored_snapshot = dict(payload["snapshot"])
            relevance = dict(stored_snapshot["relevance"])
            relevance["value"] = score
            relevance["policy"] = {"id": policy_id, "version": version}
            stored_snapshot["relevance"] = relevance
            explanation = dict(payload["relevance_explanation"])
            explanation["score"] = score
            explanation["policy"] = policy_id
            payload["snapshot"] = stored_snapshot
            payload["relevance_explanation"] = explanation
            snapshot.payload = payload
        session.commit()

    before = product_client.get(f"/api/v1/discovery/candidates/{candidate_ids[2]}").json()
    page = product_client.get("/api/v1/discovery/candidates", params={"limit": 10}).json()
    ordered = [item for item in page["items"] if item["candidate_id"] in candidate_ids]
    assert [item["candidate_id"] for item in ordered] == candidate_ids
    assert ordered[2]["relevance"]["value"] == "1.00"
    assert ordered[2]["relevance"]["policy"] == {
        "id": "deterministic-relevance-v1",
        "version": "1",
    }
    after = product_client.get(f"/api/v1/discovery/candidates/{candidate_ids[2]}").json()
    assert after["relevance"] == before["relevance"]
    assert after["snapshots"] == before["snapshots"]


def test_evidence_chart_reconstructs_exact_bounded_as_scanned_series(
    product_client: TestClient,
) -> None:
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], profile="BREAKOUT_WITH_VOLUME"),
    )
    run_id = result["summary"]["run_id"]
    match = result["matches"][0]
    response = product_client.get(
        f"/api/v1/discovery/scans/{run_id}/matches/{match['match_id']}/evidence-chart"
    )
    assert response.status_code == 200
    chart = response.json()
    assert chart["state"] == "AVAILABLE"
    assert chart["mode"] == "as_scanned"
    assert chart["instrument"]["symbol"] == "RELIANCE"
    assert 20 < len(chart["bars"]) <= 120
    assert chart["bars"][-1]["timestamp"] <= result["summary"]["started_at"]
    assert {item["key"] for item in chart["thresholds"]} == {"breakout-20"}
    predicates = {item["metric"]: item for item in chart["predicates"]}
    assert predicates["breakout.20"]["matched"] is True
    assert abs(
        Decimal(predicates["relative_volume.20"]["observed"])
        - Decimal(match["key_metrics"]["relative_volume.20"])
    ) <= Decimal("1e-9")
    assert {item["panel"] for item in chart["series"]} >= {"VOLUME"}
    assert chart["retention"]["archive_bar_count"] == 260
    assert chart["retention"]["displayed_bar_count"] == len(chart["bars"])
    assert all(item["finality"] == "COMPLETED" for item in chart["bars"])


@pytest.mark.parametrize(
    ("profile", "symbol", "expected_series", "expected_thresholds"),
    [
        (
            "RELATIVE_VOLUME",
            "MCX",
            {"average-volume-20", "roc.10"},
            {"roc.10-GT-0"},
        ),
        (
            "MOMENTUM",
            "MCX",
            {"roc.10", "rsi.14"},
            {"roc.10-GT-0", "rsi.14-GTE-50"},
        ),
        (
            "BREAKOUT_WITH_VOLUME",
            "RELIANCE",
            {"average-volume-20"},
            {"breakout-20"},
        ),
        (
            "PULLBACK_IN_UPTREND",
            "INFY",
            {
                "sma-20",
                "sma-50",
                "sma-200",
                "pullback-upper",
                "pullback-lower",
                "roc.1",
            },
            {"roc.1-LT-0"},
        ),
        (
            "TREND_CONTINUATION",
            "NIFTY",
            {"sma-50", "sma-200", "rsi.14"},
            {"rsi.14-GTE-50", "rsi.14-LTE-80"},
        ),
    ],
)
def test_evidence_chart_overlays_follow_pinned_profile_rules(
    product_client: TestClient,
    profile: str,
    symbol: str,
    expected_series: set[str],
    expected_thresholds: set[str],
) -> None:
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=[symbol], profile=profile),
    )
    match = result["matches"][0]
    chart = product_client.get(
        "/api/v1/discovery/scans/{}/matches/{}/evidence-chart".format(
            result["summary"]["run_id"], match["match_id"]
        )
    ).json()
    assert chart["state"] == "AVAILABLE"
    assert chart["profile"] == profile
    with session_scope(cast(FastAPI, product_client.app).state.session_factory) as session:
        persisted = session.get(ScanMatchRecord, UUID(match["match_id"]))
        assert persisted is not None
        pinned = persisted.payload
    assert chart["profile_revision"] == pinned["profile"]["applied_revision"]
    assert chart["definition_revision"] == pinned["definition_revision"]
    assert expected_series <= {item["key"] for item in chart["series"]}
    assert expected_thresholds <= {item["key"] for item in chart["thresholds"]}
    assert {item["metric"] for item in chart["predicates"]} == {
        item["name"]
        for evidence in pinned["evidence"]
        if evidence["category"] == "PROVIDER_SCAN"
        for item in evidence["measures"]
        if item["name"]
        not in {
            "threshold",
            "operator",
            "matched",
            "price-unit",
            "input-digest",
        }
    }


def test_evidence_chart_current_mode_uses_provider_neutral_series(
    product_client: TestClient,
) -> None:
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["MCX"], profile="MOMENTUM"),
    )
    match = result["matches"][0]
    current = product_client.get(
        "/api/v1/discovery/scans/{}/matches/{}/evidence-chart".format(
            result["summary"]["run_id"], match["match_id"]
        ),
        params={"mode": "current"},
    )
    assert current.status_code == 200
    chart = current.json()
    assert chart["mode"] == "current"
    assert chart["state"] == "AVAILABLE"
    assert chart["provider"] == "twf-native"
    assert all(item["metric"] in {"roc.10", "rsi.14"} for item in chart["predicates"])


def test_evidence_chart_owner_isolation_and_legacy_truthfulness(
    product_client: TestClient,
) -> None:
    result = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["RELIANCE"]))
    run_id = result["summary"]["run_id"]
    match_id = result["matches"][0]["match_id"]
    with session_scope(cast(FastAPI, product_client.app).state.session_factory) as session:
        from twf.infrastructure.discovery import ScanEvidenceSeriesRecord

        archive = session.get(ScanEvidenceSeriesRecord, UUID(match_id))
        assert archive is not None
        session.delete(archive)
        session.commit()
    legacy = product_client.get(
        f"/api/v1/discovery/scans/{run_id}/matches/{match_id}/evidence-chart"
    ).json()
    assert legacy["state"] == "LEGACY_UNAVAILABLE"
    assert legacy["bars"] == []
    assert legacy["predicates"]

    assert product_client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN}).status_code == 200
    assert (
        product_client.post(
            "/api/v1/auth/login",
            json={"username": "bob", "password": PASSWORD},
            headers={"Origin": ORIGIN},
        ).status_code
        == 200
    )
    denied = product_client.get(
        f"/api/v1/discovery/scans/{run_id}/matches/{match_id}/evidence-chart"
    )
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "SCAN_MATCH_NOT_FOUND"


def test_evidence_chart_integrity_failure_is_typed(product_client: TestClient) -> None:
    result = post(product_client, "/api/v1/discovery/scans", scan_payload(universe=["RELIANCE"]))
    run_id = result["summary"]["run_id"]
    match_id = result["matches"][0]["match_id"]
    with session_scope(cast(FastAPI, product_client.app).state.session_factory) as session:
        from twf.infrastructure.discovery import ScanEvidenceSeriesRecord

        archive = session.get(ScanEvidenceSeriesRecord, UUID(match_id))
        assert archive is not None
        payload = dict(archive.payload)
        stored_series = dict(payload["series"])
        bars = list(stored_series["bars"])
        bars[-1] = {**bars[-1], "volume": 1}
        archive.payload = {**payload, "series": {**stored_series, "bars": bars}}
        session.commit()
    chart = product_client.get(
        f"/api/v1/discovery/scans/{run_id}/matches/{match_id}/evidence-chart"
    ).json()
    assert chart["state"] == "RECONSTRUCTION_FAILED"
    assert chart["bars"] == []
    assert chart["predicates"]


class FakeDhanMarketData:
    def __init__(self, failure: MarketDataErrorCode | None = None) -> None:
        self.failure = failure
        self.calls: list[tuple[str, str]] = []

    async def resolve_instruments(self, symbols: tuple[str, ...]) -> tuple[Any, ...]:
        output = []
        security_ids = {"RELIANCE": "2885", "MCX": "31181", "NOMATCH": "99999"}
        for symbol in symbols:
            if self.failure == MarketDataErrorCode.INSTRUMENT_NOT_FOUND:
                raise MarketDataFailure(self.failure)
            item = identity(symbol)
            source = SourceReference(
                namespace="dhan",
                native_id=f"NSE_EQ:{security_ids.get(symbol, '90000')}",
                revision="scrip-master-v1",
            )
            output.append(
                item.model_copy(
                    update={
                        "native": source,
                        "provider_symbol": symbol,
                        "instrument_type": "EQUITY",
                    }
                )
            )
        return tuple(output)

    async def get_ohlcv(
        self,
        instrument: Any,
        interval: str,
        *,
        as_of: datetime,
        count: int,
    ) -> Any:
        self.calls.append((instrument.symbol, interval))
        if self.failure is not None:
            raise MarketDataFailure(self.failure, retryable=True)
        series = market_series(instrument, as_of - timedelta(seconds=1))
        return series.model_copy(
            update={
                "interval": interval,
                "provenance": series.provenance.model_copy(
                    update={
                        "producer": DHAN_IDENTITY,
                        "source": instrument.native,
                        "mode": SourceMode.EOD,
                        "dependence_group": "dhan-authoritative-market-data",
                    }
                ),
                "received_at": as_of,
                "requested_count": count,
                "completeness": "PARTIAL" if len(series.bars) < count else "COMPLETE",
            }
        )


def install_market_data(product_client: TestClient, provider: FakeDhanMarketData) -> None:
    app = cast(FastAPI, product_client.app)
    app.state.market_data_provider = provider
    app.state.dhan_credentials.capture = lambda owner_id, ready_only: DhanCredentialCapture(
        provider,
        DhanCredentialStatus(
            state=DhanCredentialState.READY,
            configured=True,
            enabled=True,
            generation=1,
            source="DATABASE",
        ),
    )


def test_real_mode_uses_dhan_and_archives_exact_scanner_series(
    product_client: TestClient,
) -> None:
    provider = FakeDhanMarketData()
    install_market_data(product_client, provider)
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], provider="real"),
    )
    assert result["summary"]["provider"] == "real"
    assert result["summary"]["candidate_count"] == 1
    assert "tapetide-auth_required" in result["summary"]["degraded"]
    lineage = result["summary"]["evidence_lineage"]
    assert lineage["discovery_provider"] == "internal-scanner-v0"
    assert lineage["evidence_provider"] == "dhan"
    assert lineage["requested_symbols"] == ["RELIANCE"]
    assert lineage["returned_symbols"] == ["RELIANCE"]
    assert lineage["missing_symbols"] == []
    assert result["matches"][0]["provider"] == "dhan"
    assert result["matches"][0]["verification"] == "CONFIRMED"
    run_id, match_id = result["summary"]["run_id"], result["matches"][0]["match_id"]
    scanned = product_client.get(
        f"/api/v1/discovery/scans/{run_id}/matches/{match_id}/evidence-chart",
        params={"mode": "as_scanned"},
    ).json()
    assert scanned["state"] == "AVAILABLE"
    assert scanned["provider"] == "dhan"
    assert scanned["bars"]
    assert scanned["retention"]["scan_bars_retained"] is True
    current = product_client.get(
        f"/api/v1/discovery/scans/{run_id}/matches/{match_id}/evidence-chart",
        params={"mode": "current"},
    ).json()
    assert current["state"] == "AVAILABLE"
    assert current["provider"] == "dhan"
    assert current["bars"]
    assert provider.calls == [("RELIANCE", "1d"), ("RELIANCE", "1d")]


def test_real_provider_failure_is_not_evaluated_and_does_not_close_episode(
    product_client: TestClient,
) -> None:
    healthy = FakeDhanMarketData()
    install_market_data(product_client, healthy)
    first = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], provider="real", idempotency_key="dhan-ok"),
    )
    failed_provider = FakeDhanMarketData(MarketDataErrorCode.RATE_LIMITED)
    install_market_data(product_client, failed_provider)
    failed = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(
            universe=["RELIANCE"],
            provider="real",
            idempotency_key="dhan-rate-limited",
        ),
    )
    assert failed["matches"] == []
    assert failed["summary"]["candidate_count"] == 0
    assert "dhan-rate_limited" in failed["summary"]["degraded"]
    temporal = product_client.get(
        f"/api/v1/discovery/scans/{failed['summary']['run_id']}/temporal"
    ).json()
    observation = temporal["items"][0]["observation"]
    assert observation["kind"] == "NOT_EVALUATED"
    assert observation["coverage"] == "PROVIDER_UNAVAILABLE"
    candidate = product_client.get(
        f"/api/v1/discovery/candidates/{first['candidates'][0]['candidate_id']}"
    ).json()
    assert candidate["lifecycle"] in {"NEW", "CURRENT"}


def test_real_successful_no_match_records_absent(product_client: TestClient) -> None:
    install_market_data(product_client, FakeDhanMarketData())
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["NOMATCH"], provider="real"),
    )
    assert result["matches"] == []
    temporal = product_client.get(
        f"/api/v1/discovery/scans/{result['summary']['run_id']}/temporal"
    ).json()
    observation = temporal["items"][0]["observation"]
    assert observation["kind"] == "ABSENT"
    assert observation["coverage"] == "EVALUATED"


def test_dhan_current_chart_rate_limit_is_typed_and_as_scanned_survives(
    product_client: TestClient,
) -> None:
    provider = FakeDhanMarketData()
    install_market_data(product_client, provider)
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], provider="real"),
    )
    provider.failure = MarketDataErrorCode.RATE_LIMITED
    match = result["matches"][0]
    chart = product_client.get(
        "/api/v1/discovery/scans/{}/matches/{}/evidence-chart".format(
            result["summary"]["run_id"], match["match_id"]
        ),
        params={"mode": "current"},
    ).json()
    assert chart["state"] == "RATE_LIMITED"
    assert "Dhan rate limited" in chart["message"]
    scanned = product_client.get(
        "/api/v1/discovery/scans/{}/matches/{}/evidence-chart".format(
            result["summary"]["run_id"], match["match_id"]
        ),
        params={"mode": "as_scanned"},
    ).json()
    assert scanned["state"] == "AVAILABLE"
    assert scanned["bars"]


def test_legacy_tradingview_history_and_provenance_remain_readable(
    product_client: TestClient,
) -> None:
    result = post(
        product_client,
        "/api/v1/discovery/scans",
        scan_payload(universe=["RELIANCE"], provider="synthetic"),
    )
    run_id = UUID(result["summary"]["run_id"])
    match_id = UUID(result["matches"][0]["match_id"])
    with session_scope(cast(FastAPI, product_client.app).state.session_factory) as session:
        run = session.get(ScanRunRecord, run_id)
        match = session.get(ScanMatchRecord, match_id)
        assert run is not None and match is not None
        summary = dict(run.payload)
        summary["provider"] = "real-tradingview"
        run.provider = "real-tradingview"
        run.payload = summary
        payload = dict(match.payload)
        provenance = dict(payload["provenance"])
        producer = dict(provenance["producer"])
        source = dict(provenance["source"])
        producer.update(
            {
                "service_id": "tradingview-real-evidence",
                "provider": "tradingview",
                "service_version": "1",
                "contract_version": "sd.evidence.v1",
            }
        )
        source.update({"namespace": "tradingview", "native_id": "NSE:RELIANCE"})
        provenance.update({"producer": producer, "source": source})
        payload["provenance"] = provenance
        match.payload = payload
        session.commit()

    history = product_client.get("/api/v1/discovery/scans").json()
    assert history[0]["provider"] == "real-tradingview"
    detail = product_client.get(f"/api/v1/discovery/scans/{run_id}").json()
    assert detail["matches"][0]["provider"] == "tradingview"
    chart = product_client.get(
        f"/api/v1/discovery/scans/{run_id}/matches/{match_id}/evidence-chart",
        params={"mode": "as_scanned"},
    ).json()
    assert chart["state"] == "RETENTION_RESTRICTED"
    assert chart["provider"] == "tradingview"
    assert chart["bars"] == []
    assert "Historical TradingView" in chart["message"]
