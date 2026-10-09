"""Provider-neutral option identity and exact broker mapping contracts."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OptionType(StrEnum):
    CE = "CE"
    PE = "PE"

    @classmethod
    def _missing_(cls, value: object) -> "OptionType | None":
        if isinstance(value, str):
            return {"CALL": cls.CE, "PUT": cls.PE}.get(value.strip().upper())
        return None


class UnderlyingType(StrEnum):
    INDEX = "INDEX"
    EQUITY = "EQUITY"
    UNKNOWN = "UNKNOWN"


def strike_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def option_contract_id(
    exchange: str, underlying_symbol: str, expiry: date, strike: Decimal, option_type: OptionType
) -> str:
    """Structural identity; broker symbols and tokens are deliberately excluded."""
    return ":".join(
        (
            exchange.upper(),
            underlying_symbol.strip().upper(),
            expiry.isoformat(),
            strike_text(strike),
            option_type.value,
        )
    )


class OptionContractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exchange: str = Field(min_length=1, max_length=12)
    underlying_symbol: str = Field(min_length=1, max_length=80)
    expiry: date
    strike: Decimal = Field(gt=0, allow_inf_nan=False)
    option_type: OptionType

    @field_validator("exchange", "underlying_symbol")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip().upper()


class OptionContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_id: str = Field(min_length=1, max_length=180)
    exchange: str = Field(min_length=1, max_length=12)
    segment: str = Field(min_length=1, max_length=24)
    underlying_symbol: str = Field(min_length=1, max_length=80)
    underlying_type: UnderlyingType = UnderlyingType.UNKNOWN
    expiry: date
    strike: Decimal = Field(gt=0, allow_inf_nan=False)
    option_type: OptionType
    lot_size: int = Field(gt=0)
    display_symbol: str = Field(min_length=1, max_length=180)
    tick_size: Decimal = Field(gt=0, allow_inf_nan=False)
    freeze_quantity: int | None = Field(default=None, gt=0)
    contract_multiplier: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    is_active: bool = True
    last_trading_date: date | None = None

    @field_validator("exchange", "segment", "underlying_symbol", "currency")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        expected = option_contract_id(
            self.exchange,
            self.underlying_symbol,
            self.expiry,
            self.strike,
            self.option_type,
        )
        if self.canonical_id != expected:
            raise ValueError("Option canonical_id does not match structural identity")
        if self.last_trading_date and self.last_trading_date > self.expiry:
            raise ValueError("Last trading date cannot be after expiry")
        return self


class BrokerOptionMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=32)
    canonical_id: str = Field(min_length=1, max_length=180)
    exchange: str = Field(min_length=1, max_length=12)
    trading_symbol: str = Field(min_length=1, max_length=120)
    native_token: str = Field(min_length=1, max_length=40)
    reference: str = Field(min_length=1, max_length=200)
    lot_size: int = Field(gt=0)
    tick_size: Decimal = Field(gt=0, allow_inf_nan=False)
    resolved_at: datetime
    master_version: str | None = Field(default=None, max_length=80)


class ResolvedOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: OptionContract
    mapping: BrokerOptionMapping
