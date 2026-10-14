"""Owner-scoped OE-1 application service; persistence only, never execution."""

import logging
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from twf.discovery.domain import InstrumentIdentity
from twf.infrastructure.identity import AuthSession, User
from twf.infrastructure.twf_order import TWFOrderEventRecord, TWFOrderRecord
from twf.orders.context import OrderContext
from twf.orders.contracts import (
    AssetClass,
    CreateOrder,
    DraftChanges,
    EventType,
    OrderEventView,
    OrderInstrument,
    OrderProvenance,
    OrderState,
    OrderTerms,
    OrderView,
    Product,
    ReadinessResult,
)
from twf.orders.errors import OrderError, OrderErrorCode
from twf.orders.lifecycle import REASON_REQUIRED, check_domain_transition
from twf.orders.resolution import TrustedCanonicalInstrumentAuthority

logger = logging.getLogger(__name__)


def _utc(value: datetime) -> datetime:
    # SQLite removes timezone information on read; all writes here are UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _view(row: TWFOrderRecord) -> OrderView:
    return OrderView.model_validate(
        {
            **row.payload,
            "twf_order_id": row.twf_order_id,
            "owner_id": row.owner_id,
            "state": row.state,
            "state_reason_code": row.state_reason_code,
            "state_reason": row.state_reason,
            "version": row.version,
            "created_by": row.created_by,
            "created_at": _utc(row.created_at),
            "updated_at": _utc(row.updated_at),
        }
    )


def _event_view(row: TWFOrderEventRecord) -> OrderEventView:
    return OrderEventView.model_validate(
        {
            "event_id": row.event_id,
            "twf_order_id": row.twf_order_id,
            "sequence": row.sequence,
            "order_version": row.order_version,
            "event_type": row.event_type,
            "from_state": row.from_state,
            "to_state": row.to_state,
            "actor": row.actor,
            "authority": row.authority,
            "reason_code": row.reason_code,
            "reason": row.reason,
            "correlation_id": row.correlation_id,
            "details": row.details,
            "occurred_at": _utc(row.occurred_at),
        }
    )


def _readiness(order: OrderView) -> ReadinessResult:
    violations: list[str] = []
    instrument = order.instrument
    if instrument.asset_class != AssetClass.EQUITY:
        if instrument.lot_size is not None and order.terms.quantity % instrument.lot_size:
            violations.append("QUANTITY_NOT_LOT_MULTIPLE")
        if order.terms.product == Product.DELIVERY:
            violations.append("DERIVATIVE_DELIVERY_UNSUPPORTED")
        if (
            order.terms.limit_price is not None
            and instrument.tick_size is not None
            and order.terms.limit_price % instrument.tick_size
        ):
            violations.append("LIMIT_PRICE_NOT_TICK_MULTIPLE")
    return ReadinessResult(ready=not violations, violations=tuple(violations))


@contextmanager
def _mutation_conflict() -> Iterator[None]:
    try:
        yield
    except OperationalError as exc:
        original = exc.orig
        if isinstance(original, sqlite3.OperationalError) and original.sqlite_errorcode in {
            sqlite3.SQLITE_BUSY,
            sqlite3.SQLITE_LOCKED,
            sqlite3.SQLITE_BUSY_SNAPSHOT,
        }:
            raise OrderError(
                OrderErrorCode.RETRYABLE_CONCURRENCY_CONFLICT, "Concurrent order write"
            ) from exc
        raise


