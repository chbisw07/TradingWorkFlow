"""Additive provider-neutral native observations; broker.read.v1 stays frozen."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from twf.brokers.contracts import Contract
from twf.secrets import SecretValue

DatasetName = Literal["holdings", "positions"]
ReadFailureCode = Literal[
    "AUTH_REQUIRED",
    "AUTH_EXPIRED",
    "STALE_CONNECTION",
    "TIMEOUT",
    "RATE_LIMITED",
    "UNAVAILABLE",
    "INVALID_RESPONSE",
    "TOO_LARGE",
    "PARTIAL_RESPONSE",
]


class PortfolioFailure(Exception):
    def __init__(self, code: ReadFailureCode):
        self.code = code
        super().__init__(code)


class NativeIdentity(Contract):
    native_id: str
    symbol: str
    exchange: str
    canonical_id: UUID | None = None
    catalog_version: UUID | None = None
    catalog_fingerprint: str | None = None
    instrument_fingerprint: str | None = None
    catalog_state: Literal["FRESH", "STALE", "UNAVAILABLE", "UNMAPPED"] = "UNAVAILABLE"
    name: str | None = None
    segment: str | None = None
    instrument_type: str | None = None
    expiry: date | None = None
    strike: Decimal | None = None
    derivative_kind: Literal["CE", "PE", "FUT"] | None = None
    lot_size: int | None = None
    tick_size: Decimal | None = None


class NativeObservation(Contract):
    instrument: NativeIdentity
    product: str
    product_known: bool
    quantity: Decimal
    average_price: Decimal | None = None
    last_price: Decimal | None = None
    close_price: Decimal | None = None
    pnl: Decimal | None = None
    current_value: Decimal | None = None
    pnl_percent: Decimal | None = None
    used_quantity: Decimal | None = None
    available_quantity: Decimal | None = None
    unsettled_quantity: Decimal | None = None
    settled_quantity: Decimal | None = None
    authorised_quantity: Decimal | None = None
    collateral_quantity: Decimal | None = None
    collateral_type: str | None = None
    financed_quantity: Decimal | None = None
    financed_value: Decimal | None = None
    day_change: Decimal | None = None
    day_change_percent: Decimal | None = None
    overnight_quantity: Decimal | None = None
    buy_quantity: Decimal | None = None
    sell_quantity: Decimal | None = None
    buy_average: Decimal | None = None
    sell_average: Decimal | None = None
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    multiplier: Decimal | None = None


class ProviderObservation(Contract):
    rows: tuple[NativeObservation, ...]
    activity_rows: tuple[NativeObservation, ...] = ()
    received_at: datetime
    rejected_rows: int = 0
    total_rows: int


class ReadMetadata(Contract):
    provider_id: str
    broker_account_id: UUID
    source: str
    source_as_of: datetime | None = None
    attempted_at: datetime
    received_at: datetime | None = None
    connection_generation: int
    freshness: Literal["FRESH", "STALE", "UNKNOWN"]
    freshness_policy_seconds: int
    health: Literal["AVAILABLE", "DEGRADED", "UNAVAILABLE"]
    completeness: Literal["COMPLETE", "PARTIAL", "MISSING"]
    failure_code: ReadFailureCode | None = None
    rejected_rows: int = 0
    total_rows: int | None = None


class NativeDataset(Contract):
    metadata: ReadMetadata
    rows: tuple[NativeObservation, ...] | None
    activity_rows: tuple[NativeObservation, ...] | None = None


class PortfolioSummary(Contract):
    holdings_count: int | None
    holdings_value: Decimal | None
    open_positions_count: int | None
    realized_pnl: Decimal | None
    unrealized_pnl: Decimal | None
    position_pnl: Decimal | None


class NativePortfolio(Contract):
    contract_version: Literal["broker.native-read.v1"] = "broker.native-read.v1"
    broker_account_id: UUID
    provider_id: str
    account_label: str
    connection_state: str
    holdings: NativeDataset
    positions: NativeDataset
    summary: PortfolioSummary
    trading_enabled: Literal[False] = False
    orders_available: Literal[False] = False
    funds_available: Literal[False] = False


class PortfolioProvider(Protocol):
    def read(
        self, dataset: DatasetName, api_key: str, token: SecretValue
    ) -> ProviderObservation: ...
