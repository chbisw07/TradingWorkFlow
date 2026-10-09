from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from twf.auth import create_user
from twf.config.settings import Settings
from twf.discovery.internal_scanner.market_series import MarketSeries
from twf.discovery.market_data import (
    DhanMarketDataProvider,
    MarketDataErrorCode,
    MarketDataFailure,
    QuoteSnapshot,
)
from twf.discovery.product_service import identity, market_series
from twf.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from twf.infrastructure.dhan import DhanMarketDataConnection, DhanMarketDataSecret
from twf.main import create_app

ORIGIN = "https://web.example"
HEADERS = {"Origin": ORIGIN}
PASSWORD = "test-only-dhan-password"
BASE = "/api/v1/settings/market-data/dhan"
CLIENT_ID = "1100000001"
TOKEN = "dhan-test-access-token-value"


class FakeDhanProvider:
    capabilities = DhanMarketDataProvider.capabilities

    def __init__(self, failure: MarketDataErrorCode | None = None) -> None:
        self.failure = failure

    async def health(self) -> Any:
        raise AssertionError("health is not the credential proof")

    async def resolve_instruments(self, symbols: tuple[str, ...]) -> tuple[Any, ...]:
        if self.failure is not None:
            raise MarketDataFailure(self.failure)
        return tuple(identity(symbol) for symbol in symbols)

    async def get_quotes(self, instruments: tuple[Any, ...]) -> tuple[QuoteSnapshot, ...]:
        if self.failure is not None:
            raise MarketDataFailure(self.failure)
        return tuple(
            QuoteSnapshot(
                instrument=item,
                last_price=Decimal("2500"),
                received_at=datetime.now().astimezone(),
                provider="dhan",
            )
            for item in instruments
        )

    async def get_ohlcv(
        self,
        instrument: Any,
        interval: str,
        *,
        as_of: datetime,
        count: int,
    ) -> MarketSeries:
        if self.failure is not None:
            raise MarketDataFailure(self.failure)
        assert interval == "1d" and count == 320
        return market_series(instrument, as_of, 0)

    async def read(self, context: Any, instrument: Any, interval: str) -> MarketSeries:
        return await self.get_ohlcv(instrument, interval, as_of=context.as_of, count=320)


@pytest.fixture
def dhan_client() -> Iterator[TestClient]:
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    settings = Settings(
        cors_origins=(ORIGIN,),
        credential_master_key=SecretStr(Fernet.generate_key().decode()),
    )
    engine = create_database_engine(settings)
    with session_scope(create_session_factory(engine)) as session:
        create_user(session, "alice", "Alice", PASSWORD)
        create_user(session, "bob", "Bob", PASSWORD)
        session.commit()
    app = create_app(settings, engine_factory=lambda _: engine)
    with TestClient(app) as client:
        app.state.dhan_credentials.provider_factory = lambda _: FakeDhanProvider()
        yield client


def login(client: TestClient, username: str = "alice") -> UUID:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PASSWORD},
        headers=HEADERS,
    )
    assert response.status_code == 200
    return UUID(response.json()["id"])


