"""Provider-neutral native instrument catalog contract; no execution authority."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from twf.secrets import SecretValue

Text = Annotated[str, StringConstraints(max_length=128, pattern=r"^[^\x00-\x1f\x7f]*$")]
FailureCode = Literal[
    "TIMEOUT",
    "UNAVAILABLE",
    "AUTH_REQUIRED",
    "RATE_LIMITED",
    "INVALID_RESPONSE",
    "PARTIAL_RESPONSE",
    "EMPTY",
    "TOO_LARGE",
    "STALE_CONNECTION",
]
Kind = Literal["CE", "PE", "FUT"]


class NativeInstrument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    native_id: str
    exchange_id: str | None
    symbol: str
    name: str | None
    exchange: str
    segment: str
    instrument_type: str
    expiry: date | None
    strike: Decimal | None
    derivative_kind: Kind | None
    lot_size: int
    tick_size: Decimal
    canonical_id: UUID | None = None
    fingerprint: str


class CatalogPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    instruments: tuple[NativeInstrument, ...]
    fingerprint: str
    fetched_at: datetime
    source_at: datetime | None = None
    total_rows: int


class CatalogFailure(Exception):
    def __init__(self, code: FailureCode, total: int = 0, accepted: int = 0, rejected: int = 0):
        self.code, self.total, self.accepted, self.rejected = code, total, accepted, rejected
        super().__init__(code)


class CatalogProvider(Protocol):
    def fetch(self, api_key: str, token: SecretValue) -> CatalogPayload: ...


class InstrumentQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Text = ""
    exchange: Text = ""
    segment: Text = ""
    instrument_type: Text = ""
    expiry: date | None = None
    strike: Decimal | None = Field(default=None, ge=0, le=1_000_000_000_000, decimal_places=8)
    derivative_kind: Kind | None = None
    name: Text = ""
    symbol: Text = ""
    version: UUID | None = Field(
        default=None, description="Catalog snapshot; required when offset is greater than zero."
    )
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)

    @model_validator(mode="after")
    def require_continuation_version(self) -> Self:
        if self.offset > 0 and self.version is None:
            raise ValueError("A catalog version is required for continuation pages.")
        return self


class CatalogStatus(BaseModel):
    contract_version: Literal["broker.catalog.v1"] = "broker.catalog.v1"
    broker_account_id: UUID
    account_label: str
    provider_id: str
    version: UUID | None = None
    fingerprint: str | None = None
    freshness: Literal["FRESH", "STALE", "UNKNOWN", "UNAVAILABLE"]
    completeness: Literal["COMPLETE", "PARTIAL", "UNKNOWN"] = "UNKNOWN"
    fetched_at: datetime | None = None
    verified_at: datetime | None = None
    source_at: datetime | None = None
    source: str = "Kite instrument master"
    source_freshness: Literal["UNKNOWN"] = "UNKNOWN"
    freshness_policy: str = "Daily 08:30 Asia/Kolkata acquisition; two-hour grace"
    row_count: int = 0
    last_attempt_at: datetime | None = None
    failure_code: FailureCode | None = None
    attempt_total_rows: int = 0
    attempt_accepted_rows: int = 0
    attempt_rejected_rows: int = 0
    attempt_completeness: Literal["COMPLETE", "PARTIAL", "UNKNOWN"] = "UNKNOWN"
    refreshing: bool = False
    can_refresh: bool = False
    trading_enabled: Literal[False] = False


class InstrumentResult(NativeInstrument):
    id: UUID
    provider_id: str
    catalog_version: UUID


class CatalogSearch(BaseModel):
    catalog: CatalogStatus
    instruments: tuple[InstrumentResult, ...]
    matched: int
    limit: int
    offset: int
