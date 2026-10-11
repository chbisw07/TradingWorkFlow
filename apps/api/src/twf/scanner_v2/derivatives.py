"""Bounded single-leg options scanner over canonical O2 snapshots."""

import asyncio
import math
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from twf.discovery.internal_scanner.market_series import DataUnavailable
from twf.discovery.market_data import DhanMarketDataProvider, MarketDataFailure
from twf.infrastructure.scanner_v2 import SavedScannerRow, ScannerRunRow
from twf.instrument_metadata.service import InstrumentMetadataService
from twf.options.chain_contracts import (
    OptionChainProvenance,
    OptionChainRequest,
    OptionChainSnapshot,
    OptionLegSnapshot,
    OptionMarketSnapshot,
)
from twf.options.chain_service import ChainFailure, OptionChainService
from twf.options.contracts import OptionContract
from twf.scanner_v2.engine import metrics
from twf.scanner_v2.service import ScannerHistory
from twf.watchlists.service import WatchlistFailure, WatchlistService
from twf.watchlists.system import SystemUniverseCatalog

MAX_UNDERLYINGS = 5
MIN_RELATIVE_VOLUME_COHORT = 5
MIN_RELATIVE_OI_COHORT = 5
MAX_INTERPRETATION_WINDOW_SECONDS = 30 * 60
MIN_CLEAR_MOVE_PERCENT = 0.1
NumericOperator = Literal[">", ">=", "<", "<=", "equals", "between"]
EnumOperator = Literal["equals", "not_equals"]

# The catalog, validator and evaluator use the same finite field registry.
FIELDS: dict[str, dict[str, Any]] = {
    "option_type": dict(
        category="Contract", label="Option Type", kind="enum", values=("BOTH", "CE", "PE")
    ),
    "moneyness": dict(
        category="Contract", label="Moneyness", kind="multi", values=("ITM", "ATM", "OTM")
    ),
    "dte": dict(category="Contract", label="DTE", kind="integer", minimum=0),
    "strike_distance_percent": dict(
        category="Contract", label="Strike distance %", kind="number", minimum=0, unit="%"
    ),
    "ltp": dict(
        category="Price & Liquidity", label="Option LTP", kind="number", minimum=0, unit="INR"
    ),
    "volume": dict(category="Price & Liquidity", label="Volume", kind="integer", minimum=0),
    "volume_percentile": dict(
        category="Price & Liquidity",
        label="Volume Percentile",
        kind="number",
        minimum=0,
        maximum=100,
        unit="%",
    ),
    "volume_vs_chain_median": dict(
        category="Price & Liquidity",
        label="Volume vs Chain Median",
        kind="number",
        minimum=0,
        unit="x",
    ),
    "spread_percent": dict(
        category="Price & Liquidity", label="Spread %", kind="number", minimum=0, unit="%"
    ),
    "open_interest": dict(
        category="Open Interest", label="Open Interest", kind="integer", minimum=0
    ),
    "oi_percentile": dict(
        category="Open Interest",
        label="OI Percentile",
        kind="number",
        minimum=0,
        maximum=100,
        unit="%",
    ),
    "oi_vs_chain_median": dict(
        category="Open Interest", label="OI vs Chain Median", kind="number", minimum=0, unit="x"
    ),
    "change_in_open_interest": dict(category="Open Interest", label="Change in OI", kind="integer"),
    "oi_change_percent": dict(
        category="Open Interest", label="Change in OI %", kind="number", unit="%"
    ),
    "oi_change_percentile": dict(
        category="Open Interest",
        label="Change in OI Percentile",
        kind="number",
        minimum=0,
        maximum=100,
        unit="%",
    ),
    "volume_oi_percent": dict(
        category="Open Interest",
        label="Volume / OI %",
        kind="number",
        minimum=0,
        unit="%",
    ),
    "implied_volatility": dict(
        category="Volatility & Greeks",
        label="IV %",
        kind="number",
        minimum=0,
        unit="%",
        provider_dependent=True,
    ),
    "delta": dict(
        category="Volatility & Greeks",
        label="Delta",
        kind="number",
        minimum=-1,
        maximum=1,
        provider_dependent=True,
    ),
    "theta": dict(
        category="Volatility & Greeks", label="Theta", kind="number", provider_dependent=True
    ),
    "underlying_trend": dict(
        category="Underlying Technical",
        label="Underlying Trend vs SMA20",
        kind="enum",
        values=("Up", "Down", "Sideways"),
    ),
    "underlying_rsi": dict(
        category="Underlying Technical",
        label="Underlying RSI (14)",
        kind="number",
        minimum=0,
        maximum=100,
    ),
    "underlying_supertrend": dict(
        category="Underlying Technical",
        label="Underlying Supertrend (10,3)",
        kind="enum",
        values=("Up", "Down"),
    ),
    "underlying_change": dict(
        category="Underlying Technical", label="Underlying 1D %", kind="number", unit="%"
    ),
    "underlying_roc": dict(
        category="Underlying Technical",
        label="Underlying 10-day momentum %",
        kind="number",
        unit="%",
    ),
}
TECHNICAL_FIELDS = {field for field in FIELDS if field.startswith("underlying_")}


class DerivativeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DerivativeUniverse(DerivativeModel):
    source: Literal["CUSTOM", "WATCHLIST"] = "CUSTOM"
    symbols: tuple[str, ...] = ()
    watchlist_id: UUID | None = None

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(value.strip().upper() for value in values))
        if any(not re.fullmatch(r"[A-Z0-9][A-Z0-9&._ -]{0,79}", value) for value in normalized):
            raise ValueError("Use canonical NSE underlying symbols")
        return normalized

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if self.source == "CUSTOM" and not 1 <= len(self.symbols) <= MAX_UNDERLYINGS:
            raise ValueError("Select 1 to 5 underlyings")
        if self.source == "WATCHLIST" and self.watchlist_id is None:
            raise ValueError("Choose a watchlist")
        if len(self.symbols) > MAX_UNDERLYINGS:
            raise ValueError("Select no more than 5 underlyings")
        return self


class DerivativeFilter(DerivativeModel):
    field: str
    operator: NumericOperator | EnumOperator = "equals"
    value: float | str | tuple[float, float] | tuple[str, ...]

    @model_validator(mode="after")
    def valid(self) -> Self:
        spec = FIELDS.get(self.field)
        if spec is None:
            raise ValueError("Unsupported derivatives filter field")
        kind = spec["kind"]
        if kind in {"enum", "multi"}:
            if self.operator not in {"equals", "not_equals"}:
                raise ValueError("Enum filters support equals or not_equals")
            enum_values = (self.value,) if isinstance(self.value, str) else self.value
            if (
                not isinstance(enum_values, tuple)
                or not enum_values
                or any(v not in spec["values"] for v in enum_values)
            ):
                raise ValueError("Unsupported enum filter value")
            if kind == "enum" and len(enum_values) != 1:
                raise ValueError("Choose one enum value")
            if self.field == "option_type" and self.value == "BOTH" and self.operator != "equals":
                raise ValueError("Both option types only supports equals")
        else:
            if self.operator == "not_equals":
                raise ValueError("Numeric filter does not support not_equals")
            raw_values = self.value if isinstance(self.value, tuple) else (self.value,)
            if any(
                isinstance(v, (str, bool))
                or not isinstance(v, (int, float))
                or not math.isfinite(v)
                for v in raw_values
            ):
                raise ValueError("Numeric filter requires finite numbers")
            values = tuple(float(v) for v in raw_values)
            if self.operator == "between" and len(values) != 2:
                raise ValueError("Between requires two bounds")
            if self.operator != "between" and len(values) != 1:
                raise ValueError("Choose one numeric value")
            if len(values) == 2 and values[0] > values[1]:
                raise ValueError("Between bounds must be ordered")
            if kind == "integer" and any(v != int(v) for v in values):
                raise ValueError("This field requires whole numbers")
            if any(
                v < spec.get("minimum", -math.inf) or v > spec.get("maximum", math.inf)
                for v in values
            ):
                raise ValueError("Filter value is outside field bounds")
        return self


