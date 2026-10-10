"""O2 deterministic domain, Dhan boundary, cache and authenticated API tests."""

import asyncio
import csv
import io
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from test_broker_v1 import client as client

from twf.api.options import OptionChainRegistry
from twf.discovery.dhan_credentials import (
    DhanCredentialCapture,
    DhanCredentialState,
    DhanCredentialStatus,
)
from twf.discovery.market_data import (
    DhanMarketDataProvider,
    DhanMarketDataSettings,
    MarketDataErrorCode,
    MarketDataFailure,
)
from twf.discovery.market_summary import GlobalMarketSummaryService, MarketSummaryCache
from twf.options.chain_contracts import OptionChainRequest, OptionMarketSnapshot
from twf.options.chain_service import ChainFailure, ChainMarketBatch, OptionChainService
from twf.options.contracts import OptionContract, OptionType, UnderlyingType, option_contract_id
from twf.options.dhan_chain import (
    CAPABILITIES,
    DhanOptionChainSource,
    normalize_market,
    parse_contracts,
)
from twf.watchlists.market import WatchlistHistoryCache, WatchlistQuoteCache

TODAY = datetime.now(UTC).astimezone(ZoneInfo("Asia/Kolkata")).date()
EXPIRY = TODAY + timedelta(days=7)


def contract(
    strike: int, side: str, *, underlying: str = "NIFTY", expiry: date = EXPIRY
) -> OptionContract:
    return OptionContract(
        canonical_id=option_contract_id(
            "NFO", underlying, expiry, Decimal(strike), OptionType(side)
        ),
        exchange="NFO",
        segment="NFO-OPT",
        underlying_symbol=underlying,
        underlying_type=UnderlyingType.INDEX if underlying == "NIFTY" else UnderlyingType.EQUITY,
        expiry=expiry,
        strike=Decimal(strike),
        option_type=OptionType(side),
        lot_size=65,
        display_symbol=f"{underlying} {expiry} {strike} {side}",
        tick_size=Decimal("0.05"),
    )


class Source:
    capabilities = CAPABILITIES.model_copy(update={"iv": "UNSUPPORTED", "greeks": "UNSUPPORTED"})
    quote_ttl_seconds = 5
    master_received_at = datetime.now(UTC)

    def __init__(self) -> None:
        self.items = tuple(contract(s, side) for s in range(50, 205, 5) for side in ("CE", "PE"))
        self.spot: Decimal | None = Decimal("102.5")
        self.missing: set[str] = set()
        self.fail = False
        self.calls = 0

    async def contracts(self) -> tuple[OptionContract, ...]:
        return self.items

    async def market(
        self, underlying: str, expiry: date, contracts: tuple[OptionContract, ...]
    ) -> ChainMarketBatch:
        self.calls += 1
        if self.fail:
            raise ChainFailure("provider_unavailable", 503)
        return ChainMarketBatch(
            self.spot,
            {
                c.canonical_id: OptionMarketSnapshot(
                    ltp=Decimal(10), volume=Decimal(30), open_interest=Decimal(50)
                )
                for c in contracts
                if c.canonical_id not in self.missing
            },
            datetime.now(UTC),
        )


def snapshot(source: Source, **changes: Any) -> Any:
    return asyncio.run(
        OptionChainService(source).snapshot(
            OptionChainRequest.model_validate({"underlying": "NIFTY", "expiry": EXPIRY, **changes})
        )
    )


def test_atm_tie_moneyness_distance_dte_sorted_and_bounded() -> None:
    source = Source()
    result = snapshot(source, around_atm=1)
    assert result.atm_strike == 100
    assert [r.strike for r in result.rows] == [95, 100, 105]
    assert [r.ce.moneyness for r in result.rows] == ["ITM", "ATM", "OTM"]
    assert [r.pe.moneyness for r in result.rows] == ["OTM", "ATM", "ITM"]
    assert result.rows[1].distance_from_spot == Decimal("-2.5")
    assert result.dte == 7 and source.calls == 1
    assert result.provenance.freshness == "SOURCE_TIME_UNAVAILABLE"
    assert result.rows[0].ce.market.implied_volatility is None
    assert result.rows[0].ce.market.delta is None


