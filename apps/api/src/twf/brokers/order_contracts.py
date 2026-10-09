"""Small manual execution contract; broker-specific syntax stays in the adapter."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from twf.brokers.contracts import Credentials, Instrument
from twf.options.contracts import BrokerOptionMapping, OptionContract


class OrderSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset: Literal["equity", "futures", "options"] = "equity"
    exchange: Literal["NSE", "BSE", "BOTH"] = "NSE"
    q: str = Field(default="", max_length=80)
    underlying: str = Field(default="", max_length=80)
    expiry: str = Field(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    option_type: Literal["", "CE", "PE"] = ""
    strike: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    page: int = Field(default=1, ge=1, le=10000)


class Choices(BaseModel):
    underlyings: list[str]
    expiries: list[str]
    option_types: list[str]
    strikes: list[Decimal]
    instruments: list[Instrument]
    total: int
    page: int


class TypeRule(BaseModel):
    name: str
    price_required: bool
    trigger_required: bool
    validities: list[str]


class BrokerCapabilities(BaseModel):
    supports_equity: bool
    supports_futures: bool
    supports_options: bool
    option_buy_supported: bool
    option_sell_supported: bool
    intraday_product_support: bool
    overnight_product_support: bool


class Capability(BaseModel):
    enabled: bool
    products: list[str] = Field(default_factory=list)
    order_types: list[TypeRule] = Field(default_factory=list)
    instrument: Instrument | None = None
    quantity_unit: Literal["shares", "lots"] = "shares"
    max_quantity: int = 1000000
    broker: BrokerCapabilities = Field(
        default_factory=lambda: BrokerCapabilities(
            supports_equity=False,
            supports_futures=False,
            supports_options=False,
            option_buy_supported=False,
            option_sell_supported=False,
            intraday_product_support=False,
            overnight_product_support=False,
        )
    )


class OrderDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str = Field(min_length=1, max_length=200)
    native_token: str = Field(pattern=r"^[0-9]{1,20}$")
    side: Literal["BUY", "SELL"]
    product: str = Field(max_length=12)
    order_type: str = Field(max_length=12)
    quantity: int = Field(gt=0, le=1000000, strict=True)
    lots: int | None = Field(default=None, gt=0, le=1000000, strict=True)
    price: Decimal | None = Field(
        default=None,
        gt=0,
        lt=1000000000,
        max_digits=17,
        decimal_places=8,
        allow_inf_nan=False,
    )
    trigger_price: Decimal | None = Field(
        default=None, gt=0, lt=1000000000, max_digits=17, decimal_places=8, allow_inf_nan=False
    )
    validity: str = Field(max_length=8)


class IntentView(BaseModel):
    id: UUID
    account_id: UUID
    account_name: str
    instrument: Instrument
    order: OrderDraft
    source: Literal["BROKER_WORKSPACE"] = "BROKER_WORKSPACE"
    execution_authority: Literal["MANUAL_USER"] = "MANUAL_USER"
    status: Literal["PREVIEWED", "SUBMITTING", "SUBMITTED", "BROKER_REJECTED", "SUBMISSION_UNKNOWN"]
    created_at: datetime
    expires_at: datetime
    submitted_at: datetime | None
    broker_order_id: str | None
    provider_status: str | None
    failure: str | None
    instrument_type: Literal["EQUITY", "FUTURE", "OPTION"]
    option_contract: OptionContract | None = None
    broker_option_mapping: BrokerOptionMapping | None = None
    warnings: list[str] = Field(default_factory=list)
    reference_price: Decimal | None = None
    estimated_value: Decimal | None = None
    premium_outlay: Decimal | None = None
    estimated_margin: Decimal | None = None
    margin_status: Literal["AVAILABLE", "UNAVAILABLE"] = "UNAVAILABLE"
    available_cash: Decimal | None = None


@runtime_checkable
class ExecutionAdapter(Protocol):
    async def execution_catalog(self, credentials: Credentials) -> list[Instrument]: ...
    def execution_capabilities(self) -> BrokerCapabilities: ...
    def order_capability(self, instrument: Instrument) -> Capability: ...
    async def reference_price(
        self, credentials: Credentials, instrument: Instrument
    ) -> Decimal | None: ...
    async def estimate_margin(
        self, credentials: Credentials, instrument: Instrument, order: OrderDraft
    ) -> Decimal | None: ...
    async def place_order(
        self, credentials: Credentials, instrument: Instrument, order: OrderDraft, tag: str
    ) -> str: ...
