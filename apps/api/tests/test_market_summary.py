"""Global header market-summary contracts, isolation, freshness and cache tests."""

from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from pydantic import SecretStr

from twf.discovery.market_data import DhanMarketDataProvider, DhanMarketDataSettings
from twf.discovery.market_summary import (
    GlobalMarketSummary,
    GlobalMarketSummaryService,
    MarketSummaryCache,
    SummaryAvailability,
    SummaryFreshness,
    SummaryReason,
)
from twf.watchlists.market import WatchlistHistoryCache, WatchlistQuoteCache

FIELDS = (
    "SEM_EXM_EXCH_ID",
    "SEM_SEGMENT",
    "SEM_SMST_SECURITY_ID",
    "SEM_INSTRUMENT_NAME",
    "SEM_TRADING_SYMBOL",
    "SEM_CUSTOM_SYMBOL",
    "SEM_EXCH_INSTRUMENT_TYPE",
    "SEM_SERIES",
    "SM_SYMBOL_NAME",
)
ROWS = (
    ("NSE", "I", "13", "INDEX", "NIFTY", "Nifty 50", "INDEX", "X", "NIFTY"),
    ("NSE", "I", "25", "INDEX", "BANKNIFTY", "Nifty Bank", "INDEX", "X", "BANKNIFTY"),
    ("NSE", "I", "21", "INDEX", "INDIA VIX", "India VIX", "INDEX", "X", "INDIA VIX"),
)


def master() -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(FIELDS)
    writer.writerows(ROWS)
    return output.getvalue().encode()


def provider(
    *,
    missing: str | None = None,
    zero_change: str | None = None,
    source_time: datetime | None = None,
    counter: dict[str, int] | None = None,
) -> DhanMarketDataProvider:
    prices = {"13": Decimal("24998.75"), "25": Decimal("52316.20"), "21": Decimal("13.25")}
    changes = {"13": Decimal("104.40"), "25": Decimal("301.20"), "21": Decimal("-0.27")}

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=master())
        if request.url.path == "/v2/charts/historical":
            if counter is not None:
                counter["history"] = counter.get("history", 0) + 1
            closes = {
                "13": (Decimal("24750"), Decimal("24894.35"), prices["13"]),
                "25": (Decimal("51650"), Decimal("52015"), prices["25"]),
                "21": (Decimal("13.70"), Decimal("13.52"), prices["21"]),
            }[str(json.loads(request.content)["securityId"])]
            timestamps = [
                datetime(2026, 10, day, 0, 0, tzinfo=UTC).timestamp() for day in (6, 7, 8)
            ]
            return httpx.Response(
                200,
                json={
                    "timestamp": timestamps,
                    "open": [float(value) for value in closes],
                    "high": [float(value) for value in closes],
                    "low": [float(value) for value in closes],
                    "close": [float(value) for value in closes],
                    "volume": [0, 0, 0],
                },
            )
        assert request.url.path == "/v2/marketfeed/quote"
        if counter is not None:
            counter["quotes"] = counter.get("quotes", 0) + 1
        requested = json.loads(request.content)["IDX_I"]
        data: dict[str, dict[str, object]] = {}
        for identity in requested:
            key = str(identity)
            if key == missing:
                continue
            net = Decimal(0) if key == zero_change else changes[key]
            row: dict[str, object] = {
                "last_price": float(prices[key]),
                "net_change": float(net),
                "volume": 0,
            }
            if source_time is not None:
                row["last_trade_time"] = source_time.astimezone(
                    __import__("zoneinfo").ZoneInfo("Asia/Kolkata")
                ).strftime("%d/%m/%Y %H:%M:%S")
            data[key] = row
        return httpx.Response(200, json={"status": "success", "data": {"IDX_I": data}})

    return DhanMarketDataProvider(
        DhanMarketDataSettings(
            enabled=True,
            client_id=SecretStr("client"),
            access_token=SecretStr("access-token"),
        ),
        transport=httpx.MockTransport(respond),
    )


def run(
    live: DhanMarketDataProvider | None,
    *,
    owner: UUID | None = None,
    generation: int = 1,
    now: datetime | None = None,
    quote_cache: WatchlistQuoteCache | None = None,
    history_cache: WatchlistHistoryCache | None = None,
    summary_cache: MarketSummaryCache | None = None,
) -> GlobalMarketSummary:
    service = GlobalMarketSummaryService(
        owner or uuid4(),
        generation,
        live,
        quote_cache or WatchlistQuoteCache(),
        history_cache or WatchlistHistoryCache(),
        summary_cache or MarketSummaryCache(),
    )
    return asyncio.run(service.summary(now=now))


def test_all_dhan_items_and_one_day_percent_are_normalized() -> None:
    at = datetime(2026, 10, 8, 5, 0, tzinfo=UTC)
    result = run(provider(source_time=at - timedelta(minutes=2)), now=at)
    assert result.nifty.availability == SummaryAvailability.AVAILABLE
    assert result.banknifty.source == "dhan"
    assert result.india_vix.source == "dhan"
    assert result.nifty.previous_close == Decimal("24894.35")
    assert result.nifty.change_percent == (Decimal("104.40") / Decimal("24894.35") * Decimal(100))
    assert result.india_vix.change_percent is not None
    assert result.india_vix.change_percent < 0
    assert {result.nifty.freshness, result.banknifty.freshness} == {SummaryFreshness.CURRENT}
    assert result.refresh_after_seconds == 30