@pytest.mark.parametrize("missing_side", ["CE", "PE"])
def test_missing_side_is_not_fabricated(missing_side: str) -> None:
    source = Source()
    source.items = tuple(c for c in source.items if c.option_type.value != missing_side)
    result = snapshot(source, around_atm=0)
    assert getattr(result.rows[0], missing_side.lower()) is None
    assert getattr(result.rows[0], "pe" if missing_side == "CE" else "ce") is not None


def test_partial_quotes_preserve_contract_and_other_leg() -> None:
    source = Source()
    source.missing.add(contract(100, "CE").canonical_id)
    result = snapshot(source, around_atm=0)
    assert result.status == "PARTIAL" and "quote_unavailable" in result.warnings
    assert result.rows[0].ce.availability == "UNAVAILABLE"
    assert result.rows[0].ce.market.ltp is None
    assert result.rows[0].pe.market.ltp == 10


def test_no_spot_and_total_provider_failure_retain_bounded_structure() -> None:
    source = Source()
    source.spot = None
    result = snapshot(source, around_atm=2)
    assert len(result.rows) == 5 and result.atm_strike is None
    assert result.rows[0].ce.moneyness is None
    assert result.rows[0].distance_percent is None
    source.fail = True
    result = snapshot(source)
    assert result.status == "PARTIAL" and len(result.rows) == 21
    assert result.provenance.freshness == "UNAVAILABLE"


def test_range_side_and_max_bounds() -> None:
    result = snapshot(Source(), strike_min="110", strike_max="120", side="PE")
    assert [r.strike for r in result.rows] == [110, 115, 120]
    assert all(r.ce is None for r in result.rows)
    for changes in [{"around_atm": 26}, {"around_atm": -1}, {"strike_min": 120, "strike_max": 110}]:
        with pytest.raises(ValidationError):
            OptionChainRequest.model_validate({"underlying": "NIFTY", "expiry": EXPIRY, **changes})
    with pytest.raises(ChainFailure, match="no_option_contracts"):
        snapshot(Source(), strike_min=500)


def test_same_day_expired_and_multiple_expiries() -> None:
    source = Source()
    source.items += (
        contract(100, "CE", expiry=TODAY),
        contract(100, "PE", expiry=TODAY - timedelta(days=1)),
    )
    service = OptionChainService(source)
    assert asyncio.run(service.expiries("NIFTY")) == (TODAY, EXPIRY)
    result = asyncio.run(service.snapshot(OptionChainRequest(underlying="NIFTY", expiry=TODAY)))
    assert result.dte == 0
    with pytest.raises(ChainFailure, match="expiry_not_found"):
        asyncio.run(
            service.snapshot(
                OptionChainRequest(underlying="NIFTY", expiry=TODAY - timedelta(days=1))
            )
        )
    source.items = (contract(100, "CE", underlying="HDFCBANK"),)
    assert asyncio.run(service.underlyings("hdfc")) == ("HDFCBANK",)
    result = asyncio.run(service.snapshot(OptionChainRequest(underlying="HDFCBANK", expiry=EXPIRY)))
    assert result.rows[0].ce is not None and result.rows[0].ce.contract.underlying_type == "EQUITY"


@pytest.mark.parametrize(
    "bid,ask,expected", [(10, 12, 2), (0, 12, None), (10, None, None), (12, 10, None)]
)
def test_spread(bid: int, ask: int | None, expected: int | None) -> None:
    market = normalize_market({"top_bid_price": bid, "top_ask_price": ask})
    assert market.spread == expected
    assert market.spread_percent == (Decimal(2) / 11 * 100 if expected else None)


