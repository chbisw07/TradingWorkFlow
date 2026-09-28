"""Isolated integration tests: real routes, migrations, crypto, adapter; fake provider transport."""

import asyncio
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from alembic import command
from alembic.config import Config
from broker_provider_fixture import provider
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from twf.auth import create_user
from twf.brokers.contracts import BrokerFailure, Credentials, Search
from twf.brokers.secrets import EncryptedSecretStore
from twf.brokers.service import BrokerService
from twf.brokers.zerodha import ZerodhaAdapter
from twf.config.settings import Settings
from twf.infrastructure.broker import BrokerAccount, BrokerAttempt, BrokerSecret
from twf.infrastructure.database import create_database_engine, create_session_factory
from twf.main import create_app

ORIGIN = "http://localhost:3000"
HEADERS = {"Origin": ORIGIN}
CREDENTIALS = {
    "name": "Zerodha – Primary",
    "api_key": "testapikey123",
    "api_secret": "testsecret123",
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    settings = Settings(
        credential_master_key=SecretStr(Fernet.generate_key().decode()), cors_origins=(ORIGIN,)
    )
    engine = create_database_engine(settings)
    with create_session_factory(engine)() as db:
        create_user(db, "trader", "Trader", "test-only-broker-password")
        create_user(db, "other", "Other", "test-only-broker-password")
        db.commit()
    adapter = ZerodhaAdapter(transport=httpx.MockTransport(provider))
    with TestClient(
        create_app(settings, engine_factory=lambda _: engine, broker_adapter=adapter)
    ) as test:
        assert (
            test.post(
                "/api/v1/auth/login",
                json={"username": "trader", "password": "test-only-broker-password"},
                headers=HEADERS,
            ).status_code
            == 200
        )
        yield test


def service(client: TestClient) -> BrokerService:
    return cast(BrokerService, cast(FastAPI, client.app).state.broker_service)


def configure(client: TestClient) -> str:
    result = client.post("/api/v1/brokers/accounts", json=CREDENTIALS, headers=HEADERS)
    assert result.status_code == 200, result.text
    return str(result.json()["id"])


def connect(client: TestClient, account_id: str) -> str:
    result = client.post(f"/api/v1/brokers/accounts/{account_id}/connect", json={}, headers=HEADERS)
    assert result.status_code == 200, result.text
    params = parse_qs(urlparse(str(result.json()["login_url"])).query)
    return parse_qs(params["redirect_params"][0])["state"][0]


def callback(client: TestClient, state: str, token: str | None = "request123") -> Any:
    return client.post(
        "/api/v1/brokers/callback", json={"state": state, "request_token": token}, headers=HEADERS
    )


def bound(client: TestClient) -> str:
    account_id = configure(client)
    result = callback(client, connect(client, account_id))
    assert result.status_code == 200, result.text
    return account_id


def test_full_readonly_journey_and_secret_containment(client: TestClient) -> None:
    account_id = bound(client)
    for kind in ("overview", "holdings", "positions", "orders", "funds", "instruments"):
        result = client.get(f"/api/v1/brokers/accounts/{account_id}/{kind}")
        assert result.status_code == 200, result.text
        assert result.json()["account"]["health"] == "healthy"
        assert result.headers["cache-control"] == "no-store"
        for secret in ("testapikey123", "testsecret123", "testtoken123", "MUST_NOT_LEAK"):
            assert secret not in result.text
    assert client.get(f"/api/v1/brokers/accounts/{account_id}/overview").json()["data"] == {
        "cash": "1000",
        "holdings_value": "2400",
        "positions": 1,
        "open_orders": 1,
    }
    position = client.get(f"/api/v1/brokers/accounts/{account_id}/positions").json()["data"][0]
    assert position["instrument"]["expiry"] == "2026-10-29"
    assert position["instrument"]["strike"] == "25000"
    assert (position["realized"], position["unrealized"], position["pnl"]) == ("10", "30", "40")
    closed = client.get(f"/api/v1/brokers/accounts/{account_id}/positions").json()["data"][1]
    assert closed["instrument"]["symbol"] == "HDFCBANK26OCT730PE"
    assert (closed["quantity"], closed["realized"], closed["unrealized"], closed["pnl"]) == (
        "0",
        "-1007.5",
        "0",
        "-1007.5",
    )
    with service(client).factory() as db:
        saved = db.scalar(select(BrokerSecret))
        assert (
            saved
            and "testsecret123" not in saved.ciphertext
            and "testtoken123" not in saved.ciphertext
        )
    disconnected = client.post(f"/api/v1/brokers/accounts/{account_id}/disconnect", headers=HEADERS)
    assert disconnected.json()["state"] == "disconnected"
    assert client.get(f"/api/v1/brokers/accounts/{account_id}/holdings").status_code == 409
    with service(client).factory() as db:
        saved = db.scalar(select(BrokerSecret))
        assert saved and service(client).secrets.open(saved.ciphertext).access_token is None


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_no_order_writes(client: TestClient, method: str) -> None:
    account_id = bound(client)
    assert (
        getattr(client, method)(
            f"/api/v1/brokers/accounts/{account_id}/orders", headers=HEADERS
        ).status_code
        == 405
    )


def test_ownership_session_binding_and_csrf(client: TestClient) -> None:
    account_id = configure(client)
    state = connect(client, account_id)
    assert (
        client.post(
            f"/api/v1/brokers/accounts/{account_id}/connect",
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    client.post(
        "/api/v1/auth/login",
        json={"username": "other", "password": "test-only-broker-password"},
        headers=HEADERS,
    )
    assert client.get("/api/v1/brokers/accounts").json() == []
    assert (
        client.post(
            f"/api/v1/brokers/accounts/{account_id}/disconnect", headers=HEADERS
        ).status_code
        == 404
    )
    assert callback(client, state).status_code == 409


def test_replay_cancel_expiration_and_generation(client: TestClient) -> None:
    account_id = configure(client)
    state = connect(client, account_id)
    assert callback(client, state, None).status_code == 409
    assert callback(client, state).status_code == 409
    old = connect(client, account_id)
    current = connect(client, account_id)
    assert callback(client, old).status_code == 409
    with service(client).factory() as db:
        attempt = db.scalar(
            select(BrokerAttempt)
            .where(BrokerAttempt.consumed_at.is_(None))
            .order_by(BrokerAttempt.expires_at.desc())
        )
        assert attempt
        attempt.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert callback(client, current).status_code == 409


def test_repeated_callback_concurrency_exactly_one_winner(client: TestClient) -> None:
    account_id = configure(client)
    for _ in range(8):
        state = connect(client, account_id)
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _, current=state: callback(client, current), range(4)))
        assert sorted(x.status_code for x in responses) == [200, 409, 409, 409]
        assert all("locked" not in x.text.lower() for x in responses)


class SlowStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> Any:
        for _ in range(100):
            await asyncio.sleep(0.015)
            yield b" "


def test_total_deadline_covers_slow_chunks_and_leaves_no_binding(client: TestClient) -> None:
    broker = service(client)
    broker.settings = broker.settings.model_copy(update={"broker_deadline_seconds": 0.07})
    broker.adapter = ZerodhaAdapter(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=SlowStream()))
    )
    account_id = configure(client)
    state = connect(client, account_id)
    started = time.monotonic()
    result = callback(client, state)
    assert result.status_code == 504 and result.json()["error"]["code"] == "PROVIDER_TIMEOUT"
    assert time.monotonic() - started < 1
    with broker.factory() as db:
        row = db.scalar(select(BrokerAccount))
        assert row and row.identity is None and row.state != "connected"
        secret = db.get(BrokerSecret, row.secret_id)
        assert secret and broker.secrets.open(secret.ciphertext).access_token is None


