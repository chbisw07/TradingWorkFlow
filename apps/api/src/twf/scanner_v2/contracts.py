"""Versioned typed daily filters, immutable run input, bounded universe."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from twf.integrations.contracts import Contract

Operator = Literal[
    ">",
    ">=",
    "<",
    "<=",
    "equals",
    "not_equals",
    "between",
    "crosses_above",
    "crosses_below",
]


class FilterFieldType(StrEnum):
    NUMBER = "NUMBER"
    PRICE = "PRICE"
    PERCENT = "PERCENT"
    VOLUME = "VOLUME"
    RATIO = "RATIO"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"
    DIRECTION = "DIRECTION"


class ContextMode(StrEnum):
    OFF = "OFF"
    RANKING = "RANKING"
    HARD_FILTER = "HARD_FILTER"


NUMERIC_OPERATORS: tuple[Operator, ...] = (
    ">",
    ">=",
    "<",
    "<=",
    "equals",
    "not_equals",
    "between",
    "crosses_above",
    "crosses_below",
)
LITERAL_NUMERIC_OPERATORS: tuple[Operator, ...] = (
    ">",
    ">=",
    "<",
    "<=",
    "equals",
    "not_equals",
    "between",
)
ENUM_OPERATORS: tuple[Operator, ...] = ("equals", "not_equals")


@dataclass(frozen=True, slots=True)
class FilterFieldSpec:
    category: str
    label: str
    field_type: FilterFieldType
    operators: tuple[Operator, ...]
    default_operator: Operator
    default_value: float | str
    comparison_type: FilterFieldType | None = None
    comparison_fields: tuple[str, ...] = ()
    enum_values: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    minimum_exclusive: bool = False
    unit: str | None = None


def _price(category: str, label: str) -> FilterFieldSpec:
    return FilterFieldSpec(
        category,
        label,
        FilterFieldType.PRICE,
        NUMERIC_OPERATORS,
        ">",
        0,
        comparison_type=FilterFieldType.PRICE,
        minimum=0,
        unit="INR",
    )


def _percent(category: str, label: str) -> FilterFieldSpec:
    return FilterFieldSpec(
        category,
        label,
        FilterFieldType.PERCENT,
        NUMERIC_OPERATORS,
        ">",
        0,
        comparison_type=FilterFieldType.PERCENT,
        unit="PERCENT",
    )


FIELD_SPECS: dict[str, FilterFieldSpec] = {
    "ltp": FilterFieldSpec(
        "Price & Volume",
        "LTP (Dhan quote snapshot)",
        FilterFieldType.PRICE,
        LITERAL_NUMERIC_OPERATORS,
        ">",
        0,
        comparison_type=FilterFieldType.PRICE,
        minimum=0,
        unit="INR",
    ),
    "price": _price("Price & Volume", "Completed close"),
    "change": _percent("Price & Volume", "1D change %"),
    "gap": _percent("Price & Volume", "Opening gap %"),
    "volume": FilterFieldSpec(
        "Price & Volume",
        "Volume",
        FilterFieldType.VOLUME,
        NUMERIC_OPERATORS,
        ">",
        1000000,
        comparison_type=FilterFieldType.VOLUME,
        minimum=0,
        unit="VOLUME",
    ),
    "average_volume": FilterFieldSpec(
        "Price & Volume",
        "Prior 20-day average volume",
        FilterFieldType.VOLUME,
        NUMERIC_OPERATORS,
        ">",
        1000000,
        comparison_type=FilterFieldType.VOLUME,
        minimum=0,
        unit="VOLUME",
    ),
    "rvol": FilterFieldSpec(
        "Price & Volume",
        "Relative volume (20)",
        FilterFieldType.RATIO,
        LITERAL_NUMERIC_OPERATORS,
        ">=",
        1.5,
        minimum=0,
        minimum_exclusive=True,
        unit="RATIO",
    ),
    "rsi": FilterFieldSpec(
        "Technical Indicators",
        "RSI (14)",
        FilterFieldType.NUMBER,
        LITERAL_NUMERIC_OPERATORS,
        ">",
        50,
        minimum=0,
        maximum=100,
    ),
    "sma20": _price("Technical Indicators", "SMA (20)"),
    "sma50": _price("Technical Indicators", "SMA (50)"),
    "ema20": _price("Technical Indicators", "EMA (20)"),
    "macd": FilterFieldSpec(
        "Technical Indicators",
        "MACD (12,26)",
        FilterFieldType.NUMBER,
        NUMERIC_OPERATORS,
        ">",
        0,
        comparison_fields=("macd_signal",),
    ),
    "macd_signal": FilterFieldSpec(
        "Technical Indicators",
        "MACD signal (9)",
        FilterFieldType.NUMBER,
        NUMERIC_OPERATORS,
        ">",
        0,
        comparison_fields=("macd",),
    ),
    "adx": FilterFieldSpec(
        "Technical Indicators",
        "ADX (14)",
        FilterFieldType.NUMBER,
        LITERAL_NUMERIC_OPERATORS,
        ">",
        25,
        minimum=0,
        maximum=100,
    ),
    "atr": _price("Technical Indicators", "ATR (14)"),
    "bb_upper": _price("Technical Indicators", "Bollinger upper (20,2)"),
    "bb_lower": _price("Technical Indicators", "Bollinger lower (20,2)"),
    "stochastic": FilterFieldSpec(
        "Technical Indicators",
        "Stochastic %K (14)",
        FilterFieldType.NUMBER,
        LITERAL_NUMERIC_OPERATORS,
        ">",
        50,
        minimum=0,
        maximum=100,
    ),
    "trend": FilterFieldSpec(
        "Trend & Momentum",
        "Trend versus SMA20",
        FilterFieldType.DIRECTION,
        ENUM_OPERATORS,
        "equals",
        "Up",
        enum_values=("Up", "Down", "Sideways"),
    ),
    "roc": _percent("Trend & Momentum", "10-day momentum %"),
    "supertrend": FilterFieldSpec(
        "Trend & Momentum",
        "Supertrend direction (10,3)",
        FilterFieldType.ENUM,
        ENUM_OPERATORS,
        "equals",
        "Up",
        enum_values=("Up", "Down"),
    ),
    "high20": _price("Breakouts & Patterns", "Prior 20-day high"),
    "low20": _price("Breakouts & Patterns", "Prior 20-day low"),
    "range_ratio": FilterFieldSpec(
        "Breakouts & Patterns",
        "Range / ATR (14)",
        FilterFieldType.RATIO,
        LITERAL_NUMERIC_OPERATORS,
        ">",
        1,
        minimum=0,
        minimum_exclusive=True,
        unit="RATIO",
    ),
    "high252": _price("Support / Resistance", "Prior 252-session high"),
    "low252": _price("Support / Resistance", "Prior 252-session low"),
    "pivot": _price("Support / Resistance", "Prior-session pivot"),
    "resistance": _price("Support / Resistance", "Pivot resistance R1"),
    "support": _price("Support / Resistance", "Pivot support S1"),
    "sma_distance": _percent("Support / Resistance", "Distance from SMA20 %"),
    "high252_distance": _percent("Support / Resistance", "Distance from prior 252-session high %"),
    "low252_distance": _percent("Support / Resistance", "Distance from prior 252-session low %"),
    "market_cap_inr": FilterFieldSpec(
        "Fundamentals (TapTide)",
        "Market cap (INR)",
        FilterFieldType.NUMBER,
        LITERAL_NUMERIC_OPERATORS,
        ">",
        10000,
        minimum=0,
        minimum_exclusive=True,
        unit="INR",
    ),
    "pe_ratio": FilterFieldSpec(
        "Fundamentals (TapTide)",
        "PE ratio",
        FilterFieldType.RATIO,
        LITERAL_NUMERIC_OPERATORS,
        "<",
        25,
        unit="RATIO",
    ),
}

FIELDS = {key: (spec.category, spec.label) for key, spec in FIELD_SPECS.items()}

CONTEXT_FIELD_SPECS: dict[str, FilterFieldSpec] = {
    "broad_regime": FilterFieldSpec(
        "Market Context",
        "Broad market regime",
        FilterFieldType.ENUM,
        ENUM_OPERATORS,
        "equals",
        "BULLISH",
        enum_values=("STRONGLY_BULLISH", "BULLISH", "NEUTRAL", "BEARISH", "STRONGLY_BEARISH"),
    ),
    "sector_strength": FilterFieldSpec(
        "Market Context",
        "Sector strength",
        FilterFieldType.ENUM,
        ENUM_OPERATORS,
        "equals",
        "STRONG",
        enum_values=("STRONG", "SUPPORTIVE", "NEUTRAL", "WEAK"),
    ),
    "sector_rotation": FilterFieldSpec(
        "Market Context",
        "Sector rotation",
        FilterFieldType.ENUM,
        ENUM_OPERATORS,
        "equals",
        "IMPROVING",
        enum_values=("IMPROVING", "STABLE", "DETERIORATING"),
    ),
    "vix_state": FilterFieldSpec(
        "Market Context",
        "India VIX state",
        FilterFieldType.ENUM,
        ENUM_OPERATORS,
        "not_equals",
        "HIGH",
        enum_values=("LOW", "NORMAL", "ELEVATED", "HIGH"),
    ),
    "fii_state": FilterFieldSpec(
        "Market Context",
        "FII flow",
        FilterFieldType.ENUM,
        ENUM_OPERATORS,
        "equals",
        "POSITIVE",
        enum_values=("STRONGLY_POSITIVE", "POSITIVE", "MIXED", "NEGATIVE", "STRONGLY_NEGATIVE"),
    ),
    "dii_state": FilterFieldSpec(
        "Market Context",
        "DII flow",
        FilterFieldType.ENUM,
        ENUM_OPERATORS,
        "equals",
        "POSITIVE",
        enum_values=("STRONGLY_POSITIVE", "POSITIVE", "MIXED", "NEGATIVE", "STRONGLY_NEGATIVE"),
    ),
    "net_institutional_state": FilterFieldSpec(
        "Market Context",
        "Net institutional flow",
        FilterFieldType.ENUM,
        ENUM_OPERATORS,
        "equals",
        "POSITIVE",
        enum_values=("STRONGLY_POSITIVE", "POSITIVE", "MIXED", "NEGATIVE", "STRONGLY_NEGATIVE"),
    ),
    "breadth": FilterFieldSpec(
        "Market Context",
        "Market breadth",
        FilterFieldType.ENUM,
        ENUM_OPERATORS,
        "not_equals",
        "WEAK",
        enum_values=("STRONG", "POSITIVE", "MIXED", "WEAK"),
    ),
    "event_news_risk": FilterFieldSpec(
        "Market Context",
        "Event / news risk",
        FilterFieldType.ENUM,
        ENUM_OPERATORS,
        "not_equals",
        "HIGH_RISK",
        enum_values=("POSITIVE_CATALYST", "SUPPORTIVE", "NEUTRAL", "CAUTION", "HIGH_RISK"),
    ),
}


def compatible_comparison_fields(field: str) -> tuple[str, ...]:
    spec = FIELD_SPECS[field]
    if spec.comparison_fields:
        return spec.comparison_fields
    if spec.comparison_type is None:
        return ()
    return tuple(
        key
        for key, candidate in FIELD_SPECS.items()
        if key != field and candidate.field_type == spec.comparison_type
    )


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

        spec = FIELD_SPECS.get(self.field)
        if spec is None:
            raise ValueError("Unsupported filter field")
        fundamental = self.field in {"market_cap_inr", "pe_ratio"}
        if self.source != ("tapetide" if fundamental else "internal"):
            raise ValueError("Filter source does not match its capability")
        if self.operator not in spec.operators:
            raise ValueError(f"{spec.label} does not support operator {self.operator}")
        if self.value == self.field:
            raise ValueError("A field cannot be compared with itself")
        if self.operator == "between" and not isinstance(self.value, tuple):
            raise ValueError("Between requires two numbers")

        if isinstance(self.value, str):
            if spec.enum_values:
                if self.value not in spec.enum_values:
                    raise ValueError(f"{spec.label} requires a supported enum value")
            elif self.value not in compatible_comparison_fields(self.field):
                target = FIELD_SPECS.get(self.value)
                target_label = target.label if target else self.value
                raise ValueError(f"{spec.label} cannot be compared with field {target_label}")
        elif spec.enum_values:
            raise ValueError(f"{spec.label} requires a supported enum value")
        elif isinstance(self.value, tuple):
            if self.operator != "between" or self.value[0] > self.value[1]:
                raise ValueError("Between requires an ordered pair")
            if not all(math.isfinite(value) for value in self.value):
                raise ValueError("Filter values must be finite")
            self._validate_bounds(spec, self.value)
        else:
            if self.operator == "between":
                raise ValueError("Between requires two numbers")
            if not math.isfinite(self.value):
                raise ValueError("Filter values must be finite")
            self._validate_bounds(spec, (self.value,))
        return self

    @staticmethod
    def _validate_bounds(spec: FilterFieldSpec, values: tuple[float, ...]) -> None:
        if spec.minimum is not None and any(
            value <= spec.minimum if spec.minimum_exclusive else value < spec.minimum
            for value in values
        ):
            qualifier = "greater than" if spec.minimum_exclusive else "at least"
            raise ValueError(f"{spec.label} must be {qualifier} {spec.minimum:g}")
        if spec.maximum is not None and any(value > spec.maximum for value in values):
            raise ValueError(f"{spec.label} must be at most {spec.maximum:g}")


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


class ContextFilter(Contract):
    field: str
    operator: Literal["equals", "not_equals"] = "equals"
    value: str
    source: Literal["market_context"] = "market_context"
    version: Literal["1"] = "1"

    @model_validator(mode="after")
    def valid(self) -> Self:
        spec = CONTEXT_FIELD_SPECS.get(self.field)
        if (
            spec is None
            or self.operator not in spec.operators
            or self.value not in spec.enum_values
        ):
            raise ValueError("Unsupported Market Context predicate")
        return self


class ScanConfig(Contract):
    name: str = Field(default="Untitled scan", min_length=1, max_length=80)
    scanner_type: Literal["EQUITY_INDEX"] = "EQUITY_INDEX"
    data_mode: Literal["REAL"] = "REAL"
    provider: Literal["dhan"] = "dhan"
    universe: UniverseSource
    filters: tuple[Filter, ...] = Field(min_length=1, max_length=12)
    context_mode: ContextMode = ContextMode.RANKING
    context_filters: tuple[ContextFilter, ...] = Field(default=(), max_length=9)
    sort: Literal["symbol", "change", "volume", "rsi", "relevance"] = "relevance"
    version: Literal["1"] = "1"

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({f.model_dump_json() for f in self.filters}) != len(self.filters):
            raise ValueError("Duplicate filters")
        if len({f.model_dump_json() for f in self.context_filters}) != len(self.context_filters):
            raise ValueError("Duplicate Market Context filters")
        if self.context_mode != ContextMode.HARD_FILTER and self.context_filters:
            raise ValueError("Market Context predicates require Hard filter mode")
        return self


class SavedInput(Contract):
    config: ScanConfig
    archived: bool = False
