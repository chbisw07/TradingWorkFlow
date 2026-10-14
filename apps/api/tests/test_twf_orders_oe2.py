"""OE-2 API journey: trusted catalog identity, owner isolation and no broker execution."""

from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from order_provider_fixture import EXPIRIES, OrderProvider
from test_broker_v1 import HEADERS, bound, service
from test_broker_v1 import client as client

from twf.brokers.zerodha import ZerodhaAdapter

BASE = "/api/v1/twf-orders"


@pytest.fixture
def account(client: TestClient) -> tuple[str, OrderProvider]:
    broker = service(client)
    broker.settings = broker.settings.model_copy(update={"broker_manual_trading_enabled": True})
    provider = OrderProvider()
    broker.adapter = ZerodhaAdapter(transport=httpx.MockTransport(provider))
    return bound(client), provider


def payload(account_id: str, symbol: str, token: str, **changes: Any) -> dict[str, Any]:
    return {
        "account_id": account_id,
        "reference": f"ZERODHA:{'NFO' if symbol != 'HAL' else 'NSE'}:{symbol}",
        "native_token": token,
        "side": "BUY",
        "quantity": 2 if symbol == "HAL" else 250 if symbol.startswith("RELIANCE") else 65,
        "order_type": "LIMIT",
        "limit_price": "100.05",
        "product": "NRML" if symbol != "HAL" else "CNC",
        "validity": "DAY",
        **changes,
    }


@pytest.mark.parametrize(
    "symbol,token,asset,option_type,strike",
    [
        ("HAL", "1", "EQUITY", None, None),
        ("NIFTYFUT1", "4", "FUTURES", None, None),
        ("NIFTYCE1", "5", "OPTION", "CE", "25000"),
        ("NIFTYPE1", "6", "OPTION", "PE", "25000"),
        ("RELIANCEFUT1", "22", "FUTURES", None, None),
        ("RELIANCECE1", "23", "OPTION", "CE", "1400"),
    ],
)
def test_manual_create_ready_exact_identity_and_no_execution(
    client: TestClient,
    account: tuple[str, OrderProvider],
    symbol: str,
    token: str,
    asset: str,
    option_type: str | None,
    strike: str | None,
) -> None:
    account_id, provider = account
    request = payload(account_id, symbol, token)
    preview = client.post(BASE + "/preview", json=request, headers=HEADERS)
    assert preview.status_code == 200, preview.text
    assert preview.json()["instrument"]["asset_class"] == asset
    result = client.post(
        BASE, json={**request, "preview_id": preview.json()["preview_id"]}, headers=HEADERS
    )
    assert result.status_code == 200, result.text
    body = result.json()
    order = body["order"]
    assert order["state"] == "READY"
    assert order["provenance"]["source"] == "MANUAL"
    assert body["validation"]["ready"] is True
    assert order["instrument"] == preview.json()["instrument"]
    assert order["instrument"]["option_type"] == option_type
    assert order["instrument"]["strike"] == strike
    if asset != "EQUITY":
        assert order["instrument"]["expiry"] == EXPIRIES[0]
        assert order["instrument"]["lot_size"] in (65, 250)
        assert order["instrument"]["tick_size"] == "0.05"
    order_id = order["twf_order_id"]
    assert client.get(BASE).json()[0]["twf_order_id"] == order_id
    assert client.get(BASE + "/" + order_id).json() == order
    history = client.get(BASE + "/" + order_id + "/history").json()
    assert history[0]["event_type"] == "ORDER_CREATED"
    assert any(event["event_type"] == "ORDER_VALIDATED" for event in history)
    assert history[-1]["to_state"] == "READY"
    assert provider.calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", "00000000-0000-0000-0000-000000000001"),
        ("source", "WEBHOOK"),
        ("source", "SCANNER"),
        ("source", "AGENT"),
        ("state", "FILLED"),
        ("state", "QUEUED"),
        ("state", "READY"),
        ("expiry", "2000-01-01"),
        ("strike", "999"),
        ("lot_size", 1),
        ("tick_size", "1"),
        ("canonical_identity", {}),
    ],
)
def test_client_authority_spoof_is_rejected(
    client: TestClient,
    account: tuple[str, OrderProvider],
    field: str,
    value: Any,
) -> None:
    account_id, provider = account
    request = payload(account_id, "NIFTYCE1", "5", **{field: value})
    assert client.post(BASE + "/preview", json=request, headers=HEADERS).status_code == 422
    assert client.post(BASE, json=request, headers=HEADERS).status_code == 422
    assert client.get(BASE).json() == []
    assert provider.calls == []


