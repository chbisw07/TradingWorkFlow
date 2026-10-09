"""Canonical read-only chain contracts. No provider tokens or execution authority."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from twf.options.contracts import OptionContract, OptionType

Number = Annotated[Decimal, Field(allow_inf_nan=False)]
NonNegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
Support = Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED"]
Moneyness = Literal["ITM", "ATM", "OTM"]


class ChainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OptionChainRequest(ChainModel):
    underlying: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9&._ -]+$")
    expiry: date
    around_atm: int = Field(default=10, ge=0, le=25)
    strike_min: Positive | None = None
    strike_max: Positive | None = None
    side: OptionType | None = None

    @field_validator("underlying")
    @classmethod
    def normalize(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("Underlying is required")
        return value

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if self.strike_min is not None and self.strike_max is not None:
            if self.strike_min > self.strike_max:
                raise ValueError("Inverted strike range")
        return self


class OptionChainCapabilities(ChainModel):
    provider: str
    contracts: Support
    quotes: Support
    bid_ask: Support
    volume: Support
    open_interest: Support
    oi_change: Support
    iv: Support
    greeks: Support


class OptionMarketSnapshot(ChainModel):
    ltp: NonNegative | None = None
    bid: NonNegative | None = None
    ask: NonNegative | None = None
    bid_quantity: NonNegative | None = None
    ask_quantity: NonNegative | None = None
    spread: NonNegative | None = None
    spread_percent: NonNegative | None = None
    volume: NonNegative | None = None
    open_interest: NonNegative | None = None
    previous_open_interest: NonNegative | None = None
    change_in_open_interest: Number | None = None
    implied_volatility: NonNegative | None = None
    delta: Number | None = None
    gamma: NonNegative | None = None
    theta: Number | None = None
    vega: NonNegative | None = None
    source_time: AwareDatetime | None = None


class OptionChainProvenance(ChainModel):
    provider: str
    contract_source: str
    market_source: str
    master_received_at: AwareDatetime
    received_at: AwareDatetime
    source_time: AwareDatetime | None = None
    freshness: Literal["FRESH", "STALE", "SOURCE_TIME_UNAVAILABLE", "UNAVAILABLE"]
    quote_ttl_seconds: int
    cached: bool = False
    oi_unit: str = "contracts"
    iv_unit: str = "percent"


class OptionLegSnapshot(ChainModel):
    contract: OptionContract
    moneyness: Moneyness | None
    market: OptionMarketSnapshot
    availability: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"]
    warnings: tuple[str, ...] = ()


class OptionChainRow(ChainModel):
    strike: Positive
    is_atm: bool | None
    distance_from_spot: Number | None
    distance_percent: Number | None
    ce: OptionLegSnapshot | None
    pe: OptionLegSnapshot | None


class OptionChainSnapshot(ChainModel):
    underlying: str
    spot: Positive | None
    expiry: date
    dte: int = Field(ge=0)
    as_of: AwareDatetime
    atm_strike: Positive | None
    rows: tuple[OptionChainRow, ...] = Field(max_length=51)
    status: Literal["COMPLETE", "PARTIAL"]
    capabilities: OptionChainCapabilities
    provenance: OptionChainProvenance
    warnings: tuple[str, ...] = ()
    missing_capabilities: tuple[str, ...] = ()