def test_disconnect_during_provider_read_rejects_result(client: TestClient) -> None:
    account_id = bound(client)

    async def delayed(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/portfolio/holdings":
            await asyncio.sleep(0.15)
        return provider(request)

    service(client).adapter = ZerodhaAdapter(transport=httpx.MockTransport(delayed))
    with ThreadPoolExecutor() as pool:
        reading = pool.submit(client.get, f"/api/v1/brokers/accounts/{account_id}/holdings")
        time.sleep(0.05)
        assert (
            client.post(
                f"/api/v1/brokers/accounts/{account_id}/disconnect", headers=HEADERS
            ).status_code
            == 200
        )
        assert reading.result().status_code == 409


@pytest.mark.parametrize("status", [401, 403, 429, 500, 302])
def test_sanitized_provider_failures(client: TestClient, status: int) -> None:
    account_id = bound(client)
    service(client).adapter = ZerodhaAdapter(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status, text="SECRET PRIVATE RESPONSE")
        )
    )
    result = client.get(f"/api/v1/brokers/accounts/{account_id}/holdings")
    assert result.status_code in (409, 502, 503)
    assert "SECRET" not in result.text
    account = client.get("/api/v1/brokers/accounts").json()[0]
    assert (
        account["state"] == "reauth_required"
        if status in (401, 403)
        else account["health"] == "degraded"
    )


