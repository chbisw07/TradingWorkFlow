"""Manual order regression: actual migrations/routes/crypto/transport; no external network."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from order_provider_fixture import EXPIRIES, OrderProvider
from test_broker_v1 import HEADERS, bound, service
from test_broker_v1 import client as client

from twf.brokers.zerodha import ZerodhaAdapter
from twf.infrastructure.order_intent import OrderIntent


@pytest.fixture
def orders(client: TestClient) -> tuple[str, OrderProvider]:
    broker = service(client)
    broker.settings = broker.settings.model_copy(update={"broker_manual_trading_enabled": True})
    provider = OrderProvider()
    broker.adapter = ZerodhaAdapter(transport=httpx.MockTransport(provider))
    return f"/api/v1/brokers/accounts/{bound(client)}/order-entry", provider


def draft(symbol: str = "HAL", token: str = "1", **changes: Any) -> dict[str, Any]:
    derivative = symbol != "HAL"
    return {
        "reference": f"ZERODHA:{'NFO' if derivative else 'NSE'}:{symbol}",
        "native_token": token,
        "side": "BUY",
        "product": "NRML" if derivative else "CNC",
        "order_type": "LIMIT",
        "quantity": 130 if derivative else 2,
        "lots": 2 if derivative else None,
        "price": "100.05",
        "trigger_price": None,
        "validity": "DAY",
        **changes,
    }


def preview(client: TestClient, base: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    r = client.post(base + "/preview", json=payload or draft(), headers=HEADERS)
    assert r.status_code == 200, r.text
    return cast(dict[str, Any], r.json())


@pytest.mark.parametrize(
    "symbol,token,side",
    [
        ("HAL", "1", "BUY"),
        ("HAL", "1", "SELL"),
        ("NIFTYFUT1", "4", "BUY"),
        ("NIFTYFUT1", "4", "SELL"),
        ("NIFTYCE1", "5", "BUY"),
        ("NIFTYPE1", "6", "SELL"),
    ],
)
def test_preview_confirm_mapping_and_broker_truth(
    client: TestClient, orders: tuple[str, OrderProvider], symbol: str, token: str, side: str
) -> None:
    base, provider = orders
    intent = preview(client, base, draft(symbol, token, side=side))
    assert intent["status"] == "PREVIEWED" and not provider.calls
    assert intent["available_cash"] == "1000" and intent["estimated_margin"] == "75"
    assert intent["source"] == "BROKER_WORKSPACE" and intent["execution_authority"] == "MANUAL_USER"
    path = base + f"/intents/{intent['id']}"
    response = client.post(path + "/confirm", json={}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "SUBMITTED"
    fields = provider.calls[0]
    assert fields["tradingsymbol"] == symbol and fields["transaction_type"] == side
    assert fields["quantity"] == str(intent["order"]["quantity"])
    assert fields["exchange"] == intent["instrument"]["exchange"]
    assert fields["product"] == intent["order"]["product"]
    assert fields["price"] == "100.05" and len(fields["tag"]) == 20 and fields["tag"].isalnum()
    assert set(fields) == {
        "tradingsymbol",
        "exchange",
        "transaction_type",
        "quantity",
        "product",
        "order_type",
        "price",
        "validity",
        "tag",
    }
    for _ in range(3):
        assert (
            client.post(path + "/confirm", json={}, headers=HEADERS).json()["broker_order_id"]
            == response.json()["broker_order_id"]
        )
    assert len(provider.calls) == 1
    checked = client.post(path + "/reconcile", json={}, headers=HEADERS).json()
    assert checked["provider_status"] == "OPEN"
    provider.books[next(iter(provider.books))][-1]["status"] = "REJECTED"
    checked = client.post(path + "/reconcile", json={}, headers=HEADERS).json()
    assert checked["provider_status"] == "REJECTED"  # acknowledgement never implies execution
    assert len(client.get(base + "/intents").json()) == 1
    with service(client).factory() as db:
        saved = db.get(OrderIntent, UUID(intent["id"]))
        assert saved and saved.broker_order_id == response.json()["broker_order_id"]


def test_catalog_only_dependent_choices(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, _ = orders

    def get(**q: str) -> Any:
        return client.get(base + "/choices", params=q).json()

    assert get(asset="futures")["underlyings"] == ["NIFTY", "RELIANCE"]
    assert get(asset="futures", underlying="NIFTY")["expiries"] == EXPIRIES
    assert (
        get(asset="futures", underlying="NIFTY", expiry=EXPIRIES[0])["instruments"][0]["symbol"]
        == "NIFTYFUT1"
    )
    q = {"asset": "options", "underlying": "NIFTY", "expiry": EXPIRIES[0]}
    assert get(**q)["option_types"] == ["CE", "PE"]
    assert get(**q, option_type="CE")["strikes"] == ["25000"]
    assert get(**q, option_type="CE", strike="25500")["instruments"] == []
    assert get(**q, option_type="PE", strike="25000")["instruments"][0]["native_token"] == "6"
    assert len(get(asset="equity", exchange="BOTH", q="HAL")["instruments"]) == 2
    assert get(asset="equity", q="MISSINGTICK")["instruments"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": 0},
        {"quantity": 1.5},
        {"quantity": True},
        {"quantity": 1000001},
        {"price": "0"},
        {"price": "100.03"},
        {"price": "NaN"},
        {"price": "0.00000000000000000000000000001"},
        {"product": "NRML"},
        {"side": "AUTO"},
        {"order_type": "SL"},
        {"order_type": "MARKET"},
        {"trigger_price": "90"},
        {"validity": "TTL"},
        {"native_token": "10"},
        {"reference": "HAL"},
        {"source": "SCANNER"},
        {"execution_authority": "TM"},
        {"stop_loss": "10"},
        {"lots": 2},
    ],
)
def test_invalid_terms_never_submit(
    client: TestClient, orders: tuple[str, OrderProvider], changes: dict[str, Any]
) -> None:
    base, provider = orders
    assert client.post(base + "/preview", json=draft(**changes), headers=HEADERS).status_code == 422
    assert not provider.calls


def test_lot_and_trigger_rules(client: TestClient, orders: tuple[str, OrderProvider]) -> None:
    base, provider = orders
    for changes in ({"quantity": 66}, {"lots": None}, {"lots": 3}):
        assert (
            client.post(
                base + "/preview", json=draft("NIFTYFUT1", "4", **changes), headers=HEADERS
            ).status_code
            == 422
        )
    for side, price, trigger in (("BUY", "90", "100"), ("SELL", "110", "100")):
        assert (
            client.post(
                base + "/preview",
                json=draft(side=side, order_type="SL", price=price, trigger_price=trigger),
                headers=HEADERS,
            ).status_code
            == 422
        )
    intent = preview(client, base, draft(order_type="SL", trigger_price="100"))
    client.post(base + f"/intents/{intent['id']}/confirm", json={}, headers=HEADERS)
    assert provider.calls[0]["trigger_price"] == "100"


@pytest.mark.parametrize(
    "mode,status",
    [
        ("reject", "BROKER_REJECTED"),
        ("server", "SUBMISSION_UNKNOWN"),
        ("lost", "SUBMISSION_UNKNOWN"),
    ],
)
def test_provider_outcomes_no_retry(
    client: TestClient, orders: tuple[str, OrderProvider], mode: str, status: str
) -> None:
    base, provider = orders
    intent = preview(client, base)
    provider.mode = mode
    path = base + f"/intents/{intent['id']}"
    result = client.post(path + "/confirm", json={}, headers=HEADERS)
    assert result.json()["status"] == status
    assert "MUST_NOT_LEAK" not in result.text and "testtoken123" not in result.text
    for _ in range(3):
        client.post(path + "/confirm", json={}, headers=HEADERS)
    assert len(provider.calls) == 1
    result = client.post(path + "/reconcile", json={}, headers=HEADERS)
    assert result.json()["status"] == ("SUBMITTED" if mode == "lost" else status)


@pytest.mark.parametrize(
    "message,reason",
    [
        (
            "No IPs configured for this app. Add allowed IPs on the Kite developer console.",
            "Zerodha has no IP whitelist configured. Add the TWF API server's public static IP "
            "in Kite Connect > Profile > IP Whitelist.",
        ),
        (
            "IP (192.0.2.123) is not allowed to place orders for this app. Update allowed IPs.",
            "Zerodha rejected the API server's outgoing IP. Match its public IPv4/IPv6 "
            "with Kite Connect > Profile > IP Whitelist.",
        ),
        (
            "IP (2001:db8::123) is not allowed to place orders for this app. Update allowed IPs.",
            "Zerodha rejected the API server's outgoing IP. Match its public IPv4/IPv6 "
            "with Kite Connect > Profile > IP Whitelist.",
        ),
        (
            "The user is not enabled on the app.",
            "Zerodha has not enabled this user for the Kite app. "
            "Check the app's linked client ID in Kite Connect.",
        ),
        (
            "The user is not enabled for the app.",
            "Zerodha has not enabled this user for the Kite app. "
            "Check the app's linked client ID in Kite Connect.",
        ),
        (
            "Insufficient permission for that call.",
            "Zerodha denied order permission. Check Kite Connect's IP Whitelist and app/account "
            "access; the exact cause was not identified.",
        ),
        (
            None,
            "Zerodha denied order permission. Check Kite Connect's IP Whitelist and app/account "
            "access; the exact cause was not identified.",
        ),
        (
            {"unexpected": "provider object"},
            "Zerodha denied order permission. Check Kite Connect's IP Whitelist and app/account "
            "access; the exact cause was not identified.",
        ),
    ],
)
def test_permission_rejection_is_actionable_sanitized_and_never_retried(
    client: TestClient,
    orders: tuple[str, OrderProvider],
    caplog: pytest.LogCaptureFixture,
    message: object,
    reason: str,
) -> None:
    base, provider = orders
    intent = preview(client, base)
    attempts: list[str] = []
    secret = "MUST_NOT_LEAK_testtoken123"

    def denied(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/orders/regular":
            attempts.append(request.method)
            return httpx.Response(
                403,
                json={
                    "status": "error",
                    "error_type": "PermissionException",
                    "message": message + " " + secret if isinstance(message, str) else message,
                    "data": {"credential": secret},
                },
            )
        return provider(request)

    service(client).adapter = ZerodhaAdapter(transport=httpx.MockTransport(denied))
    path = base + f"/intents/{intent['id']}"
    result = client.post(path + "/confirm", json={}, headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["status"] == "BROKER_REJECTED"
    assert result.json()["failure"] == reason and len(reason) <= 240
    assert result.json()["broker_order_id"] is None
    for _ in range(3):
        assert client.post(path + "/confirm", json={}, headers=HEADERS).json() == result.json()
    assert client.post(path + "/reconcile", json={}, headers=HEADERS).json() == result.json()
    assert client.get(path).json() == result.json()
    assert client.get(base + "/intents").json()[0]["failure"] == reason
    assert attempts == ["POST"]
    with service(client).factory() as db:
        saved = db.get(OrderIntent, UUID(intent["id"]))
        assert saved and saved.failure == reason and saved.status == "BROKER_REJECTED"
    for sensitive in (secret, "192.0.2.123", "2001:db8::123"):
        assert sensitive not in result.text + caplog.text


def test_repeated_concurrent_confirmation(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, provider = orders
    for iteration in range(6):
        intent = preview(client, base)

        def send(_: int, intent_id: str = intent["id"]) -> Any:
            return client.post(base + f"/intents/{intent_id}/confirm", json={}, headers=HEADERS)

        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(send, range(6)))
        assert any(r.status_code == 200 and r.json()["status"] == "SUBMITTED" for r in responses)
        assert all(r.status_code in (200, 409) and "locked" not in r.text for r in responses)
        assert len(provider.calls) == iteration + 1


def test_authority_ownership_csrf_and_reconnect(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, provider = orders
    intent = preview(client, base)
    path = base + f"/intents/{intent['id']}"
    assert (
        client.post(
            path + "/confirm", json={}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    client.post(base.removesuffix("/order-entry") + "/disconnect", headers=HEADERS)
    assert client.post(path + "/confirm", json={}, headers=HEADERS).status_code == 409
    assert not provider.calls
    client.post(
        "/api/v1/auth/login",
        json={"username": "other", "password": "test-only-broker-password"},
        headers=HEADERS,
    )
    for route in (base + "/intents", path, base + "/capabilities", base + "/choices"):
        assert client.get(route).status_code == 404
    assert client.post(path + "/confirm", json={}, headers=HEADERS).status_code == 404


def test_expired_preview_and_disabled_capability(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, provider = orders
    intent = preview(client, base)
    with service(client).factory() as db:
        row = db.get(OrderIntent, UUID(intent["id"]))
        assert row
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert (
        client.post(base + f"/intents/{intent['id']}/confirm", json={}, headers=HEADERS).status_code
        == 422
    )
    service(client).settings = service(client).settings.model_copy(
        update={"broker_manual_trading_enabled": False}
    )
    assert client.get(base + "/capabilities").json()["enabled"] is False
    assert client.post(base + "/preview", json=draft(), headers=HEADERS).status_code == 409
    assert not provider.calls


class SlowOrderStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> Any:
        for _ in range(100):
            await asyncio.sleep(0.02)
            yield b" "


def test_total_deadline_covers_slow_response_stream(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, provider = orders
    intent = preview(client, base)
    calls = 0

    def slow(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/orders/regular":
            calls += 1
            return httpx.Response(200, stream=SlowOrderStream())
        return provider(request)

    service(client).adapter = ZerodhaAdapter(transport=httpx.MockTransport(slow))
    service(client).settings = service(client).settings.model_copy(
        update={"broker_deadline_seconds": 0.07}
    )
    path = base + f"/intents/{intent['id']}/confirm"
    assert client.post(path, json={}, headers=HEADERS).json()["status"] == "SUBMISSION_UNKNOWN"
    assert client.post(path, json={}, headers=HEADERS).json()["status"] == "SUBMISSION_UNKNOWN"
    assert calls == 1


def test_catalog_changed_since_preview_fails_closed(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, provider = orders
    intent = preview(client, base)
    adapter = cast(ZerodhaAdapter, service(client).adapter)
    adapter.catalog = [
        i.model_copy(update={"tick_size": i.tick_size * 2})
        if i.native_token == "1" and i.tick_size
        else i
        for i in adapter.catalog
    ]
    assert (
        client.post(base + f"/intents/{intent['id']}/confirm", json={}, headers=HEADERS).status_code
        == 422
    )
    assert not provider.calls


def test_optional_cash_failure_does_not_block_preview(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, provider = orders

    def failed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503) if request.url.path == "/user/margins" else provider(request)

    service(client).adapter = ZerodhaAdapter(transport=httpx.MockTransport(failed))
    assert preview(client, base)["available_cash"] is None


def test_new_session_cannot_confirm_old_preview(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, provider = orders
    intent = preview(client, base)
    client.post(
        "/api/v1/auth/login",
        json={"username": "trader", "password": "test-only-broker-password"},
        headers=HEADERS,
    )
    assert (
        client.post(base + f"/intents/{intent['id']}/confirm", json={}, headers=HEADERS).status_code
        == 422
    )
    assert not provider.calls


def test_reconcile_acknowledged_id_tracks_external_modification(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, provider = orders
    intent = preview(client, base)
    path = base + f"/intents/{intent['id']}"
    client.post(path + "/confirm", json={}, headers=HEADERS)
    row = provider.books[next(iter(provider.books))][-1]
    row.update(price="101", status="CANCELLED")
    result = client.post(path + "/reconcile", json={}, headers=HEADERS).json()
    assert result["provider_status"] == "CANCELLED"
    assert result["order"]["price"] == "100.05"  # original human intent stays immutable


def test_unknown_absent_next_day_and_duplicate_tag_never_authorize_retry(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, provider = orders
    intent = preview(client, base)
    path = base + f"/intents/{intent['id']}"
    provider.mode = "lost"
    client.post(path + "/confirm", json={}, headers=HEADERS)
    book = provider.books[next(iter(provider.books))]
    book.append({**book[-1], "order_id": "second-with-same-tag"})
    assert (
        client.post(path + "/reconcile", json={}, headers=HEADERS).json()["status"]
        == "SUBMISSION_UNKNOWN"
    )
    book.clear()
    assert (
        client.post(path + "/reconcile", json={}, headers=HEADERS).json()["status"]
        == "SUBMISSION_UNKNOWN"
    )
    client.post(path + "/confirm", json={}, headers=HEADERS)
    assert len(provider.calls) == 1


def test_crashed_claim_is_recoverable_and_never_resubmitted(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, provider = orders
    intent = preview(client, base)
    path = base + f"/intents/{intent['id']}"
    with service(client).factory() as db:
        row = db.get(OrderIntent, UUID(intent["id"]))
        assert row
        row.status = "SUBMITTING"
        row.submitted_at = datetime.now(UTC) - timedelta(minutes=2)
        db.commit()
    assert client.get(base + "/intents").json()[0]["id"] == intent["id"]
    assert client.post(path + "/confirm", json={}, headers=HEADERS).json()["status"] == "SUBMITTING"
    assert (
        client.post(path + "/reconcile", json={}, headers=HEADERS).json()["status"]
        == "SUBMISSION_UNKNOWN"
    )
    assert not provider.calls


@pytest.mark.parametrize("mode", ["failure", "wrong_contract", "missing", "slow"])
def test_optional_margin_failure_preserves_preview(
    client: TestClient, orders: tuple[str, OrderProvider], mode: str
) -> None:
    base, provider = orders

    def failed(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/margins/orders":
            if mode == "slow":
                return httpx.Response(200, stream=SlowOrderStream())
            if mode == "failure":
                return httpx.Response(503)
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": [
                        {
                            "exchange": "NSE",
                            "tradingsymbol": "WRONG" if mode == "wrong_contract" else "HAL",
                            "total": 75 if mode == "wrong_contract" else None,
                        }
                    ],
                },
            )
        return provider(request)

    service(client).adapter = ZerodhaAdapter(transport=httpx.MockTransport(failed))
    result = preview(client, base)
    assert result["estimated_margin"] is None
    assert result["available_cash"] == "1000" and not provider.calls