def test_oi_iv_greeks_and_invalid_numbers() -> None:
    market = normalize_market(
        {
            "oi": 100,
            "previous_oi": 120,
            "volume": 1000,
            "implied_volatility": 15,
            "greeks": {"delta": -0.4, "theta": -3, "gamma": 0.1, "vega": 4},
        }
    )
    assert market.change_in_open_interest == -20 and market.implied_volatility == 15
    assert market.delta == Decimal("-0.4") and market.theta == -3
    assert normalize_market({"oi": 100, "volume": 1000}).change_in_open_interest is None
    assert (
        normalize_market({"oi": -1, "last_price": "NaN", "volume": True}).model_dump()[
            "open_interest"
        ]
        is None
    )
    assert normalize_market({"implied_volatility": 0, "greeks": {"delta": 0}}).delta is None


def master_bytes() -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "EXCH_ID",
            "SEGMENT",
            "SECURITY_ID",
            "INSTRUMENT",
            "UNDERLYING_SYMBOL",
            "LOT_SIZE",
            "SM_EXPIRY_DATE",
            "STRIKE_PRICE",
            "OPTION_TYPE",
            "TICK_SIZE",
        ],
    )
    writer.writeheader()
    for side, token in [("CE", "5"), ("PE", "6")]:
        writer.writerow(
            dict(
                EXCH_ID="NSE",
                SEGMENT="D",
                SECURITY_ID=token,
                INSTRUMENT="OPTIDX",
                UNDERLYING_SYMBOL="NIFTY",
                LOT_SIZE="65.0",
                SM_EXPIRY_DATE=EXPIRY.isoformat(),
                STRIKE_PRICE="25000.000",
                OPTION_TYPE=side,
                TICK_SIZE="5",
            )
        )
    return output.getvalue().encode()


class DhanFixture(DhanMarketDataProvider):
    async def resolve_instruments(self, symbols: tuple[str, ...]) -> Any:
        from twf.discovery.market_data import _identity

        return (
            _identity(
                {
                    "SEM_EXM_EXCH_ID": "NSE",
                    "SEM_SEGMENT": "I",
                    "SEM_SMST_SECURITY_ID": "13",
                    "SEM_TRADING_SYMBOL": "NIFTY",
                    "SEM_INSTRUMENT_NAME": "INDEX",
                }
            ),
        )


def dhan_source(
    *, fail: bool = False, mismatch: bool = False
) -> tuple[DhanOptionChainSource, list[str]]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.method == "GET":
            return httpx.Response(200, content=master_bytes())
        if request.url.path == "/v2/marketfeed/quote":
            assert json.loads(request.content) == {"IDX_I": [13]}
            return httpx.Response(
                200, json={"status": "success", "data": {"IDX_I": {"13": {"last_price": 25010}}}}
            )
        assert json.loads(request.content)["UnderlyingScrip"] == 13
        if fail:
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "last_price": 25020,
                    "oc": {
                        "25000.000000": {
                            "ce": {
                                "security_id": 999 if mismatch else 5,
                                "last_price": 100,
                                "top_bid_price": 99,
                                "top_ask_price": 101,
                                "oi": 1000,
                                "previous_oi": 900,
                                "volume": 80,
                            },
                            "pe": {"security_id": 6, "last_price": 50, "oi": 2000, "volume": 90},
                        }
                    },
                },
            },
        )

    provider = DhanFixture(
        DhanMarketDataSettings(
            enabled=True, client_id=SecretStr("123"), access_token=SecretStr("test-token")
        ),
        transport=httpx.MockTransport(handler),
    )
    return DhanOptionChainSource(provider, uuid4(), 1, WatchlistQuoteCache()), calls


def test_dhan_master_normalization_batched_fetch_and_cache() -> None:
    source, calls = dhan_source()

    async def run() -> None:
        service = OptionChainService(source)
        result = await service.snapshot(OptionChainRequest(underlying="NIFTY", expiry=EXPIRY))
        again = await service.snapshot(OptionChainRequest(underlying="NIFTY", expiry=EXPIRY))
        assert result.rows[0].ce is not None
        assert result.rows[0].ce.contract.tick_size == Decimal("0.05")
        assert result.rows[0].ce.market.change_in_open_interest == 100
        assert result.spot == 25010
        assert "underlying_spot_mismatch" not in result.warnings
        assert again.provenance.cached and not result.provenance.cached
        assert again.provenance.received_at == result.provenance.received_at
        assert len(calls) == 3  # master, chain batch, one index quote; no per-leg requests
        assert "security_id" not in result.model_dump_json()
        assert "access-token" not in result.model_dump_json()

    asyncio.run(run())