class DerivativeScanConfig(DerivativeModel):
    name: str = Field(default="Options scan", min_length=1, max_length=100)
    scanner_type: Literal["DERIVATIVES"] = "DERIVATIVES"
    data_mode: Literal["REAL"] = "REAL"
    provider: Literal["dhan"] = "dhan"
    universe: DerivativeUniverse
    expiry_mode: Literal["NEAREST", "EXACT"] = "NEAREST"
    exact_expiry: date | None = None
    strike_window: Literal[5, 10, 15, 20] = 10
    filters: tuple[DerivativeFilter, ...] = Field(min_length=1, max_length=16)
    version: Literal["1"] = "1"

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.expiry_mode == "EXACT" and self.exact_expiry is None:
            raise ValueError("Choose an exact expiry")
        if len({f.field for f in self.filters}) != len(self.filters):
            raise ValueError("Use one active predicate per field")
        return self


class SavedDerivativeInput(DerivativeModel):
    config: DerivativeScanConfig
    archived: bool = False


class DerivativeScanResult(DerivativeModel):
    """Frozen, provider-neutral O4 row archived with the exact O1 contract."""

    contract: OptionContract
    underlying: str
    spot: str | None
    expiry: date
    dte: int
    strike: str
    option_type: Literal["CE", "PE"]
    moneyness: Literal["ITM", "ATM", "OTM"] | None
    strike_distance_percent: float | None
    market: OptionMarketSnapshot
    volume_percentile: float | None
    volume_chain_median: float | None
    volume_vs_chain_median: float | None
    volume_oi_percent: float | None
    relative_volume_cohort_size: int = Field(ge=0)
    oi_percentile: float | None
    oi_chain_median: float | None
    oi_vs_chain_median: float | None
    oi_change_percent: float | None
    oi_change_percentile: float | None
    relative_oi_cohort_size: int = Field(ge=0)
    oi_interpretation: dict[str, Any]
    availability: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"]
    technical: dict[str, float | str | None]
    technical_provenance: dict[str, Any] | None
    instrument_metadata: dict[str, Any] | None
    observed: dict[str, float | str | None]
    provenance: OptionChainProvenance
    warnings: tuple[str, ...]
    outcome: Literal["MATCH", "NON_MATCH", "NOT_EVALUATED"]
    diagnostics: tuple[dict[str, Any], ...]
    missing_evidence: tuple[str, ...]
    reason: str


def catalog() -> dict[str, Any]:
    return {
        "max_underlyings": MAX_UNDERLYINGS,
        "fields": [
            dict(
                field=field,
                **spec,
                operators=["equals", "not_equals"]
                if spec["kind"] in {"enum", "multi"}
                else [">", ">=", "<", "<=", "equals", "between"],
            )
            for field, spec in FIELDS.items()
        ],
        "strike_windows": [5, 10, 15, 20],
        "expiry_modes": ["NEAREST", "EXACT"],
    }


def relative_volume_metrics(chain: OptionChainSnapshot) -> dict[str, dict[str, float | int | None]]:
    """Snapshot-local CE+PE volume ranks. Ties use count(volume <= current) / N.

    Null volumes are excluded; observed zero participates. Percentile and median
    ratio need at least five valid observations. Volume/OI is independent of that
    cohort minimum. Only this already acquired O2 chain is read.
    """
    legs = {
        leg.contract.canonical_id: leg
        for row in chain.rows
        for leg in (row.ce, row.pe)
        if leg is not None
    }
    valid = sorted(leg.market.volume for leg in legs.values() if leg.market.volume is not None)
    size = len(valid)
    middle = size // 2
    median_volume: Decimal | None = None
    if size >= MIN_RELATIVE_VOLUME_COHORT:
        median_volume = valid[middle] if size % 2 else (valid[middle - 1] + valid[middle]) / 2
    result: dict[str, dict[str, float | int | None]] = {}
    for key, leg in legs.items():
        volume = leg.market.volume
        oi = leg.market.open_interest
        percentile = (
            float(Decimal(100) * sum(v <= volume for v in valid) / size)
            if volume is not None and size >= MIN_RELATIVE_VOLUME_COHORT
            else None
        )
        vs_median = (
            float(volume / median_volume)
            if volume is not None and median_volume is not None and median_volume > 0
            else None
        )
        volume_oi = (
            float(volume / oi * 100) if volume is not None and oi is not None and oi > 0 else None
        )
        result[key] = {
            "volume_percentile": percentile,
            "volume_chain_median": float(median_volume) if median_volume is not None else None,
            "volume_vs_chain_median": vs_median,
            "volume_oi_percent": volume_oi,
            "relative_volume_cohort_size": size,
        }
    return result


