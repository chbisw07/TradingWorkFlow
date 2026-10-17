"""OE-4 tests use only the existing synthetic HTTP broker, never live credentials."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Self, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from order_provider_fixture import OrderProvider
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from test_broker_v1 import HEADERS, service
from test_broker_v1 import client as client
from test_twf_queue_oe3 import account as account
from test_twf_queue_oe3 import ready_order

from twf.brokers.order_contracts import ExecutionAdapter
from twf.infrastructure.dispatch import DispatchAttempt
from twf.infrastructure.twf_queue import TWFQueueEntryRecord
from twf.queue.dispatch import DispatchService

BASE = "/api/v1/twf-queue"


def policy(client: TestClient, aid: str, mode: str) -> dict[str, Any]:
    current = client.get(f"{BASE}/policy/{aid}")
    assert current.status_code == 200, current.text
    changed = client.post(
        f"{BASE}/policy/{aid}",
        json={"current_dispatch_mode": mode, "expected_version": current.json()["version"]},
        headers=HEADERS,
    )
    assert changed.status_code == 200, changed.text
    return cast(dict[str, Any], changed.json())


def admit(client: TestClient, aid: str) -> dict[str, Any]:
    order = ready_order(client, aid)
    response = client.post(
        BASE + "/admit",
        json={"twf_order_id": order["twf_order_id"], "broker_account_id": aid},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def enable_synthetic(client: TestClient) -> DispatchService:
    broker = service(client)
    broker.settings = broker.settings.model_copy(update={"queue_dispatch_enabled": True})
    return DispatchService(broker)


def test_admission_mode_snapshots_and_shared_dispatch(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    aid, provider = account
    dispatch = enable_synthetic(client)
    q1 = admit(client, aid)
    policy(client, aid, "AUTO")
    assert client.get(BASE + "/" + q1["queue_entry_id"]).json() == q1
    q2 = admit(client, aid)
    policy(client, aid, "MANUAL")
    assert client.get(BASE + "/" + q2["queue_entry_id"]).json() == q2
    q3 = admit(client, aid)
    assert [q["effective_dispatch_mode"] for q in (q1, q2, q3)] == ["MANUAL", "AUTO", "MANUAL"]
    asyncio.run(dispatch.cycle())
    assert len(provider.calls) == 1
    assert client.get(BASE + "/" + q2["queue_entry_id"]).json()["queue_state"] == "DISPATCHED"
    for q in (q1, q3):
        assert client.get(BASE + "/" + q["queue_entry_id"]).json()["queue_state"] == "READY"
    sent = client.post(
        BASE + "/" + q1["queue_entry_id"] + "/dispatch",
        json={"expected_version": 1},
        headers=HEADERS,
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["order"]["state"] == "BROKER_ACCEPTED", sent.text
    assert len(provider.calls) == 2
    assert q1["public_queue_id"].startswith("QID-")
    assert q1["public_order_id"].startswith("ORD-")
    assert q1["source_kind"] == "MANUAL"
    import hashlib
    import json

    print(
        "OE4_MODE_TRACE "
        + json.dumps(
            {
                "entries": [
                    {
                        "order": q["public_order_id"],
                        "queue": q["public_queue_id"],
                        "source": q["source_kind"],
                        "effective_mode": q["effective_dispatch_mode"],
                        "policy_version": q["policy_version"],
                        "admission_version": q["version"],
                        "admission_sha256": hashlib.sha256(
                            json.dumps(q, sort_keys=True).encode()
                        ).hexdigest(),
                    }
                    for q in (q1, q2, q3)
                ],
                "unchanged_across_policy_switches": True,
                "calls_after_worker": 1,
                "calls_after_manual_dispatch": len(provider.calls),
                "final_states": [
                    client.get(BASE + "/" + q["queue_entry_id"]).json()["queue_state"]
                    for q in (q1, q2, q3)
                ],
            },
            sort_keys=True,
        )
    )


def test_hold_release_retains_entry_modes(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    aid, provider = account
    dispatch = enable_synthetic(client)
    manual = admit(client, aid)
    policy(client, aid, "AUTO")
    auto = admit(client, aid)
    for q in (manual, auto):
        assert (
            client.post(
                BASE + "/" + q["queue_entry_id"] + "/hold",
                json={"expected_version": 1},
                headers=HEADERS,
            ).status_code
            == 200
        )
    policy(client, aid, "MANUAL")
    asyncio.run(dispatch.cycle())
    assert provider.calls == []
    for q in (manual, auto):
        assert (
            client.post(
                BASE + "/" + q["queue_entry_id"] + "/release",
                json={"expected_version": 2},
                headers=HEADERS,
            ).status_code
            == 200
        )
    asyncio.run(dispatch.cycle())
    assert len(provider.calls) == 1
    assert client.get(BASE + "/" + manual["queue_entry_id"]).json()["queue_state"] == "READY"


def test_manual_concurrent_dispatch_and_cancel(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    aid, provider = account
    enable_synthetic(client)
    q = admit(client, aid)

    def send(_: int) -> int:
        return client.post(
            BASE + "/" + q["queue_entry_id"] + "/dispatch",
            json={"expected_version": 1},
            headers=HEADERS,
        ).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(send, range(4)))
    assert all(x in {200, 409} for x in results), results
    assert len(provider.calls) == 1
    with service(client).factory() as db:
        assert len(list(db.scalars(select(DispatchAttempt)))) == 1
    cancelled = admit(client, aid)
    result = client.post(
        BASE + "/" + cancelled["queue_entry_id"] + "/cancel",
        json={"expected_version": 1},
        headers=HEADERS,
    )
    assert result.status_code == 200, result.text
    assert result.json()["order"]["state"] == "CANCELLED"
    assert send(1) == 200
    assert len(provider.calls) == 1


def test_mode_is_immutable_at_database_boundary(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    q = admit(client, account[0])
    with service(client).factory() as db:
        with pytest.raises(IntegrityError):
            db.execute(
                update(TWFQueueEntryRecord)
                .where(TWFQueueEntryRecord.queue_entry_id == UUID(q["queue_entry_id"]))
                .values(effective_dispatch_mode="AUTO")
            )
            db.commit()
        db.rollback()


def test_default_operator_gate_blocks_every_dispatch(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    aid, provider = account
    q = admit(client, aid)
    result = client.post(
        BASE + "/" + q["queue_entry_id"] + "/dispatch",
        json={"expected_version": 1},
        headers=HEADERS,
    )
    assert result.status_code == 409
    policy(client, aid, "AUTO")
    admit(client, aid)
    asyncio.run(DispatchService(service(client)).cycle())
    assert provider.calls == []


@pytest.mark.parametrize(
    "mode,target",
    [
        ("success", "DISPATCHED"),
        ("reject", "FAILED"),
        ("lost", "RECONCILIATION_REQUIRED"),
        ("server", "RECONCILIATION_REQUIRED"),
    ],
)
def test_broker_outcome_never_blindly_retried(
    client: TestClient, account: tuple[str, OrderProvider], mode: str, target: str
) -> None:
    aid, provider = account
    dispatch = enable_synthetic(client)
    policy(client, aid, "AUTO")
    q = admit(client, aid)
    provider.mode = mode
    asyncio.run(dispatch.cycle())
    for _ in range(3):
        asyncio.run(dispatch.cycle())
    row = client.get(BASE + "/" + q["queue_entry_id"]).json()
    assert row["queue_state"] == target, row
    assert len(provider.calls) == 1


def test_two_auto_workers_and_cancel_races(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    aid, provider = account
    dispatch = enable_synthetic(client)
    policy(client, aid, "AUTO")
    for _ in range(10):
        q = admit(client, aid)
        before = len(provider.calls)

        def worker(_: int) -> None:
            asyncio.run(dispatch.cycle())

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(worker, range(2)))
        assert len(provider.calls) == before + 1
        assert client.get(BASE + "/" + q["queue_entry_id"]).json()["queue_state"] == "DISPATCHED"
    for action in ("cancel", "hold"):
        for _ in range(5):
            q = admit(client, aid)
            before = len(provider.calls)
            with ThreadPoolExecutor(max_workers=2) as pool:
                worker_result = pool.submit(asyncio.run, dispatch.cycle())
                response = client.post(
                    BASE + "/" + q["queue_entry_id"] + "/" + action,
                    json={"expected_version": 1},
                    headers=HEADERS,
                )
                worker_result.result()
            state = client.get(BASE + "/" + q["queue_entry_id"]).json()["queue_state"]
            if response.status_code == 200:
                assert state in {"CANCELLED", "HELD"}
                assert len(provider.calls) == before
            else:
                assert response.status_code == 409
                assert state == "DISPATCHED"
                assert len(provider.calls) == before + 1


def test_policy_admission_races(client: TestClient, account: tuple[str, OrderProvider]) -> None:
    aid, provider = account
    current = policy(client, aid, "MANUAL")
    for i in range(20):
        order = ready_order(client, aid)
        target = "AUTO" if i % 2 == 0 else "MANUAL"
        with ThreadPoolExecutor(max_workers=2) as pool:
            admitted = pool.submit(
                client.post,
                BASE + "/admit",
                json={"twf_order_id": order["twf_order_id"], "broker_account_id": aid},
                headers=HEADERS,
            )
            changed = client.post(
                f"{BASE}/policy/{aid}",
                json={"current_dispatch_mode": target, "expected_version": current["version"]},
                headers=HEADERS,
            )
            response = admitted.result()
        assert changed.status_code == response.status_code == 200, (changed.text, response.text)
        q = response.json()
        assert (q["effective_dispatch_mode"], q["policy_version"]) in {
            (current["current_dispatch_mode"], current["version"]),
            (target, changed.json()["version"]),
        }
        current = changed.json()
    assert provider.calls == []


def test_crash_after_claim_and_after_broker_acceptance(
    client: TestClient, account: tuple[str, OrderProvider], monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime, timedelta

    from twf.brokers.order_service import OrderService as BrokerOrders

    aid, provider = account
    dispatch = enable_synthetic(client)
    policy(client, aid, "AUTO")
    original = BrokerOrders._submit_claimed
    for after_acceptance in (False, True):
        q = admit(client, aid)
        before = len(provider.calls)

        async def interrupted(self: Any, *args: Any, accepted: bool = after_acceptance) -> Any:
            if accepted:
                await original(self, *args)
            raise RuntimeError("synthetic process interruption")

        monkeypatch.setattr(BrokerOrders, "_submit_claimed", interrupted)
        with pytest.raises(RuntimeError, match="synthetic"):
            asyncio.run(dispatch.cycle())
        import twf.queue.dispatch as dispatch_module

        real_clock = datetime

        class Later(datetime):
            @classmethod
            def now(cls, tz: Any = None) -> Self:
                return cls.fromtimestamp(
                    (datetime.now(UTC) + timedelta(minutes=10)).timestamp(), tz
                )

        monkeypatch.setattr(dispatch_module, "datetime", Later)
        monkeypatch.setattr(BrokerOrders, "_submit_claimed", original)
        asyncio.run(dispatch.cycle())
        monkeypatch.setattr(dispatch_module, "datetime", real_clock)
        row = client.get(BASE + "/" + q["queue_entry_id"]).json()
        assert row["queue_state"] == (
            "DISPATCHED" if after_acceptance else "RECONCILIATION_REQUIRED"
        )
        assert len(provider.calls) == before + int(after_acceptance)


def test_hundred_same_bucket_ids_are_concurrency_safe(
    client: TestClient, account: tuple[str, OrderProvider], monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from test_twf_queue_oe3 import queue_service

    import twf.queue.service as queue_module
    from twf.infrastructure.dispatch import OrderPublicID
    from twf.infrastructure.twf_order import TWFOrderRecord

    aid, _ = account
    template = ready_order(client, aid)
    factory = service(client).factory
    fixed = datetime.now(UTC).replace(microsecond=0)
    with factory() as db:
        original = db.get(TWFOrderRecord, UUID(template["twf_order_id"]))
        assert original is not None
        owner, payload, actor = original.owner_id, original.payload, original.created_by
    ids = [uuid4() for _ in range(100)]

    def create(oid: UUID) -> None:
        def operation(db: Any) -> None:
            db.add(
                TWFOrderRecord(
                    twf_order_id=oid,
                    owner_id=owner,
                    state="READY",
                    version=1,
                    payload=payload,
                    created_by=actor,
                    created_at=fixed,
                    updated_at=fixed,
                )
            )

        service(client).transaction(operation)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(create, ids))
    with factory() as db:
        aliases = list(
            db.scalars(
                select(OrderPublicID.public_order_id).where(OrderPublicID.twf_order_id.in_(ids))
            )
        )
    assert len(aliases) == len(set(aliases)) == 100
    assert len({alias.rsplit("-", 1)[0] for alias in aliases}) == 1

    class Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> Self:
            return cls.fromtimestamp(fixed.timestamp(), tz)

    monkeypatch.setattr(queue_module, "datetime", Clock)
    queue = queue_service(client)

    def enqueue(oid: UUID) -> str | None:
        return queue.admit(oid, broker_account_id=UUID(aid)).public_queue_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        queue_aliases = list(pool.map(enqueue, ids))
    assert len(queue_aliases) == len(set(queue_aliases)) == 100
    assert all(alias is not None for alias in queue_aliases)
    assert len({str(alias).rsplit("-", 1)[0] for alias in queue_aliases}) == 1


def test_failed_fresh_check_sends_nothing(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    aid, provider = account
    dispatch = enable_synthetic(client)
    policy(client, aid, "AUTO")
    q = admit(client, aid)
    assert (
        client.post(f"/api/v1/brokers/accounts/{aid}/disconnect", headers=HEADERS).status_code
        == 200
    )
    asyncio.run(dispatch.cycle())
    row = client.get(BASE + "/" + q["queue_entry_id"]).json()
    assert row["queue_state"] == "FAILED"
    assert row["reason_code"] == "BROKER_REAUTH_REQUIRED"
    assert provider.calls == []


@pytest.mark.parametrize("source", ["WATCHLIST", "SCANNER"])
def test_verified_source_preview_binding_and_spoof_block(
    client: TestClient, account: tuple[str, OrderProvider], source: str
) -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from test_twf_orders_oe2 import payload
    from test_twf_queue_oe3 import queue_service

    from twf.infrastructure.scanner_v2 import ScannerRunRow
    from twf.infrastructure.watchlists import WatchlistItemRow, WatchlistRow

    aid, provider = account
    owner = queue_service(client).context.owner_id
    key = uuid4()
    from test_twf_queue_oe3 import queue_service

    from twf.brokers.service import Principal
    from twf.twf_orders.manual import ManualOrderInput, _resolve

    ctx = queue_service(client).context
    identity, _, _ = asyncio.run(
        _resolve(
            service(client),
            Principal(owner, ctx.session_hash),
            ManualOrderInput.model_validate(payload(aid, "HAL", "1")),
        )
    )
    with service(client).factory.begin() as db:
        if source == "SCANNER":
            db.add(
                ScannerRunRow(
                    id=key,
                    owner_id=owner,
                    payload={"rows": [{"instrument": identity.model_dump(mode="json")}]},
                    created_at=datetime.now(UTC),
                )
            )
        else:
            db.add(
                WatchlistRow(
                    id=key,
                    owner_id=owner,
                    name="Verified source",
                    description="",
                    favorite=False,
                    archived=False,
                    ordering=0,
                    revision=1,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            db.flush()
            db.add(
                WatchlistItemRow(
                    id=uuid4(),
                    watchlist_id=key,
                    instrument_id=identity.instrument_id,
                    instrument=identity.model_dump(mode="json"),
                    source={},
                    ordering=0,
                    added_at=datetime.now(UTC),
                )
            )
    path = f"/api/v1/twf-orders/from/{source}/{key}"
    request = payload(aid, "HAL", "1")
    preview = client.post(path + "/preview", json=request, headers=HEADERS)
    assert preview.status_code == 200, preview.text
    assert preview.json()["source"] == source
    creation = {**request, "preview_id": preview.json()["preview_id"]}
    spoof = client.post("/api/v1/twf-orders", json=creation, headers=HEADERS)
    assert spoof.status_code == 409
    invalid = client.post(
        f"/api/v1/twf-orders/from/{source}/{uuid4()}/preview", json=request, headers=HEADERS
    )
    assert invalid.status_code in (401, 404)
    created = client.post(path, json=creation, headers=HEADERS)
    assert created.status_code == 200, created.text
    order = created.json()["order"]
    assert order["provenance"]["source"] == source
    assert order["provenance"]["source_ref"] == str(key)
    admitted = client.post(
        BASE + "/admit",
        json={"twf_order_id": order["twf_order_id"], "broker_account_id": aid},
        headers=HEADERS,
    )
    assert admitted.status_code == 200, admitted.text
    assert admitted.json()["source_kind"] == source
    assert admitted.json()["source_reference"] == str(key)
    assert provider.calls == []


def test_claim_rollback_is_atomic_and_broker_io_has_no_database_lock(
    client: TestClient, account: tuple[str, OrderProvider], monkeypatch: pytest.MonkeyPatch
) -> None:
    import twf.queue.dispatch as module
    from twf.infrastructure.dispatch import PublicIDCounter

    aid, provider = account
    dispatch = enable_synthetic(client)
    q = admit(client, aid)
    original = module.transition

    def interrupted(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        raise RuntimeError("synthetic claim transaction crash")

    monkeypatch.setattr(module, "transition", interrupted)
    from test_twf_queue_oe3 import queue_service

    from twf.brokers.service import Principal

    context = queue_service(client).context
    who = Principal(context.owner_id, context.session_hash)
    with pytest.raises(RuntimeError):
        asyncio.run(dispatch.dispatch(UUID(q["queue_entry_id"]), who, expected_version=1))
    with service(client).factory() as db:
        assert db.scalar(select(DispatchAttempt)) is None
    assert client.get(BASE + "/" + q["queue_entry_id"]).json()["queue_state"] == "READY"
    assert provider.calls == []
    monkeypatch.setattr(module, "transition", original)
    place = cast(ExecutionAdapter, service(client).adapter).place_order

    async def inspect_transaction(*args: Any, **kwargs: Any) -> Any:
        with service(client).factory.begin() as db:
            row = db.scalar(
                select(TWFQueueEntryRecord)
                .where(TWFQueueEntryRecord.queue_entry_id == UUID(q["queue_entry_id"]))
                .with_for_update(nowait=True)
            )
            assert row is not None and row.queue_state == "DISPATCHING"
            assert db.scalar(select(DispatchAttempt)) is not None
            db.execute(update(PublicIDCounter).values(value=PublicIDCounter.value))
        return await place(*args, **kwargs)

    monkeypatch.setattr(service(client).adapter, "place_order", inspect_transaction)
    asyncio.run(dispatch.dispatch(UUID(q["queue_entry_id"]), who, expected_version=1))
    assert len(provider.calls) == 1


def test_snapshot_and_policy_audit_reject_direct_tampering(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    from sqlalchemy import delete

    from twf.infrastructure.dispatch import OrderPublicID, QueuePolicyEvent

    aid, _ = account
    q = admit(client, aid)
    policy(client, aid, "AUTO")
    for statement in (
        update(TWFQueueEntryRecord).values(source_kind="WEBHOOK"),
        update(TWFQueueEntryRecord).values(source_reference="forged"),
        update(TWFQueueEntryRecord).values(policy_version=999),
        update(TWFQueueEntryRecord).values(broker_account_id=None),
        update(TWFQueueEntryRecord).values(public_queue_id="forged"),
        update(QueuePolicyEvent).values(actor="forged"),
        delete(QueuePolicyEvent),
        update(OrderPublicID).values(public_order_id="forged"),
        delete(OrderPublicID),
    ):
        with service(client).factory.begin() as db:
            with pytest.raises(IntegrityError):
                db.execute(statement)
                db.flush()
            db.rollback()
    assert client.get(BASE + "/" + q["queue_entry_id"]).json() == q


@pytest.mark.parametrize("symbol,token", [("NIFTYFUT1", "4"), ("NIFTYCE1", "5"), ("NIFTYPE1", "6")])
def test_exact_derivative_identity_dispatches_through_same_bridge(
    client: TestClient, account: tuple[str, OrderProvider], symbol: str, token: str
) -> None:
    from test_twf_orders_oe2 import payload

    aid, provider = account
    enable_synthetic(client)
    request = payload(aid, symbol, token)
    preview = client.post("/api/v1/twf-orders/preview", json=request, headers=HEADERS)
    assert preview.status_code == 200, preview.text
    created = client.post(
        "/api/v1/twf-orders",
        json={**request, "preview_id": preview.json()["preview_id"]},
        headers=HEADERS,
    )
    assert created.status_code == 200, created.text
    q = client.post(
        BASE + "/admit",
        json={"twf_order_id": created.json()["order"]["twf_order_id"], "broker_account_id": aid},
        headers=HEADERS,
    ).json()
    result = client.post(
        BASE + "/" + q["queue_entry_id"] + "/dispatch",
        json={"expected_version": 1},
        headers=HEADERS,
    )
    assert result.status_code == 200, result.text
    assert result.json()["queue_state"] == "DISPATCHED", result.text
    assert len(provider.calls) == 1