@pytest.mark.parametrize("fail,mismatch", [(True, False), (False, True)])
def test_dhan_failure_and_token_mismatch(fail: bool, mismatch: bool) -> None:
    source, calls = dhan_source(fail=fail, mismatch=mismatch)
    result = asyncio.run(
        OptionChainService(source).snapshot(OptionChainRequest(underlying="NIFTY", expiry=EXPIRY))
    )
    assert result.status == "PARTIAL" and len(calls) == (2 if fail else 3)
    assert result.rows[0].ce is not None and result.rows[0].ce.market.ltp is None
    if mismatch:
        assert result.rows[0].pe is not None and result.rows[0].pe.market.ltp == 50


def test_duplicate_master_identity_rejected() -> None:
    raw = master_bytes()
    with pytest.raises(ChainFailure, match="partial_chain"):
        parse_contracts(raw + raw.splitlines(keepends=True)[1])


def test_generation_and_owner_cache_isolation() -> None:
    registry = OptionChainRegistry()
    source, _ = dhan_source()
    owner, other = uuid4(), uuid4()
    cache = WatchlistQuoteCache()
    first = registry.get(owner, 1, source.provider, cache)
    assert registry.get(owner, 1, source.provider, cache) is first
    assert registry.get(other, 1, source.provider, cache) is not first
    assert registry.get(owner, 2, source.provider, cache) is not first
    assert (owner, 1) not in registry.sources


def test_authenticated_api_bounds_and_normalized_chain(client: TestClient) -> None:
    source, _ = dhan_source()

    class Manager:
        def capture(self, *args: Any, **kwargs: Any) -> DhanCredentialCapture:
            return DhanCredentialCapture(
                source.provider,
                DhanCredentialStatus(
                    state=DhanCredentialState.READY,
                    configured=True,
                    enabled=True,
                    generation=1,
                    source="DATABASE",
                ),
            )

    app = cast(FastAPI, client.app)
    app.state.dhan_credentials = Manager()
    for path in [
        "underlyings?query=NIF",
        "expiries?underlying=NIFTY",
        f"chain?underlying=NIFTY&expiry={EXPIRY}",
    ]:
        response = client.get("/api/v1/options/" + path)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
    assert (
        client.get(
            f"/api/v1/options/chain?underlying=NIFTY&expiry={EXPIRY}&around_atm=26"
        ).status_code
        == 422
    )
    client.cookies.clear()
    assert client.get("/api/v1/options/underlyings").status_code == 401


def test_provider_capabilities_mask_unsupported_fields_and_preserve_supported() -> None:
    class FullSource(Source):
        async def market(
            self, underlying: str, expiry: date, contracts: tuple[OptionContract, ...]
        ) -> ChainMarketBatch:
            return ChainMarketBatch(
                Decimal(100),
                {
                    c.canonical_id: OptionMarketSnapshot(
                        ltp=Decimal(10), implied_volatility=Decimal(20), delta=Decimal("0.5")
                    )
                    for c in contracts
                },
                datetime.now(UTC),
            )

    source = FullSource()
    result = snapshot(source, around_atm=0)
    assert result.rows[0].ce.market.implied_volatility is None
    assert result.rows[0].ce.market.delta is None
    source.capabilities = CAPABILITIES.model_copy(update={"iv": "SUPPORTED", "greeks": "SUPPORTED"})
    result = snapshot(source, around_atm=0)
    assert result.rows[0].ce.market.implied_volatility == 20
    assert result.rows[0].ce.market.delta == Decimal("0.5")
    assert result.rows[0].ce.availability == "PARTIAL"  # missing supported bid/ask