def relative_oi_metrics(chain: OptionChainSnapshot) -> dict[str, dict[str, Decimal | int | None]]:
    """CE+PE metrics from one bounded underlying/expiry chain before filtering.

    Ties share last-rank percentile. ΔOI percentile ranks absolute change
    magnitude; its direction remains separately visible. Missing is not zero.
    """
    legs = {
        leg.contract.canonical_id: leg
        for row in chain.rows
        for leg in (row.ce, row.pe)
        if leg is not None
    }
    valid_oi = sorted(
        leg.market.open_interest for leg in legs.values() if leg.market.open_interest is not None
    )
    valid_change = sorted(
        abs(leg.market.change_in_open_interest)
        for leg in legs.values()
        if leg.market.change_in_open_interest is not None
    )
    size = len(valid_oi)
    middle = size // 2
    median = (
        (valid_oi[middle] if size % 2 else (valid_oi[middle - 1] + valid_oi[middle]) / 2)
        if size >= MIN_RELATIVE_OI_COHORT
        else None
    )
    result: dict[str, dict[str, Decimal | int | None]] = {}
    for key, leg in legs.items():
        oi = leg.market.open_interest
        change = leg.market.change_in_open_interest
        previous = oi - change if oi is not None and change is not None else None
        result[key] = {
            "oi_percentile": (
                Decimal(100) * sum(v <= oi for v in valid_oi) / size
                if oi is not None and size >= MIN_RELATIVE_OI_COHORT
                else None
            ),
            "oi_chain_median": median if median is not None else None,
            "oi_vs_chain_median": (
                oi / median if oi is not None and median is not None and median > 0 else None
            ),
            "oi_change_percent": (
                change / previous * 100
                if change is not None and previous is not None and previous > 0
                else None
            ),
            "oi_change_percentile": (
                Decimal(100) * sum(v <= abs(change) for v in valid_change) / len(valid_change)
                if change is not None and len(valid_change) >= MIN_RELATIVE_OI_COHORT
                else None
            ),
            "relative_oi_cohort_size": size,
        }
    return result


def oi_interpretation(
    chain: OptionChainSnapshot, leg: OptionLegSnapshot, previous: dict[str, Any] | None
) -> dict[str, Any]:
    """Conservative exact-contract snapshot comparison; no effect on MATCH."""
    current_at = chain.provenance.received_at
    # Dhan's chain currently has no per-leg source time. An underlying quote's
    # source time must not be presented as option-premium/OI source time.
    option_freshness = (
        "STALE"
        if chain.provenance.freshness == "STALE"
        else chain.provenance.freshness
        if leg.market.source_time is not None
        else "SOURCE_TIME_UNAVAILABLE"
    )
    evidence: dict[str, Any] = {
        "label": "Insufficient evidence",
        "inferred": True,
        "confidence": "INSUFFICIENT",
        "freshness": option_freshness,
        "window_start": None,
        "window_end": current_at.isoformat(),
        "window_seconds": None,
        "premium_change_percent": None,
        "oi_window_change_percent": None,
        "underlying_change_percent": None,
        "iv_change_points": None,
        "reason": "No comparable earlier scan snapshot",
    }
    if previous is None:
        return evidence
    market = previous.get("market") or {}
    provenance = previous.get("provenance") or {}
    try:
        previous_at = datetime.fromisoformat(provenance["received_at"])
        duration = (current_at - previous_at).total_seconds()
        old_ltp = Decimal(str(market["ltp"]))
        old_oi = Decimal(str(market["open_interest"]))
        old_spot = Decimal(str(previous["spot"]))
        ltp, oi, spot = leg.market.ltp, leg.market.open_interest, chain.spot
        if not (
            0 < duration <= MAX_INTERPRETATION_WINDOW_SECONDS
            and old_ltp > 0
            and old_oi > 0
            and old_spot > 0
            and ltp is not None
            and oi is not None
            and spot is not None
            and not chain.provenance.cached
            and not provenance.get("cached")
        ):
            evidence["reason"] = "Comparison snapshot is incomplete, cached, or outside the window"
            return evidence
        if provenance.get("provider") != "dhan":
            return evidence
        premium_move = float((ltp - old_ltp) / old_ltp * 100)
        oi_move = float((oi - old_oi) / old_oi * 100)
        spot_move = float((spot - old_spot) / old_spot * 100)
        old_iv = market.get("implied_volatility")
        iv_move = (
            float(leg.market.implied_volatility - Decimal(str(old_iv)))
            if leg.market.implied_volatility is not None and old_iv is not None
            else None
        )
    except (KeyError, ValueError, TypeError, ArithmeticError):
        evidence["reason"] = "Comparison snapshot contains incomplete values"
        return evidence
    evidence.update(
        window_start=previous_at.isoformat(),
        window_seconds=duration,
        premium_change_percent=premium_move,
        oi_window_change_percent=oi_move,
        underlying_change_percent=spot_move,
        iv_change_points=iv_move,
    )
    if (
        leg.market.source_time is not None
        and market.get("source_time") == leg.market.source_time.isoformat()
    ):
        evidence["reason"] = "Provider source time did not advance"
        return evidence
    if option_freshness == "STALE":
        evidence["reason"] = "Current source data is stale"
        return evidence
    if abs(premium_move) < MIN_CLEAR_MOVE_PERCENT or abs(oi_move) < MIN_CLEAR_MOVE_PERCENT:
        evidence.update(label="Mixed / Unclear", confidence="LOW", reason="Moves are too small")
        return evidence
    if oi_move > 0:
        label = ("Call" if leg.contract.option_type.value == "CE" else "Put") + (
            " long buildup" if premium_move > 0 else " short buildup"
        )
    else:
        label = "Short covering" if premium_move > 0 else "Long unwinding"
    # Underlying and IV only qualify the evidence; they never affect O4 MATCH.
    support = (spot_move > 0) == (leg.contract.option_type.value == "CE")
    if premium_move < 0:
        support = not support
    iv_conflict = iv_move is not None and (iv_move > 0) != (premium_move > 0)
    confidence = "HIGH" if support and not iv_conflict and option_freshness == "FRESH" else "MEDIUM"
    if not support or iv_conflict:
        confidence = "LOW"
    evidence.update(
        label=label,
        confidence=confidence,
        reason="Observed snapshot-to-snapshot premium and OI moves",
    )
    return evidence


