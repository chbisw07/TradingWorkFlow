"""OE-2 manual intake built from a fresh, owner-scoped broker instrument catalog.

The catalog supplies structured contract facts for resolution only. This module
never calls a broker order submission method and never persists provider tokens.
"""

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from json import dumps
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from twf.brokers.contracts import BrokerFailure, Instrument
from twf.brokers.order_service import OrderService as BrokerOrderService
from twf.brokers.service import BrokerService, Principal
from twf.discovery.domain import (
    InstrumentIdentity,
    RevisionRef,
    SourceReference,
    UnderlyingIdentity,
)
from twf.discovery.product_service import INDEX_SYMBOLS
from twf.infrastructure.identity import AuthSession, User
from twf.infrastructure.order_preview import ManualOrderPreviewRecord
from twf.orders.context import OrderContext, _TrustedSubsystemOrigin
from twf.orders.contracts import (
    AssetClass,
    CreateOrder,
    OrderInstrument,
    OrderProvenance,
    OrderState,
    OrderTerms,
    OrderType,
    OrderView,
    Product,
    ReadinessResult,
    Side,
    Source,
    Validity,
)
from twf.orders.errors import OrderError, OrderErrorCode
from twf.orders.resolution import _bind_trusted_canonical_resolver
from twf.orders.service import OrderService


class ManualOrderInput(BaseModel):
    """Browser intent and selection references, never canonical authority."""

    model_config = ConfigDict(extra="forbid")
    account_id: UUID
    reference: str = Field(min_length=1, max_length=200)
    native_token: str = Field(pattern=r"^[0-9]{1,20}$")
    side: Side
    quantity: int = Field(strict=True, gt=0, le=1_000_000_000)
    order_type: OrderType
    limit_price: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    product: str = Field(pattern=r"^(MIS|CNC|NRML)$")
    validity: Validity = Validity.DAY
    notes: str = Field(default="", max_length=2000)


class ManualCreateInput(ManualOrderInput):
    preview_id: UUID


class ManualPreview(BaseModel):
    preview_id: UUID
    expires_at: datetime
    instrument: OrderInstrument
    terms: OrderTerms
    source: Source = Source.MANUAL
    account_id: UUID


class ManualCreation(BaseModel):
    order: OrderView
    validation: ReadinessResult


@dataclass(frozen=True)
class _SingleResolution:
    identity: InstrumentIdentity

    def resolve(self, instrument_id: UUID) -> InstrumentIdentity | None:
        return self.identity if self.identity.instrument_id == instrument_id else None


def _uuid(text: str) -> UUID:
    return uuid5(NAMESPACE_URL, "twf-canonical-instrument-v1:" + text)