def test_re_resolve_rejects_changed_contract_and_owner_isolation(
    client: TestClient,
    account: tuple[str, OrderProvider],
) -> None:
    account_id, provider = account
    request = payload(account_id, "NIFTYCE1", "5")
    preview = client.post(BASE + "/preview", json=request, headers=HEADERS)
    assert preview.status_code == 200
    bad = {**request, "native_token": "6", "preview_id": preview.json()["preview_id"]}
    assert (
        client.post(BASE, json=bad, headers=HEADERS).json()["error"]["code"] == "PREVIEW_MISMATCH"
    )
    assert client.get(BASE).json() == []
    created = client.post(
        BASE, json={**request, "preview_id": preview.json()["preview_id"]}, headers=HEADERS
    )
    assert created.status_code == 200, created.text
    order_id = created.json()["order"]["twf_order_id"]
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": "other", "password": "test-only-broker-password"},
            headers=HEADERS,
        ).status_code
        == 200
    )
    assert client.get(BASE).json() == []
    assert client.get(BASE + "/" + order_id).status_code == 404
    assert client.get(BASE + "/" + order_id + "/history").status_code == 404
    assert (
        client.post(
            BASE, json={**request, "preview_id": preview.json()["preview_id"]}, headers=HEADERS
        ).status_code
        == 404
    )
    assert provider.calls == []