def observations(
    chain: OptionChainSnapshot,
    leg: OptionLegSnapshot,
    distance: Any,
    technical: dict[str, Any],
    relative: dict[str, float | int | None],
    relative_oi: dict[str, Decimal | int | None],
) -> dict[str, Any]:
    market = leg.market
    return {
        "option_type": leg.contract.option_type.value,
        "moneyness": leg.moneyness,
        "dte": chain.dte,
        "strike_distance_percent": abs(float(distance)) if distance is not None else None,
        **{
            field: relative[field]
            for field in (
                "volume_percentile",
                "volume_chain_median",
                "volume_vs_chain_median",
                "volume_oi_percent",
            )
        },
        **{
            field: relative_oi[field]
            for field in (
                "oi_percentile",
                "oi_chain_median",
                "oi_vs_chain_median",
                "oi_change_percent",
                "oi_change_percentile",
            )
        },
        **{
            field: float(getattr(market, field)) if getattr(market, field) is not None else None
            for field in (
                "ltp",
                "volume",
                "spread_percent",
                "open_interest",
                "change_in_open_interest",
                "implied_volatility",
                "delta",
                "theta",
            )
        },
        **{
            f"underlying_{field}": technical.get(field)
            for field in ("trend", "rsi", "supertrend", "change", "roc")
        },
    }


