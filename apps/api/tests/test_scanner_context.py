"""Deterministic Market Context scoring, filtering, and immutable history."""

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from test_scanner_v2 import config, install_market
from test_watchlists import HEADERS
from test_watchlists import client as client  # noqa: F401

from twf.discovery.market_intelligence import (
    IntelligenceClaim,
    IntelligenceKind,
    IntelligenceState,
    MarketIntelligenceBatch,
    TapTideMarketIntelligence,
)
from twf.scanner_v2.context import (
    BreadthState,
    BroadRegime,
    ContextEvidence,
    ContextStatus,
    EventRisk,
    FlowState,
    MarketContextSnapshot,
    SectorRotation,
    SectorStrength,
    SetupDirection,
    VixState,
    analyze_candidate,
    normalize_context,
    relevance_score,
)
from twf.scanner_v2.contracts import ContextFilter, ContextMode, Filter

BASE = "/api/v1/scanner"
NOW = datetime(2026, 10, 8, 10, tzinfo=UTC)


def evidence(dimension: str, state: str) -> ContextEvidence:
    return ContextEvidence(
        dimension=dimension,
        state=state,
        detail=f"{dimension} observed as {state}",
        provider="tapetide",
        provider_tool=f"get_{dimension}",
        source_time=NOW,
        received_at=NOW,
        freshness="FRESH",
    )


def snapshot(**updates: Any) -> MarketContextSnapshot:
    values: dict[str, Any] = {
        "as_of": NOW,
        "provider": "tapetide",
        "status": ContextStatus.COMPLETE,
        "source_health": "AVAILABLE",
        "broad_regime": BroadRegime.BULLISH,
        "benchmark_direction": BroadRegime.BULLISH,
        "sector_strength": SectorStrength.STRONG,
        "sector_rotation": SectorRotation.IMPROVING,
        "vix_state": VixState.NORMAL,
        "fii_state": FlowState.POSITIVE,
        "dii_state": FlowState.POSITIVE,
        "net_institutional_state": FlowState.POSITIVE,
        "breadth": BreadthState.POSITIVE,
        "event_news_risk": EventRisk.SUPPORTIVE,
        "evidence": (
            evidence("broad_regime", "BULLISH"),
            evidence("sector", "STRONG"),
            evidence("vix", "NORMAL"),
            evidence("flows", "POSITIVE"),
            evidence("breadth", "POSITIVE"),
            evidence("event_news", "SUPPORTIVE"),
        ),
        "missing_dimensions": (),
        "warnings": (),
        "coverage_count": 6,
    }
    values.update(updates)
    return MarketContextSnapshot.model_validate(values)


def technical_row() -> dict[str, Any]:
    return {
        "symbol": "RELIANCE",
        "outcome": "MATCH",
        "diagnostics": [
            {
                "filter": {"field": "trend"},
                "observed": "Up",
                "threshold": "Up",
                "passed": True,
                "reason": "Trend equals Up",
            }
        ],
    }


def test_direction_aware_scoring_reverses_market_and_sector_interpretation() -> None:
    bullish = analyze_candidate(
        "RELIANCE",
        technical_row(),
        snapshot(),
        ContextMode.RANKING,
        (),
        SetupDirection.BULLISH,
        NOW,
        "test-run",
        "11111111-1111-4111-8111-111111111111",
    )
    bearish = analyze_candidate(
        "RELIANCE",
        technical_row(),
        snapshot(),
        ContextMode.RANKING,
        (),
        SetupDirection.BEARISH,
        NOW,
        "test-run",
        "11111111-1111-4111-8111-111111111111",
    )
    assert bullish.matched and bearish.matched
    assert bullish.context_adjustment == 19
    assert bearish.context_adjustment == -15
    assert bullish.final_relevance == 99
    assert bearish.final_relevance == 65
    assert bullish.context_classification == "STRONGLY_SUPPORTIVE"
    assert bearish.context_classification == "STRONGLY_ADVERSE"
    assert sum(item.contribution for item in bullish.context_contributions) == 19


