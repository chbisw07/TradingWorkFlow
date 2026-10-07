"""Scanner V2 predicates, persistence, provenance and owner-safe handoff."""

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from internal_scanner_support import series
from pydantic import ValidationError
from test_watchlists import HEADERS, add, create, instruments, login, provider
from test_watchlists import client as client  # noqa: F401

from twf.discovery.domain import SourceMode
from twf.discovery.internal_scanner.indicators import adx, bollinger, macd, supertrend
from twf.discovery.market_data import MarketDataErrorCode, MarketDataFailure
from twf.scanner_v2.contracts import Filter, ScanConfig
from twf.scanner_v2.engine import evaluate, metrics
from twf.scanner_v2.service import ScannerHistory
from twf.scanner_v2.tapetide import normalize
from twf.scanner_v2.templates import templates

BASE = "/api/v1/scanner"


def config(**updates: Any) -> dict[str, Any]:
    return {
        "name": "Test RSI",
        "universe": {"source": "CUSTOM", "symbols": ["RELIANCE"]},
        "filters": [{"field": "rsi", "operator": ">", "value": 50}],
        **updates,
    }


@pytest.mark.parametrize(
    "field,operator,value",
    [
        ("rsi", "<", 101),
        ("made_up", ">", 2),
        ("trend", ">", "Up"),
        ("price", "between", 3),
        ("price", "between", [3, 1]),
        ("rsi", ">", float("nan")),
    ],
)
def test_filter_validation(field: str, operator: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        Filter.model_validate({"field": field, "operator": operator, "value": value})


def test_templates_parameters_and_numeric_metrics() -> None:
    assert len(templates()) >= 15
    rising = series([float(n) for n in range(100, 401)])
    m = metrics(rising.bars)
    assert m["rsi"] == 100 and m["adx"] == 100 and m["supertrend"] == "Up"
    assert m["sma20"] == 390.5
    assert m["ema20"] == pytest.approx(390.5)
    assert m["rvol"] == 1
    assert m["high20"] == 399.1
    assert m["low20"] == 379.9
    assert m["roc"] == pytest.approx(100 * (400 / 390 - 1))
    assert m["support"] < m["pivot"] < m["resistance"]  # type: ignore[operator]
    assert all(v is not None for v in m.values())
    flat = series([100.0] * 300)
    assert adx(flat.bars) == 0
    assert macd([100.0] * 100) == (0, 0)
    assert bollinger([100.0] * 30) == (100, 100)
    assert supertrend(series([float(n) for n in range(400, 99, -1)]).bars) == "Down"


def test_nonmatch_missing_input_and_crossing() -> None:
    bars = series([100.0] * 60 + [101.0]).bars
    assert (
        evaluate(bars, (Filter(field="price", operator="crosses_above", value="sma20"),))["outcome"]
        == "MATCH"
    )
    assert evaluate(bars, (Filter(field="rsi", operator="<", value=30),))["outcome"] == "NON_MATCH"
    assert (
        evaluate(bars[:4], (Filter(field="rsi", operator="<", value=30),))["outcome"]
        == "NOT_EVALUATED"
    )
    assert (
        evaluate(series([100.0] * 60, volumes=[None] * 60).bars, (Filter(field="rvol", value=2),))[
            "outcome"
        ]
        == "NOT_EVALUATED"
    )


def test_config_real_only_and_duplicates() -> None:
    with pytest.raises(ValidationError):
        ScanConfig.model_validate(config(data_mode="SYNTHETIC"))
    with pytest.raises(ValidationError):
        ScanConfig.model_validate(
            config(universe={"source": "CUSTOM", "symbols": ["INFY", "INFY"]})
        )
    assert ScanConfig.model_validate(config(universe={"source": "CUSTOM", "symbols": ["M&M"]}))


def install_market(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    p = provider()
    calls: list[str] = []

    async def history(instrument: Any, interval: str, **kwargs: Any) -> Any:
        calls.append(instrument.symbol)
        if instrument.symbol == "INFY":
            raise MarketDataFailure(MarketDataErrorCode.RATE_LIMITED)
        s = series(
            [float(n) for n in range(100, 401)], instrument=instrument, interval="1d", step=86400
        )
        return s.model_copy(
            update={
                "provenance": s.provenance.model_copy(
                    update={
                        "mode": SourceMode.EOD,
                        "producer": s.provenance.producer.model_copy(update={"provider": "dhan"}),
                    }
                )
            }
        )

    monkeypatch.setattr(p, "get_ohlcv", history)
    monkeypatch.setattr(
        cast(Any, client.app).state.dhan_credentials,
        "capture",
        lambda *args, **kw: SimpleNamespace(provider=p, status=SimpleNamespace(generation=3)),
    )
    return calls


def test_runs_saved_owner_isolation_and_immutable_watchlist(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = install_market(client, monkeypatch)
    key = create(client)
    add(client, key)
    requested = config(universe={"source": "WATCHLIST", "watchlist_id": key})
    response = client.post(BASE + "/runs", json=requested, headers=HEADERS)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["counts"] == {
        "requested": 5,
        "resolved": 5,
        "evaluated": 2,
        "not_evaluated": 3,
        "matches": 2,
    }
    assert set(calls) == {"RELIANCE", "INFY", "NIFTY"}
    assert run["data_mode"] == "REAL" and run["market_data_provider"] == "dhan"
    for r in run["rows"]:
        if r["outcome"] == "MATCH":
            assert r["provenance"]["producer"]["provider"] == "dhan"
            assert r["provenance"]["mode"] != "SYNTHETIC"
    s = client.post(BASE + "/saved", json={"config": requested}, headers=HEADERS)
    assert s.status_code == 200
    assert (
        client.patch(
            BASE + "/saved/" + s.json()["id"],
            json={"config": {**requested, "name": "Renamed"}},
            headers=HEADERS,
        ).status_code
        == 200
    )
    target = create(client, "Target")
    ids = [r["instrument"]["instrument_id"] for r in run["rows"] if r["outcome"] == "MATCH"]
    handoff = BASE + "/runs/" + run["id"] + "/watchlists/" + target
    assert client.post(handoff, json={"instrument_ids": ids}, headers=HEADERS).json()["added"] == 2
    assert client.post(handoff, json={"instrument_ids": ids}, headers=HEADERS).json()["added"] == 0
    client.post(
        "/api/v1/watchlists/" + key + "/remove", json={"instrument_ids": ids}, headers=HEADERS
    )
    assert (
        len(client.get(BASE + "/runs/" + run["id"]).json()["universe_snapshot"]["instruments"]) == 5
    )
    login(client, "bob")
    assert client.get(BASE + "/runs/" + run["id"]).status_code == 404
    assert client.get(BASE + "/saved").json() == []
    assert (
        client.patch(
            BASE + "/saved/" + s.json()["id"], json={"config": requested}, headers=HEADERS
        ).status_code
        == 404
    )


def test_partial_resolution_and_absent_credentials(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_market(client, monkeypatch)
    r = client.post(
        BASE + "/runs",
        json=config(universe={"source": "CUSTOM", "symbols": ["RELIANCE", "INVALID", "INFY"]}),
        headers=HEADERS,
    ).json()
    assert r["counts"] == {
        "requested": 3,
        "resolved": 2,
        "evaluated": 1,
        "not_evaluated": 2,
        "matches": 1,
    }
    monkeypatch.setattr(
        cast(Any, client.app).state.dhan_credentials,
        "capture",
        lambda *a, **k: SimpleNamespace(provider=None, status=SimpleNamespace(generation=4)),
    )
    r = client.post(BASE + "/runs", json=config(), headers=HEADERS).json()
    assert r["counts"]["not_evaluated"] == 1 and not r["counts"]["matches"]


def test_fixture_cannot_enter_real_cache() -> None:
    class Fake:
        async def get_ohlcv(self, *args: Any, **kwargs: Any) -> Any:
            return series([100.0] * 40)

    from twf.watchlists.service import WatchlistFailure

    with pytest.raises(WatchlistFailure, match="REAL_DATA_PROVENANCE_REQUIRED"):
        asyncio.run(ScannerHistory().read(UUID(int=1), 1, Fake(), instruments()[0]))  # type: ignore[arg-type]


def test_taptide_normalization_no_raw_schema_and_dedup() -> None:
    rows = normalize(
        {
            "buckets": {
                "bullish": [
                    {"symbol": "INFY", "ltp": 100, "change_pct": 2, "secretish": "do not copy"}
                ],
                "near_52w_high": [{"symbol": "INFY", "ltp": 100, "change_pct": 2}],
            }
        },
        "get_trending_stocks",
    )
    assert len(rows) == 1 and len(rows[0]["reasons"]) == 2
    assert rows[0]["provider"] == "tapetide" and "secretish" not in str(rows)


@pytest.mark.parametrize(
    "field",
    [
        "rsi",
        "volume",
        "rvol",
        "sma20",
        "ema20",
        "macd",
        "adx",
        "atr",
        "bb_upper",
        "roc",
        "high20",
        "support",
        "resistance",
    ],
)
def test_numeric_predicates_retain_observed_thresholds(field: str) -> None:
    bars = series([float(n) for n in range(100, 401)]).bars
    observed = metrics(bars)[field]
    assert isinstance(observed, (float, int))
    matched = evaluate(bars, (Filter(field=field, operator=">=", value=observed),))
    assert matched["outcome"] == "MATCH"
    assert matched["diagnostics"][0]["observed"] == observed
    assert matched["diagnostics"][0]["threshold"] == observed
    assert (
        evaluate(bars, (Filter(field=field, operator="<", value=observed),))["outcome"]
        == "NON_MATCH"
    )


def test_fundamentals_are_explicit_optional_inputs() -> None:
    bars = series([100.0] * 300).bars
    pe = Filter(field="pe_ratio", operator="<", value=25, source="tapetide")
    assert evaluate(bars, (pe,))["outcome"] == "NOT_EVALUATED"
    assert evaluate(bars, (pe,), {"pe_ratio": 22.06})["outcome"] == "MATCH"
    assert evaluate(bars, (Filter(field="volume", operator=">", value=0),))["outcome"] == "MATCH"
    with pytest.raises(ValidationError):
        Filter(field="pe_ratio", value=25)
    with pytest.raises(ValidationError):
        Filter(field="price", operator=">", value="price")


def test_taptide_unavailable_does_not_invent_provider_matches() -> None:
    from twf.integrations.mcp.contracts import Code, Failure
    from twf.scanner_v2.tapetide import TapTideScanner

    class Offline:
        def connection(self) -> Any:
            raise Failure(Code.AUTH_REQUIRED)

    result = asyncio.run(TapTideScanner(Offline()).read())  # type: ignore[arg-type]
    assert result["state"] == "UNAVAILABLE" and result["rows"] == []


def test_quote_loss_does_not_block_daily_scanning(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_market(client, monkeypatch)
    daily = client.post(BASE + "/runs", json=config(), headers=HEADERS).json()
    assert daily["counts"]["matches"] == 1
    quote = client.post(
        BASE + "/runs",
        json=config(filters=[{"field": "ltp", "operator": ">", "value": 0}]),
        headers=HEADERS,
    ).json()
    assert quote["counts"]["not_evaluated"] == 1
    assert quote["rows"][0]["quote_failure"]
