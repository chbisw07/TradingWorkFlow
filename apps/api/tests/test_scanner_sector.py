"""Dynamic sector policy and durable, bounded Dhan enrichment without live I/O."""

from collections import Counter
from datetime import timedelta
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from internal_scanner_support import series
from test_instrument_metadata_consumers import metadata_selects, seed, stop_observing
from test_scanner_context import NOW, snapshot, technical_row
from test_scanner_v2 import BASE, config, install_market
from test_watchlists import HEADERS
from test_watchlists import client as client  # noqa: F401

from twf.discovery.domain import SourceMode
from twf.discovery.internal_scanner.market_series import Bar
from twf.discovery.market_data import MarketDataErrorCode, MarketDataFailure
from twf.scanner_v2.context import SetupDirection, analyze_candidate, normalize_context
from twf.scanner_v2.contracts import ContextFilter, ContextMode
from twf.scanner_v2.sector import (
    SectorContextEvidence,
    assess_sector,
    assessment,
    daily_return,
    relative_return,
    rotation,
    sector_score,
    trend,
)


def bars(rate: float, count: int = 60) -> tuple[Bar, ...]:
    return series([100 * (1 + rate) ** n for n in range(count)], step=86400).bars


@pytest.mark.parametrize("rate,expected", [(0.01, "BULLISH"), (-0.01, "BEARISH"), (0, "NEUTRAL")])
def test_trend(rate: float, expected: str) -> None:
    assert trend(bars(rate)) == expected
    assert trend(bars(rate, 49)) == "UNKNOWN"


@pytest.mark.parametrize("sessions", [1, 5, 20])
def test_returns_and_percentage_points(sessions: int) -> None:
    benchmark, nifty, candidate = bars(0.01), bars(0.005), bars(0.02)
    expected = 100 * (1.01**sessions - 1)
    assert daily_return(benchmark, sessions) == pytest.approx(expected)
    assert relative_return(benchmark, nifty, sessions) == pytest.approx(
        100 * (1.01**sessions - 1.005**sessions)
    )
    assert relative_return(candidate, benchmark, sessions) == pytest.approx(
        100 * (1.02**sessions - 1.01**sessions)
    )
    assert relative_return(nifty, benchmark, sessions) == pytest.approx(
        -100 * (1.01**sessions - 1.005**sessions)
    )
    assert daily_return(bars(0.01, sessions), sessions) is None


def test_misaligned_sessions_cannot_manufacture_relative_strength() -> None:
    left = bars(0.01)
    shifted = tuple(
        b.model_copy(update={"timestamp": b.timestamp + timedelta(days=1)}) for b in left
    )
    assert relative_return(left, shifted, 5) is None
    gap = (*left[:-4], *left[-3:])
    assert relative_return(left, gap, 5) is None
    assert relative_return(left, gap, 20) is None


@pytest.mark.parametrize(
    "rs5,rs20,state",
    [
        (2, 4, "IMPROVING"),
        (-2, -4, "DETERIORATING"),
        (0.1, 0.2, "STABLE"),
        (1, 4, "STABLE"),
        (None, 4, "UNKNOWN"),
        (1, None, "UNKNOWN"),
    ],
)
def test_rotation(rs5: float | None, rs20: float | None, state: str) -> None:
    assert rotation(rs5, rs20) == state


@pytest.mark.parametrize(
    "state,score", [("STRONG", 5), ("SUPPORTIVE", 3), ("NEUTRAL", 0), ("WEAK", -5), ("UNKNOWN", 0)]
)
def test_direction_and_bounds(state: str, score: int) -> None:
    for direction, expected in [("BULLISH", score), ("BEARISH", -score), ("UNKNOWN", 0)]:
        assert sector_score(state, direction) == expected
        packet = analyze_candidate(
            "INFY",
            technical_row(),
            snapshot(),
            ContextMode.RANKING,
            (),
            SetupDirection(direction),
            NOW,
            "run",
            None,
            sector=SectorContextEvidence(sector_state=state, contribution=expected),
        )
        assert packet.matched and packet.technical_match and packet.technical_score == 80
        contribution = next(c for c in packet.context_contributions if c.factor == "sector")
        assert contribution.contribution == expected
        assert abs(packet.context_adjustment) <= 20