def test_hard_filter_rejects_only_explicit_context_predicate() -> None:
    high_vix = snapshot(
        vix_state=VixState.HIGH,
        evidence=(
            evidence("broad_regime", "BULLISH"),
            evidence("sector", "STRONG"),
            evidence("vix", "HIGH"),
            evidence("flows", "POSITIVE"),
            evidence("breadth", "POSITIVE"),
            evidence("event_news", "SUPPORTIVE"),
        ),
    )
    ranking = analyze_candidate(
        "RELIANCE",
        technical_row(),
        high_vix,
        ContextMode.RANKING,
        (),
        SetupDirection.BULLISH,
        NOW,
        "test-run",
        "11111111-1111-4111-8111-111111111111",
    )
    hard = analyze_candidate(
        "RELIANCE",
        technical_row(),
        high_vix,
        ContextMode.HARD_FILTER,
        (ContextFilter(field="vix_state", operator="not_equals", value="HIGH"),),
        SetupDirection.BULLISH,
        NOW,
        "test-run",
        "11111111-1111-4111-8111-111111111111",
    )
    assert ranking.matched and ranking.technical_match
    assert not hard.matched and hard.technical_match
    assert hard.context_filter_diagnostics[0]["passed"] is False


def test_normalization_is_provider_neutral_partial_and_missing_is_zero() -> None:
    vix = IntelligenceClaim(
        kind=IntelligenceKind.MARKET_VOLATILITY,
        subject="vix",
        scope="india",
        values={"level": 21.4, "change_percent": 2.1},
        provider="tapetide",
        provider_tool="get_india_vix",
        source_time=NOW,
        received_at=NOW,
        freshness="FRESH",
        source_reference="tapetide:get_india_vix",
    )
    normalized = normalize_context(
        MarketIntelligenceBatch(
            provider="tapetide",
            state=IntelligenceState.PARTIAL,
            claims=(vix,),
            received_at=NOW,
            failures=("get_market_news:provider-error",),
        )
    )
    assert normalized.status == ContextStatus.PARTIAL
    assert normalized.vix_state == VixState.ELEVATED
    assert normalized.coverage_count == 1
    assert set(normalized.missing_dimensions) == {
        "broad_regime",
        "sector",
        "flows",
        "breadth",
        "event_news",
    }
    packet = analyze_candidate(
        "RELIANCE",
        technical_row(),
        normalized,
        ContextMode.RANKING,
        (),
        SetupDirection.BULLISH,
        NOW,
        "test-run",
        "11111111-1111-4111-8111-111111111111",
    )
    assert packet.context_adjustment == -1
    assert all(
        item.contribution == 0
        for item in packet.context_contributions
        if item.observed_state == "UNKNOWN"
    )
    assert "values" not in packet.model_dump()
    assert len(packet.short_reason) <= 180


def test_context_unavailable_is_non_blocking_and_reason_remains_available() -> None:
    empty = normalize_context(None, NOW)
    packet = analyze_candidate(
        "RELIANCE",
        technical_row(),
        empty,
        ContextMode.RANKING,
        (),
        SetupDirection.UNKNOWN,
        NOW,
        "test-run",
        "11111111-1111-4111-8111-111111111111",
    )
    assert packet.matched
    assert packet.context_adjustment == 0
    assert packet.context_classification == "UNAVAILABLE"
    assert "Context unavailable" in packet.short_reason
    assert packet.final_relevance == 80


def test_api_acquires_context_once_and_persists_immutable_analysis(
    client: TestClient, monkeypatch: Any
) -> None:
    market_calls = install_market(client, monkeypatch)
    calls = 0

    async def observe(self: TapTideMarketIntelligence, instruments: Any) -> MarketIntelligenceBatch:
        nonlocal calls
        calls += 1
        assert instruments == ()
        assert market_calls == ["RELIANCE"]
        assert self.cache is client.app.state.market_intelligence_cache
        return MarketIntelligenceBatch(
            provider="tapetide",
            state=IntelligenceState.AVAILABLE,
            claims=(
                IntelligenceClaim(
                    kind=IntelligenceKind.MARKET_VOLATILITY,
                    subject="vix",
                    scope="india",
                    values={"level": 14.0},
                    provider="tapetide",
                    provider_tool="get_india_vix",
                    source_time=NOW,
                    received_at=NOW,
                    freshness="FRESH",
                    source_reference="tapetide:get_india_vix",
                ),
            ),
            received_at=NOW,
        )

    monkeypatch.setattr(TapTideMarketIntelligence, "observe", observe)
    payload = config(
        filters=[{"field": "trend", "operator": "equals", "value": "Up"}],
        context_mode="RANKING",
    )
    response = client.post(BASE + "/runs", json=payload, headers=HEADERS)
    assert response.status_code == 200, response.text
    run = response.json()
    assert calls == 1
    assert run["counts"]["matches"] == 1
    assert run["context_snapshot"]["status"] == "PARTIAL"
    analysis = run["rows"][0]["analysis"]
    assert analysis["run_id"] == run["id"]
    assert analysis["candidate_instrument_id"] == run["rows"][0]["instrument"]["instrument_id"]
    assert analysis["candidate_symbol"] == "RELIANCE"
    assert analysis["technical_match"] is True
    assert analysis["matched"] is True
    assert analysis["final_relevance"] == 81
    stored = client.get(BASE + "/runs/" + run["id"]).json()
    assert stored["context_snapshot"] == run["context_snapshot"]
    assert stored["rows"][0]["analysis"] == run["rows"][0]["analysis"]