def test_concurrent_requests_share_master_and_quote_batch() -> None:
    source, calls = dhan_source()

    async def run() -> None:
        service = OptionChainService(source)
        requests = [
            service.snapshot(OptionChainRequest(underlying="NIFTY", expiry=EXPIRY))
            for _ in range(4)
        ]
        snapshots = await asyncio.gather(*requests)
        assert len(calls) == 3
        assert sum(s.provenance.cached for s in snapshots) == 3

    asyncio.run(run())


def test_dte_uses_india_calendar_boundary() -> None:
    source = Source()
    source.items = (contract(100, "CE", expiry=EXPIRY),)
    instant = datetime.combine(EXPIRY - timedelta(days=1), datetime.min.time(), tzinfo=UTC).replace(
        hour=20
    )
    result = asyncio.run(
        OptionChainService(source).snapshot(
            OptionChainRequest(underlying="NIFTY", expiry=EXPIRY), now=instant
        )
    )
    assert result.dte == 0


def test_request_with_no_listed_selected_side_rejects_empty_rows() -> None:
    source = Source()
    source.items = (contract(100, "CE"),)
    with pytest.raises(ChainFailure, match="no_option_contracts"):
        snapshot(source, side="PE")


@pytest.mark.parametrize(
    ("symbol", "security_id", "canonical_spot", "chain_spot", "strikes", "expected_atm"),
    [
        ("NIFTY", "13", 22520, 23122, (22500, 22550, 23100), 22500),
        ("BANKNIFTY", "25", 48040, 49050, (48000, 48100, 49000), 48000),
        ("FINNIFTY", "27", 23370, 24020, (23350, 23400, 24000), 23350),
        ("MIDCPNIFTY", "442", 11820, 12100, (11800, 11850, 12100), 11800),
        ("NIFTYNXT50", "38", 68040, 69050, (68000, 68100, 69000), 68000),
    ],
)
def test_index_spot_uses_canonical_quote_and_drives_atm(
    symbol: str,
    security_id: str,
    canonical_spot: int,
    chain_spot: int,
    strikes: tuple[int, ...],
    expected_atm: int,
) -> None:
    from twf.discovery.market_data import _identity

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "EXCH_ID",
            "SEGMENT",
            "SECURITY_ID",
            "INSTRUMENT",
            "UNDERLYING_SYMBOL",
            "LOT_SIZE",
            "SM_EXPIRY_DATE",
            "STRIKE_PRICE",
            "OPTION_TYPE",
            "TICK_SIZE",
        ],
    )
    writer.writeheader()
    chain: dict[str, dict[str, dict[str, int]]] = {}
    for index, strike in enumerate(strikes):
        chain[f"{strike}.000000"] = {}
        for side, token in (("CE", 100 + index * 2), ("PE", 101 + index * 2)):
            writer.writerow(
                {
                    "EXCH_ID": "NSE",
                    "SEGMENT": "D",
                    "SECURITY_ID": str(token),
                    "INSTRUMENT": "OPTIDX",
                    "UNDERLYING_SYMBOL": symbol,
                    "LOT_SIZE": "65",
                    "SM_EXPIRY_DATE": EXPIRY.isoformat(),
                    "STRIKE_PRICE": str(strike),
                    "OPTION_TYPE": side,
                    "TICK_SIZE": "5",
                }
            )
            chain[f"{strike}.000000"][side.lower()] = {
                "security_id": token,
                "last_price": 100,
                "top_bid_price": 99,
                "top_ask_price": 101,
                "volume": 80,
                "oi": 1000,
            }
    instrument = _identity(
        {
            "SEM_EXM_EXCH_ID": "NSE",
            "SEM_SEGMENT": "I",
            "SEM_SMST_SECURITY_ID": security_id,
            "SEM_TRADING_SYMBOL": symbol,
            "SEM_INSTRUMENT_NAME": "INDEX",
        }
    )
    calls: list[str] = []

    class IndexProvider(DhanMarketDataProvider):
        async def resolve_instruments(self, symbols: tuple[str, ...]) -> Any:
            assert symbols == (symbol,)
            return (instrument,)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.method == "GET":
            return httpx.Response(200, content=output.getvalue().encode())
        if request.url.path == "/v2/marketfeed/quote":
            assert json.loads(request.content) == {"IDX_I": [int(security_id)]}
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {"IDX_I": {security_id: {"last_price": canonical_spot}}},
                },
            )
        assert json.loads(request.content)["UnderlyingSeg"] == "IDX_I"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "last_price": chain_spot,
                    "oc": chain,
                },
            },
        )

    provider = IndexProvider(
        DhanMarketDataSettings(
            enabled=True, client_id=SecretStr("123"), access_token=SecretStr("test-token")
        ),
        transport=httpx.MockTransport(handler),
    )
    source = DhanOptionChainSource(provider, uuid4(), 1, WatchlistQuoteCache())
    result = asyncio.run(
        OptionChainService(source).snapshot(
            OptionChainRequest(underlying=symbol, expiry=EXPIRY, around_atm=2)
        )
    )
    assert result.spot == canonical_spot
    assert result.atm_strike == expected_atm
    assert result.rows[0].is_atm is (strikes[0] == expected_atm)
    assert result.rows[0].ce is not None and result.rows[0].pe is not None
    assert result.rows[0].ce.moneyness == "ATM"
    assert result.rows[0].pe.moneyness == "ATM"
    assert result.rows[1].ce is not None and result.rows[1].pe is not None
    assert result.rows[1].ce.moneyness == "OTM"
    assert result.rows[1].pe.moneyness == "ITM"
    assert "underlying_spot_mismatch" in result.warnings
    assert result.provenance.market_source == "option-chain + underlying-quote"
    assert calls.count("/v2/marketfeed/quote") == 1
    assert calls.count("/v2/optionchain") == 1