@pytest.mark.parametrize(
    "market_trend,rs5,rs20,state",
    [
        ("BULLISH", 1, 2, "STRONG"),
        ("BULLISH", 1, None, "SUPPORTIVE"),
        ("BULLISH", 0.1, 0.2, "SUPPORTIVE"),
        ("BEARISH", -1, -2, "WEAK"),
        ("NEUTRAL", 1, 2, "NEUTRAL"),
        ("UNKNOWN", 1, 2, "UNKNOWN"),
        ("BULLISH", None, 2, "UNKNOWN"),
    ],
)
def test_minimum_assessment(
    market_trend: str, rs5: float | None, rs20: float | None, state: str
) -> None:
    assert assessment(market_trend, rs5, rs20) == state


def test_sector_hard_filter_and_coverage() -> None:
    predicate = ContextFilter(field="sector_strength", operator="equals", value="STRONG")
    for state, passes in [("STRONG", True), ("WEAK", False), ("UNKNOWN", False)]:
        evidence = SectorContextEvidence(
            sector_state=state, status="AVAILABLE" if passes else "UNAVAILABLE"
        )
        packet = analyze_candidate(
            "INFY",
            technical_row(),
            normalize_context(None, at=NOW),
            ContextMode.HARD_FILTER,
            (predicate,),
            SetupDirection.BULLISH,
            NOW,
            "run",
            None,
            evidence,
        )
        assert packet.matched is passes
        assert packet.technical_match and packet.technical_score == 80
        assert packet.context_coverage == ("0/6" if state == "UNKNOWN" else "1/6")
        assert packet.context_filter_diagnostics[0]["passed"] is passes


def test_no_benchmark_preserves_identity_without_counting_it_as_market_evidence() -> None:
    evidence = assess_sector(None, (), (), bars(0.01), direction="BULLISH", candidate_symbol="INFY")
    assert evidence.sector_state == "UNKNOWN" and evidence.contribution == 0
    assert "No analytical context benchmark mapped" in evidence.missing_evidence


def install_sector_market(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, failure: str = ""
) -> Counter[str]:
    install_market(client, monkeypatch)
    seed(client)
    app = cast(Any, client.app)
    # Real resolver with a deterministic Dhan master; no parallel ID registry.
    live = app.state.dhan_credentials.capture(None).provider
    live._master += tuple(
        {**live._master[2], "SEM_SMST_SECURITY_ID": str(900 + n), "SEM_TRADING_SYMBOL": symbol}
        for n, symbol in enumerate(["NIFTYOILGAS", "NIFTYIT"])
    )
    calls: Counter[str] = Counter()

    async def history(instrument: Any, interval: str, **kwargs: Any) -> Any:
        calls[instrument.symbol] += 1
        if instrument.symbol == "NIFTYOILGAS" and failure == "RATE_LIMITED":
            raise MarketDataFailure(MarketDataErrorCode.RATE_LIMITED)
        if instrument.symbol == "NIFTYOILGAS" and failure == "TIMEOUT":
            raise TimeoutError
        rates = {"NIFTY": 0.001, "NIFTYOILGAS": 0.01, "NIFTYIT": 0.01}
        rate = rates.get(instrument.symbol, 0.02)
        result = series(
            [100 * (1 + rate) ** n for n in range(60)],
            instrument=instrument,
            interval="1d",
            step=86400,
        )
        if failure == "FINALITY" and instrument.symbol == "NIFTYOILGAS":
            result = result.model_copy(
                update={
                    "bars": tuple(
                        b.model_copy(update={"finality": "PROVIDER_UNSPECIFIED"})
                        for b in result.bars
                    )
                }
            )
        return result.model_copy(
            update={
                "provenance": result.provenance.model_copy(
                    update={
                        "mode": SourceMode.EOD,
                        "producer": result.provenance.producer.model_copy(
                            update={"provider": "dhan"}
                        ),
                    }
                )
            }
        )

    monkeypatch.setattr(live, "get_ohlcv", history)
    return calls