def test_context_contract_defaults_and_direction_inference() -> None:
    from twf.scanner_v2.context import infer_direction
    from twf.scanner_v2.contracts import ScanConfig

    parsed = ScanConfig.model_validate(config())
    assert parsed.context_mode == ContextMode.RANKING
    assert parsed.context_filters == ()
    assert parsed.sort == "relevance"
    assert (
        infer_direction((Filter(field="supertrend", operator="equals", value="Up"),))
        == SetupDirection.BULLISH
    )
    assert (
        infer_direction((Filter(field="trend", operator="equals", value="Down"),))
        == SetupDirection.BEARISH
    )


def test_catalog_exposes_only_reliably_supported_context_predicates(
    client: TestClient,
) -> None:
    response = client.get(BASE + "/catalog")
    assert response.status_code == 200
    fields = {item["field"]: item for item in response.json()["context_fields"]}
    assert set(fields) == {
        "broad_regime",
        "sector_strength",
        "sector_rotation",
        "vix_state",
        "fii_state",
        "dii_state",
        "net_institutional_state",
        "breadth",
        "event_news_risk",
    }
    assert all(item["field_type"] == "ENUM" for item in fields.values())
    assert all(item["operators"] == ["equals", "not_equals"] for item in fields.values())
    assert fields["vix_state"]["enabled"] is True
    assert fields["fii_state"]["enabled"] is True
    assert fields["event_news_risk"]["enabled"] is True
    assert fields["broad_regime"]["enabled"] is False
    assert fields["sector_strength"]["enabled"] is True
    assert fields["sector_rotation"]["enabled"] is True
    assert fields["breadth"]["enabled"] is False


