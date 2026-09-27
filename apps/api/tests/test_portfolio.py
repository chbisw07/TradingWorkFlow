"""BW-2.4 deterministic reads; no real broker calls or developer databases."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import monotonic
from typing import cast
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_broker_auth import HEADERS, account, login
from test_catalog import CatalogFixture, refresh
from test_catalog import browser as browser
from test_catalog import catalog as catalog
from test_catalog import database as database

from twf.brokers.foundation_contracts import BrokerPermission, PersonalBrokerPermissionPolicy
from twf.brokers.portfolio_contracts import (
    DatasetName,
    PortfolioFailure,
    ProviderObservation,
    ReadFailureCode,
)
from twf.brokers.zerodha_portfolio import KitePortfolioClient
from twf.infrastructure.broker_auth import BrokerSecretLifecycle
from twf.infrastructure.broker_foundation import BrokerAccountRecord, BrokerConnectionRecord
from twf.infrastructure.catalog import CatalogPointer
from twf.secrets import SecretValue

HOLDING = dict(
    instrument_token=1,
    tradingsymbol="HAL",
    exchange="NSE",
    product="CNC",
    quantity=5,
    used_quantity=1,
    average_price=100,
    last_price=110,
    pnl=50,
    close_price=108,
    t1_quantity=2,
    collateral_quantity=1,
    day_change=2,
    day_change_percentage=1.85,
)
POSITION = dict(
    instrument_token=3,
    tradingsymbol="HAL26OCT4500CE",
    exchange="NFO",
    product="NRML",
    quantity=150,
    average_price=10,
    last_price=12,
    pnl=300,
    realised=0,
    unrealised=300,
    buy_quantity=150,
    sell_quantity=0,
    buy_price=10,
    sell_price=0,
    overnight_quantity=150,
    multiplier=1,
)


def payload(dataset: DatasetName, rows: list[object]) -> bytes:
    return json.dumps(
        {
            "status": "success",
            "data": rows
            if dataset == "holdings"
            else {"net": rows, "day": [{**POSITION, "quantity": 0, "pnl": 999}]},
        }
    ).encode()


class FixtureProvider:
    def __init__(self) -> None:
        self.rows: dict[DatasetName, list[object]] = {
            "holdings": [HOLDING],
            "positions": [POSITION],
        }
        self.fail: dict[DatasetName, ReadFailureCode] = {}
        self.calls: list[DatasetName] = []

    def read(self, dataset: DatasetName, api_key: str, token: SecretValue) -> ProviderObservation:
        assert api_key == "appkey" and token.reveal() == "raw-access-token"
        self.calls.append(dataset)
        if code := self.fail.get(dataset):
            raise PortfolioFailure(code)
        return KitePortfolioClient().parse(
            payload(dataset, self.rows[dataset]), dataset, monotonic() + 2
        )


def endpoint(aid: str) -> str:
    return f"/api/v1/broker-portfolio/accounts/{aid}"


def setup(
    catalog: tuple[TestClient, str, CatalogFixture],
) -> tuple[TestClient, str, FixtureProvider, FastAPI]:
    client, aid, _ = catalog
    app = cast(FastAPI, client.app)
    provider = FixtureProvider()
    app.state.portfolio_provider = provider
    return client, aid, provider, app


def test_complete_native_reads_and_dashboard_consistency(
    catalog: tuple[TestClient, str, CatalogFixture],
) -> None:
    client, aid, provider, _ = setup(catalog)
    version = refresh(client, aid)["version"]
    response = client.get(endpoint(aid))
    assert response.status_code == 200
    data = response.json()
    assert data["contract_version"] == "broker.native-read.v1"
    assert (
        data["trading_enabled"] is False
        and not data["orders_available"]
        and not data["funds_available"]
    )
    assert response.headers["cache-control"] == "no-store"
    assert provider.calls == ["holdings", "positions"]
    h = data["holdings"]["rows"][0]
    p = data["positions"]["rows"][0]
    assert (h["current_value"], h["available_quantity"], h["unsettled_quantity"]) == (
        "550",
        "4",
        "2",
    )
    assert Decimal(h["pnl_percent"]) == 10
    i = p["instrument"]
    assert i["catalog_version"] == version and i["derivative_kind"] == "CE"
    assert i["expiry"] == "2026-10-29" and Decimal(i["strike"]) == 4500 and i["lot_size"] == 150
    assert i["catalog_fingerprint"] and i["instrument_fingerprint"] and i["canonical_id"] is None
    assert data["summary"] == dict(
        holdings_count=1,
        holdings_value="550",
        open_positions_count=1,
        realized_pnl="0",
        unrealized_pnl="300",
        position_pnl="300",
    )
    assert data["positions"]["activity_rows"][0]["pnl"] == "999"
    for name in ("holdings", "positions"):
        meta = data[name]["metadata"]
        assert meta["completeness"] == "COMPLETE" and meta["health"] == "AVAILABLE"
        assert (
            meta["source_as_of"] is None
            and meta["connection_generation"] == 1
            and meta["received_at"]
        )


@pytest.mark.parametrize("dataset", ["holdings", "positions"])
def test_empty_and_missing_optional_values(
    catalog: tuple[TestClient, str, CatalogFixture], dataset: DatasetName
) -> None:
    client, aid, provider, _ = setup(catalog)
    provider.rows[dataset] = []
    data = client.get(endpoint(aid)).json()
    assert data[dataset]["rows"] == []
    assert data[dataset]["metadata"]["completeness"] == "COMPLETE"
    provider.rows[dataset] = [
        dict(
            instrument_token=9,
            tradingsymbol="UNKNOWN",
            exchange="NSE",
            product="FUTURE_PRODUCT",
            quantity=1,
        )
    ]
    data = client.get(endpoint(aid)).json()
    row = data[dataset]["rows"][0]
    assert row["last_price"] is None and row["pnl"] is None and row["average_price"] is None
    assert not row["product_known"] and row["product"] == "FUTURE_PRODUCT"
    assert (
        row["instrument"]["native_id"] == "9"
        and row["instrument"]["catalog_state"] == "UNAVAILABLE"
    )
    assert data["summary"]["holdings_value" if dataset == "holdings" else "unrealized_pnl"] is None


@pytest.mark.parametrize(
    "code",
    ["AUTH_EXPIRED", "TIMEOUT", "RATE_LIMITED", "UNAVAILABLE", "INVALID_RESPONSE", "TOO_LARGE"],
)
@pytest.mark.parametrize("dataset", ["holdings", "positions"])
def test_failure_isolation(
    catalog: tuple[TestClient, str, CatalogFixture], code: ReadFailureCode, dataset: DatasetName
) -> None:
    client, aid, provider, _ = setup(catalog)
    provider.fail[dataset] = code
    data = client.get(endpoint(aid)).json()
    assert data[dataset]["rows"] is None
    assert data[dataset]["metadata"]["received_at"] is None
    assert data[dataset]["metadata"]["attempted_at"]
    assert (
        data[dataset]["metadata"]["failure_code"] == code
        and data[dataset]["metadata"]["completeness"] == "MISSING"
    )
    other = "holdings" if dataset == "positions" else "positions"
    assert len(data[other]["rows"]) == 1
    assert client.get("/ready").status_code == 200
    if code == "AUTH_EXPIRED":
        assert data["connection_state"] == "REAUTH_REQUIRED"


@pytest.mark.parametrize("dataset", ["holdings", "positions"])
def test_partial_rows_never_make_complete_totals(
    catalog: tuple[TestClient, str, CatalogFixture], dataset: DatasetName
) -> None:
    client, aid, provider, _ = setup(catalog)
    provider.rows[dataset].append({"quantity": 7})
    data = client.get(endpoint(aid)).json()
    assert len(data[dataset]["rows"]) == 1
    assert (
        data[dataset]["metadata"]["rejected_rows"] == 1
        and data[dataset]["metadata"]["completeness"] == "PARTIAL"
    )
    assert data["summary"]["holdings_value" if dataset == "holdings" else "position_pnl"] is None


def test_catalog_staleness_and_token_reuse_do_not_retarget(
    catalog: tuple[TestClient, str, CatalogFixture],
) -> None:
    client, aid, provider, app = setup(catalog)
    refresh(client, aid)
    with app.state.session_factory() as session:
        pointer = session.get(CatalogPointer, UUID(aid))
        pointer.verified_at = datetime.now(UTC) - timedelta(days=3)
        session.commit()
    data = client.get(endpoint(aid)).json()
    assert data["positions"]["rows"][0]["instrument"]["catalog_state"] == "STALE"
    provider.rows["positions"] = [{**POSITION, "tradingsymbol": "DIFFERENT_CONTRACT"}]
    row = client.get(endpoint(aid)).json()["positions"]["rows"][0]
    assert (
        row["instrument"]["symbol"] == "DIFFERENT_CONTRACT"
        and row["instrument"]["catalog_state"] == "UNMAPPED"
    )
    assert (
        row["instrument"]["derivative_kind"] is None
        and row["instrument"]["catalog_version"] is None
    )


@pytest.mark.parametrize("mode", ["expired", "stale_secret", "disabled"])
def test_current_authority_before_provider_use(
    catalog: tuple[TestClient, str, CatalogFixture], mode: str
) -> None:
    client, aid, provider, app = setup(catalog)
    with app.state.session_factory() as session:
        connection = session.get(BrokerConnectionRecord, UUID(aid))
        if mode == "expired":
            connection.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif mode == "disabled":
            session.get(BrokerAccountRecord, UUID(aid)).enabled = False
        else:
            session.get(BrokerSecretLifecycle, connection.secret_reference).generation += 1
        session.commit()
    response = client.get(endpoint(aid))
    assert not provider.calls
    if mode == "stale_secret":
        assert response.status_code == 409
    else:
        assert response.json()["holdings"]["metadata"]["failure_code"] == (
            "AUTH_EXPIRED" if mode == "expired" else "AUTH_REQUIRED"
        )


def test_disconnect_during_read_discards_both_datasets(
    catalog: tuple[TestClient, str, CatalogFixture],
) -> None:
    client, aid, provider, app = setup(catalog)

    class Disconnect:
        def read(
            self, dataset: DatasetName, api_key: str, token: SecretValue
        ) -> ProviderObservation:
            assert (
                client.post(
                    f"/api/v1/broker-auth/accounts/{aid}/disconnect",
                    headers=HEADERS,
                    json={"expected_generation": 1},
                ).status_code
                == 200
            )
            return provider.read(dataset, api_key, token)

    app.state.portfolio_provider = Disconnect()
    response = client.get(endpoint(aid))
    assert response.status_code == 409 and "holdings" not in response.json()
    assert provider.calls == ["holdings"]


def test_owner_permission_and_unsupported_methods(
    catalog: tuple[TestClient, str, CatalogFixture],
) -> None:
    client, aid, provider, app = setup(catalog)
    assert client.post(endpoint(aid)).status_code == 405

    class Deny(PersonalBrokerPermissionPolicy):
        def allows(
            self, actor_user_id: UUID, permission: BrokerPermission, owner_user_id: UUID
        ) -> bool:
            return False

    app.state.broker_permission_policy = Deny()
    assert client.get(endpoint(aid)).status_code == 403
    app.state.broker_permission_policy = PersonalBrokerPermissionPolicy()
    login(client, "bob")
    assert client.get(endpoint(aid)).status_code == 404
    own = account(client, "Bob")
    assert client.get(endpoint(own)).json()["holdings"]["rows"] is None
    client.cookies.clear()
    assert client.get(endpoint(aid)).status_code == 401
    assert not provider.calls


class Stream(httpx.AsyncByteStream):
    def __init__(self, body: bytes, delay: float = 0):
        self.body, self.delay, self.closed = body, delay, False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for start in range(0, len(self.body), 16):
            await asyncio.sleep(self.delay)
            yield self.body[start : start + 16]

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    "status,code",
    [(403, "AUTH_EXPIRED"), (429, "RATE_LIMITED"), (500, "UNAVAILABLE"), (302, "UNAVAILABLE")],
)
def test_http_errors_and_fixed_read_transport(status: int, code: ReadFailureCode) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert (
            request.method == "GET"
            and str(request.url) == "https://api.kite.trade/portfolio/holdings"
        )
        assert request.headers["authorization"] == "token app:token"
        return httpx.Response(status, stream=Stream(b"private error"))

    with pytest.raises(PortfolioFailure) as error:
        KitePortfolioClient(httpx.MockTransport(handler)).read(
            "holdings", "app", SecretValue("token")
        )
    assert error.value.code == code and "private" not in str(error.value)


@pytest.mark.parametrize(
    "case", ["slow", "size", "rows", "malformed", "encoding", "parse_timeout", "success"]
)
def test_transport_and_total_bounds(case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    stream = Stream(payload("holdings", [HOLDING]), 0.02 if case == "slow" else 0)
    if case == "malformed":
        stream.body = b"not json"
    client = KitePortfolioClient(
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                stream=stream,
                headers={"Content-Encoding": "gzip" if case == "encoding" else "identity"},
            )
        )
    )
    if case == "slow":
        client.TOTAL_DEADLINE_SECONDS = 0.05
    if case == "size":
        client.MAX_BYTES = 16
    if case == "rows":
        client.MAX_ROWS = 0
    if case == "parse_timeout":
        original = client.parse
        monkeypatch.setattr(
            client,
            "parse",
            lambda body, dataset, deadline: original(body, dataset, monotonic() - 1),
        )
    started = monotonic()
    if case == "success":
        assert len(client.read("holdings", "app", SecretValue("token")).rows) == 1
    else:
        with pytest.raises(PortfolioFailure) as failure:
            client.read("holdings", "app", SecretValue("token"))
        assert failure.value.code == (
            "TIMEOUT"
            if case in ("slow", "parse_timeout")
            else "TOO_LARGE"
            if case in ("size", "rows")
            else "INVALID_RESPONSE"
        )
    assert monotonic() - started < 1 and stream.closed


@pytest.mark.parametrize("value", [True, "2", None, float("nan")])
def test_invalid_quantity_is_partial_not_zero(value: object) -> None:
    result = KitePortfolioClient().parse(
        payload("holdings", [{**HOLDING, "quantity": value}]), "holdings", monotonic() + 2
    )
    assert result.rejected_rows == 1 and not result.rows


def test_equity_short_positions_and_zero_prices_remain_observations(
    catalog: tuple[TestClient, str, CatalogFixture],
) -> None:
    client, aid, provider, _ = setup(catalog)
    provider.rows["positions"] = [
        {
            **HOLDING,
            "product": "MIS",
            "quantity": -2,
            "pnl": -5,
            "realised": 0,
            "unrealised": -5,
            "last_price": 0,
        }
    ]
    data = client.get(endpoint(aid)).json()
    row = data["positions"]["rows"][0]
    assert row["quantity"] == "-2" and row["last_price"] == "0" and row["pnl"] == "-5"
    assert row["instrument"]["symbol"] == "HAL" and row["instrument"]["derivative_kind"] is None
    assert data["summary"]["open_positions_count"] == 1
    assert data["summary"]["position_pnl"] == "-5"


@pytest.mark.parametrize("data", [{"net": []}, {"net": {}, "day": []}, [], None])
def test_malformed_position_groups_are_missing_not_empty(data: object) -> None:
    with pytest.raises(PortfolioFailure) as failure:
        KitePortfolioClient().parse(
            json.dumps({"status": "success", "data": data}).encode(), "positions", monotonic() + 1
        )
    assert failure.value.code == "INVALID_RESPONSE"


def test_disconnect_during_second_read_also_discards_completed_holdings(
    catalog: tuple[TestClient, str, CatalogFixture],
) -> None:
    client, aid, provider, app = setup(catalog)

    class Disconnect:
        def read(
            self, dataset: DatasetName, api_key: str, token: SecretValue
        ) -> ProviderObservation:
            result = provider.read(dataset, api_key, token)
            if dataset == "positions":
                assert (
                    client.post(
                        f"/api/v1/broker-auth/accounts/{aid}/disconnect",
                        headers=HEADERS,
                        json={"expected_generation": 1},
                    ).status_code
                    == 200
                )
            return result

    app.state.portfolio_provider = Disconnect()
    response = client.get(endpoint(aid))
    assert response.status_code == 409 and "holdings" not in response.json()
    assert provider.calls == ["holdings", "positions"]


@pytest.mark.parametrize(
    "value", ["NaN", "Infinity", "1e19", "1e999999999", "1e-999999999", "1e-13"]
)
def test_extreme_price_precision_is_partial_not_an_arithmetic_error(value: str) -> None:
    result = KitePortfolioClient().parse(
        payload("holdings", [{**HOLDING, "average_price": value}]), "holdings", monotonic() + 2
    )
    assert result.rejected_rows == 1 and not result.rows