def test_shared_fetch_real_scoring_and_immutable_history(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import update

    from twf.infrastructure.instrument_metadata import InstrumentMetadataRow

    calls = install_sector_market(client, monkeypatch)
    app = cast(Any, client.app)
    # Two equities intentionally share a metadata benchmark in this isolated snapshot.
    with app.state.session_factory.begin() as db:
        db.execute(
            update(InstrumentMetadataRow)
            .where(InstrumentMetadataRow.symbol == "INFY")
            .values(context_benchmark="NIFTY OIL & GAS", context_benchmark_symbol="NIFTYOILGAS")
        )
    statements, handle = metadata_selects(client)
    try:
        response = client.post(
            BASE + "/runs",
            json=config(
                universe={"source": "CUSTOM", "symbols": ["RELIANCE", "INFY", "NIFTY"]},
                filters=[{"field": "trend", "operator": "equals", "value": "Up"}],
            ),
            headers=HEADERS,
        )
    finally:
        stop_observing(handle)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["counts"]["matches"] == 3 and run["counts"]["evaluated"] == 3
    assert calls == {"RELIANCE": 1, "INFY": 1, "NIFTY": 1, "NIFTYOILGAS": 1}
    assert len(statements) == 1
    for row in run["rows"]:
        if row["symbol"] == "NIFTY":
            continue
        evidence = row["analysis"]["sector_context"]
        assert evidence["sector_state"] == "STRONG" and evidence["contribution"] == 5
        assert evidence["source"] == "dhan" and evidence["as_of"]
        assert row["analysis"]["technical_score"] == 80
        assert row["analysis"]["context_coverage"] == "1/6"
        assert row["analysis"]["supporting_factors"]
    # Read history after making provider acquisition impossible; stored A must survive.
    before = dict(calls)
    live = app.state.dhan_credentials.capture(None).provider
    monkeypatch.setattr(live, "get_ohlcv", lambda *a, **k: pytest.fail("History performed I/O"))
    stored = client.get(BASE + "/runs/" + run["id"]).json()
    assert stored == run and calls == before


@pytest.mark.parametrize("failure", ["RATE_LIMITED", "TIMEOUT", "FINALITY"])
def test_benchmark_failure_is_optional(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    install_sector_market(client, monkeypatch, failure)
    response = client.post(
        BASE + "/runs",
        json=config(filters=[{"field": "trend", "operator": "equals", "value": "Up"}]),
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    row = response.json()["rows"][0]
    assert row["outcome"] == "MATCH" and row["analysis"]["technical_score"] == 80
    evidence = row["analysis"]["sector_context"]
    assert evidence["sector_state"] == "UNKNOWN" and evidence["contribution"] == 0
    assert any(
        {"RATE_LIMITED": "rate limited", "TIMEOUT": "timed out", "FINALITY": "finality"}[failure]
        in reason
        for reason in evidence["missing_evidence"]
    )


def test_off_acquires_no_sector_data(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_sector_market(client, monkeypatch)
    response = client.post(BASE + "/runs", json=config(context_mode="OFF"), headers=HEADERS)
    assert response.status_code == 200
    assert calls == {"RELIANCE": 1}
    assert response.json()["rows"][0]["analysis"]["sector_context"] is None


def metadata_summary() -> Any:
    from twf.instrument_metadata.contracts import InstrumentMetadataSummary

    return InstrumentMetadataSummary(
        applies_to_symbol="INFY",
        metadata_symbol="INFY",
        resolution_basis="DIRECT",
        sector="Technology",
        industry="IT Services",
        market_cap=None,
        market_cap_currency=None,
        market_cap_rank=None,
        market_cap_category=None,
        twf_cap_tier=None,
        context_benchmark="NIFTY IT",
        context_benchmark_symbol="NIFTYIT",
        resolution_status="RESOLVED",
        present_in_latest_snapshot=True,
        sector_as_of=None,
        industry_as_of=None,
        market_cap_as_of=None,
        dataset_generated_at=NOW,
        metadata_updated_at=NOW,
    )


@pytest.mark.parametrize(
    "candidate_rate,expected",
    [(0.02, "OUTPERFORMING"), (0.005, "UNDERPERFORMING"), (0.01005, "IN_LINE")],
)
def test_candidate_band_and_directional_facts(candidate_rate: float, expected: str) -> None:
    evidence = assess_sector(
        metadata_summary(),
        bars(0.01),
        bars(0.001),
        bars(candidate_rate),
        direction="BULLISH",
        candidate_symbol="INFY",
        received_at=NOW,
    )
    assert evidence.candidate_relative_state == expected
    assert evidence.status == "AVAILABLE" and evidence.freshness == "COMPLETED_DAILY_AS_OF"
    assert evidence.sector_state == "STRONG" and evidence.contribution == 5
    assert evidence.supporting_factors
    if expected == "UNDERPERFORMING":
        assert any("INFY" in item for item in evidence.contradicting_factors)
    if expected == "IN_LINE":
        assert any("in line" in item for item in evidence.neutral_factors)
    unknown = assess_sector(
        metadata_summary(),
        bars(0.01),
        bars(0.001),
        bars(candidate_rate),
        direction="UNKNOWN",
        candidate_symbol="INFY",
    )
    assert unknown.contribution == 0 and not unknown.supporting_factors
    assert unknown.neutral_factors


def test_partial_evidence_and_stale_mapping_are_explicit() -> None:
    reference = bars(0.001)[-6:]
    evidence = assess_sector(
        metadata_summary(), bars(0.01), reference, (), direction="BULLISH", candidate_symbol="INFY"
    )
    assert evidence.status == "PARTIAL" and evidence.sector_state == "SUPPORTIVE"
    assert evidence.contribution == 3 and evidence.rotation_state == "UNKNOWN"
    assert evidence.candidate_relative_state == "UNKNOWN"
    assert evidence.missing_evidence and evidence.nifty_return_20d is None
    missing = metadata_summary().model_copy(
        update={"context_benchmark": None, "context_benchmark_symbol": None}
    )
    no_mapping = assess_sector(
        missing, bars(0.01), reference, (), direction="BULLISH", candidate_symbol="INFY"
    )
    assert no_mapping.sector == "Technology"
    assert no_mapping.contribution == 0 and no_mapping.sector_state == "UNKNOWN"
    assert "No analytical context benchmark mapped" in no_mapping.missing_evidence
    stale = metadata_summary().model_copy(update={"present_in_latest_snapshot": False})
    stale_evidence = assess_sector(
        stale, bars(0.01), bars(0.001), bars(0.02), direction="BULLISH", candidate_symbol="INFY"
    )
    assert stale_evidence.status == "PARTIAL" and stale_evidence.warnings


def test_actual_dhan_aliases_compute_for_four_representative_stocks(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import update
    from test_dhan_benchmarks import INDEX_ROWS

    from twf.infrastructure.instrument_metadata import InstrumentMetadataRow

    calls = install_sector_market(client, monkeypatch)
    app = cast(Any, client.app)
    live = app.state.dhan_credentials.capture(None).provider
    equity = live._master[0]
    live._master = INDEX_ROWS + tuple(
        {**equity, "SEM_TRADING_SYMBOL": symbol, "SEM_SMST_SECURITY_ID": str(10000 + n)}
        for n, symbol in enumerate(["COFORGE", "HDFCBANK", "RELIANCE", "20MICRONS", "INFY"])
    )
    with app.state.session_factory.begin() as db:
        db.execute(
            update(InstrumentMetadataRow)
            .where(InstrumentMetadataRow.symbol == "INFY")
            .values(symbol="COFORGE")
        )
    resolutions: Counter[str] = Counter()
    original = live.resolve_instruments

    async def resolve(symbols: tuple[str, ...]) -> Any:
        resolutions.update(symbols)
        return await original(symbols)

    monkeypatch.setattr(live, "resolve_instruments", resolve)
    response = client.post(
        BASE + "/runs",
        json=config(
            universe={
                "source": "CUSTOM",
                "symbols": ["COFORGE", "HDFCBANK", "RELIANCE", "20MICRONS"],
            },
            filters=[{"field": "trend", "operator": "equals", "value": "Up"}],
        ),
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["counts"]["matches"] == 4
    expected = {
        "COFORGE": "NIFTYIT",
        "HDFCBANK": "NIFTYBANK",
        "RELIANCE": "NIFTYOILGAS",
        "20MICRONS": "NIFTYMETAL",
    }
    for row in run["rows"]:
        evidence = row["analysis"]["sector_context"]
        assert evidence["context_benchmark_symbol"] == expected[row["symbol"]]
        assert evidence["status"] == "AVAILABLE" and evidence["source"] == "dhan"
        assert evidence["benchmark_trend"] == "BULLISH"
        assert all(evidence[f"benchmark_return_{days}d"] is not None for days in (1, 5, 20))
        assert evidence["sector_rs_20d"] is not None
        assert row["analysis"]["technical_score"] == 80
        assert "security_id" not in evidence and "native_id" not in evidence
    assert len(calls) == 9 and all(count == 1 for count in calls.values())
    assert all(resolutions[symbol] == 1 for symbol in ["NIFTY", *expected.values()])


@pytest.mark.parametrize("failure", ["MASTER", "HISTORY", "UNSUPPORTED", "SHORT"])
def test_resolution_and_history_failures_leave_technical_match_intact(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    install_sector_market(client, monkeypatch)
    live = cast(Any, client.app).state.dhan_credentials.capture(None).provider
    original_resolve, original_history = live.resolve_instruments, live.get_ohlcv

    async def resolve(symbols: tuple[str, ...]) -> Any:
        if symbols == ("NIFTYOILGAS",) and failure in {"MASTER", "UNSUPPORTED"}:
            raise MarketDataFailure(
                MarketDataErrorCode.PROVIDER_ERROR
                if failure == "MASTER"
                else MarketDataErrorCode.BENCHMARK_UNSUPPORTED_BY_DHAN
            )
        return await original_resolve(symbols)

    async def history(instrument: Any, interval: str, **kwargs: Any) -> Any:
        if instrument.symbol == "NIFTYOILGAS" and failure == "HISTORY":
            raise MarketDataFailure(MarketDataErrorCode.PROVIDER_ERROR)
        result = await original_history(instrument, interval, **kwargs)
        if instrument.symbol == "NIFTYOILGAS" and failure == "SHORT":
            return result.model_copy(update={"bars": result.bars[-49:]})
        return result

    monkeypatch.setattr(live, "resolve_instruments", resolve)
    monkeypatch.setattr(live, "get_ohlcv", history)
    response = client.post(
        BASE + "/runs",
        json=config(filters=[{"field": "trend", "operator": "equals", "value": "Up"}]),
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    row = response.json()["rows"][0]
    assert row["outcome"] == "MATCH" and row["analysis"]["technical_score"] == 80
    evidence = row["analysis"]["sector_context"]
    assert evidence["sector"] == "Energy" and evidence["context_benchmark"] == "NIFTY OIL & GAS"
    assert evidence["sector_state"] == "UNKNOWN" and evidence["contribution"] == 0
    assert row["analysis"]["context_coverage"] == "0/6"
    expected = {
        "MASTER": "index resolution is temporarily unavailable",
        "HISTORY": "daily history is temporarily unavailable",
        "UNSUPPORTED": "does not support",
        "SHORT": "fewer than 50 completed",
    }[failure]
    assert any(expected in reason for reason in evidence["missing_evidence"])


def test_two_bank_candidates_share_one_resolution_and_history(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import update
    from test_dhan_benchmarks import INDEX_ROWS

    from twf.infrastructure.instrument_metadata import InstrumentMetadataRow

    calls = install_sector_market(client, monkeypatch)
    app = cast(Any, client.app)
    live = app.state.dhan_credentials.capture(None).provider
    live._master = tuple(r for r in live._master if r["SEM_SEGMENT"] != "I") + INDEX_ROWS
    with app.state.session_factory.begin() as db:
        db.execute(
            update(InstrumentMetadataRow)
            .where(InstrumentMetadataRow.symbol.in_(["RELIANCE", "INFY"]))
            .values(context_benchmark="NIFTY BANK", context_benchmark_symbol="NIFTYBANK")
        )
    resolutions: Counter[str] = Counter()
    original = live.resolve_instruments

    async def resolve(symbols: tuple[str, ...]) -> Any:
        resolutions.update(symbols)
        return await original(symbols)

    monkeypatch.setattr(live, "resolve_instruments", resolve)
    response = client.post(
        BASE + "/runs",
        json=config(
            universe={"source": "CUSTOM", "symbols": ["RELIANCE", "INFY"]},
            filters=[{"field": "trend", "operator": "equals", "value": "Up"}],
        ),
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["counts"]["matches"] == 2
    assert resolutions["NIFTYBANK"] == resolutions["NIFTY"] == 1
    assert calls == {"RELIANCE": 1, "INFY": 1, "NIFTY": 1, "BANKNIFTY": 1}
    assert all(
        r["analysis"]["sector_context"]["status"] == "AVAILABLE" for r in response.json()["rows"]
    )