def test_catalog_filters_stable_pagination_and_missing_values() -> None:
    adapter = ZerodhaAdapter(transport=httpx.MockTransport(provider))
    credentials = Credentials(api_key=SecretStr("key"), api_secret=SecretStr("secret"))

    async def exercise() -> None:
        first = await adapter.search_instruments(credentials, Search(limit=1))
        second = await adapter.search_instruments(credentials, Search(limit=1, page=2))
        assert first.total == 2 and first.items[0].reference != second.items[0].reference
        options = await adapter.search_instruments(
            credentials,
            Search(underlying="NIFTY", expiry="2026-10-29", strike=Decimal("25000"), kind="CE"),
        )
        assert len(options.items) == 1 and options.items[0].native_token == "2"
        adapter.transport = httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": [{"tradingsymbol": "UNKNOWN", "exchange": "BSE"}],
                },
            )
        )
        holding = (await adapter.get_holdings(credentials))[0]
        assert holding.quantity is None and holding.pnl is None and holding.value is None
        assert holding.instrument.symbol == "UNKNOWN"

    asyncio.run(exercise())


def test_secret_boundary_fails_closed() -> None:
    for settings in (
        Settings(),
        Settings(credential_master_key=SecretStr("invalid")),
    ):
        with pytest.raises(BrokerFailure, match="SECRET_STORE_UNAVAILABLE"):
            EncryptedSecretStore(settings).cipher()