def test_context_off_makes_zero_market_intelligence_calls(
    client: TestClient, monkeypatch: Any
) -> None:
    install_market(client, monkeypatch)
    calls = 0

    async def observe(self: TapTideMarketIntelligence, instruments: Any) -> MarketIntelligenceBatch:
        nonlocal calls
        calls += 1
        raise AssertionError("OFF mode must not acquire Market Context")

    monkeypatch.setattr(TapTideMarketIntelligence, "observe", observe)
    response = client.post(
        BASE + "/runs",
        json=config(
            filters=[{"field": "trend", "operator": "equals", "value": "Up"}],
            context_mode="OFF",
        ),
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    run = response.json()
    assert calls == 0
    assert run["counts"]["matches"] == 1
    assert run["context_snapshot"]["status"] == "UNAVAILABLE"
    assert run["rows"][0]["analysis"]["context_mode"] == "OFF"
    assert run["rows"][0]["analysis"]["context_adjustment"] == 0
    assert run["rows"][0]["analysis"]["matched"] is True


def test_fully_adverse_bullish_and_supportive_bearish_context() -> None:
    adverse_market = snapshot(
        broad_regime=BroadRegime.BEARISH,
        benchmark_direction=BroadRegime.BEARISH,
        sector_strength=SectorStrength.WEAK,
        sector_rotation=SectorRotation.DETERIORATING,
        vix_state=VixState.HIGH,
        fii_state=FlowState.NEGATIVE,
        dii_state=FlowState.NEGATIVE,
        net_institutional_state=FlowState.NEGATIVE,
        breadth=BreadthState.WEAK,
        event_news_risk=EventRisk.HIGH_RISK,
        evidence=(
            evidence("broad_regime", "BEARISH"),
            evidence("sector", "WEAK"),
            evidence("vix", "HIGH"),
            evidence("flows", "NEGATIVE"),
            evidence("breadth", "WEAK"),
            evidence("event_news", "HIGH_RISK"),
        ),
    )
    bullish = analyze_candidate(
        "RELIANCE",
        technical_row(),
        adverse_market,
        ContextMode.RANKING,
        (),
        SetupDirection.BULLISH,
        NOW,
        "test-run",
        "11111111-1111-4111-8111-111111111111",
    )
    bearish = analyze_candidate(
        "RELIANCE",
        technical_row(),
        adverse_market,
        ContextMode.RANKING,
        (),
        SetupDirection.BEARISH,
        NOW,
        "test-run",
        "11111111-1111-4111-8111-111111111111",
    )
    assert bullish.context_adjustment == -20
    assert bullish.final_relevance == 60
    assert bullish.context_classification == "STRONGLY_ADVERSE"
    assert bullish.short_reason == "1/1 technical · Context -20 Strongly Adverse · Final 60"
    assert bearish.context_adjustment == 14
    assert bearish.final_relevance == 94
    assert bearish.context_classification == "STRONGLY_SUPPORTIVE"
    assert bearish.short_reason == "1/1 technical · Context +14 Strongly Supportive · Final 94"


def test_mixed_zero_adjustment_and_relevance_clamps_are_deterministic() -> None:
    neutral_event = snapshot(
        broad_regime=BroadRegime.UNKNOWN,
        benchmark_direction=BroadRegime.UNKNOWN,
        sector_strength=SectorStrength.UNKNOWN,
        sector_rotation=SectorRotation.UNKNOWN,
        vix_state=VixState.UNKNOWN,
        fii_state=FlowState.UNKNOWN,
        dii_state=FlowState.UNKNOWN,
        net_institutional_state=FlowState.UNKNOWN,
        breadth=BreadthState.UNKNOWN,
        event_news_risk=EventRisk.NEUTRAL,
        evidence=(
            evidence("broad_regime", "UNKNOWN"),
            evidence("sector", "UNKNOWN"),
            evidence("vix", "UNKNOWN"),
            evidence("flows", "UNKNOWN"),
            evidence("breadth", "UNKNOWN"),
            evidence("event_news", "NEUTRAL"),
        ),
        missing_dimensions=("broad_regime", "sector", "vix", "flows", "breadth"),
        coverage_count=1,
    )
    packet = analyze_candidate(
        "RELIANCE",
        technical_row(),
        neutral_event,
        ContextMode.RANKING,
        (),
        SetupDirection.UNKNOWN,
        NOW,
        "test-run",
        "11111111-1111-4111-8111-111111111111",
    )
    assert packet.context_adjustment == 0
    assert packet.context_classification == "MIXED"
    assert packet.final_relevance == 80
    assert packet.short_reason == "1/1 technical · Context +0 Mixed · Final 80"
    assert relevance_score(95, 20) == 100
    assert relevance_score(5, -20) == 0


def test_relevance_ties_sort_by_symbol_and_history_keeps_execution_snapshot(
    client: TestClient, monkeypatch: Any
) -> None:
    install_market(client, monkeypatch)
    calls = 0

    async def observe(self: TapTideMarketIntelligence, instruments: Any) -> MarketIntelligenceBatch:
        nonlocal calls
        calls += 1
        return MarketIntelligenceBatch(
            provider="tapetide",
            state=IntelligenceState.UNAVAILABLE,
            claims=(),
            received_at=NOW,
            failures=("provider-unavailable",),
        )

    monkeypatch.setattr(TapTideMarketIntelligence, "observe", observe)
    response = client.post(
        BASE + "/runs",
        json=config(
            universe={"source": "CUSTOM", "symbols": ["RELIANCE", "NIFTY"]},
            filters=[{"field": "rsi", "operator": ">", "value": 0}],
            context_mode="RANKING",
            sort="relevance",
        ),
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    run = response.json()
    assert calls == 1
    assert [row["symbol"] for row in run["rows"]] == ["NIFTY", "RELIANCE"]
    assert {row["analysis"]["final_relevance"] for row in run["rows"]} == {80}
    stored = client.get(BASE + "/runs/" + run["id"]).json()
    assert calls == 1
    assert stored["context_snapshot"] == run["context_snapshot"]
    assert stored["rows"] == run["rows"]