def evaluate(
    filters: tuple[DerivativeFilter, ...], values: dict[str, Any], *, quote_available: bool
) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    for item in filters:
        observed = values.get(item.field)
        passed: bool | None = None
        if observed is not None:
            if item.operator == "between" and isinstance(item.value, tuple):
                if isinstance(observed, Decimal):
                    passed = Decimal(str(item.value[0])) <= observed <= Decimal(str(item.value[1]))
                else:
                    passed = item.value[0] <= observed <= item.value[1]
            elif item.operator in {"equals", "not_equals"}:
                values_to_compare = (item.value,) if isinstance(item.value, str) else item.value
                same = item.field == "option_type" and item.value == "BOTH"
                if not same:
                    same = (
                        observed in values_to_compare
                        if isinstance(values_to_compare, tuple)
                        else observed == values_to_compare
                    )
                passed = same if item.operator == "equals" else not same
            elif isinstance(observed, (int, float, Decimal)) and isinstance(
                item.value, (int, float)
            ):
                threshold = (
                    Decimal(str(item.value)) if isinstance(observed, Decimal) else item.value
                )
                passed = {
                    ">": observed > threshold,
                    ">=": observed >= threshold,
                    "<": observed < threshold,
                    "<=": observed <= threshold,
                }[item.operator]
        diagnostics.append(
            {
                "filter": item.model_dump(mode="json"),
                "observed": observed,
                "threshold": item.value,
                "passed": passed,
                "reason": f"{FIELDS[item.field]['label']} {item.operator} {item.value}",
            }
        )
    outcome = (
        "NOT_EVALUATED"
        if not quote_available or any(d["passed"] is None for d in diagnostics)
        else "MATCH"
        if all(d["passed"] for d in diagnostics)
        else "NON_MATCH"
    )
    return {
        "outcome": outcome,
        "diagnostics": diagnostics,
        "missing_evidence": [
            FIELDS[d["filter"]["field"]]["label"] for d in diagnostics if d["passed"] is None
        ]
        + (["Option quote"] if not quote_available else []),
        "reason": f"{len(diagnostics)}/{len(diagnostics)} active filters matched"
        if outcome == "MATCH"
        else "Required evidence unavailable"
        if outcome == "NOT_EVALUATED"
        else (
            f"{sum(d['passed'] is True for d in diagnostics)}/"
            f"{len(diagnostics)} active filters matched"
        ),
    }


