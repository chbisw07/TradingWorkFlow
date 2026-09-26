"""Versioned broker read models; no command or provider-native payloads."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Health(StrEnum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class FailureCode(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    DENIED = "DENIED"
    INCOMPATIBLE = "INCOMPATIBLE"


class BrokerFailure(Exception):
    def __init__(self, code: FailureCode) -> None:
        self.code = code
        super().__init__(code.value)


class BrokerProvider(Contract):
    provider_id: str
    name: str


class BrokerCapability(Contract):
    dashboard: Literal[True] = True
    holdings: Literal[True] = True
    positions: Literal[True] = True
    orders: Literal[True] = True
    funds: Literal[True] = True
    commands: Literal[False] = False


class AccountMode(StrEnum):
    SYNTHETIC = "SYNTHETIC"
    SANDBOX = "SANDBOX"
    LIVE = "LIVE"


class BrokerAccount(Contract):
    broker_account_id: UUID
    provider_id: str
    owner_user_id: UUID
    label: str
    mode: AccountMode = AccountMode.SYNTHETIC
    capabilities: BrokerCapability = BrokerCapability()


class OperationHealth(Contract):
    connection: Literal["CONNECTED", "AUTH_EXPIRED", "UNAVAILABLE"]
    read: Health
    error: FailureCode | None = None


class ObservationMetadata(Contract):
    source: str
    broker_account_id: UUID
    source_as_of: AwareDatetime | None
    fetched_at: AwareDatetime
    health: Health
    freshness: Literal["FRESH", "STALE", "UNKNOWN"]
    completeness: Literal["COMPLETE", "PARTIAL", "MISSING"]
    revision: Annotated[
        str,
        StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
    ]
    freshness_policy_seconds: int


class Instrument(Contract):
    canonical_id: str | None
    exchange: str
    broker_symbol: str
    native_id: str
    currency: Literal["INR"] = "INR"
    quantity_unit: Literal["SHARES"] = "SHARES"


class Holding(Contract):
    instrument: Instrument
    quantity: Decimal
    average_cost: Decimal
    last_price: Decimal
    current_value: Decimal
    pnl: Decimal
    pnl_percent: Decimal | None


class Position(Contract):
    instrument: Instrument
    product: str
    quantity: Decimal
    average_price: Decimal
    last_price: Decimal
    realized_pnl: Decimal | None
    unrealized_pnl: Decimal | None
    broker_state: str


class BrokerOrder(Contract):
    broker_order_id: str
    instrument: Instrument
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    price: Decimal | None
    status: Literal[
        "OPEN", "PENDING", "PARTIALLY_FILLED", "COMPLETE", "REJECTED", "CANCELLED", "UNKNOWN"
    ]
    observed_at: AwareDatetime
    reason: str | None = None


class FundsSnapshot(Contract):
    currency: Literal["INR"] = "INR"
    available_cash: Decimal | None
    used_margin: Decimal | None
    collateral: Decimal | None


class HoldingsDataset(Contract):
    metadata: ObservationMetadata
    rows: tuple[Holding, ...] | None


class PositionsDataset(Contract):
    metadata: ObservationMetadata
    rows: tuple[Position, ...] | None


class OrdersDataset(Contract):
    metadata: ObservationMetadata
    rows: tuple[BrokerOrder, ...] | None


class FundsDataset(Contract):
    metadata: ObservationMetadata
    values: FundsSnapshot | None


class BrokerSnapshot(Contract):
    contract_version: Literal["broker.read.v1"] = "broker.read.v1"
    request_id: str
    account: BrokerAccount
    operation: OperationHealth
    holdings: HoldingsDataset
    positions: PositionsDataset
    orders: OrdersDataset
    funds: FundsDataset


class PositionContribution(Contract):
    broker_account_id: UUID
    quantity: Decimal
    metadata: ObservationMetadata


class CanonicalPositionAggregate(Contract):
    canonical_id: str
    exchange: str
    product: str
    currency: str
    quantity_unit: str
    quantity: Decimal
    contributions: tuple[PositionContribution, ...]
    qualified: bool


class UnifiedBrokerSnapshot(Contract):
    contract_version: Literal["broker.read.v1"] = "broker.read.v1"
    providers: tuple[BrokerProvider, ...]
    accounts: tuple[BrokerSnapshot, ...]
    position_aggregates: tuple[CanonicalPositionAggregate, ...]
    unmapped_position_count: int
    missing_position_accounts: int
    scenario_time: AwareDatetime


class BrokerReadClient(Protocol):
    def read(self, account: BrokerAccount, request_id: str, now: datetime) -> BrokerSnapshot: ...
