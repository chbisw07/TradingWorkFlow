"""Canonical, provider-neutral order values and bounded OE-1 request semantics."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from twf.discovery.domain import InstrumentIdentity
from twf.integrations.contracts import Contract


class AssetClass(StrEnum):
    EQUITY = "EQUITY"
    FUTURES = "FUTURES"
    OPTION = "OPTION"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class Product(StrEnum):
    INTRADAY = "INTRADAY"
    DELIVERY = "DELIVERY"
    CARRY_FORWARD = "CARRY_FORWARD"


class Validity(StrEnum):
    DAY = "DAY"
    IOC = "IOC"


class Source(StrEnum):
    MANUAL = "MANUAL"
    WATCHLIST = "WATCHLIST"
    SCANNER = "SCANNER"
    DISCOVERY = "DISCOVERY"
    STRATEGY = "STRATEGY"
    AGENT = "AGENT"
    WEBHOOK = "WEBHOOK"


class Intent(StrEnum):
    INTRADAY = "INTRADAY"
    POSITIONAL = "POSITIONAL"
    HEDGE = "HEDGE"
    EXIT = "EXIT"
    SCALE_IN = "SCALE_IN"
    SCALE_OUT = "SCALE_OUT"
    OTHER = "OTHER"


class AuthorityMode(StrEnum):
    MANUAL = "MANUAL"
    CONFIRM_REQUIRED = "CONFIRM_REQUIRED"


class OrderState(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    QUEUED = "QUEUED"
    SUBMITTING = "SUBMITTING"
    BROKER_ACCEPTED = "BROKER_ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class EventType(StrEnum):
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_UPDATED = "ORDER_UPDATED"
    ORDER_VALIDATED = "ORDER_VALIDATED"
    STATE_TRANSITIONED = "STATE_TRANSITIONED"


# Broker-neutral structural ceilings; broker capability limits remain OE-4 work.
MAX_QUANTITY = 1_000_000_000
MAX_PRICE = Decimal("1000000000")
MAX_DECIMAL_PLACES = 8


def _bounded_decimal(value: Decimal | None, label: str) -> None:
    if value is None:
        return
    exponent = value.as_tuple().exponent
    if value > MAX_PRICE or (isinstance(exponent, int) and -exponent > MAX_DECIMAL_PLACES):
        raise ValueError(f"{label} exceeds magnitude or decimal-place limit")


class OrderInstrument(Contract):
    """Exact canonical identity; no provider-native security identifier or token."""

    asset_class: AssetClass
    instrument_id: UUID
    exchange: str = Field(min_length=1, max_length=24)
    symbol: str = Field(min_length=1, max_length=128)
    underlying_id: UUID | None = None
    expiry: date | None = None
    strike: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    option_type: str | None = None
    lot_size: int | None = Field(default=None, strict=True, gt=0)
    tick_size: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)

    @classmethod
    def from_canonical(
        cls,
        identity: InstrumentIdentity,
        asset_class: AssetClass,
    ) -> Self:
        """Project trusted canonical facts without provider-native identifiers."""
        if identity.underlying.ambiguous:
            raise ValueError("Ambiguous canonical underlying cannot identify an order")
        canonical_asset = {
            "EQUITY": AssetClass.EQUITY,
            "FUTSTK": AssetClass.FUTURES,
            "FUTIDX": AssetClass.FUTURES,
            "OPTSTK": AssetClass.OPTION,
            "OPTIDX": AssetClass.OPTION,
        }.get(identity.instrument_type or "")
        if canonical_asset is None or canonical_asset != asset_class:
            raise ValueError("Order asset class conflicts with canonical instrument type")
        if asset_class != AssetClass.EQUITY and identity.expiry_date is None:
            raise ValueError("Derivative requires an explicit exchange-calendar expiry date")
        return cls(
            asset_class=asset_class,
            instrument_id=identity.instrument_id,
            exchange=identity.exchange,
            symbol=identity.symbol,
            underlying_id=(
                identity.underlying.underlying_id if asset_class != AssetClass.EQUITY else None
            ),
            expiry=identity.expiry_date,
            strike=identity.strike,
            option_type={"CALL": "CE", "PUT": "PE"}.get(identity.right or ""),
            lot_size=identity.lot_size,
            tick_size=identity.tick_size,
        )

    @model_validator(mode="after")
    def exact_identity(self) -> Self:
        _bounded_decimal(self.strike, "Strike")
        _bounded_decimal(self.tick_size, "Tick size")
        if self.lot_size is not None and self.lot_size > MAX_QUANTITY:
            raise ValueError("Lot size exceeds quantity limit")
        if self.asset_class == AssetClass.EQUITY:
            if any(
                value is not None
                for value in (
                    self.underlying_id,
                    self.expiry,
                    self.strike,
                    self.option_type,
                    self.lot_size,
                    self.tick_size,
                )
            ):
                raise ValueError("Equity cannot carry derivative contract terms")
        elif self.underlying_id is None or self.expiry is None:
            raise ValueError("Derivative requires exact underlying and expiry")
        elif self.lot_size is None or self.tick_size is None:
            raise ValueError("Derivative requires lot size and tick size")
        elif self.asset_class == AssetClass.FUTURES:
            if self.strike is not None or self.option_type is not None:
                raise ValueError("Futures cannot carry option terms")
        elif self.strike is None or self.option_type not in {"CE", "PE"}:
            raise ValueError("Option requires strike and CE/PE")
        return self


class OrderTerms(Contract):
    side: Side
    quantity: int = Field(strict=True, gt=0, le=MAX_QUANTITY)
    order_type: OrderType
    limit_price: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    product: Product
    validity: Validity = Validity.DAY

    @model_validator(mode="after")
    def price_matches_type(self) -> Self:
        _bounded_decimal(self.limit_price, "Limit price")
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT requires limit_price")
        if self.order_type == OrderType.MARKET and self.limit_price is not None:
            raise ValueError("MARKET cannot carry limit_price")
        return self


class OrderProvenance(Contract):
    source: Source
    source_ref: str | None = Field(default=None, min_length=1, max_length=256)
    references: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded_references(self) -> Self:
        if len(self.references) > 16 or any(
            not key or len(key) > 64 or not value or len(value) > 512
            for key, value in self.references.items()
        ):
            raise ValueError("Provenance references exceed bounded key/value limits")
        if self.source_ref is not None and not self.source_ref.strip():
            raise ValueError("Source reference cannot be blank")
        if self.source != Source.MANUAL and self.source_ref is None:
            raise ValueError("Non-manual source requires a traceable source_ref")
        return self


class CreateOrder(Contract):
    instrument: OrderInstrument
    terms: OrderTerms
    provenance: OrderProvenance
    authority_mode: AuthorityMode = AuthorityMode.MANUAL
    intent: Intent | None = None
    notes: str = Field(default="", max_length=2000)


class DraftChanges(Contract):
    terms: OrderTerms | None = None
    notes: str | None = Field(default=None, max_length=2000)


class OrderView(CreateOrder):
    twf_order_id: UUID
    owner_id: UUID
    state: OrderState
    state_reason_code: str | None
    state_reason: str | None
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime


class ReadinessResult(Contract):
    ready: bool
    violations: tuple[str, ...] = ()
    order_version: int | None = None


class OrderEventView(Contract):
    event_id: UUID
    twf_order_id: UUID
    sequence: int
    order_version: int
    event_type: EventType
    from_state: OrderState | None
    to_state: OrderState | None
    actor: str
    authority: str
    reason_code: str | None
    reason: str | None
    correlation_id: str | None
    details: dict[str, object]
    occurred_at: datetime