def test_expected_readiness_failure_remains_explained_draft(
    client: TestClient,
    account: tuple[str, OrderProvider],
) -> None:
    account_id, provider = account
    request = payload(account_id, "NIFTYFUT1", "4", quantity=1)
    preview = client.post(BASE + "/preview", json=request, headers=HEADERS).json()
    result = client.post(
        BASE, json={**request, "preview_id": preview["preview_id"]}, headers=HEADERS
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["order"]["state"] == "DRAFT"
    assert body["validation"]["ready"] is False
    assert body["validation"]["violations"]
    events = client.get(BASE + "/" + body["order"]["twf_order_id"] + "/history").json()
    assert [event["event_type"] for event in events] == ["ORDER_CREATED", "ORDER_VALIDATED"]
    assert provider.calls == []


def test_create_requires_origin_and_login(
    client: TestClient,
    account: tuple[str, OrderProvider],
) -> None:
    account_id, provider = account
    request = payload(account_id, "HAL", "1")
    assert client.post(BASE, json=request).status_code == 403
    assert client.post(BASE + "/preview", json=request).status_code == 403
    assert provider.calls == []


def _preview_id(client: TestClient, request: dict[str, Any]) -> str:
    response = client.post(BASE + "/preview", json=request, headers=HEADERS)
    assert response.status_code == 200, response.text
    return str(response.json()["preview_id"])


@pytest.mark.parametrize(
    "change",
    [
        {"reference": "ZERODHA:NFO:NIFTYPE1", "native_token": "6"},
        {"reference": "ZERODHA:NFO:NIFTYCE2", "native_token": "7"},
        {"side": "SELL"},
        {"quantity": 130},
        {"order_type": "MARKET", "limit_price": None},
        {"limit_price": "101.05"},
        {"product": "MIS"},
        {"validity": "IOC"},
        {"notes": "changed"},
    ],
)
def test_valid_replacement_or_terms_never_bypass_preview(
    client: TestClient, account: tuple[str, OrderProvider], change: dict[str, Any]
) -> None:
    account_id, provider = account
    request = payload(account_id, "NIFTYCE1", "5")
    preview_id = _preview_id(client, request)
    result = client.post(
        BASE, json={**request, **change, "preview_id": preview_id}, headers=HEADERS
    )
    assert result.status_code == 409, result.text
    assert result.json()["error"]["code"] == "PREVIEW_MISMATCH"
    assert client.get(BASE).json() == []
    assert provider.calls == []
    original = client.post(BASE, json={**request, "preview_id": preview_id}, headers=HEADERS)
    assert original.status_code == 200, original.text


def test_server_catalog_drift_requires_new_preview(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    from decimal import Decimal

    account_id, provider = account
    request = payload(account_id, "NIFTYCE1", "5")
    preview_id = _preview_id(client, request)
    adapter = service(client).adapter
    assert isinstance(adapter, ZerodhaAdapter)
    adapter.catalog = [
        row.model_copy(update={"strike": Decimal("25100")}) if row.native_token == "5" else row
        for row in adapter.catalog
    ]
    result = client.post(BASE, json={**request, "preview_id": preview_id}, headers=HEADERS)
    assert result.status_code == 409, result.text
    assert result.json()["error"]["code"] == "PREVIEW_MISMATCH"
    assert client.get(BASE).json() == []
    assert provider.calls == []


def test_preview_expiry_and_single_use(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    from datetime import UTC, datetime, timedelta
    from uuid import UUID

    from twf.infrastructure.order_preview import ManualOrderPreviewRecord

    account_id, provider = account
    request = payload(account_id, "HAL", "1")
    preview_id = _preview_id(client, request)
    with service(client).factory.begin() as db:
        row = db.get(ManualOrderPreviewRecord, UUID(preview_id))
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    expired = client.post(BASE, json={**request, "preview_id": preview_id}, headers=HEADERS)
    assert expired.status_code == 409
    assert expired.json()["error"]["code"] == "PREVIEW_EXPIRED"
    assert client.get(BASE).json() == []
    fresh_id = _preview_id(client, request)
    first = client.post(BASE, json={**request, "preview_id": fresh_id}, headers=HEADERS)
    assert first.status_code == 200
    replay = client.post(BASE, json={**request, "preview_id": fresh_id}, headers=HEADERS)
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert len(client.get(BASE).json()) == 1
    assert provider.calls == []


def test_preview_cannot_cross_account(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    from test_broker_v1 import configure

    account_id, provider = account
    request = payload(account_id, "HAL", "1")
    preview_id = _preview_id(client, request)
    other_account = configure(client)
    changed = {**request, "account_id": other_account, "preview_id": preview_id}
    result = client.post(BASE, json=changed, headers=HEADERS)
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "PREVIEW_MISMATCH"
    assert client.get(BASE).json() == []
    assert provider.calls == []


def test_preview_claim_is_single_use_under_concurrent_create(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    account_id, provider = account
    request = payload(account_id, "HAL", "1")
    request["preview_id"] = _preview_id(client, request)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: client.post(BASE, json=request, headers=HEADERS), range(2))
        )
    assert [result.status_code for result in results] == [200, 200]
    assert results[0].json() == results[1].json()
    assert len(client.get(BASE).json()) == 1
    assert provider.calls == []


def test_preview_is_bound_to_authenticated_session(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    account_id, provider = account
    request = payload(account_id, "HAL", "1")
    preview_id = _preview_id(client, request)
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "trader", "password": "test-only-broker-password"},
        headers=HEADERS,
    )
    assert login.status_code == 200
    result = client.post(BASE, json={**request, "preview_id": preview_id}, headers=HEADERS)
    assert result.status_code == 404
    assert result.json()["error"]["code"] == "PREVIEW_NOT_FOUND"
    assert client.get(BASE).json() == []
    assert provider.calls == []


def test_preview_survives_application_recreation(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    from twf.main import create_app

    account_id, provider = account
    request = payload(account_id, "HAL", "1")
    preview_id = _preview_id(client, request)
    broker = service(client)
    engine = cast(FastAPI, client.app).state.database_engine
    with TestClient(
        create_app(
            broker.settings,
            engine_factory=lambda _: engine,
            broker_adapter=ZerodhaAdapter(transport=httpx.MockTransport(provider)),
        )
    ) as restarted:
        restarted.cookies.update(client.cookies)
        result = restarted.post(BASE, json={**request, "preview_id": preview_id}, headers=HEADERS)
        assert result.status_code == 200, result.text
        assert result.json()["order"]["state"] == "READY"
    assert provider.calls == []


def test_same_preview_fifty_concurrent_creates_have_one_durable_result(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from uuid import UUID

    from twf.infrastructure.order_preview import ManualOrderPreviewRecord
    from twf.infrastructure.twf_order import TWFOrderEventRecord, TWFOrderRecord

    account_id, provider = account
    broker = service(client)
    for _ in range(50):
        request = payload(account_id, "HAL", "1")
        request["preview_id"] = _preview_id(client, request)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _, request=request: client.post(BASE, json=request, headers=HEADERS),
                    range(2),
                )
            )
        assert [response.status_code for response in responses] == [200, 200], [
            response.text for response in responses
        ]
        assert responses[0].json() == responses[1].json()
        order_id = UUID(responses[0].json()["order"]["twf_order_id"])
        with broker.factory() as db:
            preview = db.get(ManualOrderPreviewRecord, UUID(request["preview_id"]))
            assert preview is not None
            assert preview.consumed_at is not None
            assert preview.order_id == order_id
            assert preview.validation is not None
            assert db.get(TWFOrderRecord, order_id) is not None
            from sqlalchemy import select

            events = db.scalars(
                select(TWFOrderEventRecord).where(TWFOrderEventRecord.twf_order_id == order_id)
            ).all()
            assert [event.event_type for event in events] == [
                "ORDER_CREATED",
                "ORDER_VALIDATED",
                "ORDER_VALIDATED",
                "STATE_TRANSITIONED",
            ]
    assert len(client.get(BASE).json()) == 50
    assert provider.calls == []


@pytest.mark.parametrize("stage", ["claim", "draft", "ready"])
def test_failed_atomic_create_rolls_back_and_same_preview_can_retry(
    client: TestClient,
    account: tuple[str, OrderProvider],
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    from uuid import UUID

    from sqlalchemy import select

    from twf.infrastructure.order_preview import ManualOrderPreviewRecord
    from twf.infrastructure.twf_order import TWFOrderEventRecord, TWFOrderRecord
    from twf.orders.service import OrderService

    account_id, provider = account
    broker = service(client)
    request = payload(account_id, "HAL", "1")
    request["preview_id"] = _preview_id(client, request)
    method = "create_order" if stage in {"claim", "draft"} else "transition_order"
    original = getattr(OrderService, method)

    def fail(*args: Any, **kwargs: Any) -> Any:
        if stage != "claim":
            original(*args, **kwargs)
        raise RuntimeError("injected failure after " + stage)

    with monkeypatch.context() as patcher:
        patcher.setattr(OrderService, method, fail)
        failed = client.post(BASE, json=request, headers=HEADERS)
        assert failed.status_code == 500
    with broker.factory() as db:
        preview = db.get(ManualOrderPreviewRecord, UUID(request["preview_id"]))
        assert preview is not None
        assert preview.consumed_at is None
        assert preview.order_id is None
        assert preview.validation is None
        assert db.scalars(select(TWFOrderRecord)).all() == []
        assert db.scalars(select(TWFOrderEventRecord)).all() == []
    result = client.post(BASE, json=request, headers=HEADERS)
    assert result.status_code == 200, result.text
    assert result.json()["order"]["state"] == "READY"
    assert provider.calls == []


def test_preview_link_is_unique_at_database_boundary(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    from datetime import UTC, datetime
    from uuid import UUID

    from sqlalchemy.exc import IntegrityError

    from twf.infrastructure.order_preview import ManualOrderPreviewRecord

    account_id, provider = account
    request = payload(account_id, "HAL", "1")
    first_id = _preview_id(client, request)
    second_id = _preview_id(client, request)
    created = client.post(BASE, json={**request, "preview_id": first_id}, headers=HEADERS)
    assert created.status_code == 200
    broker = service(client)
    with pytest.raises(IntegrityError), broker.factory.begin() as db:
        other = db.get(ManualOrderPreviewRecord, UUID(second_id))
        assert other is not None
        other.consumed_at = datetime.now(UTC)
        other.order_id = UUID(created.json()["order"]["twf_order_id"])
        other.validation = created.json()["validation"]
    with broker.factory() as db:
        other = db.get(ManualOrderPreviewRecord, UUID(second_id))
        assert other is not None and other.order_id is None and other.consumed_at is None
    assert provider.calls == []


def test_distinct_previews_are_not_globally_idempotent(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    account_id, provider = account
    request = payload(account_id, "HAL", "1")
    ids = [_preview_id(client, request), _preview_id(client, request)]
    results = [
        client.post(BASE, json={**request, "preview_id": preview_id}, headers=HEADERS)
        for preview_id in ids
    ]
    assert all(result.status_code == 200 for result in results)
    assert results[0].json()["order"]["twf_order_id"] != results[1].json()["order"]["twf_order_id"]
    assert provider.calls == []


def test_retryable_conflict_retries_whole_preview_operation(
    client: TestClient,
    account: tuple[str, OrderProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from twf.orders.errors import OrderError, OrderErrorCode
    from twf.twf_orders import manual

    account_id, provider = account
    request = payload(account_id, "HAL", "1")
    request["preview_id"] = _preview_id(client, request)
    original = manual._create_atomic
    attempts = 0

    def once(*args: Any, **kwargs: Any) -> Any:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OrderError(
                OrderErrorCode.RETRYABLE_CONCURRENCY_CONFLICT, "injected SQLite conflict"
            )
        return original(*args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(manual, "_create_atomic", once)
        response = client.post(BASE, json=request, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert attempts == 2
    assert len(client.get(BASE).json()) == 1
    assert provider.calls == []


def test_same_preview_converges_across_separate_application_services(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from twf.main import create_app

    account_id, provider = account
    request = payload(account_id, "HAL", "1")
    request["preview_id"] = _preview_id(client, request)
    broker = service(client)
    engine = cast(FastAPI, client.app).state.database_engine
    with TestClient(
        create_app(
            broker.settings,
            engine_factory=lambda _: engine,
            broker_adapter=ZerodhaAdapter(transport=httpx.MockTransport(provider)),
        )
    ) as second:
        second.cookies.update(client.cookies)
        with ThreadPoolExecutor(max_workers=2) as pool:
            calls = [
                pool.submit(target.post, BASE, json=request, headers=HEADERS)
                for target in (client, second)
            ]
            results = [call.result() for call in calls]
    assert [result.status_code for result in results] == [200, 200], [
        result.text for result in results
    ]
    assert results[0].json() == results[1].json()
    assert len(client.get(BASE).json()) == 1
    assert provider.calls == []
