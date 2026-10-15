"""Trusted OE-3 Queue boundary: owner-scoped, atomic, and non-executing.

This distinct subsystem alone writes READY -> QUEUED with TWF_QUEUE audit
authority. OE-1's public domain transition method stays unchanged.
"""

import logging
import sqlite3
import time
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from twf.infrastructure.identity import AuthSession, User
from twf.infrastructure.twf_order import TWFOrderEventRecord, TWFOrderRecord
from twf.infrastructure.twf_queue import TWFQueueEntryRecord, TWFQueueEventRecord
from twf.orders.context import OrderContext
from twf.orders.contracts import EventType, OrderState, Source
from twf.orders.service import _view as order_view
from twf.queue.contracts import QueueEntryView, QueueEventType, QueueEventView, QueueState
from twf.queue.errors import QueueError, QueueErrorCode

logger = logging.getLogger(__name__)
_AUTHORITY = "TWF_QUEUE"


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _entry_view(row: TWFQueueEntryRecord, order: TWFOrderRecord) -> QueueEntryView:
    return QueueEntryView(
        queue_entry_id=row.queue_entry_id,
        twf_order_id=row.twf_order_id,
        owner_id=row.owner_id,
        queue_state=QueueState(row.queue_state),
        version=row.version,
        admitted_at=_utc(row.admitted_at),
        updated_at=_utc(row.updated_at),
        created_by=row.created_by,
        reason_code=row.reason_code,
        reason_message=row.reason_message,
        order=order_view(order),
    )


def _event_view(row: TWFQueueEventRecord) -> QueueEventView:
    return QueueEventView(
        event_id=row.event_id,
        queue_entry_id=row.queue_entry_id,
        twf_order_id=row.twf_order_id,
        sequence=row.sequence,
        queue_version=row.queue_version,
        event_type=QueueEventType(row.event_type),
        from_state=QueueState(row.from_state) if row.from_state else None,
        to_state=QueueState(row.to_state),
        actor=row.actor,
        reason_code=row.reason_code,
        reason_message=row.reason_message,
        occurred_at=_utc(row.occurred_at),
    )


def _sqlite_contention(exc: OperationalError) -> bool:
    original = exc.orig
    return isinstance(original, sqlite3.OperationalError) and getattr(
        original, "sqlite_errorcode", 0
    ) & 0xFF in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}


def _duplicate_order_link(exc: IntegrityError) -> bool:
    return "uq_twf_queue_entries_order" in str(exc.orig) or (
        "twf_queue_entries.twf_order_id" in str(exc.orig)
    )


class _AdmissionRace(Exception):
    pass