class OrderService:
    """No Queue/Broker adapter is injectable or imported into this boundary."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        context: OrderContext,
        canonical_resolver: TrustedCanonicalInstrumentAuthority,
    ) -> None:
        if (
            type(canonical_resolver) is not TrustedCanonicalInstrumentAuthority
            or not canonical_resolver.is_issued()
        ):
            raise OrderError(OrderErrorCode.UNAUTHORIZED, "Trusted canonical resolver required")
        self.sessions = sessions
        self.context = context
        self.canonical_resolver = canonical_resolver

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
            raise OrderError(
                OrderErrorCode.UNAUTHORIZED, "Order context is no longer authenticated"
            )
        return user.id

    @staticmethod
    def _owned(db: Session, owner_id: UUID, order_id: UUID) -> TWFOrderRecord:
        row = db.scalar(
            select(TWFOrderRecord).where(
                TWFOrderRecord.twf_order_id == order_id,
                TWFOrderRecord.owner_id == owner_id,
            )
        )
        if row is None:
            raise OrderError(OrderErrorCode.ORDER_NOT_FOUND, "Order not found")
        return row

    @staticmethod
    def _check_version(row: TWFOrderRecord, expected_version: int) -> None:
        if row.version != expected_version:
            raise OrderError(OrderErrorCode.VERSION_CONFLICT, "Order version changed")

    @staticmethod
    def _cas(db: Session, row: TWFOrderRecord, expected_version: int, **values: object) -> None:
        result = cast(
            CursorResult[Any],
            db.execute(
                update(TWFOrderRecord)
                .where(
                    TWFOrderRecord.twf_order_id == row.twf_order_id,
                    TWFOrderRecord.owner_id == row.owner_id,
                    TWFOrderRecord.version == expected_version,
                )
                .values(version=expected_version + 1, updated_at=datetime.now(UTC), **values)
                .execution_options(synchronize_session=False)
            ),
        )
        if result.rowcount != 1:
            raise OrderError(OrderErrorCode.VERSION_CONFLICT, "Order version changed")
        db.refresh(row)

    @staticmethod
    def _append(
        db: Session,
        row: TWFOrderRecord,
        event_type: EventType,
        *,
        actor: str,
        from_state: OrderState | None = None,
        to_state: OrderState | None = None,
        reason_code: str | None = None,
        reason: str | None = None,
        correlation_id: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        sequence = db.scalar(
            select(func.max(TWFOrderEventRecord.sequence)).where(
                TWFOrderEventRecord.twf_order_id == row.twf_order_id,
                TWFOrderEventRecord.owner_id == row.owner_id,
            )
        )
        db.add(
            TWFOrderEventRecord(
                event_id=uuid4(),
                twf_order_id=row.twf_order_id,
                owner_id=row.owner_id,
                sequence=(sequence or 0) + 1,
                order_version=row.version,
                event_type=event_type.value,
                from_state=from_state.value if from_state else None,
                to_state=to_state.value if to_state else None,
                actor=actor,
                authority="TWF_DOMAIN",
                reason_code=reason_code,
                reason=reason,
                correlation_id=correlation_id,
                details=details or {},
                occurred_at=datetime.now(UTC),
            )
        )
        db.flush()

    def create_order(self, request: CreateOrder) -> OrderView:
        if (
            type(request) is not CreateOrder
            or type(request.instrument) is not OrderInstrument
            or type(request.terms) is not OrderTerms
            or type(request.provenance) is not OrderProvenance
        ):
            raise OrderError(OrderErrorCode.INVALID_ORDER, "Exact CreateOrder contract required")
        try:
            normalized = CreateOrder.model_validate(request.model_dump(mode="json"))
            canonical_identity = self.canonical_resolver.resolve(
                normalized.instrument.instrument_id
            )
            if type(canonical_identity) is not InstrumentIdentity:
                raise OrderError(OrderErrorCode.INVALID_ORDER, "Canonical instrument not found")
            if canonical_identity.instrument_id != normalized.instrument.instrument_id:
                raise OrderError(
                    OrderErrorCode.INVALID_ORDER, "Canonical resolver returned wrong identity"
                )
            expected_instrument = OrderInstrument.from_canonical(
                canonical_identity, normalized.instrument.asset_class
            )
        except (ValidationError, ValueError) as exc:
            raise OrderError(OrderErrorCode.INVALID_ORDER, "Invalid canonical order input") from exc
        if normalized.instrument != expected_instrument:
            raise OrderError(
                OrderErrorCode.INVALID_ORDER, "Order instrument conflicts with canonical identity"
            )
        if normalized.provenance.source != self.context.source or (
            self.context.source_ref is not None
            and normalized.provenance.source_ref != self.context.source_ref
        ):
            raise OrderError(
                OrderErrorCode.INVALID_ORDER, "Order source conflicts with trusted context"
            )
        actor = self.context.actor
        correlation_id = self.context.correlation_id
        now = datetime.now(UTC)
        row = TWFOrderRecord(
            twf_order_id=uuid4(),
            owner_id=self.context.owner_id,
            state=OrderState.DRAFT.value,
            version=1,
            payload=normalized.model_dump(mode="json"),
            created_by=actor,
            created_at=now,
            updated_at=now,
            state_reason_code=None,
            state_reason=None,
        )
        with _mutation_conflict(), self.sessions() as db, db.begin():
            self._owner(db)
            db.add(row)
            db.flush()
            self._append(
                db,
                row,
                EventType.ORDER_CREATED,
                actor=actor,
                to_state=OrderState.DRAFT,
                correlation_id=correlation_id,
                details={"provenance": normalized.provenance.model_dump(mode="json")},
            )
            output = _view(row)
        logger.info("twf_order_created", extra={"twf_order_id": str(output.twf_order_id)})
        return output

    def get_order(self, order_id: UUID) -> OrderView:
        with self.sessions() as db:
            return _view(self._owned(db, self._owner(db), order_id))

    def list_orders(self, *, limit: int = 100) -> tuple[OrderView, ...]:
        if not 1 <= limit <= 500:
            raise OrderError(OrderErrorCode.INVALID_ORDER, "Limit must be 1..500")
        with self.sessions() as db:
            owner_id = self._owner(db)
            rows = db.scalars(
                select(TWFOrderRecord)
                .where(TWFOrderRecord.owner_id == owner_id)
                .order_by(TWFOrderRecord.created_at.desc(), TWFOrderRecord.twf_order_id)
                .limit(limit)
            ).all()
            return tuple(_view(row) for row in rows)

    def get_order_history(self, order_id: UUID) -> tuple[OrderEventView, ...]:
        with self.sessions() as db:
            owner_id = self._owner(db)
            self._owned(db, owner_id, order_id)
            rows = db.scalars(
                select(TWFOrderEventRecord)
                .where(
                    TWFOrderEventRecord.owner_id == owner_id,
                    TWFOrderEventRecord.twf_order_id == order_id,
                )
                .order_by(TWFOrderEventRecord.sequence)
            ).all()
            return tuple(_event_view(row) for row in rows)

    def update_draft_order(
        self,
        order_id: UUID,
        changes: DraftChanges,
        *,
        expected_version: int,
    ) -> OrderView:
        if not changes.model_fields_set:
            raise OrderError(OrderErrorCode.INVALID_ORDER, "No draft changes supplied")
        with _mutation_conflict(), self.sessions() as db, db.begin():
            row = self._owned(db, self._owner(db), order_id)
            self._check_version(row, expected_version)
            if row.state != OrderState.DRAFT.value:
                raise OrderError(OrderErrorCode.IMMUTABLE_FIELD, "Only DRAFT is editable")
            request = CreateOrder.model_validate(row.payload)
            payload = request.model_dump(mode="json")
            before = {field: payload[field] for field in changes.model_fields_set}
            if "terms" in changes.model_fields_set:
                if changes.terms is None:
                    raise OrderError(OrderErrorCode.INVALID_ORDER, "Terms cannot be cleared")
                payload["terms"] = changes.terms.model_dump(mode="json")
            if "notes" in changes.model_fields_set:
                payload["notes"] = changes.notes or ""
            self._cas(db, row, expected_version, payload=payload)
            self._append(
                db,
                row,
                EventType.ORDER_UPDATED,
                actor=self.context.actor,
                details={
                    "changed_fields": sorted(changes.model_fields_set),
                    "before": before,
                    "after": {field: payload[field] for field in changes.model_fields_set},
                },
            )
            output = _view(row)
        logger.info("twf_order_draft_updated", extra={"twf_order_id": str(order_id)})
        return output

    def validate_for_readiness(self, order_id: UUID, *, expected_version: int) -> ReadinessResult:
        with _mutation_conflict(), self.sessions() as db, db.begin():
            row = self._owned(db, self._owner(db), order_id)
            self._check_version(row, expected_version)
            if row.state not in {OrderState.DRAFT.value, OrderState.BLOCKED.value}:
                raise OrderError(
                    OrderErrorCode.INVALID_TRANSITION, "Readiness requires DRAFT or BLOCKED"
                )
            result = _readiness(_view(row))
            self._cas(db, row, expected_version)
            result = result.model_copy(update={"order_version": row.version})
            self._append(
                db,
                row,
                EventType.ORDER_VALIDATED,
                actor=self.context.actor,
                details={"ready": result.ready, "violations": list(result.violations)},
            )
        logger.info(
            "twf_order_validated", extra={"twf_order_id": str(order_id), "ready": result.ready}
        )
        return result

    def transition_order(
        self,
        order_id: UUID,
        target: OrderState,
        *,
        expected_version: int,
        reason_code: str | None = None,
        reason: str | None = None,
    ) -> OrderView:
        if not isinstance(target, OrderState):
            raise OrderError(OrderErrorCode.INVALID_ORDER, "Target must be an OrderState")
        if target in REASON_REQUIRED and (
            not reason_code
            or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", reason_code)
            or not reason
            or len(reason) > 512
        ):
            raise OrderError(
                OrderErrorCode.INVALID_ORDER, "Exceptional state requires code and reason"
            )
        with _mutation_conflict(), self.sessions() as db, db.begin():
            row = self._owned(db, self._owner(db), order_id)
            self._check_version(row, expected_version)
            current = OrderState(row.state)
            check_domain_transition(current, target)
            if target == OrderState.READY:
                result = _readiness(_view(row))
                if not result.ready:
                    raise OrderError(
                        OrderErrorCode.INVALID_ORDER,
                        "Readiness violations: " + ", ".join(result.violations),
                    )
            self._cas(
                db,
                row,
                expected_version,
                state=target.value,
                state_reason_code=reason_code,
                state_reason=reason,
            )
            if target == OrderState.READY:
                self._append(
                    db,
                    row,
                    EventType.ORDER_VALIDATED,
                    actor=self.context.actor,
                    details={"ready": True, "violations": []},
                )
            self._append(
                db,
                row,
                EventType.STATE_TRANSITIONED,
                actor=self.context.actor,
                from_state=current,
                to_state=target,
                reason_code=reason_code,
                reason=reason,
                correlation_id=self.context.correlation_id,
            )
            output = _view(row)
        logger.info(
            "twf_order_transitioned",
            extra={
                "twf_order_id": str(order_id),
                "from_state": current.value,
                "to_state": target.value,
            },
        )
        return output
