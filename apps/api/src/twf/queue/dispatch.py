"""One governed dispatch path. Durable claim precedes all broker write I/O."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from twf.brokers.contracts import BrokerFailure, Instrument
from twf.brokers.order_contracts import IntentView, OrderDraft
from twf.brokers.order_service import OrderService as BrokerOrders
from twf.brokers.order_service import view as intent_view
from twf.brokers.queue_authority import _issue
from twf.brokers.service import BrokerService, Principal, public
from twf.infrastructure.dispatch import DispatchAttempt
from twf.infrastructure.order_intent import OrderIntent
from twf.infrastructure.twf_order import TWFOrderEventRecord, TWFOrderRecord
from twf.infrastructure.twf_queue import TWFQueueEntryRecord, TWFQueueEventRecord
from twf.orders.contracts import OrderInstrument
from twf.orders.service import _view as order_view
from twf.queue.errors import QueueError, QueueErrorCode
from twf.twf_orders.manual import _canonical

logger = logging.getLogger(__name__)


def conflict(message: str) -> QueueError:
    return QueueError(QueueErrorCode.INVALID_QUEUE_TRANSITION, message)


def transition(
    db: Session,
    entry: TWFQueueEntryRecord,
    order: TWFOrderRecord,
    target: str,
    order_target: str,
    actor: str,
    event: str,
    reason: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Caller holds Queue row lock (or SQLite write reservation)."""
    now = datetime.now(UTC)
    previous = entry.queue_state
    entry.queue_state, entry.version, entry.updated_at = target, entry.version + 1, now
    entry.reason_code, entry.reason_message = reason, reason
    db.add(
        TWFQueueEventRecord(
            event_id=uuid4(),
            queue_entry_id=entry.queue_entry_id,
            twf_order_id=order.twf_order_id,
            owner_id=entry.owner_id,
            sequence=entry.version,
            queue_version=entry.version,
            event_type=event,
            from_state=previous,
            to_state=target,
            actor=actor,
            reason_code=reason,
            reason_message=reason,
            occurred_at=now,
            details=details or {},
        )
    )
    if order.state != order_target:
        previous_order = order.state
        order.state, order.version, order.updated_at = order_target, order.version + 1, now
        order.state_reason_code, order.state_reason = reason, reason
        from sqlalchemy import func

        sequence = (
            db.scalar(
                select(func.max(TWFOrderEventRecord.sequence)).where(
                    TWFOrderEventRecord.twf_order_id == order.twf_order_id
                )
            )
            or 0
        )
        db.add(
            TWFOrderEventRecord(
                event_id=uuid4(),
                twf_order_id=order.twf_order_id,
                owner_id=order.owner_id,
                sequence=sequence + 1,
                order_version=order.version,
                event_type="STATE_TRANSITIONED",
                from_state=previous_order,
                to_state=order_target,
                actor=actor,
                authority="TWF_QUEUE_BRIDGE",
                reason_code=reason,
                reason=reason,
                correlation_id=None,
                details={"queue_entry_id": str(entry.queue_entry_id), **(details or {})},
                occurred_at=now,
            )
        )
    db.flush()