class DerivativeScannerService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        owner: UUID,
        system_universes: SystemUniverseCatalog | None = None,
    ) -> None:
        self.factory, self.owner, self.system_universes = factory, owner, system_universes

    def saved(self) -> list[dict[str, Any]]:
        with self.factory() as db:
            rows = db.scalars(
                select(SavedScannerRow)
                .where(
                    SavedScannerRow.owner_id == self.owner,
                    SavedScannerRow.config["scanner_type"].as_string() == "DERIVATIVES",
                )
                .order_by(SavedScannerRow.updated_at.desc())
                .limit(100)
            )
            return [
                dict(
                    id=str(r.id),
                    config=r.config,
                    archived=r.archived,
                    updated_at=r.updated_at.isoformat(),
                )
                for r in rows
                if r.config.get("scanner_type") == "DERIVATIVES"
            ]

    def save(self, payload: SavedDerivativeInput, key: UUID | None = None) -> dict[str, Any]:
        with self.factory.begin() as db:
            row = db.get(SavedScannerRow, key) if key else None
            if key and (
                row is None
                or row.owner_id != self.owner
                or row.config.get("scanner_type") != "DERIVATIVES"
            ):
                raise WatchlistFailure("SAVED_SCAN_NOT_FOUND", 404)
            now = datetime.now(UTC)
            if row is None:
                row = SavedScannerRow(
                    id=uuid4(),
                    owner_id=self.owner,
                    config={},
                    archived=False,
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
            row.config = payload.config.model_dump(mode="json")
            row.archived = payload.archived
            row.updated_at = now
            return dict(
                id=str(row.id), config=row.config, archived=row.archived, updated_at=now.isoformat()
            )

    def history(self) -> list[dict[str, Any]]:
        with self.factory() as db:
            rows = db.scalars(
                select(ScannerRunRow)
                .where(
                    ScannerRunRow.owner_id == self.owner,
                    ScannerRunRow.payload["config"]["scanner_type"].as_string() == "DERIVATIVES",
                )
                .order_by(ScannerRunRow.created_at.desc())
                .limit(50)
            )
            return [
                {k: v for k, v in r.payload.items() if k != "rows"}
                for r in rows
                if r.payload.get("config", {}).get("scanner_type") == "DERIVATIVES"
            ]

    def run(self, key: UUID) -> dict[str, Any]:
        with self.factory() as db:
            row = db.get(ScannerRunRow, key)
            if (
                row is None
                or row.owner_id != self.owner
                or row.payload.get("config", {}).get("scanner_type") != "DERIVATIVES"
            ):
                raise WatchlistFailure("SCAN_NOT_FOUND", 404)
            return dict(row.payload)

    async def execute(
        self,
        config: DerivativeScanConfig,
        provider: DhanMarketDataProvider,
        generation: int,
        chain_service: OptionChainService,
        history_cache: ScannerHistory,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        if config.universe.source == "CUSTOM":
            symbols = config.universe.symbols
        else:
            assert config.universe.watchlist_id
            if self.system_universes and self.system_universes.definition(
                config.universe.watchlist_id
            ):
                snap = await self.system_universes.snapshot(config.universe.watchlist_id, provider)
            else:
                snap = WatchlistService(self.factory, self.owner).snapshot(
                    config.universe.watchlist_id
                )
            available = tuple(dict.fromkeys(item.symbol for item in snap.instruments))
            if config.universe.symbols and set(config.universe.symbols) - set(available):
                raise WatchlistFailure("WATCHLIST_SELECTION_CHANGED", 409)
            symbols = config.universe.symbols or available
        if not 1 <= len(symbols) <= MAX_UNDERLYINGS:
            raise WatchlistFailure("SELECT_1_TO_5_UNDERLYINGS", 422)
        rows: list[dict[str, Any]] = []
        underlyings: list[dict[str, Any]] = []
        master_error: str | None = None
        try:
            async with asyncio.timeout(30):
                active = await chain_service.active(now)
        except (ChainFailure, MarketDataFailure, TimeoutError) as exc:
            active = ()
            master_error = "TIMEOUT" if isinstance(exc, TimeoutError) else str(exc.code)
        by_symbol: dict[str, set[date]] = {}
        for contract in active:
            by_symbol.setdefault(contract.underlying_symbol, set()).add(contract.expiry)
        technical_active = bool({f.field for f in config.filters} & TECHNICAL_FIELDS)
        with self.factory() as db:
            metadata_service = InstrumentMetadataService(db)
            metadata = metadata_service.get_many_by_exchange_symbols(
                tuple(("NSE", s) for s in symbols)
            )
            summaries = {
                s: metadata_service.summary(
                    metadata[("NSE", s)], applies_to_symbol=s, resolution_basis="DIRECT"
                ).model_dump(mode="json")
                if ("NSE", s) in metadata
                else None
                for s in symbols
            }
        # One bounded local archive read, keyed by exact O1 contract. It never
        # acquires more market data and cannot affect deterministic matching.
        previous_by_contract: dict[str, dict[str, Any]] = {}
        with self.factory() as db:
            prior_runs = db.scalars(
                select(ScannerRunRow)
                .where(
                    ScannerRunRow.owner_id == self.owner,
                    ScannerRunRow.payload["config"]["scanner_type"].as_string() == "DERIVATIVES",
                )
                .order_by(ScannerRunRow.created_at.desc())
                .limit(10)
            )
            for prior_run in prior_runs:
                if prior_run.payload.get("market_data_provider") != "dhan":
                    continue
                for prior_row in prior_run.payload.get("rows", ()):
                    contract_id = prior_row.get("contract", {}).get("canonical_id")
                    if contract_id and contract_id not in previous_by_contract:
                        previous_by_contract[contract_id] = prior_row
        chains_evaluated = 0
        seen_contracts: set[str] = set()
        for symbol in symbols:
            status: dict[str, Any] = {"symbol": symbol, "outcome": "NOT_EVALUATED", "failure": None}
            underlyings.append(status)
            expiries = sorted(by_symbol.get(symbol, ()))
            if not expiries:
                status["failure"] = master_error or "NO_OPTION_CONTRACTS"
                continue
            selected_expiry = (
                expiries[0] if config.expiry_mode == "NEAREST" else config.exact_expiry
            )
            if selected_expiry not in expiries:
                status["failure"] = "EXPIRY_NOT_AVAILABLE"
                continue
            technical: dict[str, Any] = {}
            technical_provenance: dict[str, Any] | None = None
            if technical_active:
                try:
                    async with asyncio.timeout(20):
                        resolved = await provider.resolve_instruments((symbol,))
                        if len(resolved) != 1 or resolved[0].exchange != "NSE":
                            raise WatchlistFailure("UNDERLYING_UNRESOLVED", 422)
                        series = await history_cache.read(
                            self.owner, generation, provider, resolved[0]
                        )
                    technical = metrics(series.at(now))
                    technical_provenance = series.provenance.model_dump(mode="json")
                except (MarketDataFailure, WatchlistFailure, DataUnavailable, TimeoutError) as exc:
                    status["technical_failure"] = (
                        "TIMEOUT"
                        if isinstance(exc, TimeoutError)
                        else exc.reason.value
                        if isinstance(exc, DataUnavailable)
                        else str(exc.code)
                    )
            try:
                async with asyncio.timeout(40):
                    chain = await chain_service.snapshot(
                        OptionChainRequest(
                            underlying=symbol,
                            expiry=selected_expiry,
                            around_atm=config.strike_window,
                        ),
                        now=now,
                    )
            except (ChainFailure, MarketDataFailure, TimeoutError) as exc:
                status["failure"] = "TIMEOUT" if isinstance(exc, TimeoutError) else str(exc.code)
                continue
            if chain.provenance.provider != "dhan":
                status["failure"] = "REAL_DATA_PROVENANCE_REQUIRED"
                continue
            if chain.provenance.freshness == "UNAVAILABLE":
                status["failure"] = "CHAIN_MARKET_UNAVAILABLE"
                status["chain_status"] = chain.status
                continue
            chains_evaluated += 1
            status.update(
                outcome="EVALUATED",
                expiry=selected_expiry.isoformat(),
                chain_status=chain.status,
                provenance=chain.provenance.model_dump(mode="json"),
            )
            relative_by_contract = relative_volume_metrics(chain)
            oi_by_contract = relative_oi_metrics(chain)
            for chain_row in chain.rows:
                for leg in (chain_row.ce, chain_row.pe):
                    if leg is None or leg.contract.canonical_id in seen_contracts:
                        continue
                    seen_contracts.add(leg.contract.canonical_id)
                    relative = relative_by_contract[leg.contract.canonical_id]
                    relative_oi = oi_by_contract[leg.contract.canonical_id]
                    values = observations(
                        chain,
                        leg,
                        chain_row.distance_percent,
                        technical,
                        relative,
                        relative_oi,
                    )
                    interpretation = oi_interpretation(
                        chain, leg, previous_by_contract.get(leg.contract.canonical_id)
                    )
                    result = evaluate(
                        config.filters, values, quote_available=leg.market.ltp is not None
                    )
                    rows.append(
                        DerivativeScanResult.model_validate(
                            {
                                "contract": leg.contract.model_dump(mode="json"),
                                "underlying": symbol,
                                "spot": str(chain.spot) if chain.spot is not None else None,
                                "expiry": selected_expiry.isoformat(),
                                "dte": chain.dte,
                                "strike": str(leg.contract.strike),
                                "option_type": leg.contract.option_type.value,
                                "moneyness": leg.moneyness,
                                "strike_distance_percent": values["strike_distance_percent"],
                                "market": leg.market.model_dump(mode="json"),
                                **relative,
                                **relative_oi,
                                "oi_interpretation": interpretation,
                                "availability": leg.availability,
                                "technical": technical,
                                "technical_provenance": technical_provenance,
                                "instrument_metadata": summaries[symbol],
                                "observed": values,
                                "provenance": chain.provenance.model_dump(mode="json"),
                                "warnings": list(dict.fromkeys((*chain.warnings, *leg.warnings))),
                                **result,
                            }
                        ).model_dump(mode="json")
                    )
        rows.sort(
            key=lambda row: (
                row["underlying"],
                row["expiry"],
                float(row["strike"]),
                0 if row["option_type"] == "CE" else 1,
            )
        )
        key = uuid4()
        result = {
            "id": str(key),
            "created_at": now.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "config": config.model_dump(mode="json"),
            "data_mode": "REAL",
            "market_data_provider": "dhan",
            "generation": generation,
            "underlyings": underlyings,
            "counts": {
                "requested": len(symbols),
                "resolved": sum(bool(by_symbol.get(s)) for s in symbols),
                "chains_evaluated": chains_evaluated,
                "contracts_evaluated": sum(r["outcome"] != "NOT_EVALUATED" for r in rows),
                "not_evaluated": sum(r["outcome"] == "NOT_EVALUATED" for r in rows)
                + sum(u["outcome"] == "NOT_EVALUATED" for u in underlyings),
                "matches": sum(r["outcome"] == "MATCH" for r in rows),
            },
            "rows": rows,
        }
        with self.factory.begin() as db:
            db.add(ScannerRunRow(id=key, owner_id=self.owner, payload=result, created_at=now))
        return result