def test_missing_source_time_stays_unavailable_instead_of_false_zero() -> None:
    result = run(provider(zero_change="13"))
    assert result.nifty.availability == SummaryAvailability.AVAILABLE
    assert result.nifty.previous_close is None
    assert result.nifty.change_percent is None


def test_closing_quote_uses_previous_session_history_when_net_change_resets() -> None:
    calls: dict[str, int] = {}
    at = datetime(2026, 10, 8, 11, 0, tzinfo=UTC)
    result = run(
        provider(zero_change="13", source_time=at - timedelta(minutes=1), counter=calls),
        now=at,
    )
    assert result.nifty.availability == SummaryAvailability.AVAILABLE
    assert result.nifty.previous_close == Decimal("24894.35")
    assert result.nifty.change_percent == (
        (Decimal("24998.75") - Decimal("24894.35")) / Decimal("24894.35") * Decimal(100)
    )
    assert calls["quotes"] == 1
    assert calls["history"] == 1


def test_partial_batch_recovers_each_item_without_blanking_peers() -> None:
    calls: dict[str, int] = {}
    result = run(provider(missing="21", counter=calls))
    assert result.nifty.availability == SummaryAvailability.AVAILABLE
    assert result.banknifty.availability == SummaryAvailability.AVAILABLE
    assert result.india_vix.availability == SummaryAvailability.UNAVAILABLE
    assert result.india_vix.reason == SummaryReason.TEMPORARILY_UNAVAILABLE
    assert calls["quotes"] == 4  # one batch, then one bounded isolation call per item


def test_provider_not_ready_is_honest_and_does_not_require_tapetide() -> None:
    result = run(None)
    assert all(
        item.availability == SummaryAvailability.UNAVAILABLE
        and item.reason == SummaryReason.PROVIDER_NOT_READY
        for item in (result.nifty, result.banknifty, result.india_vix)
    )


def test_stale_source_is_explicit() -> None:
    at = datetime(2026, 10, 8, 5, 0, tzinfo=UTC)
    result = run(provider(source_time=at - timedelta(hours=2)), now=at)
    assert result.nifty.freshness == SummaryFreshness.STALE


def test_summary_cache_is_owner_and_generation_fenced() -> None:
    calls: dict[str, int] = {}
    live = provider(counter=calls)
    quotes = WatchlistQuoteCache()
    summaries = MarketSummaryCache()
    owner = uuid4()
    at = datetime(2026, 10, 8, 5, 0, tzinfo=UTC)
    first = run(live, owner=owner, now=at, quote_cache=quotes, summary_cache=summaries)
    second = run(live, owner=owner, now=at, quote_cache=quotes, summary_cache=summaries)
    assert first == second
    assert calls["quotes"] == 1
    assert summaries.hits == 1 and summaries.misses == 1
    run(live, owner=uuid4(), now=at, quote_cache=quotes, summary_cache=summaries)
    run(
        live,
        owner=owner,
        generation=2,
        now=at,
        quote_cache=quotes,
        summary_cache=summaries,
    )
    assert calls["quotes"] == 3


def test_authenticated_endpoint_uses_owner_scoped_ready_capture(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from twf.auth import create_user
    from twf.config.settings import Settings
    from twf.discovery.dhan_credentials import (
        DhanCredentialCapture,
        DhanCredentialState,
        DhanCredentialStatus,
    )
    from twf.infrastructure.database import Base, create_database_engine, create_session_factory
    from twf.main import create_app

    database = tmp_path / "market-summary.db"
    settings = Settings(database_url=f"sqlite+pysqlite:///{database}")
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    with create_session_factory(engine).begin() as session:
        create_user(session, "summary-user", "Summary User", "test-only-summary-password")
    live = provider()
    capture = DhanCredentialCapture(
        live,
        DhanCredentialStatus(
            state=DhanCredentialState.READY,
            configured=True,
            enabled=True,
            generation=7,
            source="NONE",
        ),
    )

    class Credentials:
        def capture(self, owner_id: UUID, *, ready_only: bool) -> DhanCredentialCapture:
            assert owner_id.int != 0 and ready_only is True
            return capture

    app = create_app(settings, engine_factory=lambda _: engine)
    with TestClient(app) as client:
        assert client.get("/api/v1/market/summary").status_code == 403
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"username": "summary-user", "password": "test-only-summary-password"},
                headers={"Origin": "http://localhost:3000"},
            ).status_code
            == 200
        )
        app.state.dhan_credentials = Credentials()
        response = client.get("/api/v1/market/summary")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
        assert response.json()["nifty"]["source"] == "dhan"
        assert response.json()["india_vix"]["availability"] == "AVAILABLE"


def test_cache_does_not_hold_unavailable_state_across_ready_transition() -> None:
    owner = uuid4()
    summaries = MarketSummaryCache()
    quotes = WatchlistQuoteCache()
    at = datetime(2026, 10, 8, 5, 0, tzinfo=UTC)
    unavailable = run(
        None,
        owner=owner,
        generation=9,
        now=at,
        quote_cache=quotes,
        summary_cache=summaries,
    )
    available = run(
        provider(),
        owner=owner,
        generation=9,
        now=at,
        quote_cache=quotes,
        summary_cache=summaries,
    )
    assert unavailable.nifty.availability == SummaryAvailability.UNAVAILABLE
    assert available.nifty.availability == SummaryAvailability.AVAILABLE
