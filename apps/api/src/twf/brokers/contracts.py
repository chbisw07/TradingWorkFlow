from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class BrokerFailure(Exception):
    def __init__(self, code: str, message: str, status: int = 502) -> None:
        super().__init__(code)
        self.code, self.message, self.status = code, message, status


class Credentials(BaseModel):
    api_key: SecretStr
    api_secret: SecretStr
    access_token: SecretStr | None = None


class Binding(BaseModel):
    identity: str
    access_token: SecretStr


class Account(BaseModel):
    id: UUID
    provider: str
    name: str
    identity: str | None
    state: Literal["configured", "connecting", "connected", "reauth_required", "disconnected"]
    health: Literal["unknown", "healthy", "degraded"]
    generation: int
    updated_at: datetime
    last_read_at: datetime | None


class Provider(BaseModel):
    id: str
    name: str
    supported: bool = False


class Instrument(BaseModel):
    symbol: str
    exchange: str
    reference: str
    native_token: str | None = None
    name: str | None = None
    underlying: str | None = None
    expiry: str | None = None
    strike: Decimal | None = None
    kind: str | None = None
    segment: str | None = None
    lot_size: Decimal | None = None
    tick_size: Decimal | None = None
    canonical_id: str | None = None
    underlying_type: Literal["INDEX", "EQUITY", "UNKNOWN"] | None = None
    option_type: Literal["CE", "PE"] | None = None
    currency: str | None = None
    is_active: bool | None = None
    last_trading_date: str | None = None
    freeze_quantity: int | None = None
    contract_multiplier: Decimal | None = None


class Holding(BaseModel):
    instrument: Instrument
    quantity: Decimal | None
    average: Decimal | None
    last_price: Decimal | None
    value: Decimal | None
    pnl: Decimal | None
    pnl_percent: Decimal | None


class Position(BaseModel):
    instrument: Instrument
    ownership: Literal["BROKER_EXTERNAL"] = "BROKER_EXTERNAL"
    managed: Literal[False] = False
    product: str | None
    quantity: Decimal | None
    average: Decimal | None
    last_price: Decimal | None
    realized: Decimal | None
    unrealized: Decimal | None
    pnl: Decimal | None


class Order(BaseModel):
    id: str
    instrument: Instrument
    time: str | None
    side: str | None
    quantity: Decimal | None
    kind: str | None
    price: Decimal | None
    status: str | None
    tag: str | None = None
    product: str | None = None
    validity: str | None = None
    trigger_price: Decimal | None = None


class Funds(BaseModel):
    segment: str
    enabled: bool
    cash: Decimal | None
    used_margin: Decimal | None
    available_margin: Decimal | None
    collateral: Decimal | None


class Overview(BaseModel):
    cash: Decimal | None
    holdings_value: Decimal | None
    positions: int | None
    open_orders: int | None


class Search(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(default="", max_length=80)
    underlying: str = Field(default="", max_length=80)
    expiry: str = Field(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    strike: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    kind: Literal["", "EQ", "CE", "PE", "FUT"] = ""
    page: int = Field(default=1, ge=1, le=10000)
    limit: int = Field(default=50, ge=1, le=100)


class CatalogPage(BaseModel):
    items: list[Instrument]
    total: int
    page: int
    limit: int
    fetched_at: datetime


class Snapshot[T](BaseModel):
    account: Account
    fetched_at: datetime
    data: T


class BrokerAdapter(Protocol):
    async def authenticate(self, credentials: Credentials, request_token: str) -> Binding: ...
    async def get_profile(self, credentials: Credentials) -> str: ...
    async def get_holdings(self, credentials: Credentials) -> list[Holding]: ...
    async def get_positions(self, credentials: Credentials) -> list[Position]: ...
    async def get_orders(self, credentials: Credentials) -> list[Order]: ...
    async def get_funds(self, credentials: Credentials) -> list[Funds]: ...
    async def search_instruments(self, credentials: Credentials, query: Search) -> CatalogPage: ...
    async def disconnect(self, credentials: Credentials) -> None: ...