def test_missing_index_quote_preserves_listed_option_quotes_without_atm() -> None:
    source, calls = dhan_source()
    source.quote_cache.read = lambda *args: asyncio.sleep(
        0, result={"error": "RATE_LIMITED", "quotes": []}
    )
    result = asyncio.run(
        OptionChainService(source).snapshot(OptionChainRequest(underlying="NIFTY", expiry=EXPIRY))
    )
    assert result.spot is None and result.atm_strike is None
    assert result.status == "PARTIAL"
    assert {"underlying_spot_unavailable", "spot_unavailable"} <= set(result.warnings)
    assert result.rows[0].ce is not None and result.rows[0].ce.market.ltp == 100
    assert result.rows[0].ce.moneyness is None
    assert calls == ["/api-data/api-scrip-master-detailed.csv", "/v2/optionchain"]


@pytest.mark.parametrize(
    ("segment", "instrument_type", "symbol"),
    [("D", "FUTIDX", "NIFTY"), ("E", "EQUITY", "NIFTY"), ("I", "INDEX", "NIFTYIT")],
)
def test_wrong_underlying_instrument_rejected_before_chain_or_quote(
    segment: str, instrument_type: str, symbol: str
) -> None:
    from twf.discovery.market_data import _identity

    source, calls = dhan_source()
    wrong = _identity(
        {
            "SEM_EXM_EXCH_ID": "NSE",
            "SEM_SEGMENT": segment,
            "SEM_SMST_SECURITY_ID": "13",
            "SEM_TRADING_SYMBOL": symbol,
            "SEM_INSTRUMENT_NAME": instrument_type,
        }
    )

    async def resolve(symbols: tuple[str, ...]) -> Any:
        return (wrong,)

    source.provider.resolve_instruments = resolve
    result = asyncio.run(
        OptionChainService(source).snapshot(OptionChainRequest(underlying="NIFTY", expiry=EXPIRY))
    )
    assert "underlying_instrument_type_mismatch" in result.warnings
    assert result.spot is None and result.atm_strike is None
    assert calls == ["/api-data/api-scrip-master-detailed.csv"]