def _canonical(
    item: Instrument, catalog: list[Instrument]
) -> tuple[InstrumentIdentity, AssetClass]:
    """Project one exact structured catalog row; never parse a trading symbol."""
    kind = item.kind
    if kind not in {"EQ", "FUT", "CE", "PE"}:
        raise BrokerFailure("INSTRUMENT_UNAVAILABLE", "Unsupported instrument type.", 422)
    if kind == "EQ":
        asset = AssetClass.EQUITY
        key = f"{item.exchange}:EQUITY:{item.symbol}"
        canonical_type = "EQUITY"
        expiry = None
        underlying_symbol = item.symbol
        lot = None
        tick = None
        display_symbol = item.symbol
    else:
        if not item.underlying or not item.expiry or not item.lot_size or not item.tick_size:
            raise BrokerFailure(
                "INSTRUMENT_UNAVAILABLE", "Exact derivative identity is unavailable.", 422
            )
        try:
            expiry = date.fromisoformat(item.expiry)
        except ValueError as exc:
            raise BrokerFailure(
                "INSTRUMENT_UNAVAILABLE", "Invalid exchange expiry date.", 422
            ) from exc
        if item.lot_size != item.lot_size.to_integral_value():
            raise BrokerFailure("INSTRUMENT_UNAVAILABLE", "Invalid derivative lot size.", 422)
        underlying_symbol = item.underlying.strip().upper()
        # A structured equity listing or the existing canonical index catalog
        # establishes the class; an unclassified underlying is rejected.
        equity_listing = any(
            row.kind == "EQ" and row.exchange == "NSE" and row.symbol == underlying_symbol
            for row in catalog
        )
        is_index = underlying_symbol in INDEX_SYMBOLS
        if equity_listing == is_index:
            raise BrokerFailure(
                "INSTRUMENT_UNAVAILABLE", "Underlying classification is unavailable.", 422
            )
        canonical_type = ("FUT" if kind == "FUT" else "OPT") + ("IDX" if is_index else "STK")
        asset = AssetClass.FUTURES if kind == "FUT" else AssetClass.OPTION
        key = f"{item.exchange}:{canonical_type}:{underlying_symbol}:{expiry.isoformat()}"
        if kind in {"CE", "PE"}:
            strike_value = item.strike
            if strike_value is None or strike_value <= 0:
                raise BrokerFailure(
                    "INSTRUMENT_UNAVAILABLE", "Exact option strike is unavailable.", 422
                )
            key += f":{format(strike_value.normalize(), 'f')}:{kind}"
        lot = int(item.lot_size)
        tick = item.tick_size
        display_symbol = f"{underlying_symbol} {expiry.isoformat()}"
        if kind == "FUT":
            display_symbol += " FUT"
        else:
            strike_value = item.strike
            if strike_value is None:
                raise BrokerFailure(
                    "INSTRUMENT_UNAVAILABLE", "Exact option strike is unavailable.", 422
                )
            display_symbol += f" {format(strike_value.normalize(), 'f')} {kind}"
    source = SourceReference(namespace="zerodha", native_id=item.reference, revision="catalog-v1")
    underlying_source = SourceReference(
        namespace="NSE", native_id=underlying_symbol, revision="catalog-v1"
    )
    right: Literal["CALL", "PUT"] | None = (
        "CALL" if kind == "CE" else "PUT" if kind == "PE" else None
    )
    identity = InstrumentIdentity(
        instrument_id=_uuid(key),
        underlying=UnderlyingIdentity(
            underlying_id=_uuid(f"UNDERLYING:NSE:{underlying_symbol}"),
            source=underlying_source,
            mapping=RevisionRef(id="nse-structured-underlying", version="1"),
        ),
        native=source,
        symbol=display_symbol,
        exchange=item.exchange,
        segment=item.segment or item.exchange,
        instrument_type=canonical_type,
        provider_symbol=item.symbol,
        expiry_date=expiry,
        lot_size=lot,
        tick_size=tick,
        strike=item.strike if kind in {"CE", "PE"} else None,
        right=right,
    )
    return identity, asset


def _terms(payload: ManualOrderInput) -> OrderTerms:
    product = {"MIS": Product.INTRADAY, "CNC": Product.DELIVERY, "NRML": Product.CARRY_FORWARD}[
        payload.product
    ]
    return OrderTerms(
        side=payload.side,
        quantity=payload.quantity,
        order_type=payload.order_type,
        limit_price=payload.limit_price,
        product=product,
        validity=payload.validity,
    )


async def _resolve(
    broker: BrokerService, who: Principal, payload: ManualOrderInput
) -> tuple[InstrumentIdentity, OrderInstrument, OrderTerms]:
    orders = BrokerOrderService(broker)
    catalog = await orders.catalog(who, payload.account_id)
    item = orders.resolve(catalog, payload.reference, payload.native_token)
    identity, asset = _canonical(item, catalog)
    instrument = OrderInstrument.from_canonical(identity, asset)
    terms = _terms(payload)
    return identity, instrument, terms


PREVIEW_TTL = timedelta(minutes=5)


def _selection_digest(payload: ManualOrderInput) -> str:
    # Bind the exact account/catalog selection without persisting a native token.
    selected = [str(payload.account_id), payload.reference, payload.native_token]
    return sha256(dumps(selected, separators=(",", ":")).encode()).hexdigest()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _context(
    broker: BrokerService, who: Principal, origin: _TrustedSubsystemOrigin | None = None
) -> OrderContext:
    with broker.factory() as db:
        user = db.get(User, who.user_id)
        login = db.get(AuthSession, who.session_hash)
        if user is None or login is None:
            raise BrokerFailure("UNAUTHORIZED", "Please sign in again.", 401)
        if origin is not None:
            return OrderContext.from_trusted_subsystem(user, login, origin)
        return OrderContext.from_authenticated_session(user, login)


