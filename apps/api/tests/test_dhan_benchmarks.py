"""Provider-side analytical benchmark aliases, using a captured public master."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from test_market_data import MASTER_FIELDS, master, settings

from twf.discovery.dhan_benchmarks import BENCHMARK_ALIASES, BenchmarkSupportStatus
from twf.discovery.market_data import DhanMarketDataProvider, MarketDataErrorCode, MarketDataFailure

FIXTURES = Path(__file__).parent / "fixtures"
INDEX_ROWS: tuple[dict[str, str], ...] = tuple(
    json.loads((FIXTURES / "dhan_sector_index_master.json").read_text())
)
MAPPINGS: tuple[tuple[str, str], ...] = tuple(
    tuple(x) for x in json.loads((FIXTURES / "sector_benchmark_mappings.json").read_text())
)


def provider(rows: tuple[dict[str, str], ...] = INDEX_ROWS) -> DhanMarketDataProvider:
    p = DhanMarketDataProvider(settings())
    p._master = rows
    p._master_at = datetime.now(UTC)
    return p


@pytest.mark.parametrize("name,symbol", MAPPINGS)
def test_every_current_benchmark_resolves_to_observed_master(name: str, symbol: str) -> None:
    p = provider()
    found = asyncio.run(p.resolve_instruments((symbol,)))[0]
    expected_name = BENCHMARK_ALIASES[symbol][1]
    expected = next(r for r in INDEX_ROWS if r["SEM_TRADING_SYMBOL"] == expected_name)
    assert found.provider_symbol == expected_name
    assert found.native.native_id == "IDX_I:" + expected["SEM_SMST_SECURITY_ID"]
    assert found.exchange == "NSE" and found.segment == "INDEX" and found.instrument_type == "INDEX"
    diagnostic = asyncio.run(p.validate_sector_benchmark_support(((name, symbol),)))[0]
    assert diagnostic.status == BenchmarkSupportStatus.SUPPORTED
    assert diagnostic.exchange_segment == "IDX_I"
    assert diagnostic.security_id == expected["SEM_SMST_SECURITY_ID"]


def test_all_emitted_families_are_covered_without_a_security_id_registry() -> None:
    assert {symbol for _, symbol in MAPPINGS} == set(BENCHMARK_ALIASES)
    result = asyncio.run(provider().validate_sector_benchmark_support(MAPPINGS))
    assert len(result) == 11 and all(r.status == "SUPPORTED" for r in result)
    assert all(
        not any(character.isdigit() for character in alias[1])
        for alias in BENCHMARK_ALIASES.values()
    )


@pytest.mark.parametrize(
    "alias,canonical",
    [
        (" nifty _ metal ", "NIFTY METAL"),
        ("NIFTY BANK", "BANKNIFTY"),
        ("nifty_fin_service", "FINNIFTY"),
        ("NIFTY OIL & GAS", "NIFTY OIL AND GAS"),
        ("banknifty", "BANKNIFTY"),
        ("NIFTYIT", "NIFTYIT"),
    ],
)
def test_exact_alias_and_case_spacing(alias: str, canonical: str) -> None:
    assert asyncio.run(provider().resolve_instruments((alias,)))[0].provider_symbol == canonical


def test_exact_match_precedes_normalized_alias() -> None:
    bank = next(r for r in INDEX_ROWS if r["SEM_TRADING_SYMBOL"] == "BANKNIFTY")
    alternate = {**bank, "SEM_TRADING_SYMBOL": "NIFTYBANK", "SEM_SMST_SECURITY_ID": "9999"}
    found = asyncio.run(provider((*INDEX_ROWS, alternate)).resolve_instruments(("NIFTYBANK",)))[0]
    assert found.native.native_id == "IDX_I:9999"


def test_ambiguity_never_falls_through_to_pick_a_registry_target() -> None:
    bank = next(r for r in INDEX_ROWS if r["SEM_TRADING_SYMBOL"] == "BANKNIFTY")
    alternate = {**bank, "SEM_TRADING_SYMBOL": "OTHER BANK", "SEM_SMST_SECURITY_ID": "9999"}
    # Same normalized custom alias, distinct indices: selecting BANKNIFTY would be unsafe.
    with pytest.raises(MarketDataFailure) as caught:
        asyncio.run(provider((*INDEX_ROWS, alternate)).resolve_instruments(("NIFTYBANK",)))
    assert caught.value.code == MarketDataErrorCode.AMBIGUOUS_INSTRUMENT


@pytest.mark.parametrize("symbol", ["NIFTYFIN", "NIFTY OIL", "NIFTYBANK50", "METAL", "NIFTY METL"])
def test_no_substring_or_fuzzy_selection(symbol: str) -> None:
    with pytest.raises(MarketDataFailure) as caught:
        asyncio.run(provider().resolve_instruments((symbol,)))
    assert caught.value.code == MarketDataErrorCode.INSTRUMENT_NOT_FOUND


def test_registry_does_not_manufacture_absent_master_instrument() -> None:
    rows = tuple(r for r in INDEX_ROWS if r["SEM_TRADING_SYMBOL"] != "NIFTY OIL AND GAS")
    p = provider(rows)
    with pytest.raises(MarketDataFailure) as caught:
        asyncio.run(p.resolve_instruments(("NIFTYOILGAS",)))
    assert caught.value.code == MarketDataErrorCode.BENCHMARK_ALIAS_UNRESOLVED
    result = asyncio.run(p.validate_sector_benchmark_support((("NIFTY OIL & GAS", "NIFTYOILGAS"),)))
    assert result[0].status == "UNRESOLVED_ALIAS"


def test_explicit_unsupported_and_invalid_mapping_are_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "twf.discovery.market_data.UNSUPPORTED_BENCHMARKS", frozenset({"NIFTYBANK"})
    )
    p = provider()
    values = asyncio.run(
        p.validate_sector_benchmark_support(
            (("NIFTY BANK", "NIFTYBANK"), ("NIFTY IT", "NIFTYBANK"))
        )
    )
    assert values[0].status == "UNSUPPORTED_BY_DHAN"
    assert values[0].reason == "BENCHMARK_UNSUPPORTED_BY_DHAN"
    assert values[1].status == "INVALID_METADATA_MAPPING"
    with pytest.raises(MarketDataFailure) as caught:
        asyncio.run(p.resolve_instruments(("nifty bank",)))
    assert caught.value.code == MarketDataErrorCode.BENCHMARK_UNSUPPORTED_BY_DHAN


def test_cached_lookup_tracks_master_refresh_without_stale_ids() -> None:
    p = provider()
    first = asyncio.run(p.resolve_instruments(("NIFTYMETAL",)))[0]
    lookup = p._index_lookup
    asyncio.run(p.resolve_instruments(("NIFTYIT", "NIFTYBANK")))
    assert p._index_lookup is lookup
    p._master = tuple(
        {**r, "SEM_SMST_SECURITY_ID": "9999"} if r["SEM_TRADING_SYMBOL"] == "NIFTY METAL" else r
        for r in INDEX_ROWS
    )
    second = asyncio.run(p.resolve_instruments(("NIFTYMETAL",)))[0]
    assert second.native.native_id == "IDX_I:9999" and second != first
    assert p._index_lookup is not lookup


def test_master_failure_is_typed_and_diagnostic_does_not_claim_unsupported() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503)

    p = DhanMarketDataProvider(settings(), transport=httpx.MockTransport(respond))
    results = asyncio.run(p.validate_sector_benchmark_support(MAPPINGS))
    assert len(requests) == 1
    assert len(results) == 11
    assert all(r.status == "UNRESOLVED_ALIAS" and r.reason == "PROVIDER_ERROR" for r in results)


def test_all_benchmarks_use_existing_history_request_and_exclude_incomplete_bar() -> None:
    calls: list[dict[str, Any]] = []
    at = datetime(2026, 10, 9, 9, 30, tzinfo=UTC)  # 15:00 IST, before cash close
    end = datetime(2026, 10, 8, 18, 30, tzinfo=UTC)  # today's daily timestamp

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                content=master(
                    *(tuple(row.get(key, "") for key in MASTER_FIELDS) for row in INDEX_ROWS)
                ),
            )
        body = json.loads(request.content)
        calls.append(body)
        assert request.url.path == "/v2/charts/historical"
        assert body["exchangeSegment"] == "IDX_I" and body["instrument"] == "INDEX"
        return httpx.Response(
            200,
            json={
                "timestamp": [int((end - timedelta(days=60 - i)).timestamp()) for i in range(61)],
                "open": [100.0] * 61,
                "high": [102.0] * 61,
                "low": [99.0] * 61,
                "close": [101.0] * 61,
                "volume": [0] * 61,
            },
        )

    p = DhanMarketDataProvider(settings(), transport=httpx.MockTransport(respond))

    async def run() -> None:
        for _, symbol in MAPPINGS:
            identity = (await p.resolve_instruments((symbol,)))[0]
            value = await p.get_ohlcv(identity, "1d", as_of=at, count=60)
            assert len(value.bars) == 60 and value.live_bar_excluded
            assert all(b.finality == "COMPLETED" and b.available_at <= at for b in value.bars)
            assert value.bars[-1].timestamp == end - timedelta(days=1)
            assert value.provenance.producer.provider == "dhan"

    asyncio.run(run())
    assert len(calls) == len(MAPPINGS) == 11
    assert len({c["securityId"] for c in calls}) == 11
