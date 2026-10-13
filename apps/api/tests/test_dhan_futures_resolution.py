"""Public Dhan detailed-master shape captured 2026-10-13 (no credentials)."""

import asyncio
import csv
import io
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from test_watchlists import HEADERS
from test_watchlists import client as client  # noqa: F401
from test_watchlists import provider as base_provider

from twf.discovery.dhan_futures import FuturesMaster, parse_master
from twf.discovery.market_data import MarketDataErrorCode, MarketDataFailure

FIXTURE = Path(__file__).parent / "fixtures/dhan_futures_detailed.json"
TODAY = date(2026, 10, 13)


def raw_rows() -> list[dict[str, str]]:
    return json.loads(FIXTURE.read_text())  # type: ignore[no-any-return]


def content(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


@pytest.mark.parametrize(
    "symbol,kind,token,lot,tick",
    [
        ("RELIANCE", "FUTSTK", "48987", "500.0", "0.1000"),
        ("HDFCBANK", "FUTSTK", "48864", "650.0", "0.0500"),
        ("INFY", "FUTSTK", "48886", "400.0", "0.0500"),
        ("NIFTY", "FUTIDX", "48704", "65.0", "0.1000"),
        ("BANKNIFTY", "FUTIDX", "48699", "30.0", "0.2000"),
    ],
)
def test_real_master_exact_contract(
    symbol: str, kind: str, token: str, lot: str, tick: str
) -> None:
    index = FuturesMaster(parse_master(content(raw_rows())), TODAY)
    result, failure = index.resolve(f" {symbol.lower()} ")
    assert failure is None and result
    expiry, row = result
    assert expiry == date(2026, 10, 27)
    assert row["SEM_INSTRUMENT_NAME"] == kind
    assert row["SEM_SEGMENT"] == "D"
    assert row["SEM_SMST_SECURITY_ID"] == token
    assert row["SEM_TRADING_SYMBOL"] == symbol + "-Oct2026-FUT"
    assert row["SEM_LOT_UNITS"] == lot
    assert row["SEM_TICK_SIZE"] == tick


def test_aliases_expiry_partial_invalid_and_cash_only() -> None:
    rows = raw_rows()
    expired_row = next(r.copy() for r in rows if r["INSTRUMENT"] == "FUTIDX")
    expired_row.update(SM_EXPIRY_DATE="2026-09-29", SECURITY_ID="1")
    rows.insert(0, expired_row)
    for row in rows:
        if row["UNDERLYING_SYMBOL"] == "HDFCBANK" and row["INSTRUMENT"] == "FUTSTK":
            row["SM_EXPIRY_DATE"] = "broken"
    cash = next(r.copy() for r in rows if r["INSTRUMENT"] == "EQUITY")
    cash.update(SYMBOL_NAME="CASHONLY", UNDERLYING_SYMBOL="CASHONLY")
    rows.append(cash)
    index = FuturesMaster(parse_master(content(rows)), TODAY)
    assert index.resolve("HDFCBANK")[1] == "INVALID_FUTURES_METADATA"
    assert all(index.resolve(s)[0] for s in ("RELIANCE", "INFY", "NIFTY"))
    assert index.resolve("DOESNOTEXIST")[1] == "NO_MASTER_MATCH"
    assert index.resolve("CASHONLY")[1] == "NO_ACTIVE_FUTURES"
    assert index.resolve("Nifty 50") == index.resolve("NIFTY")
    assert index.resolve("NIFTY_BANK") == index.resolve("BANKNIFTY")
    assert index.resolve("NIFTY", date(2026, 11, 23))[0][0] == date(2026, 11, 23)  # type: ignore[index]
    assert index.resolve("NIFTY", date(2026, 11, 24))[1] == "EXPIRY_NOT_FOUND"
    expired = FuturesMaster(parse_master(content(rows)), date(2027, 1, 1))
    assert expired.resolve("NIFTY")[1] == "NO_ACTIVE_FUTURES"
    on_expiry = FuturesMaster(parse_master(content(rows)), date(2026, 10, 27))
    assert on_expiry.resolve("NIFTY")[0][0] == date(2026, 10, 27)  # type: ignore[index]
    after = FuturesMaster(parse_master(content(rows)), date(2026, 10, 28))
    assert after.resolve("NIFTY")[0][0] == date(2026, 11, 23)  # type: ignore[index]


def test_loader_caches_one_snapshot_and_refreshes() -> None:
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(200, content=content(raw_rows()))

    provider = base_provider()
    provider.transport = httpx.MockTransport(handle)

    async def check() -> None:
        first, second = await asyncio.gather(
            provider._load_futures_master(), provider._load_futures_master()
        )
        assert first is second and len(calls) == 1
        provider._futures_master_at = datetime.now(UTC) - timedelta(days=1)
        await provider._load_futures_master()
        assert len(calls) == 2

    asyncio.run(check())


def test_custom_and_watchlist_use_same_structured_resolution(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from twf.scanner_v2.futures import FuturesScannerService

    provider = base_provider()
    rows = raw_rows()
    # Keep recorded provider identities/metadata but move listings into the test's active window.
    for row in rows:
        if row["INSTRUMENT"] in {"FUTSTK", "FUTIDX"}:
            row["SM_EXPIRY_DATE"] = (datetime.now(UTC).date() + timedelta(days=30)).isoformat()
    provider._futures_master = parse_master(content(rows))
    provider._futures_master_at = datetime.now(UTC)
    calls: list[set[str]] = []

    async def quotes(instruments: tuple[Any, ...]) -> tuple[tuple[Any, ...], tuple[str, ...]]:
        ids = {i.native.native_id for i in instruments}
        calls.append(ids)
        assert {"NSE_FNO:48987", "NSE_FNO:48864", "NSE_FNO:48886", "NSE_FNO:48704"} <= ids
        assert "IDX_I:13" in ids and "NSE_EQ:2885" in ids
        for item in instruments:
            if item.instrument_type in {"FUTSTK", "FUTIDX"}:
                assert item.segment == "FNO" and item.native.native_id.startswith("NSE_FNO:")
                assert item.underlying.source.native_id == "NSE:" + next(
                    s
                    for s in ("RELIANCE", "HDFCBANK", "INFY", "NIFTY")
                    if item.symbol.startswith(s + "-")
                )
        return (), tuple(ids)

    monkeypatch.setattr(provider, "get_quotes_partial", quotes)
    monkeypatch.setattr(
        cast(Any, client.app).state.dhan_credentials,
        "capture",
        lambda *args, **kw: SimpleNamespace(
            provider=provider, status=SimpleNamespace(generation=3)
        ),
    )
    symbols = ["RELIANCE", "HDFCBANK", "INFY", "NIFTY"]
    config = {
        "instrument_scope": "FUTURES",
        "universe": {"source": "CUSTOM", "symbols": symbols},
        "filters": [{"field": "volume", "operator": ">=", "value": 0}],
    }
    response = client.post("/api/v1/scanner/derivatives/futures/runs", json=config, headers=HEADERS)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["counts"]["resolved"] == 4 and len(calls) == 1
    assert all(r["failure"] == "FUTURES_QUOTE_MISSING" for r in run["underlyings"])
    assert len(run["rows"]) == 4
    reliance = next(r for r in run["rows"] if r["underlying"] == "RELIANCE")
    assert reliance["contract"]["trading_symbol"] == "RELIANCE-Oct2026-FUT"
    assert reliance["contract"]["lot_size"] == 500
    assert reliance["contract"]["tick_size"] == "0.1000"
    # Refreshing/replacing the master must not rewrite an archived contract snapshot.
    snapshot = run["rows"]
    original_master = provider._futures_master
    provider._futures_master = ()
    historical = client.get("/api/v1/scanner/derivatives/runs/" + run["id"])
    assert historical.status_code == 200
    assert historical.json()["rows"] == snapshot
    provider._futures_master = original_master

    async def members(*args: Any) -> tuple[tuple[str, ...], None]:
        return (*symbols, "DOESNOTEXIST"), None

    monkeypatch.setattr(FuturesScannerService, "_members", members)
    from uuid import uuid4

    eligibility = client.get(f"/api/v1/scanner/derivatives/futures/watchlists/{uuid4()}/eligible")
    assert eligibility.status_code == 200, eligibility.text
    assert eligibility.json()["eligible"] == 4 and eligibility.json()["members"] == 5
    assert eligibility.json()["excluded"] == ["DOESNOTEXIST"]


def test_unavailable_master_is_resolution_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = base_provider()

    async def unavailable() -> tuple[dict[str, str], ...]:
        raise MarketDataFailure(MarketDataErrorCode.PROVIDER_ERROR)

    monkeypatch.setattr(provider, "_load_futures_master", unavailable)
    monkeypatch.setattr(
        cast(Any, client.app).state.dhan_credentials,
        "capture",
        lambda *args, **kw: SimpleNamespace(
            provider=provider, status=SimpleNamespace(generation=3)
        ),
    )
    response = client.post(
        "/api/v1/scanner/derivatives/futures/runs",
        headers=HEADERS,
        json={
            "instrument_scope": "FUTURES",
            "universe": {"source": "CUSTOM", "symbols": ["NIFTY"]},
            "filters": [{"field": "volume", "operator": ">=", "value": 0}],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["rows"] == []
    assert response.json()["underlyings"][0]["failure"] == "PROVIDER_MASTER_UNAVAILABLE"


def test_invalid_contract_metadata_is_excluded_before_stable_tie_break() -> None:
    rows = raw_rows()
    good = next(r for r in rows if r["SECURITY_ID"] == "48987")
    duplicate = {**good, "SECURITY_ID": "99999"}
    invalid = {**good, "SECURITY_ID": "1", "TICK_SIZE": "NaN"}
    wrong_segment = {**good, "SECURITY_ID": "2", "SEGMENT": "E"}
    index = FuturesMaster(
        parse_master(content([duplicate, invalid, wrong_segment, *reversed(rows)])), TODAY
    )
    result, failure = index.resolve("RELIANCE")
    assert result and failure is None
    assert result[1]["SEM_SMST_SECURITY_ID"] == "48987"