class QueueService:
    """Only this server-owned boundary has Queue lifecycle authority.

    A caller provides an authenticated context, never an authority, owner,
    state, actor, or broker payload. All mutations recheck the persisted login.
    """

    def __init__(self, sessions: sessionmaker[Session], context: OrderContext) -> None:
        if type(context) is not OrderContext or context.source != Source.MANUAL:
            raise QueueError(QueueErrorCode.UNAUTHORIZED, "Manual Queue context required")
        self.sessions = sessions
        self.context = context

    def _owner(self, db: Session) -> UUID:
        login = db.get(AuthSession, self.context.session_hash)
        user = db.get(User, self.context.owner_id)
        if (
            login is None
            or user is None
            or not user.is_active
            or login.user_id != user.id
            or login.revoked_at is not None
            or _utc(login.expires_at) <= datetime.now(UTC)
        ):
            raise QueueError(QueueErrorCode.UNAUTHORIZED, "Please sign in again")
        return user.id

    @staticmethod
    def _owned_order(db: Session, owner_id: UUID, order_id: UUID) -> TWFOrderRecord:
        row = db.scalar(
            select(TWFOrderRecord).where(
                TWFOrderRecord.twf_order_id == order_id,
                TWFOrderRecord.owner_id == owner_id,
            )
        )
        if row is None:
            raise QueueError(QueueErrorCode.ORDER_NOT_FOUND, "Order not found")
        return row

    @staticmethod
    def _owned_entry(db: Session, owner_id: UUID, entry_id: UUID) -> TWFQueueEntryRecord:
        row = db.scalar(
            select(TWFQueueEntryRecord).where(
                TWFQueueEntryRecord.queue_entry_id == entry_id,
                TWFQueueEntryRecord.owner_id == owner_id,
            )
        )
        if row is None:
            raise QueueError(QueueErrorCode.QUEUE_ENTRY_NOT_FOUND, "Queue entry not found")
        return row

    def _after_step(self, step: str) -> None:
        """Test fault-injection seam; production has no side effect."""

    @staticmethod
    def _existing_admission(db: Session, owner_id: UUID, order_id: UUID) -> QueueEntryView | None:
        # The caller has authenticated and established ownership of this Order.
        # One statement observes Entry + Order in one READ COMMITTED snapshot.
        # populate_existing is essential: the identity map may hold READY from
        # before a competing transaction atomically committed the admission.
        pair = db.execute(
            select(TWFQueueEntryRecord, TWFOrderRecord)
            .outerjoin(
                TWFOrderRecord,
                (TWFOrderRecord.twf_order_id == TWFQueueEntryRecord.twf_order_id)
                & (TWFOrderRecord.owner_id == TWFQueueEntryRecord.owner_id),
            )
            .where(TWFQueueEntryRecord.twf_order_id == order_id)
            .execution_options(populate_existing=True)
        ).one_or_none()
        if pair is None:
            return None
        entry, order = pair
        if (
            order is None
            or entry.owner_id != owner_id
            or order.owner_id != owner_id
            or order.twf_order_id != order_id
            or order.state != OrderState.QUEUED.value
        ):
            raise QueueError(
                QueueErrorCode.QUEUE_INVARIANT_FAILURE, "Queue and order state disagree"
            )
        return _entry_view(entry, order)

    def _admit_once(self, order_id: UUID, expected_order_version: int | None) -> QueueEntryView:
        with self.sessions() as db, db.begin():
            owner_id = self._owner(db)
            order = self._owned_order(db, owner_id, order_id)
            existing = self._existing_admission(db, owner_id, order_id)
            if existing is not None:
                logger.info("twf_queue_admission_replayed", extra={"twf_order_id": str(order_id)})
                return existing
            if order.state != OrderState.READY.value:
                raise QueueError(QueueErrorCode.ORDER_NOT_READY, "Order is not READY")
            if expected_order_version is not None and order.version != expected_order_version:
                raise QueueError(QueueErrorCode.ORDER_VERSION_CONFLICT, "Order version changed")
            now = datetime.now(UTC)
            entry = TWFQueueEntryRecord(
                queue_entry_id=uuid4(),
                twf_order_id=order_id,
                owner_id=owner_id,
                queue_state=QueueState.READY.value,
                version=1,
                admitted_at=now,
                updated_at=now,
                created_by=self.context.actor,
                reason_code=None,
                reason_message=None,
            )
            db.add(entry)
            db.flush()
            self._after_step("queue_insert")
            changed = cast(
                CursorResult[Any],
                db.execute(
                    update(TWFOrderRecord)
                    .where(
                        TWFOrderRecord.twf_order_id == order_id,
                        TWFOrderRecord.owner_id == owner_id,
                        TWFOrderRecord.state == OrderState.READY.value,
                        TWFOrderRecord.version == order.version,
                    )
                    .values(
                        state=OrderState.QUEUED.value,
                        version=order.version + 1,
                        updated_at=now,
                    )
                    .execution_options(synchronize_session=False)
                ),
            )
            if changed.rowcount != 1:
                raise _AdmissionRace
            db.refresh(order)
            self._after_step("order_transition")
            sequence = db.scalar(
                select(func.max(TWFOrderEventRecord.sequence)).where(
                    TWFOrderEventRecord.twf_order_id == order_id,
                    TWFOrderEventRecord.owner_id == owner_id,
                )
            )
            db.add(
                TWFOrderEventRecord(
                    event_id=uuid4(),
                    twf_order_id=order_id,
                    owner_id=owner_id,
                    sequence=(sequence or 0) + 1,
                    order_version=order.version,
                    event_type=EventType.STATE_TRANSITIONED.value,
                    from_state=OrderState.READY.value,
                    to_state=OrderState.QUEUED.value,
                    actor=self.context.actor,
                    authority=_AUTHORITY,
                    reason_code=None,
                    reason=None,
                    correlation_id=self.context.correlation_id,
                    details={"queue_entry_id": str(entry.queue_entry_id)},
                    occurred_at=now,
                )
            )
            db.add(
                TWFQueueEventRecord(
                    event_id=uuid4(),
                    queue_entry_id=entry.queue_entry_id,
                    twf_order_id=order_id,
                    owner_id=owner_id,
                    sequence=1,
                    queue_version=1,
                    event_type=QueueEventType.QUEUE_ADMITTED.value,
                    from_state=None,
                    to_state=QueueState.READY.value,
                    actor=self.context.actor,
                    reason_code=None,
                    reason_message=None,
                    occurred_at=now,
                )
            )
            db.flush()
            self._after_step("queue_event")
            output = _entry_view(entry, order)
        logger.info("twf_queue_admitted", extra={"queue_entry_id": str(output.queue_entry_id)})
        return output

    def admit(self, order_id: UUID, *, expected_order_version: int | None = None) -> QueueEntryView:
        for attempt in range(8):
            try:
                return self._admit_once(order_id, expected_order_version)
            except _AdmissionRace:
                pass
            except IntegrityError as exc:
                if not _duplicate_order_link(exc):
                    raise
            except OperationalError as exc:
                if not _sqlite_contention(exc):
                    raise
            time.sleep(0.01 * (attempt + 1))
        # A winner may have committed on the final attempt. Recover its exact
        # entry before returning a typed concurrency conflict.
        try:
            with self.sessions() as db:
                owner_id = self._owner(db)
                self._owned_order(db, owner_id, order_id)
                existing = self._existing_admission(db, owner_id, order_id)
                if existing is not None:
                    return existing
        except OperationalError as exc:
            if not _sqlite_contention(exc):
                raise
        raise QueueError(
            QueueErrorCode.RETRYABLE_CONCURRENCY_CONFLICT, "Concurrent Queue admission; retry"
        )

    def list_entries(self, *, limit: int = 50) -> tuple[QueueEntryView, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("Queue limit must be 1..100")
        with self.sessions() as db:
            owner_id = self._owner(db)
            rows = db.execute(
                select(TWFQueueEntryRecord, TWFOrderRecord)
                .join(
                    TWFOrderRecord,
                    (TWFOrderRecord.twf_order_id == TWFQueueEntryRecord.twf_order_id)
                    & (TWFOrderRecord.owner_id == TWFQueueEntryRecord.owner_id),
                )
                .where(TWFQueueEntryRecord.owner_id == owner_id)
                .order_by(
                    TWFQueueEntryRecord.admitted_at,
                    TWFQueueEntryRecord.queue_entry_id,
                )
                .limit(limit)
            ).all()
            return tuple(_entry_view(entry, order) for entry, order in rows)

    def get_for_order(self, order_id: UUID) -> QueueEntryView:
        with self.sessions() as db:
            owner_id = self._owner(db)
            order = self._owned_order(db, owner_id, order_id)
            entry = db.scalar(
                select(TWFQueueEntryRecord).where(
                    TWFQueueEntryRecord.twf_order_id == order_id,
                    TWFQueueEntryRecord.owner_id == owner_id,
                )
            )
            if entry is None:
                raise QueueError(QueueErrorCode.QUEUE_ENTRY_NOT_FOUND, "Queue entry not found")
            return _entry_view(entry, order)

    def get_entry(self, entry_id: UUID) -> QueueEntryView:
        with self.sessions() as db:
            owner_id = self._owner(db)
            entry = self._owned_entry(db, owner_id, entry_id)
            order = self._owned_order(db, owner_id, entry.twf_order_id)
            return _entry_view(entry, order)

    def history(self, entry_id: UUID) -> tuple[QueueEventView, ...]:
        with self.sessions() as db:
            owner_id = self._owner(db)
            self._owned_entry(db, owner_id, entry_id)
            rows = db.scalars(
                select(TWFQueueEventRecord)
                .where(
                    TWFQueueEventRecord.queue_entry_id == entry_id,
                    TWFQueueEventRecord.owner_id == owner_id,
                )
                .order_by(TWFQueueEventRecord.sequence)
            ).all()
            return tuple(_event_view(row) for row in rows)

    def _change(
        self, entry_id: UUID, expected_version: int, target: QueueState, reason: str | None
    ) -> QueueEntryView:
        try:
            with self.sessions() as db, db.begin():
                owner_id = self._owner(db)
                entry = self._owned_entry(db, owner_id, entry_id)
                order = self._owned_order(db, owner_id, entry.twf_order_id)
                if order.state != OrderState.QUEUED.value:
                    raise QueueError(
                        QueueErrorCode.QUEUE_INVARIANT_FAILURE, "Queue and order state disagree"
                    )
                if entry.version != expected_version:
                    raise QueueError(QueueErrorCode.QUEUE_VERSION_CONFLICT, "Queue version changed")
                current = QueueState(entry.queue_state)
                if (current, target) not in {
                    (QueueState.READY, QueueState.HELD),
                    (QueueState.HELD, QueueState.READY),
                }:
                    raise QueueError(
                        QueueErrorCode.INVALID_QUEUE_TRANSITION,
                        f"{current} -> {target} is not allowed",
                    )
                now = datetime.now(UTC)
                changed = cast(
                    CursorResult[Any],
                    db.execute(
                        update(TWFQueueEntryRecord)
                        .where(
                            TWFQueueEntryRecord.queue_entry_id == entry_id,
                            TWFQueueEntryRecord.owner_id == owner_id,
                            TWFQueueEntryRecord.version == expected_version,
                            TWFQueueEntryRecord.queue_state == current.value,
                        )
                        .values(
                            queue_state=target.value,
                            version=expected_version + 1,
                            updated_at=now,
                            reason_code="MANUAL_HOLD" if target == QueueState.HELD else None,
                            reason_message=reason if target == QueueState.HELD else None,
                        )
                        .execution_options(synchronize_session=False)
                    ),
                )
                if changed.rowcount != 1:
                    raise QueueError(QueueErrorCode.QUEUE_VERSION_CONFLICT, "Queue version changed")
                db.refresh(entry)
                db.add(
                    TWFQueueEventRecord(
                        event_id=uuid4(),
                        queue_entry_id=entry_id,
                        twf_order_id=entry.twf_order_id,
                        owner_id=owner_id,
                        sequence=entry.version,
                        queue_version=entry.version,
                        event_type=(
                            QueueEventType.QUEUE_HELD.value
                            if target == QueueState.HELD
                            else QueueEventType.QUEUE_RELEASED.value
                        ),
                        from_state=current.value,
                        to_state=target.value,
                        actor=self.context.actor,
                        reason_code="MANUAL_HOLD" if target == QueueState.HELD else None,
                        reason_message=reason if target == QueueState.HELD else None,
                        occurred_at=now,
                    )
                )
                db.flush()
                output = _entry_view(entry, order)
            logger.info(
                "twf_queue_state_changed",
                extra={"queue_entry_id": str(entry_id), "queue_state": target.value},
            )
            return output
        except OperationalError as exc:
            if _sqlite_contention(exc):
                raise QueueError(
                    QueueErrorCode.RETRYABLE_CONCURRENCY_CONFLICT, "Concurrent Queue write; retry"
                ) from exc
            raise

    def _change_with_retry(
        self, entry_id: UUID, expected_version: int, target: QueueState, reason: str | None
    ) -> QueueEntryView:
        for attempt in range(8):
            try:
                return self._change(entry_id, expected_version, target, reason)
            except QueueError as exc:
                if exc.code != QueueErrorCode.RETRYABLE_CONCURRENCY_CONFLICT or attempt == 7:
                    raise
                # The failed transaction was rolled back. Retry the complete
                # state CAS and audit write, never just the event insert.
                time.sleep(0.01 * (attempt + 1))
        raise AssertionError("unreachable Queue retry limit")

    def hold(
        self, entry_id: UUID, *, expected_version: int, reason: str | None = None
    ) -> QueueEntryView:
        return self._change_with_retry(entry_id, expected_version, QueueState.HELD, reason)

    def release(self, entry_id: UUID, *, expected_version: int) -> QueueEntryView:
        return self._change_with_retry(entry_id, expected_version, QueueState.READY, None)