async def preview(
    broker: BrokerService,
    who: Principal,
    payload: ManualOrderInput,
    *,
    _origin: _TrustedSubsystemOrigin | None = None,
) -> ManualPreview:
    context = _context(broker, who, _origin)
    _, instrument, terms = await _resolve(broker, who, payload)
    now = datetime.now(UTC)
    preview_id = uuid4()
    expires_at = now + PREVIEW_TTL
    with broker.factory.begin() as db:
        # Opportunistic bounded retention; no background worker in OE-2.
        db.execute(
            delete(ManualOrderPreviewRecord).where(
                ManualOrderPreviewRecord.expires_at < now - timedelta(days=1)
            )
        )
        db.add(
            ManualOrderPreviewRecord(
                preview_id=preview_id,
                owner_id=who.user_id,
                session_hash=who.session_hash,
                account_id=payload.account_id,
                selection_digest=_selection_digest(payload),
                instrument=instrument.model_dump(mode="json"),
                terms=terms.model_dump(mode="json"),
                notes=payload.notes,
                source=context.source.value,
                source_ref=context.source_ref,
                created_at=now,
                expires_at=expires_at,
            )
        )
    return ManualPreview(
        preview_id=preview_id,
        expires_at=expires_at,
        instrument=instrument,
        terms=terms,
        account_id=payload.account_id,
        source=context.source,
    )


class _ReadOnlyResolution:
    def resolve(self, instrument_id: UUID) -> None:
        return None


class _ClaimLost(Exception):
    """Another writer claimed or expired this preview; reload durable state."""


def _reviewed(
    broker: BrokerService,
    who: Principal,
    payload: ManualCreateInput,
    context: OrderContext,
) -> tuple[OrderInstrument, OrderTerms, str, UUID | None, ReadinessResult | None]:
    with broker.factory() as db:
        bound = db.get(ManualOrderPreviewRecord, payload.preview_id)
        if bound is None or bound.owner_id != who.user_id or bound.session_hash != who.session_hash:
            raise BrokerFailure(
                "PREVIEW_NOT_FOUND", "Preview is unavailable. Preview the order again.", 404
            )
        if bound.account_id != payload.account_id or bound.selection_digest != _selection_digest(
            payload
        ):
            raise BrokerFailure(
                "PREVIEW_MISMATCH", "Order selection changed. Preview the order again.", 409
            )
        instrument = OrderInstrument.model_validate(bound.instrument)
        terms = OrderTerms.model_validate(bound.terms)
        if (
            terms != _terms(payload)
            or bound.notes != payload.notes
            or bound.source != context.source.value
            or bound.source_ref != context.source_ref
        ):
            raise BrokerFailure(
                "PREVIEW_MISMATCH", "Order details changed. Preview the order again.", 409
            )
        if bound.consumed_at is not None:
            if bound.order_id is None or bound.validation is None:
                raise BrokerFailure("PREVIEW_USED", "Preview result is unavailable.", 409)
            return (
                instrument,
                terms,
                bound.notes,
                bound.order_id,
                ReadinessResult.model_validate(bound.validation),
            )
        if _utc(bound.expires_at) <= datetime.now(UTC):
            raise BrokerFailure("PREVIEW_EXPIRED", "Preview expired. Preview the order again.", 409)
        return instrument, terms, bound.notes, None, None


def _sqlite_contention(exc: OperationalError) -> bool:
    original = exc.orig
    return isinstance(original, sqlite3.OperationalError) and getattr(
        original, "sqlite_errorcode", 0
    ) & 0xFF in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}