def test_token_and_profile_must_match(client: TestClient) -> None:
    def mismatch(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/profile":
            return httpx.Response(
                200, json={"status": "success", "data": {"user_id": "OTHER", "broker": "ZERODHA"}}
            )
        return provider(request)

    service(client).adapter = ZerodhaAdapter(transport=httpx.MockTransport(mismatch))
    assert callback(client, connect(client, configure(client))).status_code == 409


def test_no_unauthenticated_broker_access(client: TestClient) -> None:
    client.cookies.clear()
    for path in ("accounts", "providers", "setup"):
        assert client.get("/api/v1/brokers/" + path).status_code == 401


def test_openapi_and_migration_roundtrip(client: TestClient) -> None:
    document = cast(FastAPI, client.app).openapi()
    assert "/api/v1/brokers/callback" in document["paths"]
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.downgrade(config, "0003_preferences")
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    assert client.get("/api/v1/brokers/accounts").json() == []


def test_same_user_new_login_cannot_complete_old_attempt(client: TestClient) -> None:
    account_id = configure(client)
    state = connect(client, account_id)
    client.post(
        "/api/v1/auth/login",
        json={"username": "trader", "password": "test-only-broker-password"},
        headers=HEADERS,
    )
    assert callback(client, state).status_code == 409


def test_bound_identity_cannot_be_replaced(client: TestClient) -> None:
    account_id = bound(client)

    def other_identity(request: httpx.Request) -> httpx.Response:
        result = provider(request)
        if request.url.path in ("/session/token", "/user/profile"):
            value = result.json()
            value["data"]["user_id"] = "OTHER"
            return httpx.Response(200, json=value)
        return result

    service(client).adapter = ZerodhaAdapter(transport=httpx.MockTransport(other_identity))
    result = callback(client, connect(client, account_id))
    assert result.status_code == 409
    assert client.get("/api/v1/brokers/accounts").json()[0]["identity"] == "AB1234"


def test_total_deadline_includes_profile_verification(client: TestClient) -> None:
    broker = service(client)
    broker.settings = broker.settings.model_copy(update={"broker_deadline_seconds": 0.08})

    async def delayed(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return provider(request)

    broker.adapter = ZerodhaAdapter(transport=httpx.MockTransport(delayed))
    result = callback(client, connect(client, configure(client)))
    assert result.status_code == 504
    assert client.get("/api/v1/brokers/accounts").json()[0]["identity"] is None


def test_total_deadline_includes_json_parsing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    broker = service(client)
    broker.settings = broker.settings.model_copy(update={"broker_deadline_seconds": 0.05})
    account_id = configure(client)
    state = connect(client, account_id)
    original = json.loads

    def slow_parse(value: str | bytes | bytearray, *args: Any, **kwargs: Any) -> Any:
        if isinstance(value, bytearray):
            time.sleep(0.15)
        return original(value, *args, **kwargs)

    monkeypatch.setattr(json, "loads", slow_parse)
    assert callback(client, state).status_code == 504
    assert client.get("/api/v1/brokers/accounts").json()[0]["identity"] is None


@pytest.mark.parametrize("body", [b"[]", b'{"status":"success"}', b"not-json", b" " * 4_000_001])
def test_invalid_or_oversized_provider_body_is_safe(client: TestClient, body: bytes) -> None:
    service(client).adapter = ZerodhaAdapter(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    )
    result = callback(client, connect(client, configure(client)))
    assert result.status_code == 502
    assert result.json()["error"]["code"] == "PROVIDER_RESPONSE_INVALID"


def test_disconnect_during_callback_never_binds(client: TestClient) -> None:
    async def delayed(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/profile":
            await asyncio.sleep(0.15)
        return provider(request)

    service(client).adapter = ZerodhaAdapter(transport=httpx.MockTransport(delayed))
    account_id = configure(client)
    state = connect(client, account_id)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(callback, client, state)
        time.sleep(0.05)
        assert (
            client.post(
                f"/api/v1/brokers/accounts/{account_id}/disconnect", headers=HEADERS
            ).status_code
            == 200
        )
        assert future.result().status_code == 409
    account = client.get("/api/v1/brokers/accounts").json()[0]
    assert account["state"] == "disconnected" and account["identity"] is None


def test_cached_catalog_does_not_hide_expired_provider_session(client: TestClient) -> None:
    account_id = bound(client)
    assert client.get(f"/api/v1/brokers/accounts/{account_id}/instruments").status_code == 200
    adapter = cast(ZerodhaAdapter, service(client).adapter)
    adapter.transport = httpx.MockTransport(
        lambda _: httpx.Response(403, text="private provider error")
    )
    assert client.get(f"/api/v1/brokers/accounts/{account_id}/instruments").status_code == 409


def test_rejection_bookkeeping_contention_preserves_original_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    broker = service(client)
    account_id = configure(client)
    state = connect(client, account_id)
    original = broker.write

    async def sometimes_locked(operation: Any) -> Any:
        if operation.__name__ == "mark":
            raise BrokerFailure("BROKER_STATE_CONFLICT", "safe rejection", 409)
        return await original(operation)

    monkeypatch.setattr(broker, "write", sometimes_locked)
    result = callback(client, state, None)
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "BROKER_LOGIN_CANCELLED"