class DispatchService:
    def __init__(self, broker: BrokerService) -> None:
        self.broker = broker
        self.orders = BrokerOrders(broker)

    def _load(
        self, db: Session, entry_id: UUID, owner_id: UUID
    ) -> tuple[TWFQueueEntryRecord, TWFOrderRecord]:
        entry = db.scalar(
            select(TWFQueueEntryRecord)
            .where(
                TWFQueueEntryRecord.queue_entry_id == entry_id,
                TWFQueueEntryRecord.owner_id == owner_id,
            )
            .with_for_update()
        )
        if entry is None:
            raise QueueError(QueueErrorCode.QUEUE_ENTRY_NOT_FOUND, "Queue entry not found")
        order = db.get(TWFOrderRecord, entry.twf_order_id, with_for_update=True)
        if order is None or order.owner_id != owner_id or order.queue_entry_id != entry_id:
            raise QueueError(QueueErrorCode.QUEUE_INVARIANT_FAILURE, "Order/Queue binding mismatch")
        return entry, order

    async def cancel(self, who: Principal, entry_id: UUID, version: int) -> None:
        def save(db: Session) -> None:
            self.broker.authorize(db, who)
            entry, order = self._load(db, entry_id, who.user_id)
            if (
                entry.version != version
                or entry.queue_state not in {"READY", "HELD"}
                or order.state != "QUEUED"
            ):
                raise conflict("Entry changed or dispatch has already claimed it")
            transition(
                db,
                entry,
                order,
                "CANCELLED",
                "CANCELLED",
                f"USER:{who.user_id}",
                "CANCELLED_BEFORE_DISPATCH",
                "CANCELLED_BEFORE_DISPATCH",
            )

        await self.broker.write(save)

    async def dispatch(
        self, entry_id: UUID, who: Principal | None = None, *, expected_version: int | None = None
    ) -> None:
        if not self.broker.settings.queue_dispatch_enabled:
            raise conflict("Queue dispatch is disabled by the operator")
        automatic = who is None
        # No database transaction survives this block; external catalog reads follow.
        with self.broker.factory() as db:
            if automatic:
                entry = db.get(TWFQueueEntryRecord, entry_id)
                if (
                    entry is None
                    or entry.effective_dispatch_mode != "AUTO"
                    or entry.queue_state != "READY"
                    or entry.broker_account_id is None
                ):
                    return
                who = _issue(entry.owner_id, entry_id, entry.broker_account_id)
            assert who is not None
            self.broker.authorize(db, who)
            entry, order = self._load(db, entry_id, who.user_id)
            required_mode = "AUTO" if automatic else "MANUAL"
            if entry.effective_dispatch_mode != required_mode:
                raise conflict("Dispatch authority does not match the entry's immutable mode")
            if entry.queue_state in {
                "DISPATCHING",
                "DISPATCHED",
                "RECONCILIATION_REQUIRED",
                "FAILED",
            }:
                return  # Repeat observes the existing attempt; never another broker send.
            if entry.queue_state != "READY" or order.state != "QUEUED":
                raise conflict("Entry is not READY for dispatch")
            if expected_version is not None and entry.version != expected_version:
                raise conflict("Entry version changed")
            version, account_id = entry.version, entry.broker_account_id
            snapshot = order_view(order)
        if account_id is None:
            raise conflict(
                "Legacy admission has no bound execution account; cancel and create a "
                "new reviewed order"
            )
        actor = "SYSTEM:TWF_QUEUE_AUTO" if automatic else f"USER:{who.user_id}"
        try:
            adapter = self.orders.adapter()
            account, credentials = self.broker.capture(who, account_id)
            catalog = await self.broker.deadline(adapter.execution_catalog(credentials))
            matches: list[Instrument] = []
            for item in catalog:
                # Use existing structured canonical projection, never parse trading symbols.
                try:
                    identity, asset = _canonical(item, catalog)
                    if OrderInstrument.from_canonical(identity, asset) == snapshot.instrument:
                        matches.append(item)
                except (BrokerFailure, ValueError):
                    continue
            if len(matches) != 1:
                raise BrokerFailure(
                    "EXACT_CONTRACT_UNAVAILABLE",
                    "Current catalog does not match the frozen order.",
                    422,
                )
            item = self.orders.resolve(catalog, matches[0].reference, matches[0].native_token or "")
            terms = snapshot.terms
            draft = OrderDraft(
                reference=item.reference,
                native_token=item.native_token or "",
                side=terms.side.value,
                quantity=terms.quantity,
                order_type=terms.order_type.value,
                price=terms.limit_price,
                validity=terms.validity.value,
                product={"INTRADAY": "MIS", "DELIVERY": "CNC", "CARRY_FORWARD": "NRML"}[
                    terms.product.value
                ],
                lots=None if item.kind == "EQ" else terms.quantity // int(item.lot_size or 1),
            )
            self.orders.validate(item, draft)

            def claim(db: Session) -> tuple[IntentView, str] | None:
                self.broker.authorize(db, who)
                entry, order = self._load(db, entry_id, who.user_id)
                if entry.version != version or entry.queue_state != "READY":
                    return None
                if order.state != "QUEUED" or order_view(order) != snapshot:
                    raise conflict("Order changed since validation")
                current = self.broker.owned(db, who, account_id)
                if (
                    current.generation != account.generation
                    or public(current).state != "connected"
                    or not current.identity
                ):
                    raise BrokerFailure("BROKER_STATE_CONFLICT", "Broker connection changed.", 409)
                now = datetime.now(UTC)
                intent = OrderIntent(
                    id=uuid4(),
                    user_id=who.user_id,
                    account_id=account_id,
                    account_name=current.name,
                    provider=current.provider,
                    session_hash=who.session_hash,
                    generation=current.generation,
                    broker_identity=current.identity,
                    instrument_json=item.model_dump_json(),
                    order_json=draft.model_dump_json(),
                    source="TWF_QUEUE",
                    execution_authority="QUEUE_SYSTEM" if automatic else "QUEUE_USER",
                    tag=uuid4().hex[:20],
                    status="SUBMITTING",
                    created_at=now,
                    expires_at=now + timedelta(minutes=5),
                    submitted_at=now,
                )
                db.add(intent)
                db.flush()
                attempt = DispatchAttempt(
                    dispatch_attempt_id=uuid4(),
                    queue_entry_id=entry_id,
                    owner_id=who.user_id,
                    broker_intent_id=intent.id,
                    authority="SYSTEM" if automatic else "USER",
                    actor=actor,
                    claimed_at=now,
                )
                db.add(attempt)
                transition(
                    db,
                    entry,
                    order,
                    "DISPATCHING",
                    "SUBMITTING",
                    actor,
                    "DISPATCH_CLAIMED",
                    details={
                        "dispatch_attempt_id": str(attempt.dispatch_attempt_id),
                        "broker_intent_id": str(intent.id),
                        "effective_dispatch_mode": entry.effective_dispatch_mode,
                        "dispatch_authority": attempt.authority,
                    },
                )
                return intent_view(intent), intent.tag

            claimed = await self.broker.write(claim)
        except BrokerFailure as exc:
            await self._check_failed(
                entry_id, who.user_id, version, actor, exc.code, exc.status >= 500
            )
            return
        if claimed is None:
            return
        intent, tag = claimed
        # TX1 committed. Existing Broker V2 owns the only place_order invocation.
        result = await self.orders._submit_claimed(intent, tag, credentials, item)
        await self._finish(entry_id, who.user_id, result.status, result.broker_order_id)

    async def _check_failed(
        self, entry_id: UUID, owner_id: UUID, version: int, actor: str, code: str, temporary: bool
    ) -> None:
        def save(db: Session) -> None:
            entry, order = self._load(db, entry_id, owner_id)
            if entry.queue_state == "READY" and entry.version == version:
                transition(
                    db,
                    entry,
                    order,
                    "FAILED",
                    "FAILED",
                    actor,
                    "DISPATCH_FAILED",
                    code,
                    {
                        "classification": "temporary_pre_dispatch"
                        if temporary
                        else "permanent_pre_dispatch",
                        "broker_calls": 0,
                    },
                )

        await self.broker.write(save)

    async def _finish(
        self, entry_id: UUID, owner_id: UUID, status: str, broker_order_id: str | None
    ) -> None:
        def save(db: Session) -> None:
            entry, order = self._load(db, entry_id, owner_id)
            if entry.queue_state != "DISPATCHING":
                return
            attempt = db.scalar(
                select(DispatchAttempt).where(DispatchAttempt.queue_entry_id == entry_id)
            )
            assert attempt is not None
            if status == "SUBMITTED" and broker_order_id:
                target, order_target, event, reason = (
                    "DISPATCHED",
                    "BROKER_ACCEPTED",
                    "DISPATCH_SUBMITTED",
                    None,
                )
            elif status == "BROKER_REJECTED":
                target, order_target, event, reason = (
                    "FAILED",
                    "REJECTED",
                    "DISPATCH_FAILED",
                    "BROKER_REJECTED",
                )
            else:
                target, order_target, event, reason = (
                    "RECONCILIATION_REQUIRED",
                    "SUBMITTING",
                    "RECONCILIATION_REQUIRED",
                    "BROKER_OUTCOME_UNKNOWN",
                )
            attempt.finished_at, attempt.outcome = datetime.now(UTC), target
            transition(
                db,
                entry,
                order,
                target,
                order_target,
                attempt.actor,
                event,
                reason,
                {
                    "broker_intent_id": str(attempt.broker_intent_id),
                    "broker_order_id": broker_order_id,
                },
            )

        await self.broker.write(save)

    async def cycle(self) -> None:
        if not self.broker.settings.queue_dispatch_enabled:
            return
        # Current Queue policy intentionally absent from both selection queries.
        with self.broker.factory() as db:
            ready = list(
                db.scalars(
                    select(TWFQueueEntryRecord.queue_entry_id)
                    .where(
                        TWFQueueEntryRecord.queue_state == "READY",
                        TWFQueueEntryRecord.effective_dispatch_mode == "AUTO",
                    )
                    .order_by(TWFQueueEntryRecord.admitted_at, TWFQueueEntryRecord.queue_entry_id)
                    .limit(20)
                )
            )
            cutoff = datetime.now(UTC) - timedelta(
                seconds=self.broker.settings.broker_deadline_seconds + 30
            )
            recovery = db.execute(
                select(
                    DispatchAttempt.queue_entry_id,
                    DispatchAttempt.owner_id,
                    OrderIntent.status,
                    OrderIntent.broker_order_id,
                )
                .join(OrderIntent, OrderIntent.id == DispatchAttempt.broker_intent_id)
                .where(DispatchAttempt.finished_at.is_(None), DispatchAttempt.claimed_at < cutoff)
            ).all()
        for entry_id, owner_id, status, order_id in recovery:
            await self._finish(entry_id, owner_id, status, order_id)
        for entry_id in ready:
            try:
                await self.dispatch(entry_id)
            except (BrokerFailure, QueueError):
                logger.warning("queue_auto_dispatch_conflict", extra={"entry_id": str(entry_id)})

    async def run(self) -> None:
        while True:
            try:
                await self.cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("queue_auto_cycle_failed")
            await asyncio.sleep(2)