@pytest.mark.parametrize("symbol", ["HDFCBANK", "RELIANCE", "ABB"])
def test_equity_option_spot_keeps_chain_semantics_without_index_quote(symbol: str) -> None:
    from twf.discovery.market_data import _identity

    source, calls = dhan_source()
    equity = _identity(
        {
            "SEM_EXM_EXCH_ID": "NSE",
            "SEM_SEGMENT": "E",
            "SEM_SMST_SECURITY_ID": "1333",
            "SEM_TRADING_SYMBOL": "HDFCBANK",
            "SEM_INSTRUMENT_NAME": "EQUITY",
        }
    )
    contracts = tuple(
        item.model_copy(
            update={
                "underlying_symbol": symbol,
                "underlying_type": UnderlyingType.EQUITY,
                "canonical_id": option_contract_id(
                    "NFO", symbol, EXPIRY, item.strike, item.option_type
                ),
            }
        )
        for item in parse_contracts(master_bytes())[0]
    )
    source._tokens = {item.canonical_id: str(5 + index) for index, item in enumerate(contracts)}

    async def resolve(symbols: tuple[str, ...]) -> Any:
        return (equity,)

    source.provider.resolve_instruments = resolve

    # Equity retains option-chain last_price without requesting an index quote.
    async def run() -> ChainMarketBatch:
        original_json = source.provider._json

        async def chain_json(path: str, payload: Any) -> Any:
            assert path == "/optionchain"
            return {
                "status": "success",
                "data": {
                    "last_price": 25020,
                    "oc": {
                        "25000.000000": {
                            "ce": {"security_id": 5, "last_price": 100},
                            "pe": {"security_id": 6, "last_price": 50},
                        },
                    },
                },
            }

        source.provider._json = chain_json
        try:
            return await source.market(symbol, EXPIRY, contracts)
        finally:
            source.provider._json = original_json

    batch = asyncio.run(run())
    assert batch.spot == 25020
    assert batch.market_source == "option-chain"
    assert calls == []


def test_market_summary_and_options_share_canonical_index_quote() -> None:
    source, calls = dhan_source()

    async def run() -> None:
        (instrument,) = await source.provider.resolve_instruments(("NIFTY",))
        summary = GlobalMarketSummaryService(
            source.owner,
            source.generation,
            source.provider,
            source.quote_cache,
            WatchlistHistoryCache(),
            MarketSummaryCache(),
        )
        quotes, errors = await summary._quotes((instrument,))
        assert not errors
        result = await OptionChainService(source).snapshot(
            OptionChainRequest(underlying="NIFTY", expiry=EXPIRY)
        )
        assert result.spot == quotes[instrument.instrument_id].last_price
        assert result.provenance.market_source == "option-chain + underlying-quote"
        assert calls.count("/v2/marketfeed/quote") == 1

    asyncio.run(run())


def test_unresolved_index_does_not_use_option_chain_spot() -> None:
    source, calls = dhan_source()

    async def unresolved(symbols: tuple[str, ...]) -> Any:
        raise MarketDataFailure(MarketDataErrorCode.INSTRUMENT_NOT_FOUND)

    source.provider.resolve_instruments = unresolved
    result = asyncio.run(
        OptionChainService(source).snapshot(OptionChainRequest(underlying="NIFTY", expiry=EXPIRY))
    )
    assert result.spot is None and result.atm_strike is None
    assert "underlying_index_unresolved" in result.warnings
    assert calls == ["/api-data/api-scrip-master-detailed.csv"]


def test_index_validation_allows_exact_or_explicit_alias_not_fuzzy() -> None:
    from twf.discovery.market_data import _identity

    def index(symbol: str) -> Any:
        return _identity(
            {
                "SEM_EXM_EXCH_ID": "NSE",
                "SEM_SEGMENT": "I",
                "SEM_SMST_SECURITY_ID": "25",
                "SEM_TRADING_SYMBOL": symbol,
                "SEM_INSTRUMENT_NAME": "INDEX",
            }
        )

    assert DhanOptionChainSource._validated_index(index("BANKNIFTY"), "NIFTYBANK")
    assert DhanOptionChainSource._validated_index(index("NIFTYBANK"), "NIFTYBANK")
    assert not DhanOptionChainSource._validated_index(index("NIFTYBANK50"), "NIFTYBANK")
