"""OE-3 Queue admission, owner authority, atomicity and non-execution probes."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from order_provider_fixture import OrderProvider
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from test_broker_v1 import HEADERS, bound, service
from test_broker_v1 import client as client
from test_twf_orders_oe2 import payload

from twf.brokers.zerodha import ZerodhaAdapter
from twf.infrastructure.identity import AuthSession, User
from twf.infrastructure.twf_order import TWFOrderEventRecord, TWFOrderRecord
from twf.infrastructure.twf_queue import TWFQueueEntryRecord, TWFQueueEventRecord
from twf.orders.context import OrderContext
from twf.orders.contracts import OrderState
from twf.orders.resolution import _bind_trusted_canonical_resolver
from twf.orders.service import OrderService
from twf.queue.errors import QueueError, QueueErrorCode
from twf.queue.service import QueueService

BASE = "/api/v1/twf-queue"


@pytest.fixture
def account(client: TestClient) -> tuple[str, OrderProvider]:
    broker = service(client)
    broker.settings = broker.settings.model_copy(update={"broker_manual_trading_enabled": True})
    provider = OrderProvider()
    broker.adapter = ZerodhaAdapter(transport=httpx.MockTransport(provider))
    return bound(client), provider


def ready_order(client: TestClient, account_id: str) -> dict[str, Any]:
    request = payload(account_id, "HAL", "1")
    preview = client.post("/api/v1/twf-orders/preview", json=request, headers=HEADERS)
    assert preview.status_code == 200, preview.text
    result = client.post(
        "/api/v1/twf-orders",
        json={**request, "preview_id": preview.json()["preview_id"]},
        headers=HEADERS,
    )
    assert result.status_code == 200, result.text
    order = cast(dict[str, Any], result.json()["order"])
    assert order["state"] == "READY"
    return order


def queue_service(client: TestClient) -> QueueService:
    factory = service(client).factory
    with factory() as db:
        user = db.scalar(select(User).where(User.username == "trader"))
        assert user is not None
        login = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
        assert login is not None
        context = OrderContext.from_authenticated_session(user, login)
    return QueueService(factory, context)


def test_explicit_admission_replay_history_hold_release_and_no_broker(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    account_id, provider = account
    order = ready_order(client, account_id)
    oid = order["twf_order_id"]
    assert client.get(BASE).json()["items"] == []
    admitted = client.post(
        BASE + "/admit",
        json={"twf_order_id": oid, "expected_order_version": order["version"]},
        headers=HEADERS,
    )
    assert admitted.status_code == 200, admitted.text
    entry = admitted.json()
    assert entry["queue_entry_id"] != oid
    assert entry["queue_state"] == "READY"
    assert entry["version"] == 1
    assert entry["order"]["state"] == "QUEUED"
    assert entry["order"]["version"] == order["version"] + 1
    assert entry["order"]["provenance"]["source"] == "MANUAL"
    assert client.get("/api/v1/twf-orders/" + oid).json()["state"] == "QUEUED"
    assert client.get(BASE + "/by-order/" + oid).json() == entry
    assert client.get(BASE + "/" + entry["queue_entry_id"]).json() == entry
    assert client.get(BASE).json()["items"] == [entry]
    assert client.post(BASE + "/admit", json={"twf_order_id": oid}, headers=HEADERS).json() == entry
    history = client.get(BASE + "/" + entry["queue_entry_id"] + "/history").json()
    assert [(event["sequence"], event["event_type"]) for event in history] == [
        (1, "QUEUE_ADMITTED")
    ]
    order_history = client.get("/api/v1/twf-orders/" + oid + "/history").json()
    assert order_history[-1]["from_state"] == "READY"
    assert order_history[-1]["to_state"] == "QUEUED"
    assert order_history[-1]["authority"] == "TWF_QUEUE"
    assert order_history[-1]["actor"].startswith("USER:")
    held = client.post(
        BASE + "/" + entry["queue_entry_id"] + "/hold",
        json={"expected_version": 1, "reason": "Review before future execution"},
        headers=HEADERS,
    )
    assert held.status_code == 200, held.text
    assert held.json()["queue_state"] == "HELD"
    assert held.json()["order"]["state"] == "QUEUED"
    assert held.json()["version"] == 2
    restarted = queue_service(client)
    saved = restarted.get_entry(UUID(entry["queue_entry_id"]))
    assert saved.queue_state == "HELD" and saved.version == 2
    assert [event.sequence for event in restarted.history(saved.queue_entry_id)] == [1, 2]
    same_state = client.post(
        BASE + "/" + entry["queue_entry_id"] + "/hold",
        json={"expected_version": 2},
        headers=HEADERS,
    )
    assert same_state.status_code == 409
    assert same_state.json()["error"]["code"] == "INVALID_QUEUE_TRANSITION"
    assert (
        client.post(
            BASE + "/" + entry["queue_entry_id"] + "/hold",
            json={"expected_version": 1},
            headers=HEADERS,
        ).json()["error"]["code"]
        == "QUEUE_VERSION_CONFLICT"
    )
    released = client.post(
        BASE + "/" + entry["queue_entry_id"] + "/release",
        json={"expected_version": 2},
        headers=HEADERS,
    )
    assert released.status_code == 200, released.text
    assert released.json()["queue_state"] == "READY"
    assert released.json()["order"]["state"] == "QUEUED"
    same_state = client.post(
        BASE + "/" + entry["queue_entry_id"] + "/release",
        json={"expected_version": 3},
        headers=HEADERS,
    )
    assert same_state.status_code == 409
    assert same_state.json()["error"]["code"] == "INVALID_QUEUE_TRANSITION"
    assert [
        event["event_type"]
        for event in client.get(BASE + "/" + entry["queue_entry_id"] + "/history").json()
    ] == ["QUEUE_ADMITTED", "QUEUE_HELD", "QUEUE_RELEASED"]
    assert provider.calls == []


def test_admission_does_not_require_broker_connection(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    account_id, provider = account
    order = ready_order(client, account_id)
    disconnected = client.post(f"/api/v1/brokers/accounts/{account_id}/disconnect", headers=HEADERS)
    assert disconnected.status_code == 200, disconnected.text
    admitted = client.post(
        BASE + "/admit", json={"twf_order_id": order["twf_order_id"]}, headers=HEADERS
    )
    assert admitted.status_code == 200, admitted.text
    assert admitted.json()["queue_state"] == "READY"
    assert admitted.json()["order"]["state"] == "QUEUED"
    assert provider.calls == []


def test_draft_and_foreign_owner_cannot_admit_or_read(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    account_id, provider = account
    request = payload(account_id, "NIFTYFUT1", "4", quantity=1)
    preview = client.post("/api/v1/twf-orders/preview", json=request, headers=HEADERS).json()
    created = client.post(
        "/api/v1/twf-orders",
        json={**request, "preview_id": preview["preview_id"]},
        headers=HEADERS,
    ).json()["order"]
    assert created["state"] == "DRAFT"
    rejected = client.post(
        BASE + "/admit", json={"twf_order_id": created["twf_order_id"]}, headers=HEADERS
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "ORDER_NOT_READY"
    assert client.get(BASE).json()["items"] == []
    order = ready_order(client, account_id)
    queued = client.post(
        BASE + "/admit", json={"twf_order_id": order["twf_order_id"]}, headers=HEADERS
    ).json()
    second = ready_order(client, account_id)
    assert (
        client.post(
            BASE + "/admit", json={"twf_order_id": second["twf_order_id"]}, headers=HEADERS
        ).status_code
        == 200
    )
    owner_cursor = client.get(BASE, params={"limit": 1}).json()["next_cursor"]
    assert owner_cursor
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": "other", "password": "test-only-broker-password"},
            headers=HEADERS,
        ).status_code
        == 200
    )
    assert client.get(BASE).json()["items"] == []
    foreign_cursor = client.get(BASE, params={"limit": 1, "cursor": owner_cursor})
    assert foreign_cursor.status_code == 400
    assert foreign_cursor.json()["error"]["code"] == "INVALID_CURSOR"
    assert client.get(BASE + "/" + queued["queue_entry_id"]).status_code == 404
    assert client.get(BASE + "/by-order/" + order["twf_order_id"]).status_code == 404
    assert client.get(BASE + "/" + queued["queue_entry_id"] + "/history").status_code == 404
    assert (
        client.post(
            BASE + "/admit", json={"twf_order_id": order["twf_order_id"]}, headers=HEADERS
        ).status_code
        == 404
    )
    assert (
        client.post(
            BASE + "/" + queued["queue_entry_id"] + "/hold",
            json={"expected_version": 1},
            headers=HEADERS,
        ).status_code
        == 404
    )
    assert (
        client.post(
            BASE + "/" + queued["queue_entry_id"] + "/release",
            json={"expected_version": 1},
            headers=HEADERS,
        ).status_code
        == 404
    )
    assert provider.calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", str(uuid4())),
        ("queue_state", "SUBMITTING"),
        ("actor", "QUEUE"),
        ("authority", "QUEUE"),
        ("state", "QUEUED"),
        ("broker_order_id", "forged"),
    ],
)
def test_client_cannot_assign_queue_authority(
    client: TestClient, account: tuple[str, OrderProvider], field: str, value: str
) -> None:
    order = ready_order(client, account[0])
    result = client.post(
        BASE + "/admit", json={"twf_order_id": order["twf_order_id"], field: value}, headers=HEADERS
    )
    assert result.status_code == 422
    assert client.get(BASE).json()["items"] == []
    assert account[1].calls == []


@pytest.mark.parametrize("step", ["queue_insert", "order_transition", "queue_event"])
def test_failure_rolls_back_all_and_preview_remains_admissible(
    client: TestClient, account: tuple[str, OrderProvider], step: str
) -> None:
    order = ready_order(client, account[0])
    queue = queue_service(client)

    def fail(at: str) -> None:
        if at == step:
            raise RuntimeError("injected Queue failure")

    queue._after_step = fail  # type: ignore[assignment,method-assign]
    with pytest.raises(RuntimeError, match="injected"):
        queue.admit(UUID(order["twf_order_id"]))
    with service(client).factory() as db:
        saved = db.get(TWFOrderRecord, UUID(order["twf_order_id"]))
        assert saved is not None and saved.state == "READY"
        assert db.scalar(select(func.count()).select_from(TWFQueueEntryRecord)) == 0
        assert db.scalar(select(func.count()).select_from(TWFQueueEventRecord)) == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(TWFOrderEventRecord)
                .where(
                    TWFOrderEventRecord.twf_order_id == saved.twf_order_id,
                    TWFOrderEventRecord.to_state == "QUEUED",
                )
            )
            == 0
        )
    restored = queue_service(client).admit(UUID(order["twf_order_id"]))
    assert restored.order.state == "QUEUED"
    assert account[1].calls == []


@pytest.mark.parametrize(
    "terminal", [OrderState.CANCELLED, OrderState.REJECTED, OrderState.EXPIRED]
)
def test_terminal_orders_cannot_be_admitted(
    client: TestClient, account: tuple[str, OrderProvider], terminal: OrderState
) -> None:
    order = ready_order(client, account[0])
    queue = queue_service(client)

    class ReadOnlyResolver:
        def resolve(self, instrument_id: UUID) -> None:
            return None

    domain = OrderService(
        service(client).factory,
        queue.context,
        _bind_trusted_canonical_resolver(ReadOnlyResolver()),
    )
    changed = domain.transition_order(
        UUID(order["twf_order_id"]),
        terminal,
        expected_version=order["version"],
        reason_code="MANUAL_DECISION",
        reason="Do not execute",
    )
    assert changed.state == terminal
    response = client.post(
        BASE + "/admit", json={"twf_order_id": order["twf_order_id"]}, headers=HEADERS
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ORDER_NOT_READY"
    assert client.get(BASE).json()["items"] == []
    assert account[1].calls == []


def test_direct_database_owner_and_unique_link_constraints(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    order = ready_order(client, account[0])
    queued = queue_service(client).admit(UUID(order["twf_order_id"]))
    factory = service(client).factory
    unqueued = ready_order(client, account[0])
    with factory() as db:
        other = db.scalar(select(User).where(User.username == "other"))
        assert other is not None
        other_id = other.id
        db.rollback()
        with pytest.raises(IntegrityError), db.begin():
            db.add(
                TWFQueueEntryRecord(
                    queue_entry_id=uuid4(),
                    twf_order_id=UUID(unqueued["twf_order_id"]),
                    owner_id=other_id,
                    queue_state="READY",
                    version=1,
                    admitted_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                    created_by="USER:other",
                )
            )
            db.flush()
    with factory() as db:
        with pytest.raises(IntegrityError), db.begin():
            db.add(
                TWFQueueEntryRecord(
                    queue_entry_id=uuid4(),
                    twf_order_id=queued.twf_order_id,
                    owner_id=queued.owner_id,
                    queue_state="READY",
                    version=1,
                    admitted_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                    created_by="USER:trader",
                )
            )
            db.flush()
    assert account[1].calls == []


def test_hold_release_retries_entire_transaction_after_transient_contention(
    client: TestClient,
    account: tuple[str, OrderProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = ready_order(client, account[0])
    queue = queue_service(client)
    entry = queue.admit(UUID(order["twf_order_id"]))
    original = queue._change
    attempts = 0

    def transient(*args: Any, **kwargs: Any) -> Any:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise QueueError(QueueErrorCode.RETRYABLE_CONCURRENCY_CONFLICT, "injected lock")
        return original(*args, **kwargs)

    monkeypatch.setattr(queue, "_change", transient)
    held = queue.hold(entry.queue_entry_id, expected_version=1)
    assert attempts == 3
    assert held.queue_state == "HELD" and held.version == 2
    assert [event.event_type for event in queue.history(entry.queue_entry_id)] == [
        "QUEUE_ADMITTED",
        "QUEUE_HELD",
    ]
    assert account[1].calls == []


def test_fifo_list_is_bounded_and_projects_exact_orders_without_history_queries(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    first_order = ready_order(client, account[0])
    second_order = ready_order(client, account[0])
    queue = queue_service(client)
    first = queue.admit(UUID(first_order["twf_order_id"]))
    second = queue.admit(UUID(second_order["twf_order_id"]))
    assert [entry.queue_entry_id for entry in queue.list_entries().items] == [
        second.queue_entry_id,
        first.queue_entry_id,
    ]
    page = queue.list_entries(limit=1)
    assert [entry.queue_entry_id for entry in page.items] == [second.queue_entry_id]
    assert page.next_cursor and page.has_more
    assert (
        queue.list_entries(limit=1, cursor=page.next_cursor).items[0].queue_entry_id
        == first.queue_entry_id
    )
    assert queue.list_entries(limit=2).items[0].order.twf_order_id == UUID(
        second_order["twf_order_id"]
    )
    assert client.get(BASE, params={"limit": 0}).status_code == 422
    assert client.get(BASE, params={"limit": 101}).status_code == 422
    assert account[1].calls == []


def test_fifty_two_concurrent_admission_rounds_converge(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    account_id, provider = account
    queue = queue_service(client)
    factory = service(client).factory
    for _ in range(52):
        order = ready_order(client, account_id)
        oid = UUID(order["twf_order_id"])
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(queue.admit, oid, expected_order_version=order["version"])
                for _ in range(2)
            ]
            first, second = [future.result() for future in futures]
        assert first.queue_entry_id == second.queue_entry_id
        assert first.order.state == second.order.state == "QUEUED"
        with factory() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(TWFQueueEntryRecord)
                    .where(
                        TWFQueueEntryRecord.twf_order_id == oid,
                    )
                )
                == 1
            )
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(TWFQueueEventRecord)
                    .where(
                        TWFQueueEventRecord.twf_order_id == oid,
                        TWFQueueEventRecord.event_type == "QUEUE_ADMITTED",
                    )
                )
                == 1
            )
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(TWFOrderEventRecord)
                    .where(
                        TWFOrderEventRecord.twf_order_id == oid,
                        TWFOrderEventRecord.from_state == "READY",
                        TWFOrderEventRecord.to_state == "QUEUED",
                    )
                )
                == 1
            )
    assert provider.calls == []
