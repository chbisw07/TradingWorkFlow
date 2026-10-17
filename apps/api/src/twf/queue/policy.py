"""Current policy is consulted ONLY during admission, never worker selection."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from twf.infrastructure.broker import BrokerAccount
from twf.infrastructure.dispatch import QueueDispatchPolicy, QueuePolicyEvent
from twf.queue.errors import QueueError, QueueErrorCode


def locked_policy(db: Session, owner_id: UUID, account_id: UUID) -> QueueDispatchPolicy:
    account = db.scalar(
        select(BrokerAccount).where(
            BrokerAccount.id == account_id, BrokerAccount.user_id == owner_id
        )
    )
    if account is None:
        raise QueueError(QueueErrorCode.ORDER_NOT_FOUND, "Broker account not found")
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert
    else:
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    db.execute(
        (
            pg_insert(QueueDispatchPolicy)
            if db.get_bind().dialect.name == "postgresql"
            else sqlite_insert(QueueDispatchPolicy)
        )
        .values(
            owner_id=owner_id,
            broker_account_id=account_id,
            current_dispatch_mode="MANUAL",
            version=1,
            updated_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(
            index_elements=[QueueDispatchPolicy.owner_id, QueueDispatchPolicy.broker_account_id]
        )
    )
    policy = db.scalar(
        select(QueueDispatchPolicy)
        .where(
            QueueDispatchPolicy.owner_id == owner_id,
            QueueDispatchPolicy.broker_account_id == account_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert policy is not None
    return policy


def change_policy(
    db: Session, owner_id: UUID, account_id: UUID, mode: str, expected_version: int, actor: str
) -> QueueDispatchPolicy:
    if mode not in {"MANUAL", "AUTO"}:
        raise QueueError(QueueErrorCode.INVALID_QUEUE_TRANSITION, "Invalid dispatch mode")
    policy = locked_policy(db, owner_id, account_id)
    if policy.version != expected_version:
        raise QueueError(QueueErrorCode.QUEUE_VERSION_CONFLICT, "Queue policy changed; reload")
    if policy.current_dispatch_mode != mode:
        now = datetime.now(UTC)
        db.add(
            QueuePolicyEvent(
                event_id=uuid4(),
                owner_id=owner_id,
                broker_account_id=account_id,
                previous_mode=policy.current_dispatch_mode,
                new_mode=mode,
                version=policy.version + 1,
                actor=actor,
                occurred_at=now,
            )
        )
        policy.current_dispatch_mode = mode
        policy.version += 1
        policy.updated_at = now
    db.flush()
    return policy