def configure(client: TestClient, generation: int = 0, token: str = TOKEN) -> dict[str, Any]:
    response = client.put(
        BASE + "/credentials",
        headers=HEADERS,
        json={
            "generation": generation,
            "client_id": CLIENT_ID,
            "access_token": token,
        },
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def test_credentials_are_encrypted_masked_replaceable_and_owner_scoped(
    dhan_client: TestClient,
) -> None:
    owner_id = login(dhan_client)
    assert dhan_client.get(BASE).json()["state"] == "NOT_CONFIGURED"

    saved = configure(dhan_client)
    assert saved == {
        "state": "CONFIGURED",
        "configured": True,
        "enabled": True,
        "generation": 1,
        "source": "DATABASE",
        "checked_at": None,
        "last_error": None,
    }
    assert CLIENT_ID not in dhan_client.get(BASE).text
    assert TOKEN not in dhan_client.get(BASE).text

    app = dhan_client.app
    assert isinstance(app, FastAPI)
    with session_scope(app.state.session_factory) as session:
        row = session.get(DhanMarketDataConnection, owner_id)
        assert row is not None and row.secret_id is not None
        secret = session.get(DhanMarketDataSecret, row.secret_id)
        assert secret is not None
        assert CLIENT_ID not in secret.ciphertext
        assert TOKEN not in secret.ciphertext

    replacement = configure(dhan_client, 1, "replacement-dhan-access-token")
    assert replacement["generation"] == 2
    with session_scope(app.state.session_factory) as session:
        assert session.scalar(select(func.count()).select_from(DhanMarketDataSecret)) == 1

    login(dhan_client, "bob")
    other = dhan_client.get(BASE).json()
    assert other["state"] == "NOT_CONFIGURED"
    assert other["configured"] is False

    login(dhan_client, "alice")
    disconnected = dhan_client.post(BASE + "/disconnect", headers=HEADERS, json={"generation": 2})
    assert disconnected.status_code == 200
    assert disconnected.json()["state"] == "DISABLED"
    with session_scope(app.state.session_factory) as session:
        assert session.scalar(select(func.count()).select_from(DhanMarketDataSecret)) == 0


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (MarketDataErrorCode.AUTH_REQUIRED, "AUTH_FAILED"),
        (MarketDataErrorCode.RATE_LIMITED, "RATE_LIMITED"),
        (MarketDataErrorCode.TIMEOUT, "PROVIDER_ERROR"),
        (MarketDataErrorCode.PROVIDER_ERROR, "PROVIDER_ERROR"),
    ],
)
def test_connection_failure_states_are_sanitized(
    dhan_client: TestClient,
    failure: MarketDataErrorCode,
    expected: str,
) -> None:
    login(dhan_client)
    configure(dhan_client)
    app = dhan_client.app
    assert isinstance(app, FastAPI)
    app.state.dhan_credentials._drop_cached(UUID(dhan_client.get("/api/v1/auth/me").json()["id"]))
    app.state.dhan_credentials.provider_factory = lambda _: FakeDhanProvider(failure)

    response = dhan_client.post(BASE + "/test", headers=HEADERS, json={"generation": 1})
    assert response.status_code == 200
    assert response.json()["state"] == expected
    assert TOKEN not in response.text
    assert CLIENT_ID not in response.text


def test_successful_test_enables_real_scan_without_synthetic_fallback(
    dhan_client: TestClient,
) -> None:
    login(dhan_client)
    configure(dhan_client)
    payload = {
        "universe": ["RELIANCE"],
        "provider": "real",
        "profile": "RELATIVE_VOLUME",
        "horizon": "5d",
        "intent": "MOMENTUM",
        "include_llm": False,
        "context_mode": "partial",
    }
    refused = dhan_client.post("/api/v1/discovery/scans", headers=HEADERS, json=payload)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "DHAN_NOT_READY"

    tested = dhan_client.post(BASE + "/test", headers=HEADERS, json={"generation": 1})
    assert tested.status_code == 200
    assert tested.json()["state"] == "READY"
    statuses = dhan_client.get("/api/v1/discovery/status").json()
    dhan = next(item for item in statuses if item["id"] == "dhan")
    assert dhan["enabled"] is True and dhan["health"] == "AVAILABLE"

    scan = dhan_client.post("/api/v1/discovery/scans", headers=HEADERS, json=payload)
    assert scan.status_code == 201, scan.text
    assert scan.json()["summary"]["provider"] == "real"


def test_stale_generation_and_validation_never_echo_secrets(
    dhan_client: TestClient,
) -> None:
    login(dhan_client)
    configure(dhan_client)
    stale = dhan_client.put(
        BASE + "/credentials",
        headers=HEADERS,
        json={
            "generation": 0,
            "client_id": CLIENT_ID,
            "access_token": "never-echo-this-token",
        },
    )
    assert stale.status_code == 409
    assert "never-echo-this-token" not in stale.text

    invalid = dhan_client.put(
        BASE + "/credentials",
        headers=HEADERS,
        json={
            "generation": 1,
            "client_id": CLIENT_ID,
            "access_token": "short",
        },
    )
    assert invalid.status_code == 422
    assert "short" not in invalid.text
