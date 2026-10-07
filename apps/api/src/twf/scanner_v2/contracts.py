"""Versioned explicit daily filters, immutable run input, bounded universe."""

from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from twf.integrations.contracts import Contract

FIELDS = {
    "ltp": ("Price & Volume", "LTP (Dhan quote snapshot)"),
    "price": ("Price & Volume", "Completed close"),
    "change": ("Price & Volume", "1D change %"),
    "gap": ("Price & Volume", "Opening gap %"),
    "volume": ("Price & Volume", "Volume"),
    "average_volume": ("Price & Volume", "Prior 20-day average volume"),
    "rvol": ("Price & Volume", "Relative volume (20)"),
    "rsi": ("Technical Indicators", "RSI (14)"),
    "sma20": ("Technical Indicators", "SMA (20)"),
    "sma50": ("Technical Indicators", "SMA (50)"),
    "ema20": ("Technical Indicators", "EMA (20)"),
    "macd": ("Technical Indicators", "MACD (12,26)"),
    "macd_signal": ("Technical Indicators", "MACD signal (9)"),
    "adx": ("Technical Indicators", "ADX (14)"),
    "atr": ("Technical Indicators", "ATR (14)"),
    "bb_upper": ("Technical Indicators", "Bollinger upper (20,2)"),
    "bb_lower": ("Technical Indicators", "Bollinger lower (20,2)"),
    "stochastic": ("Technical Indicators", "Stochastic %K (14)"),
    "trend": ("Trend & Momentum", "Trend versus SMA20"),
    "roc": ("Trend & Momentum", "10-day momentum %"),
    "supertrend": ("Trend & Momentum", "Supertrend direction (10,3)"),
    "high20": ("Breakouts & Patterns", "Prior 20-day high"),
    "low20": ("Breakouts & Patterns", "Prior 20-day low"),
    "range_ratio": ("Breakouts & Patterns", "Range / ATR (14)"),
    "high252": ("Support / Resistance", "Prior 252-session high"),
    "low252": ("Support / Resistance", "Prior 252-session low"),
    "pivot": ("Support / Resistance", "Prior-session pivot"),
    "resistance": ("Support / Resistance", "Pivot resistance R1"),
    "support": ("Support / Resistance", "Pivot support S1"),
    "sma_distance": ("Support / Resistance", "Distance from SMA20 %"),
    "high252_distance": ("Support / Resistance", "Distance from prior 252-session high %"),
    "low252_distance": ("Support / Resistance", "Distance from prior 252-session low %"),
    "market_cap_inr": ("Fundamentals (TapTide)", "Market cap (INR)"),
    "pe_ratio": ("Fundamentals (TapTide)", "PE ratio"),
}
Operator = Literal[">", ">=", "<", "<=", "equals", "between", "crosses_above", "crosses_below"]


class Filter(Contract):
    field: str
    operator: Operator = ">"
    value: float | str | tuple[float, float]
    timeframe: Literal["1d"] = "1d"
    version: Literal["1"] = "1"
    source: Literal["internal", "tapetide"] = "internal"

    @model_validator(mode="after")
    def valid(self) -> Self:
        import math

        fundamental = self.field in {"market_cap_inr", "pe_ratio"}
        if self.source != ("tapetide" if fundamental else "internal"):
            raise ValueError("Filter source does not match its capability")
        if self.field == "ltp" and self.operator in {"crosses_above", "crosses_below"}:
            raise ValueError("Quote snapshot crossovers are unavailable")
        if fundamental and self.operator in {"crosses_above", "crosses_below"}:
            raise ValueError("Historical fundamental crossovers are unavailable")
        if self.field not in FIELDS:
            raise ValueError("Unsupported filter field")
        if isinstance(self.value, str):
            allowed = {"Up", "Down", "Sideways"} if self.field == "trend" else {"Up", "Down"}
            if self.field in {"trend", "supertrend"}:
                if self.operator != "equals" or self.value not in allowed:
                    raise ValueError("Direction requires equals and a supported direction")
            elif self.value not in FIELDS or self.value in {"trend", "supertrend"}:
                raise ValueError("Unknown comparison field")
        elif self.field in {"trend", "supertrend"}:
            raise ValueError("Direction requires a text value")
        elif isinstance(self.value, tuple):
            if self.operator != "between" or self.value[0] > self.value[1]:
                raise ValueError("Between requires an ordered pair")
            if not all(math.isfinite(v) for v in self.value):
                raise ValueError("Filter values must be finite")
        elif not math.isfinite(self.value):
            raise ValueError("Filter values must be finite")
        if self.value == self.field:
            raise ValueError("A field cannot be compared with itself")
        if isinstance(self.value, str) and self.value in {"market_cap_inr", "pe_ratio"}:
            raise ValueError("Fundamentals require an explicit numeric threshold")
        if self.operator == "between" and not isinstance(self.value, tuple):
            raise ValueError("Between requires two numbers")
        if self.field in {"rsi", "adx", "stochastic"} and isinstance(self.value, (float, tuple)):
            values = self.value if isinstance(self.value, tuple) else (self.value,)
            if any(not 0 <= v <= 100 for v in values):
                raise ValueError("Oscillator thresholds must be between 0 and 100")
        return self


class UniverseSource(Contract):
    source: Literal["WATCHLIST", "INDEX", "SECTOR", "MARKET", "CUSTOM"] = "CUSTOM"
    watchlist_id: UUID | None = None
    symbols: tuple[str, ...] = Field(default=(), max_length=20)
    instrument_ids: tuple[UUID, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def valid(self) -> Self:
        import re

        if self.source == "WATCHLIST" and self.watchlist_id is None:
            raise ValueError("Choose a watchlist")
        if self.source == "CUSTOM" and not self.symbols:
            raise ValueError("Enter at least one symbol")
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("Remove duplicate symbols")
        if any(not re.fullmatch(r"[A-Z0-9][A-Z0-9&. _-]{0,49}", s) for s in self.symbols):
            raise ValueError("Use canonical uppercase NSE symbols")
        return self


class ScanConfig(Contract):
    name: str = Field(default="Untitled scan", min_length=1, max_length=80)
    scanner_type: Literal["EQUITY_INDEX"] = "EQUITY_INDEX"
    data_mode: Literal["REAL"] = "REAL"
    provider: Literal["dhan"] = "dhan"
    universe: UniverseSource
    filters: tuple[Filter, ...] = Field(min_length=1, max_length=12)
    sort: Literal["symbol", "change", "volume", "rsi", "relevance"] = "symbol"
    version: Literal["1"] = "1"

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({f.model_dump_json() for f in self.filters}) != len(self.filters):
            raise ValueError("Duplicate filters")
        return self


class SavedInput(Contract):
    config: ScanConfig
    archived: bool = False
