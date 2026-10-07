"""Collection isolation, data identity, migration and provider-boundary tests."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event

from twf.api.watchlists import catalog as catalog_dependency
from twf.auth import create_user
from twf.config.settings import Settings
from twf.discovery.market_data import DhanMarketDataProvider, DhanMarketDataSettings
from twf.infrastructure.database import create_database_engine, create_session_factory
from twf.main import create_app
from twf.watchlists.catalog import WatchlistCatalog, kind
from twf.watchlists.market import WatchlistQuoteCache
from twf.watchlists.service import WatchlistService

ORIGIN = "https://web.example"
HEADERS = {"Origin": ORIGIN}
BASE = "/api/v1/watchlists"


def provider() -> DhanMarketDataProvider:
    value = DhanMarketDataProvider(DhanMarketDataSettings())
    value._master_at = datetime.now(UTC)
    value._master = tuple(
        {
            "SEM_EXM_EXCH_ID": "NSE",
            "SEM_SEGMENT": segment,
            "SEM_SMST_SECURITY_ID": str(n),
            "SEM_INSTRUMENT_NAME": asset,
            "SEM_TRADING_SYMBOL": symbol,
            "SEM_CUSTOM_SYMBOL": symbol,
            "SEM_EXCH_INSTRUMENT_TYPE": "",
            "SEM_SERIES": "EQ",
            "SM_SYMBOL_NAME": "NIFTY" if segment == "D" else symbol,
            "SEM_EXPIRY_DATE": "2099-12-30",
            "SEM_STRIKE_PRICE": "25000",
            "SEM_OPTION_TYPE": "CE",
        }
        for n, (symbol, segment, asset) in enumerate(
            [
                ("RELIANCE", "E", "EQUITY"),
                ("INFY", "E", "EQUITY"),
                ("NIFTY", "I", "INDEX"),
                ("NIFTY99DECFUT", "D", "FUTIDX"),
                ("NIFTY99DEC25000CE", "D", "OPTIDX"),
            ],
            1,
        )
    )
    return value


@pytest.fixture
def client() -> Iterator[TestClient]:
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    settings = Settings(cors_origins=(ORIGIN,))
    engine = create_database_engine(settings)
    with create_session_factory(engine).begin() as db:
        create_user(db, "alice", "Alice", "test-only-watchlist-password")
        create_user(db, "bob", "Bob", "test-only-watchlist-password")
    app = create_app(settings, engine_factory=lambda _: engine)
    app.dependency_overrides[catalog_dependency] = lambda: WatchlistCatalog(provider())
    with TestClient(app) as c:
        login(c)
        yield c


def login(client: TestClient, name: str = "alice") -> None:
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": name, "password": "test-only-watchlist-password"},
            headers=HEADERS,
        ).status_code
        == 200
    )


def create(client: TestClient, name: str = "My Core") -> str:
    result = client.post(BASE, json={"name": name}, headers=HEADERS)
    assert result.status_code == 201, result.text
    return str(result.json()["id"])


def instruments() -> tuple[Any, ...]:
    return asyncio.run(WatchlistCatalog(provider()).instruments())


def add(client: TestClient, key: str) -> None:
    r = client.post(
        f"{BASE}/{key}/items",
        headers=HEADERS,
        json={"instrument_ids": [str(i.instrument_id) for i in instruments()]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 5


def test_crud_types_order_duplicates_notes_activity_snapshot(client: TestClient) -> None:
    key = create(client)
    add(client, key)
    r = client.get(f"{BASE}/{key}").json()
    assert [i["kind"] for i in r["items"]] == ["EQUITY", "EQUITY", "INDEX", "FUTURE", "OPTION"]
    assert r["count"] == 5
    snap = client.get(f"{BASE}/{key}/universe").json()
    ids = [i["instrument"]["instrument_id"] for i in r["items"]]
    duplicate = client.post(f"{BASE}/{key}/items", headers=HEADERS, json={"instrument_ids": ids})
    assert duplicate.json() == {"added": 0, "duplicates": 5}
    assert (
        client.post(
            f"{BASE}/{key}/notes", headers=HEADERS, json={"text": "Review earnings"}
        ).status_code
        == 201
    )
    client.delete(f"{BASE}/{key}/items/{ids[0]}", headers=HEADERS)
    current = client.get(f"{BASE}/{key}").json()
    assert current["count"] == 4 and current["notes"][0]["text"] == "Review earnings"
    assert len(snap["instruments"]) == 5  # immutable prior snapshot
    assert any(a["action"] == "REMOVED" for a in current["activity"])
    for archived in (True, False):
        client.patch(
            f"{BASE}/{key}", headers=HEADERS, json={"name": "Renamed", "archived": archived}
        )
        assert client.get(f"{BASE}/{key}").json()["archived"] == archived
    assert client.get(BASE).json()[0]["name"] == "Renamed"


def test_owner_isolation_and_origin(client: TestClient) -> None:
    key = create(client)
    add(client, key)
    assert client.post(BASE, json={"name": "Without origin"}).status_code == 403
    login(client, "bob")
    assert client.get(BASE).json() == []
    for suffix in ("", "/export", "/universe", "/quotes"):
        assert client.get(f"{BASE}/{key}{suffix}").status_code == 404
    assert (
        client.patch(f"{BASE}/{key}", headers=HEADERS, json={"archived": True}).status_code == 404
    )
    for action in ("restore", "permanent-delete"):
        assert (
            client.post(
                f"{BASE}/trash/{action}", headers=HEADERS, json={"watchlist_ids": [key]}
            ).status_code
            == 404
        )
    assert (
        client.post(f"{BASE}/{key}/notes", headers=HEADERS, json={"text": "Attack"}).status_code
        == 404
    )
    target = create(client, "Bob's list")
    assert (
        client.post(
            f"{BASE}/{key}/transfer",
            headers=HEADERS,
            json={"target_id": target, "instrument_ids": [str(instruments()[0].instrument_id)]},
        ).status_code
        == 404
    )


def test_trash_bulk_restore_and_permanent_delete(client: TestClient) -> None:
    first = create(client, "First")
    second = create(client, "Second")
    active = create(client, "Active")
    add(client, first)
    for key in (first, second):
        assert (
            client.patch(f"{BASE}/{key}", headers=HEADERS, json={"archived": True}).status_code
            == 200
        )

    restored = client.post(
        f"{BASE}/trash/restore", headers=HEADERS, json={"watchlist_ids": [first]}
    )
    assert restored.status_code == 200 and restored.json() == {"restored": 1}
    detail = client.get(f"{BASE}/{first}").json()
    assert detail["archived"] is False and detail["count"] == 5
    assert any(row["action"] == "RESTORED" for row in detail["activity"])

    rejected = client.post(
        f"{BASE}/trash/permanent-delete",
        headers=HEADERS,
        json={"watchlist_ids": [first, second]},
    )
    assert rejected.status_code == 409
    assert client.get(f"{BASE}/{second}").status_code == 200

    deleted = client.post(
        f"{BASE}/trash/permanent-delete", headers=HEADERS, json={"watchlist_ids": [second]}
    )
    assert deleted.status_code == 200 and deleted.json() == {"deleted": 1}
    assert client.get(f"{BASE}/{second}").status_code == 404
    assert client.get(f"{BASE}/{active}").status_code == 200


def test_import_export_transfer_and_provider_unavailable(client: TestClient) -> None:
    key, target = create(client), create(client, "Other")
    result = client.post(
        f"{BASE}/{key}/import",
        headers=HEADERS,
        json={"csv": "canonical_symbol\nNSE:RELIANCE\nNSE:RELIANCE\nNSE:NO_SUCH_SYMBOL\n"},
    )
    assert result.json()["added"] == 1 and result.json()["duplicates"] == 1
    assert len(result.json()["invalid"]) == 1
    exported = client.get(f"{BASE}/{key}/export")
    assert "NSE:RELIANCE,NSE,EQUITY,RELIANCE" in exported.text
    identity = str(instruments()[0].instrument_id)
    for move in (False, True):
        assert (
            client.post(
                f"{BASE}/{key}/transfer",
                headers=HEADERS,
                json={"target_id": target, "instrument_ids": [identity], "move": move},
            ).status_code
            == 200
        )
    assert client.get(f"{BASE}/{target}").json()["count"] == 1
    result = client.get(f"{BASE}/{target}/quotes").json()
    assert result["error"] == "AUTH_REQUIRED" and result["quotes"] == []
    assert client.get(f"{BASE}/{target}").json()["count"] == 1


def test_invalid_and_archived_items_rejected(client: TestClient) -> None:
    key = create(client)
    assert client.post(BASE, headers=HEADERS, json={"name": " "}).status_code == 422
    r = client.post(
        f"{BASE}/{key}/items",
        headers=HEADERS,
        json={"instrument_ids": ["00000000-0000-0000-0000-000000000000"]},
    )
    assert r.status_code == 422
    client.patch(f"{BASE}/{key}", headers=HEADERS, json={"archived": True})
    r = client.post(
        f"{BASE}/{key}/items",
        headers=HEADERS,
        json={"instrument_ids": [str(instruments()[0].instrument_id)]},
    )
    assert r.status_code == 409


def test_catalog_exact_native_derivative_identity() -> None:
    rows = instruments()
    assert {kind(i) for i in rows} == {"EQUITY", "INDEX", "FUTURE", "OPTION"}
    assert rows[-1].native.native_id == "NSE_FNO:5"
    assert rows[-1].right == "CALL" and rows[-1].strike == 25000
    assert rows[-1].segment == "FNO"


def test_provider_io_has_no_open_db_transaction_and_quotes_are_batched(client: TestClient) -> None:
    key = create(client)
    add(client, key)
    app = client.app
    state = app.state  # type: ignore[attr-defined]
    owner = UUID(client.get("/api/v1/auth/me").json()["id"])
    active = 0

    def begin(*args: Any) -> None:
        nonlocal active
        active += 1

    def end(*args: Any) -> None:
        nonlocal active
        active -= 1

    event.listen(state.database_engine, "begin", begin)
    event.listen(state.database_engine, "rollback", end)
    event.listen(state.database_engine, "commit", end)
    snapshot = WatchlistService(state.session_factory, owner).snapshot(UUID(key))
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert active == 0
        assert request.url.path == "/v2/marketfeed/quote"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "NSE_EQ": {str(n): {"last_price": 100 + n} for n in (1, 2)},
                    "IDX_I": {"3": {"last_price": 20000}},
                    "NSE_FNO": {str(n): {"last_price": 100 + n} for n in (4, 5)},
                },
            },
        )

    live = DhanMarketDataProvider(
        DhanMarketDataSettings(
            enabled=True, client_id=SecretStr("test-client"), access_token=SecretStr("test-token")
        ),
        transport=httpx.MockTransport(respond),
    )

    async def run() -> None:
        cache = WatchlistQuoteCache()
        for _ in range(2):
            r = await cache.read(owner, 1, live, snapshot.instruments)
            assert len(r["quotes"]) == 5 and r["error"] is None

    asyncio.run(run())
    assert calls == 1 and active == 0


def test_transfer_preserves_order_and_inbound_provenance(client: TestClient) -> None:
    key, target = create(client), create(client, "Target")
    ids = [str(i.instrument_id) for i in instruments()[:2]]
    source = {"source": "scanner", "run_id": "00000000-0000-0000-0000-000000000123"}
    assert (
        client.post(
            f"{BASE}/{key}/items",
            headers=HEADERS,
            json={"instrument_ids": ids, "source_metadata": source},
        ).status_code
        == 200
    )
    result = client.post(
        f"{BASE}/{key}/transfer",
        headers=HEADERS,
        json={"target_id": target, "instrument_ids": ids, "move": True},
    )
    assert result.json() == {"added": 2, "duplicates": 0}
    items = client.get(f"{BASE}/{target}").json()["items"]
    assert [i["ordering"] for i in items] == [0, 1]
    assert all(i["source"]["run_id"] == source["run_id"] for i in items)
    assert client.get(f"{BASE}/{key}").json()["count"] == 0


def test_broker_mapping_exact_identity_and_fail_closed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decimal import Decimal

    from twf.brokers.contracts import Instrument
    from twf.brokers.order_service import OrderService
    from twf.brokers.service import Principal

    key = create(client)
    add(client, key)
    identity = instruments()[0].instrument_id
    path = (
        f"{BASE}/{key}/items/{identity}/broker-instrument"
        "?account_id=00000000-0000-0000-0000-000000000001"
    )
    assert client.get(path).status_code == 409  # Trading disabled: existing broker adapter guard.
    rows = [
        Instrument(
            symbol="RELIANCE",
            exchange="NSE",
            reference="ZERODHA:NSE:RELIANCE",
            native_token="2885",
            kind="EQ",
            segment="NSE",
            tick_size=Decimal("0.05"),
            lot_size=Decimal(1),
        )
    ]
    calls = []

    async def catalog(self: OrderService, who: Principal, account_id: UUID) -> list[Instrument]:
        calls.append(who.user_id)
        return rows

    monkeypatch.setattr(OrderService, "catalog", catalog)
    assert client.get(path).json()["reference"] == "ZERODHA:NSE:RELIANCE"
    option = instruments()[-1]
    rows.append(
        Instrument(
            symbol="NIFTY99DEC25000CE",
            exchange="NFO",
            reference="ZERODHA:NFO:NIFTY99DEC25000CE",
            native_token="option-token",
            kind="CE",
            segment="NFO-OPT",
            underlying="NIFTY",
            expiry="2099-12-30",
            strike=Decimal(25000),
            lot_size=Decimal(75),
            tick_size=Decimal("0.05"),
        )
    )
    # The mapping does not depend on Dhan and broker contract symbols being identical.
    option_path = path.replace(str(identity), str(option.instrument_id))
    rows[-1] = rows[-1].model_copy(update={"symbol": "NIFTY99D3025000CE"})
    assert client.get(option_path).json()["native_token"] == "option-token"
    rows[-1] = rows[-1].model_copy(update={"strike": Decimal(25100)})
    assert client.get(option_path).status_code == 422
    rows.append(rows[0].model_copy(update={"native_token": "other"}))
    assert client.get(path).status_code == 422  # Ambiguous native identity is never guessed.
    index = instruments()[2].instrument_id
    assert client.get(path.replace(str(identity), str(index))).status_code == 422
    before = len(calls)
    login(client, "bob")
    assert client.get(path).status_code == 404
    assert len(calls) == before  # No cross-owner broker I/O.


def test_lazy_history_metrics_do_not_invent_missing_data() -> None:
    from datetime import timedelta

    from twf.discovery.internal_scanner.market_series import Bar
    from twf.watchlists.market import history_metrics

    at = datetime.now(UTC)
    bars = tuple(
        Bar(
            timestamp=at + timedelta(days=i),
            available_at=at + timedelta(days=i + 1),
            open=100 + i,
            close=100 + i,
            high=101 + i,
            low=99 + i,
            volume=1000,
        )
        for i in range(22)
    )
    result = history_metrics(bars, "1d")
    assert result and result["rsi14"] == 100 and result["trend"] == "Up"
    assert result["average_volume20"] == 1000
    assert history_metrics(bars[:5], "1d") is None
    assert history_metrics(bars, "5m") is None
    missing = (*bars[:-1], bars[-1].model_copy(update={"volume": None}))
    assert history_metrics(missing, "1d")["average_volume20"] is None  # type: ignore[index]


def test_history_cache_deduplicates_and_fences_owner_generation() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from twf.watchlists.market import WatchlistHistoryCache

    async def run() -> None:
        cache = WatchlistHistoryCache()
        p = SimpleNamespace(
            get_ohlcv=AsyncMock(
                return_value=SimpleNamespace(bars=(), received_at=datetime.now(UTC))
            )
        )
        item = (await WatchlistCatalog(provider()).instruments())[0]
        owner = uuid4()
        a, b = await asyncio.gather(
            cache.read(owner, 1, p, item, "1d", 22),
            cache.read(owner, 1, p, item, "1d", 22),
        )
        assert a == b and p.get_ohlcv.await_count == 1
        await cache.read(owner, 1, p, item, "1d", 22)
        assert p.get_ohlcv.await_count == 1
        cache.next_start = 0
        await cache.read(owner, 2, p, item, "1d", 22)
        cache.next_start = 0
        await cache.read(uuid4(), 2, p, item, "1d", 22)
        assert p.get_ohlcv.await_count == 3
        key = owner, 1, item.instrument_id, "1d", 22
        cache.values[key] = (0, a)
        cache.next_start = 0
        await cache.read(owner, 1, p, item, "1d", 22)
        assert p.get_ohlcv.await_count == 4
        assert (await cache.read(owner, 1, None, item, "1d", 22))["error"] == "AUTH_REQUIRED"

    asyncio.run(run())


def test_history_cache_rate_limit_stops_other_cold_rows() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from twf.discovery.market_data import MarketDataErrorCode, MarketDataFailure
    from twf.watchlists.market import WatchlistHistoryCache

    async def run() -> None:
        cache = WatchlistHistoryCache()
        p = SimpleNamespace(
            get_ohlcv=AsyncMock(side_effect=MarketDataFailure(MarketDataErrorCode.RATE_LIMITED))
        )
        owner = uuid4()
        for item in (await WatchlistCatalog(provider()).instruments())[:2]:
            assert (await cache.read(owner, 1, p, item, "1d", 22))["error"] == "RATE_LIMITED"
        assert p.get_ohlcv.await_count == 1

    asyncio.run(run())


def test_reference_normalization_units_missing_values_and_identity() -> None:
    from decimal import Decimal

    from twf.watchlists.reference import normalize_reference

    at = datetime.now(UTC)
    raw: dict[str, Any] = {
        "data": {
            "found": True,
            "symbol": "RELIANCE",
            "market_cap": 1648263.22,
            "pe_ttm": 22.06,
            "high_52w": 1611.8,
            "low_52w": 1160.8,
            "updated_at": at.isoformat(),
            "raw_secret_field": "must-not-escape",
        }
    }
    result = normalize_reference("RELIANCE", raw, at)
    assert result.state == "AVAILABLE" and result.market_cap_inr == Decimal("16482632200000")
    assert result.pe_ratio == Decimal("22.06") and result.high_52_week == Decimal("1611.8")
    assert result.source_time == at and result.freshness == "CURRENT"
    assert result.provider == "tapetide" and result.tool == "get_stock_quote"
    assert "must-not-escape" not in result.model_dump_json()
    raw["data"]["pe_ttm"] = None
    assert normalize_reference("RELIANCE", raw, at).pe_ratio is None
    assert normalize_reference("INFY", raw, at).state == "UNAVAILABLE"
    raw["data"]["low_52w"] = 2000
    result = normalize_reference("RELIANCE", raw, at)
    assert result.high_52_week is None and result.low_52_week is None
    assert normalize_reference("RELIANCE", {}, at).state == "UNAVAILABLE"


def test_reference_endpoint_owner_checks_before_provider(client: TestClient) -> None:
    key = create(client)
    add(client, key)
    item = instruments()[0]
    path = f"{BASE}/{key}/items/{item.instrument_id}/reference"
    assert client.get(path).json()["state"] == "UNAVAILABLE"
    login(client, "bob")
    assert client.get(path).status_code == 404


def test_reference_cache_deduplicates_and_fences_owner_generation() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    from uuid import uuid4

    from twf.integrations.mcp.contracts import Context
    from twf.watchlists.reference import WatchlistReferenceCache

    async def run() -> None:
        cache = WatchlistReferenceCache()
        item = (await WatchlistCatalog(provider()).instruments())[0]
        who = Context(owner_id=uuid4(), session_hash="a" * 64)
        connection = uuid4()
        manager: Any = SimpleNamespace(
            tools=AsyncMock(
                return_value=(
                    None,
                    {
                        "structuredContent": {
                            "data": {
                                "found": True,
                                "symbol": item.symbol,
                                "pe_ttm": 22.06,
                            }
                        }
                    },
                )
            ),
            operations=SimpleNamespace(wait_receipts=AsyncMock()),
        )
        with patch("twf.watchlists.reference.TapTideMarketIntelligence.connection") as connected:
            connected.return_value = (connection, 1, frozenset({"get_stock_quote"}))
            a, b = await asyncio.gather(
                cache.read(manager, who, item), cache.read(manager, who, item)
            )
            assert a == b and a.state == "PARTIAL" and manager.tools.await_count == 1
            assert manager.tools.call_args.kwargs["arguments"] == {"symbol": item.symbol}
            assert manager.tools.call_args.kwargs["policy"].allowed == frozenset(
                {"get_stock_quote"}
            )
            await cache.read(manager, who, item)
            assert manager.tools.await_count == 1
            connected.return_value = (connection, 2, frozenset({"get_stock_quote"}))
            await cache.read(manager, who, item)
            await cache.read(manager, who.model_copy(update={"owner_id": uuid4()}), item)
            assert manager.tools.await_count == 3
            await cache.read(manager, who, item.model_copy(update={"instrument_type": "INDEX"}))
            assert manager.tools.await_count == 3
            connected.return_value = (connection, 2, frozenset())
            assert (await cache.read(manager, who, item)).state == "UNAVAILABLE"
            assert manager.operations.wait_receipts.await_count == 3

    asyncio.run(run())