def _create_atomic(
    broker: BrokerService,
    who: Principal,
    payload: ManualCreateInput,
    context: OrderContext,
    identity: InstrumentIdentity,
    instrument: OrderInstrument,
    terms: OrderTerms,
) -> ManualCreation:
    """OE-1 keeps its own service transactions as savepoints of this OE-2 transaction."""
    with broker.factory.begin() as db:
        now = datetime.now(UTC)
        claim = db.connection().execute(
            update(ManualOrderPreviewRecord)
            .where(
                ManualOrderPreviewRecord.preview_id == payload.preview_id,
                ManualOrderPreviewRecord.owner_id == who.user_id,
                ManualOrderPreviewRecord.session_hash == who.session_hash,
                ManualOrderPreviewRecord.account_id == payload.account_id,
                ManualOrderPreviewRecord.selection_digest == _selection_digest(payload),
                ManualOrderPreviewRecord.consumed_at.is_(None),
                ManualOrderPreviewRecord.expires_at > now,
            )
            # A conditional no-op UPDATE takes the writer lock. The preview stays
            # OPEN until the order and its validation are ready to link atomically.
            .values(selection_digest=ManualOrderPreviewRecord.selection_digest)
        )
        if claim.rowcount != 1:
            raise _ClaimLost
        bound = db.get(ManualOrderPreviewRecord, payload.preview_id)
        if (
            bound is None
            or OrderInstrument.model_validate(bound.instrument) != instrument
            or OrderTerms.model_validate(bound.terms) != terms
            or bound.notes != payload.notes
            or bound.source != context.source.value
            or bound.source_ref != context.source_ref
        ):
            raise BrokerFailure(
                "PREVIEW_MISMATCH", "Order details changed. Preview the order again.", 409
            )
        # The outer connection owns the durable transaction. Frozen OE-1 methods
        # still open/commit their normal Session transactions, now as savepoints.
        joined = sessionmaker(
            bind=db.connection(),
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
            close_resets_only=False,
        )
        authority = _bind_trusted_canonical_resolver(_SingleResolution(identity))
        service = OrderService(joined, context, authority)
        request = CreateOrder(
            instrument=instrument,
            terms=terms,
            provenance=OrderProvenance(source=context.source, source_ref=context.source_ref),
            notes=payload.notes,
        )
        draft = service.create_order(request)
        validation = service.validate_for_readiness(
            draft.twf_order_id, expected_version=draft.version
        )
        order = service.get_order(draft.twf_order_id)
        if validation.ready:
            order = service.transition_order(
                draft.twf_order_id,
                OrderState.READY,
                expected_version=validation.order_version or draft.version + 1,
            )
        linked = db.connection().execute(
            update(ManualOrderPreviewRecord)
            .where(
                ManualOrderPreviewRecord.preview_id == payload.preview_id,
                ManualOrderPreviewRecord.consumed_at.is_(None),
            )
            .values(
                consumed_at=now,
                order_id=order.twf_order_id,
                validation=validation.model_dump(mode="json"),
            )
        )
        if linked.rowcount != 1:
            raise _ClaimLost
        return ManualCreation(order=order, validation=validation)


async def create(
    broker: BrokerService,
    who: Principal,
    payload: ManualCreateInput,
    *,
    _origin: _TrustedSubsystemOrigin | None = None,
) -> ManualCreation:
    # The whole transaction, including the conditional claim, is retried only
    # for known SQLite contention. Every retry reloads preview and catalog truth.
    for attempt in range(6):
        try:
            context = _context(broker, who, _origin)
            instrument, terms, _, existing_id, validation = _reviewed(broker, who, payload, context)
            if existing_id is not None:
                assert validation is not None
                reader = OrderService(
                    broker.factory,
                    context,
                    _bind_trusted_canonical_resolver(_ReadOnlyResolution()),
                )
                return ManualCreation(order=reader.get_order(existing_id), validation=validation)
            try:
                identity, current_instrument, current_terms = await _resolve(broker, who, payload)
            except BrokerFailure as exc:
                if exc.status in (404, 422):
                    raise BrokerFailure(
                        "PREVIEW_MISMATCH", "Instrument changed. Preview the order again.", 409
                    ) from exc
                raise
            if current_instrument != instrument or current_terms != terms:
                raise BrokerFailure(
                    "PREVIEW_MISMATCH", "Order details changed. Preview the order again.", 409
                )
            return _create_atomic(broker, who, payload, context, identity, instrument, terms)
        except _ClaimLost:
            # The winning transaction has either linked an order or the preview
            # expired. Reload at the top, where owner and payload are checked.
            continue
        except OrderError as exc:
            if exc.code != OrderErrorCode.RETRYABLE_CONCURRENCY_CONFLICT:
                raise
        except OperationalError as exc:
            if not _sqlite_contention(exc):
                raise
        await asyncio.sleep(0.01 * (attempt + 1))
    # A final read can still recover a winner that committed on the last attempt.
    try:
        context = _context(broker, who, _origin)
        _, _, _, existing_id, validation = _reviewed(broker, who, payload, context)
        if existing_id is not None:
            assert validation is not None
            reader = OrderService(
                broker.factory, context, _bind_trusted_canonical_resolver(_ReadOnlyResolution())
            )
            return ManualCreation(order=reader.get_order(existing_id), validation=validation)
    except OperationalError as exc:
        if not _sqlite_contention(exc):
            raise
    raise OrderError(OrderErrorCode.RETRYABLE_CONCURRENCY_CONFLICT, "Concurrent order write")
