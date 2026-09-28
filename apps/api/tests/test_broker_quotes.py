"""Quotes use mock HTTP, exact identities and isolated databases, never live credentials."""

import asyncio
import time
from collections.abc import AsyncIterator
from typing import cast

import httpx
import pytest
from fastapi.testclient import TestClient
from order_provider_fixture import OrderProvider
from sqlalchemy import func, select
from test_broker_orders import orders as orders
from test_broker_v1 import HEADERS, service
from test_broker_v1 import client as client

from twf.brokers.zerodha import ZerodhaAdapter
from twf.infrastructure.order_intent import OrderIntent


def identities() -> dict[str, object]:
    return {
        "instruments": [
            {"reference": "ZERODHA:NSE:RELIANCE", "native_token": "11"},
            {"reference": "ZERODHA:NFO:RELIANCEFUT1", "native_token": "22"},
            {"reference": "ZERODHA:NFO:RELIANCECE1", "native_token": "23"},
        ]
    }


def test_batched_exact_quotes_ephemeral_and_sanitized(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, provider = orders
    before = client.get("/api/v1/brokers/accounts").json()
    response = client.post(base + "/quotes", json=identities(), headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["received_at"] and len(body["quotes"]) == 3
    assert {q["native_token"]: q["price"] for q in body["quotes"]} == {
        "11": "111.05",
        "22": "122.05",
        "23": "123.05",
    }
    assert len(provider.quote_calls) == 1
    assert set(provider.quote_calls[0]) == {"NSE:RELIANCE", "NFO:RELIANCEFUT1", "NFO:RELIANCECE1"}
    assert all(
        secret not in response.text for secret in ("testtoken123", "testapikey123", "MUST_NOT_LEAK")
    )
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get("/api/v1/brokers/accounts").json() == before
    with service(client).factory() as db:
        assert db.scalar(select(func.count()).select_from(OrderIntent)) == 0
    assert not provider.calls


@pytest.mark.parametrize("value", [None, 0, -1, "NaN", "Infinity", True, ""])
def test_absent_or_invalid_quotes_are_unknown(
    client: TestClient, orders: tuple[str, OrderProvider], value: object
) -> None:
    base, provider = orders
    adapter = cast(ZerodhaAdapter, service(client).adapter)

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/quote/ltp":
            return provider(request)
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {}
                if value is None
                else {"NSE:RELIANCE": {"instrument_token": 11, "last_price": value}},
            },
        )

    adapter.transport = httpx.MockTransport(transport)
    response = client.post(base + "/quotes", json=identities(), headers=HEADERS)
    assert response.status_code == 200, response.text
    assert all(q["price"] is None for q in response.json()["quotes"])


def test_identity_validation_and_bounded_request(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, provider = orders
    for items in (
        [],
        [{"reference": "ZERODHA:NSE:RELIANCE", "native_token": "999"}],
        [{"reference": "ZERODHA:NSE:RELIANCE", "native_token": "11"}] * 31,
    ):
        assert (
            client.post(base + "/quotes", json={"instruments": items}, headers=HEADERS).status_code
            == 422
        )
    assert not provider.quote_calls
    adapter = cast(ZerodhaAdapter, service(client).adapter)
    adapter.transport = httpx.MockTransport(
        lambda r: (
            httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {"NSE:RELIANCE": {"instrument_token": 999, "last_price": 100}},
                },
            )
            if r.url.path == "/quote/ltp"
            else provider(r)
        )
    )
    response = client.post(base + "/quotes", json=identities(), headers=HEADERS)
    assert response.status_code == 502
    assert "PROVIDER_RESPONSE_INVALID" in response.text


def test_quote_security_and_rate_admission(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, provider = orders
    assert (
        client.post(
            base + "/quotes", json=identities(), headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.post(base + "/quotes", json=identities(), headers=HEADERS).status_code == 200
    assert client.post(base + "/quotes", json=identities(), headers=HEADERS).status_code == 503
    assert len(provider.quote_calls) == 1
    client.post("/api/v1/auth/logout", headers=HEADERS)
    assert client.post(base + "/quotes", json=identities(), headers=HEADERS).status_code == 401
    client.post(
        "/api/v1/auth/login",
        json={"username": "other", "password": "test-only-broker-password"},
        headers=HEADERS,
    )
    assert client.post(base + "/quotes", json=identities(), headers=HEADERS).status_code == 404


@pytest.mark.parametrize("status", [403, 429, 500])
def test_quote_failures_are_safe(
    client: TestClient, orders: tuple[str, OrderProvider], status: int
) -> None:
    base, provider = orders
    adapter = cast(ZerodhaAdapter, service(client).adapter)
    adapter.transport = httpx.MockTransport(
        lambda r: (
            httpx.Response(status, text="MUST_NOT_LEAK_testtoken123")
            if r.url.path == "/quote/ltp"
            else provider(r)
        )
    )
    response = client.post(base + "/quotes", json=identities(), headers=HEADERS)
    assert response.status_code in (409, 502, 503)
    assert "MUST_NOT_LEAK" not in response.text and "testtoken123" not in response.text
    if status == 429:
        assert max(adapter.quote_next.values()) - time.monotonic() > 9


def test_quote_stream_obeys_total_deadline(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, provider = orders
    broker = service(client)
    broker.settings = broker.settings.model_copy(update={"broker_deadline_seconds": 0.05})

    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            for _ in range(100):
                await asyncio.sleep(0.02)
                yield b" "

    adapter = cast(ZerodhaAdapter, broker.adapter)
    adapter.transport = httpx.MockTransport(
        lambda r: httpx.Response(200, stream=Slow()) if r.url.path == "/quote/ltp" else provider(r)
    )
    started = time.monotonic()
    response = client.post(base + "/quotes", json=identities(), headers=HEADERS)
    assert response.status_code == 504 and "PROVIDER_TIMEOUT" in response.text
    assert time.monotonic() - started < 0.5
    assert not provider.calls


def test_reconnected_account_rejects_inflight_quotes(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    from uuid import UUID

    from twf.infrastructure.broker import BrokerAccount

    base, provider = orders
    broker = service(client)
    adapter = cast(ZerodhaAdapter, broker.adapter)

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/quote/ltp":
            with broker.factory() as db:
                account = db.get(BrokerAccount, UUID(base.split("/")[-2]))
                assert account
                account.generation += 1
                db.commit()
        return provider(request)

    adapter.transport = httpx.MockTransport(transport)
    response = client.post(base + "/quotes", json=identities(), headers=HEADERS)
    assert response.status_code == 409
    assert "BROKER_STATE_CONFLICT" in response.text
    assert "111.05" not in response.text
