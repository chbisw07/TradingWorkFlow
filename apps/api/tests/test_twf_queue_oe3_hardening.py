"""OE-3 persistence-boundary attacks and operator keyset traversal."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import TypeVar
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from order_provider_fixture import OrderProvider
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from test_broker_v1 import bound, service
from test_broker_v1 import client as client
from test_twf_queue_oe3 import queue_service, ready_order

from twf.brokers.zerodha import ZerodhaAdapter
from twf.infrastructure.twf_order import TWFOrderEventRecord, TWFOrderRecord
from twf.infrastructure.twf_queue import TWFQueueEntryRecord, TWFQueueEventRecord
from twf.queue.contracts import QueueState
from twf.queue.errors import QueueError, QueueErrorCode

_T = TypeVar("_T")


def _reject(factory: sessionmaker[Session], operation: Callable[[Session], object]) -> None:
    # The exception may arrive at statement time or at COMMIT (deferred FK).
    with pytest.raises(IntegrityError):
        with factory() as db, db.begin():
            operation(db)


@pytest.fixture
def account_data(client: TestClient) -> tuple[str, OrderProvider]:
    broker = service(client)
    broker.settings = broker.settings.model_copy(update={"broker_manual_trading_enabled": True})
    provider = OrderProvider()
    broker.adapter = ZerodhaAdapter(transport=httpx.MockTransport(provider))
    return bound(client), provider


def test_direct_db_split_states_and_pair_tampering_are_rejected(
    client: TestClient, account_data: tuple[str, OrderProvider]
) -> None:
    factory = service(client).factory
    first = ready_order(client, account_data[0])
    second = ready_order(client, account_data[0])
    oid = UUID(first["twf_order_id"])
    other_id = UUID(second["twf_order_id"])
    with factory() as db:
        order_row = db.get(TWFOrderRecord, oid)
        assert order_row is not None
        owner = order_row.owner_id
    new_id = uuid4()

    def entry_for_ready(db: Session) -> None:
        db.add(
            TWFQueueEntryRecord(
                queue_entry_id=new_id,
                twf_order_id=oid,
                owner_id=owner,
                queue_state="READY",
                version=1,
                admitted_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                created_by="DB_ATTACK",
            )
        )

    _reject(factory, entry_for_ready)
    _reject(
        factory,
        lambda db: db.execute(
            update(TWFOrderRecord)
            .where(TWFOrderRecord.twf_order_id == oid)
            .values(state="QUEUED", queue_entry_id=uuid4())
        ),
    )
    _reject(
        factory,
        lambda db: db.execute(
            update(TWFOrderRecord).where(TWFOrderRecord.twf_order_id == oid).values(state="QUEUED")
        ),
    )
    queue = queue_service(client)
    one = queue.admit(oid)
    two = queue.admit(other_id)
    _reject(
        factory,
        lambda db: db.execute(
            update(TWFOrderRecord)
            .where(TWFOrderRecord.twf_order_id == oid)
            .values(queue_entry_id=two.queue_entry_id)
        ),
    )
    _reject(
        factory,
        lambda db: db.execute(
            update(TWFQueueEntryRecord)
            .where(TWFQueueEntryRecord.queue_entry_id == one.queue_entry_id)
            .values(owner_id=uuid4())
        ),
    )
    _reject(
        factory,
        lambda db: db.execute(
            delete(TWFQueueEntryRecord).where(
                TWFQueueEntryRecord.queue_entry_id == one.queue_entry_id
            )
        ),
    )
    with factory() as db:
        order_row = db.get(TWFOrderRecord, oid)
        assert order_row is not None
        assert order_row.queue_entry_id == one.queue_entry_id
        assert order_row.state == "QUEUED"
        entry_row = db.get(TWFQueueEntryRecord, one.queue_entry_id)
        assert entry_row is not None and entry_row.owner_id == owner
        assert db.scalar(select(func.count()).select_from(TWFQueueEntryRecord)) == 2
    # Schema deliberately permits later post-QUEUED lifecycle states when bound.
    with factory() as db, db.begin():
        db.execute(
            update(TWFOrderRecord)
            .where(TWFOrderRecord.twf_order_id == oid)
            .values(state="SUBMITTING")
        )
    with factory() as db:
        order_row = db.get(TWFOrderRecord, oid)
        assert order_row is not None and order_row.queue_entry_id == one.queue_entry_id
    with factory() as db, db.begin():
        db.execute(
            update(TWFOrderRecord).where(TWFOrderRecord.twf_order_id == oid).values(state="QUEUED")
        )


def test_queue_events_are_database_append_only(
    client: TestClient, account_data: tuple[str, OrderProvider]
) -> None:
    factory = service(client).factory
    order = ready_order(client, account_data[0])
    queue = queue_service(client)
    entry = queue.admit(UUID(order["twf_order_id"]))
    queue.hold(entry.queue_entry_id, expected_version=1)
    with factory() as db:
        ids = db.scalars(select(TWFQueueEventRecord.event_id)).all()
    _reject(factory, lambda db: db.execute(update(TWFQueueEventRecord).values(actor="ATTACK")))
    _reject(factory, lambda db: db.execute(delete(TWFQueueEventRecord)))
    _reject(
        factory,
        lambda db: db.execute(
            update(TWFQueueEventRecord)
            .where(TWFQueueEventRecord.event_id == ids[0])
            .values(actor="ATTACK")
        ),
    )
    _reject(
        factory,
        lambda db: db.execute(
            delete(TWFQueueEventRecord).where(TWFQueueEventRecord.event_id == ids[0])
        ),
    )
    with factory() as db:
        prior = db.get(TWFQueueEventRecord, ids[0])
        assert prior is not None
        trial = TWFQueueEventRecord(
            event_id=uuid4(),
            queue_entry_id=prior.queue_entry_id,
            twf_order_id=prior.twf_order_id,
            owner_id=prior.owner_id,
            sequence=3,
            queue_version=3,
            event_type="RELEASED",
            from_state="HELD",
            to_state="READY",
            actor="TEST",
            occurred_at=datetime.now(UTC),
        )

    def insert_then_mutate(db: Session) -> None:
        db.add(trial)
        db.flush()
        db.execute(
            update(TWFQueueEventRecord)
            .where(TWFQueueEventRecord.event_id == ids[0])
            .values(actor="ATTACK")
        )

    _reject(factory, insert_then_mutate)
    assert [event.sequence for event in queue.history(entry.queue_entry_id)] == [1, 2]
    queue.release(entry.queue_entry_id, expected_version=2)
    assert [event.sequence for event in queue.history(entry.queue_entry_id)] == [1, 2, 3]


@pytest.mark.parametrize("count", [125, 500])
def test_newest_keyset_traverses_all_tied_rows_and_validates_cursor(
    client: TestClient, account_data: tuple[str, OrderProvider], count: int
) -> None:
    factory = service(client).factory
    seed = ready_order(client, account_data[0])
    with factory() as db:
        original = db.get(TWFOrderRecord, UUID(seed["twf_order_id"]))
        assert original is not None
        owner, payload = original.owner_id, original.payload
    admitted = datetime.now(UTC).replace(microsecond=123456)
    expected: list[tuple[datetime, UUID]] = []
    with factory() as db, db.begin():
        for index in range(count):
            oid, qid = uuid4(), uuid4()
            at = admitted - timedelta(seconds=index // 3)
            expected.append((at, qid))
            db.add(
                TWFOrderRecord(
                    twf_order_id=oid,
                    owner_id=owner,
                    state="QUEUED",
                    version=2,
                    payload=payload,
                    created_by="TEST",
                    created_at=at,
                    updated_at=at,
                    queue_entry_id=qid,
                )
            )
            db.add(
                TWFQueueEntryRecord(
                    queue_entry_id=qid,
                    twf_order_id=oid,
                    owner_id=owner,
                    queue_state="READY" if index % 2 else "HELD",
                    version=1,
                    admitted_at=at,
                    updated_at=at,
                    created_by="TEST",
                )
            )
    expected.sort(reverse=True)
    queue = queue_service(client)
    cursor = None
    received: list[UUID] = []
    pages = 0
    while True:
        page = queue.list_entries(limit=37, cursor=cursor)
        received.extend(item.queue_entry_id for item in page.items)
        pages += 1
        if not page.has_more:
            assert page.next_cursor is None
            break
        assert page.next_cursor and page.next_cursor != cursor
        cursor = page.next_cursor
    assert received == [qid for _, qid in expected]
    assert pages == (count + 36) // 37
    assert len(set(received)) == count
    assert queue.list_entries(limit=1).items[0].queue_entry_id == expected[0][1]
    first = queue.list_entries(limit=3)
    assert first.next_cursor
    with pytest.raises(QueueError) as error:
        queue.list_entries(limit=3, cursor=first.next_cursor + "x")
    assert error.value.code == QueueErrorCode.INVALID_CURSOR
    with pytest.raises(QueueError) as error:
        queue.list_entries(limit=3, cursor=first.next_cursor, state=QueueState.READY)
    assert error.value.code == QueueErrorCode.INVALID_CURSOR
    ready_first = queue.list_entries(limit=3, state=QueueState.READY)
    assert ready_first.next_cursor
    with factory() as db, db.begin():
        db.execute(
            update(TWFQueueEntryRecord)
            .where(TWFQueueEntryRecord.queue_entry_id == ready_first.items[0].queue_entry_id)
            .values(queue_state="HELD")
        )
    ready_second = queue.list_entries(
        limit=3, cursor=ready_first.next_cursor, state=QueueState.READY
    )
    assert all(item.queue_state == QueueState.READY for item in ready_second.items)
    assert not {item.queue_entry_id for item in ready_first.items} & {
        item.queue_entry_id for item in ready_second.items
    }
    # A new admission after page one belongs to the refreshed top, not page two.
    old_second = queue.list_entries(limit=3, cursor=first.next_cursor)
    newer = uuid4()
    with factory() as db, db.begin():
        oid = uuid4()
        at = admitted + timedelta(seconds=1)
        db.add(
            TWFOrderRecord(
                twf_order_id=oid,
                owner_id=owner,
                state="QUEUED",
                version=2,
                payload=payload,
                created_by="TEST",
                created_at=at,
                updated_at=at,
                queue_entry_id=newer,
            )
        )
        db.add(
            TWFQueueEntryRecord(
                queue_entry_id=newer,
                twf_order_id=oid,
                owner_id=owner,
                queue_state="READY",
                version=1,
                admitted_at=at,
                updated_at=at,
                created_by="TEST",
            )
        )
    assert [
        x.queue_entry_id for x in queue.list_entries(limit=3, cursor=first.next_cursor).items
    ] == [x.queue_entry_id for x in old_second.items]
    assert queue.list_entries(limit=1).items[0].queue_entry_id == newer
    assert client.get("/api/v1/twf-queue", params={"limit": 1}).json()["has_more"]
    if count == 500:
        with factory() as db:
            if db.bind is not None and db.bind.dialect.name == "postgresql":
                plan = (
                    db.execute(
                        text(
                            "EXPLAIN SELECT queue_entry_id FROM twf_queue_entries "
                            "WHERE owner_id = :owner ORDER BY admitted_at DESC, "
                            "queue_entry_id DESC LIMIT 37"
                        ),
                        {"owner": owner},
                    )
                    .scalars()
                    .all()
                )
                assert plan
                print("OE-3 PostgreSQL first-page plan:", " | ".join(plan))


def test_migration_preserves_existing_queue_data_and_refuses_corrupt_0025(
    client: TestClient, account_data: tuple[str, OrderProvider]
) -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext

    factory = service(client).factory
    order = ready_order(client, account_data[0])
    queue = queue_service(client)
    entry = queue.admit(UUID(order["twf_order_id"]))
    queue.hold(entry.queue_entry_id, expected_version=1)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.downgrade(config, "0025_twf_queue")
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(TWFQueueEntryRecord)) == 1
        assert db.scalar(select(func.count()).select_from(TWFQueueEventRecord)) == 2
    command.upgrade(config, "head")
    with factory() as db:
        order_row = db.get(TWFOrderRecord, UUID(order["twf_order_id"]))
        assert order_row is not None
        assert order_row.queue_entry_id == entry.queue_entry_id
        assert db.scalar(select(func.count()).select_from(TWFQueueEventRecord)) == 2
    assert queue.get_entry(entry.queue_entry_id).queue_state == "HELD"

    command.downgrade(config, "0025_twf_queue")
    with factory() as db, db.begin():
        db.execute(
            update(TWFOrderRecord)
            .where(TWFOrderRecord.twf_order_id == UUID(order["twf_order_id"]))
            .values(state="READY")
        )
    with pytest.raises(RuntimeError, match="refused incoherent"):
        command.upgrade(config, "head")
    with factory() as db:
        assert (
            MigrationContext.configure(db.connection()).get_current_revision() == "0025_twf_queue"
        )
        assert db.scalar(select(func.count()).select_from(TWFQueueEntryRecord)) == 1


def test_bounded_queue_operation_timings(
    client: TestClient, account_data: tuple[str, OrderProvider]
) -> None:
    queue = queue_service(client)
    first = ready_order(client, account_data[0])
    second = ready_order(client, account_data[0])
    timings: dict[str, float] = {}

    def timed(name: str, operation: Callable[[], _T]) -> _T:
        started = perf_counter()
        result = operation()
        timings[name] = round((perf_counter() - started) * 1000, 2)
        return result

    entry = timed("admission", lambda: queue.admit(UUID(first["twf_order_id"])))
    replay = timed("replay", lambda: queue.admit(UUID(first["twf_order_id"])))
    assert replay.queue_entry_id == entry.queue_entry_id
    held = timed("hold", lambda: queue.hold(entry.queue_entry_id, expected_version=1))
    released = timed(
        "release", lambda: queue.release(entry.queue_entry_id, expected_version=held.version)
    )
    assert released.queue_state == QueueState.READY
    queue.admit(UUID(second["twf_order_id"]))
    first_page = timed("first_page", lambda: queue.list_entries(limit=1))
    assert first_page.next_cursor
    next_page = timed(
        "next_page", lambda: queue.list_entries(limit=1, cursor=first_page.next_cursor)
    )
    assert next_page.items and next_page.items[0].queue_entry_id == entry.queue_entry_id
    print(f"OE-3 bounded operation timings (ms): {timings}")


def test_postgres_runtime_metadata(client: TestClient) -> None:
    from sqlalchemy import text

    factory = service(client).factory
    with factory() as db:
        if db.bind is None or db.bind.dialect.name != "postgresql":
            pytest.skip("PostgreSQL runtime metadata")
        version, pid, database, isolation = db.execute(
            text(
                "SELECT current_setting('server_version'), pg_backend_pid(), "
                "current_database(), current_setting('transaction_isolation')"
            )
        ).one()
        assert int(str(version).split(".")[0]) >= 14
        assert isinstance(pid, int) and pid > 0
        assert str(database).startswith("twf_test_")
        assert str(isolation) == "read committed"
        print(f"PostgreSQL {version}; PID {pid}; database {database}; isolation {isolation}")


def test_order_events_are_append_only_in_managed_database(
    client: TestClient, account_data: tuple[str, OrderProvider]
) -> None:
    order = ready_order(client, account_data[0])
    factory = service(client).factory
    with factory() as db:
        event_id = db.scalar(
            select(TWFOrderEventRecord.event_id).where(
                TWFOrderEventRecord.twf_order_id == UUID(order["twf_order_id"])
            )
        )
    assert event_id is not None
    _reject(
        factory,
        lambda db: db.execute(
            update(TWFOrderEventRecord)
            .where(TWFOrderEventRecord.event_id == event_id)
            .values(actor="TAMPERED")
        ),
    )
    _reject(
        factory,
        lambda db: db.execute(
            delete(TWFOrderEventRecord).where(TWFOrderEventRecord.event_id == event_id)
        ),
    )
    with factory() as db:
        assert db.get(TWFOrderEventRecord, event_id) is not None
