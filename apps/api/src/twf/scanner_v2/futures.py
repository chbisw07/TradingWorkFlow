"""O5 NSE futures scanner. One master read and one bounded quote batch per run.

The contract, quote and predicate evidence are archived together. No option-chain
percentile or synthetic market data enters this scanner.
"""

from __future__ import annotations

import asyncio
import math
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Self
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from twf.discovery.dhan_futures import FuturesMaster
from twf.discovery.market_data import DhanMarketDataProvider, MarketDataFailure, QuoteSnapshot
from twf.infrastructure.scanner_v2 import SavedScannerRow, ScannerRunRow
from twf.scanner_v2.derivatives import DerivativeModel
from twf.watchlists.catalog import canonical
from twf.watchlists.service import WatchlistFailure, WatchlistService
from twf.watchlists.system import SystemUniverseCatalog

IST = ZoneInfo("Asia/Kolkata")
MAX_FUTURES_UNDERLYINGS = 50
MIN_PERCENTILE_COHORT = 5
MAX_COMPARISON_AGE = timedelta(minutes=30)
MAX_BASIS_SOURCE_GAP = timedelta(minutes=5)
MIN_DIRECTION_PERCENT = Decimal("0.1")
FIELDS: dict[str, dict[str, Any]] = {
    "ltp": dict(
        category="Price & Liquidity", label="Futures Price", kind="number", minimum=0, unit="INR"
    ),
    "change_percent": dict(category="Price & Liquidity", label="Change %", kind="number", unit="%"),
    "volume": dict(category="Price & Liquidity", label="Volume", kind="integer", minimum=0),
    "volume_percentile": dict(
        category="Price & Liquidity",
        label="Volume Percentile",
        kind="number",
        minimum=0,
        maximum=100,
        unit="%",
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
    "change_in_open_interest": dict(
        category="Open Interest", label="Change in OI (comparison window)", kind="integer"
    ),
    "oi_change_percent": dict(
        category="Open Interest",
        label="Change in OI % (comparison window)",
        kind="number",
        unit="%",
    ),
    "basis_abs": dict(category="Basis", label="Basis (Abs)", kind="number", unit="INR"),
    "basis_percent": dict(category="Basis", label="Basis %", kind="number", unit="%"),
    "underlying_trend": dict(
        category="Spot direction",
        label="Spot 1D Direction",
        kind="enum",
        values=("Up", "Down", "Sideways"),
    ),
    "interpretation": dict(
        category="Participation",
        label="Futures Interpretation",
        kind="enum",
        values=(
            "Long buildup",
            "Short buildup",
            "Short covering",
            "Long unwinding",
            "Mixed / Unclear",
            "Insufficient evidence",
        ),
    ),
    "dte": dict(category="Contract", label="DTE", kind="integer", minimum=0),
}


class FuturesUniverse(DerivativeModel):
    source: Literal["CUSTOM", "WATCHLIST"] = "CUSTOM"
    symbols: tuple[str, ...] = ()
    watchlist_id: UUID | None = None

    @field_validator("symbols")
    @classmethod
    def symbols_valid(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        result = tuple(dict.fromkeys(v.strip().upper() for v in values))
        if any(not re.fullmatch(r"[A-Z0-9][A-Z0-9&._ -]{0,79}", v) for v in result):
            raise ValueError("Use canonical NSE underlying symbols")
        return result

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.source == "CUSTOM" and not 1 <= len(self.symbols) <= MAX_FUTURES_UNDERLYINGS:
            raise ValueError("Select 1 to 50 underlyings")
        if self.source == "WATCHLIST" and self.watchlist_id is None:
            raise ValueError("Choose a watchlist")
        if len(self.symbols) > MAX_FUTURES_UNDERLYINGS:
            raise ValueError("Select no more than 50 underlyings")
        return self


class FuturesFilter(DerivativeModel):
    field: str
    operator: Literal[">", ">=", "<", "<=", "equals", "between", "not_equals"]
    value: float | str | tuple[float, float]

    @model_validator(mode="after")
    def valid(self) -> Self:
        spec = FIELDS.get(self.field)
        if spec is None:
            raise ValueError("Unsupported futures filter field")
        if spec["kind"] == "enum":
            if (
                self.operator not in {"equals", "not_equals"}
                or not isinstance(self.value, str)
                or self.value not in spec["values"]
            ):
                raise ValueError("Invalid futures enum predicate")
        else:
            if self.operator == "not_equals":
                raise ValueError("Numeric predicate does not support not_equals")
            values = self.value if isinstance(self.value, tuple) else (self.value,)
            if len(values) != (2 if self.operator == "between" else 1) or any(
                isinstance(v, (str, bool))
                or not isinstance(v, (int, float))
                or not math.isfinite(v)
                for v in values
            ):
                raise ValueError("Numeric predicate requires finite numbers")
            if len(values) == 2 and values[0] > values[1]:
                raise ValueError("Between bounds must be ordered")
            if spec["kind"] == "integer" and any(v != int(v) for v in values):
                raise ValueError("Whole-number predicate required")
            if any(
                v < spec.get("minimum", -math.inf) or v > spec.get("maximum", math.inf)
                for v in values
            ):
                raise ValueError("Predicate outside field bounds")
        return self


class FuturesScanConfig(DerivativeModel):
    name: str = Field(default="Futures scan", min_length=1, max_length=100)
    scanner_type: Literal["DERIVATIVES"] = "DERIVATIVES"
    instrument_scope: Literal["FUTURES"] = "FUTURES"
    data_mode: Literal["REAL"] = "REAL"
    provider: Literal["dhan"] = "dhan"
    universe: FuturesUniverse
    expiry_mode: Literal["NEAREST", "EXACT"] = "NEAREST"
    exact_expiry: date | None = None
    filters: tuple[FuturesFilter, ...] = Field(min_length=1, max_length=16)
    version: Literal["1"] = "1"
    origin_template_id: str | None = Field(default=None, max_length=100)
    origin_template_name: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.expiry_mode == "EXACT" and self.exact_expiry is None:
            raise ValueError("Choose an exact expiry")
        if len({f.field for f in self.filters}) != len(self.filters):
            raise ValueError("Use one active predicate per field")
        return self


class SavedFuturesInput(DerivativeModel):
    config: FuturesScanConfig
    archived: bool = False


def catalog() -> dict[str, Any]:
    return {
        "max_underlyings": MAX_FUTURES_UNDERLYINGS,
        "fields": [
            dict(
                field=key,
                **spec,
                operators=["equals", "not_equals"]
                if spec["kind"] == "enum"
                else [">", ">=", "<", "<=", "equals", "between"],
            )
            for key, spec in FIELDS.items()
        ],
        "expiry_modes": ["NEAREST", "EXACT"],
        "percentile_min_cohort": MIN_PERCENTILE_COHORT,
        "methodology": (
            "Current scan exact-contract cross-section; ties use "
            "count(value <= current) / N × 100. Percentiles require five observed values."
        ),
    }


def percentile(values: list[Decimal], value: Decimal | None) -> float | None:
    if value is None or len(values) < MIN_PERCENTILE_COHORT:
        return None
    return float(Decimal(100) * sum(item <= value for item in values) / len(values))


def interpretation(
    price_change: Decimal | None, oi_change: Decimal | None, previous_oi: Decimal | None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "label": "Insufficient evidence",
        "inferred": True,
        "reason": "Price and comparable OI changes are required",
        "price_threshold_percent": str(MIN_DIRECTION_PERCENT),
    }
    if price_change is None or oi_change is None or previous_oi is None or previous_oi <= 0:
        return result
    oi_pct = oi_change / previous_oi * 100
    if abs(price_change) < MIN_DIRECTION_PERCENT or abs(oi_pct) < MIN_DIRECTION_PERCENT:
        result.update(
            label="Mixed / Unclear",
            reason="A price or OI change is below the 0.1% direction threshold",
        )
    else:
        result.update(
            label={
                (True, True): "Long buildup",
                (False, True): "Short buildup",
                (True, False): "Short covering",
                (False, False): "Long unwinding",
            }[(price_change > 0, oi_change > 0)],
            reason="Inferred from futures price change and exact-contract OI comparison",
        )
    return result


def evaluate(
    filters: tuple[FuturesFilter, ...], observed: dict[str, Any], quote_available: bool
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for predicate in filters:
        value = observed.get(predicate.field)
        passed = None
        if value is not None:
            threshold = predicate.value
            if predicate.operator == "between" and isinstance(threshold, tuple):
                passed = (
                    Decimal(str(threshold[0])) <= Decimal(str(value)) <= Decimal(str(threshold[1]))
                )
            elif predicate.operator == "equals":
                passed = value == threshold
            elif predicate.operator == "not_equals":
                passed = value != threshold
            elif isinstance(threshold, (float, int)):
                left, right = Decimal(str(value)), Decimal(str(threshold))
                passed = {
                    ">": left > right,
                    ">=": left >= right,
                    "<": left < right,
                    "<=": left <= right,
                }[predicate.operator]
        checks.append(
            {
                "filter": predicate.model_dump(mode="json"),
                "observed": float(value) if isinstance(value, Decimal) else value,
                "threshold": predicate.value,
                "passed": passed,
                "reason": (
                    f"{FIELDS[predicate.field]['label']} {predicate.operator} {predicate.value}"
                ),
            }
        )
    # A known failed condition is a non-match even if another metric is missing.
    outcome = (
        "NOT_EVALUATED"
        if not quote_available
        else "NON_MATCH"
        if any(item["passed"] is False for item in checks)
        else "NOT_EVALUATED"
        if any(item["passed"] is None for item in checks)
        else "MATCH"
    )
    missing = [
        FIELDS[item["filter"]["field"]]["label"] for item in checks if item["passed"] is None
    ]
    if not quote_available:
        missing.append("Futures quote")
    return {
        "outcome": outcome,
        "diagnostics": checks,
        "missing_evidence": missing,
        "reason": "Required evidence unavailable"
        if outcome == "NOT_EVALUATED"
        else (
            f"{sum(item['passed'] is True for item in checks)}/{len(checks)} active filters matched"
        ),
    }


def _positive_decimal(raw: str | None) -> Decimal | None:
    try:
        value = Decimal(str(raw))
        return value if value.is_finite() and value > 0 else None
    except (InvalidOperation, TypeError):
        return None


class FuturesScannerService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        owner: UUID,
        systems: SystemUniverseCatalog | None = None,
    ) -> None:
        self.factory, self.owner, self.systems = factory, owner, systems

    async def _members(
        self, watchlist_id: UUID, provider: DhanMarketDataProvider
    ) -> tuple[tuple[str, ...], dict[str, Any]]:
        if self.systems and self.systems.definition(watchlist_id):
            snap = await self.systems.snapshot(watchlist_id, provider)
        else:
            snap = WatchlistService(self.factory, self.owner).snapshot(watchlist_id)
        symbols = tuple(dict.fromkeys(item.symbol for item in snap.instruments))
        return symbols, snap.model_dump(mode="json")

    async def watchlist_eligibility(
        self, watchlist_id: UUID, provider: DhanMarketDataProvider
    ) -> dict[str, Any]:
        members, _ = await self._members(watchlist_id, provider)
        contracts = FuturesMaster(await provider._load_futures_master(), datetime.now(IST).date())
        eligible = tuple(symbol for symbol in members if contracts.resolve(symbol)[0] is not None)
        return {
            "watchlist_id": str(watchlist_id),
            "members": len(members),
            "eligible": len(eligible),
            "excluded": [s for s in members if s not in eligible],
            "symbols": eligible,
            "max_underlyings": MAX_FUTURES_UNDERLYINGS,
        }

    def save(self, payload: SavedFuturesInput, key: UUID | None = None) -> dict[str, Any]:
        with self.factory.begin() as db:
            row = db.get(SavedScannerRow, key) if key else None
            if key and (
                row is None
                or row.owner_id != self.owner
                or row.config.get("instrument_scope") != "FUTURES"
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
            return {
                "id": str(row.id),
                "config": row.config,
                "archived": row.archived,
                "updated_at": now.isoformat(),
            }

    async def execute(
        self, config: FuturesScanConfig, provider: DhanMarketDataProvider, generation: int
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        today = now.astimezone(IST).date()
        universe_snapshot = None
        if config.universe.source == "WATCHLIST":
            assert config.universe.watchlist_id
            members, universe_snapshot = await self._members(config.universe.watchlist_id, provider)
            if config.universe.symbols and set(config.universe.symbols) - set(members):
                raise WatchlistFailure("WATCHLIST_SELECTION_CHANGED", 409)
            symbols = config.universe.symbols or members
        else:
            symbols = config.universe.symbols
        if not 1 <= len(symbols) <= MAX_FUTURES_UNDERLYINGS:
            raise WatchlistFailure("SELECT_1_TO_50_UNDERLYINGS", 422)
        master_error = None
        try:
            async with asyncio.timeout(30):
                master = await provider._load_futures_master()
        except (MarketDataFailure, TimeoutError):
            master = ()
            master_error = "PROVIDER_MASTER_UNAVAILABLE"
        available = FuturesMaster(master, today)
        underlyings: list[dict[str, Any]] = []
        resolved = []
        for symbol in symbols:
            item: dict[str, Any] = {"symbol": symbol, "outcome": "NOT_EVALUATED", "failure": None}
            underlyings.append(item)
            candidate, failure = available.resolve(
                symbol, config.exact_expiry if config.expiry_mode == "EXACT" else None
            )
            if candidate is None:
                item["failure"] = master_error or failure
                continue
            expiry, source = candidate
            symbol = source["SM_SYMBOL_NAME"]
            identity = canonical(source)
            if identity is None:
                item["failure"] = "FUTURES_IDENTITY_UNAVAILABLE"
                continue
            item.update(
                outcome="RESOLVED",
                expiry=expiry.isoformat(),
                contract_symbol=identity.provider_symbol or identity.symbol,
            )
            resolved.append((symbol, expiry, source, identity, item))
        # Equity spots are indexed from this run's master snapshot. Index aliases
        # retain the O2 benchmark resolver; only index underlyings use it.
        cash_rows: dict[str, list[dict[str, str]]] = {}
        for row in master:
            if (
                row.get("SEM_EXM_EXCH_ID") == "NSE"
                and row.get("SEM_SEGMENT") == "E"
                and row.get("SEM_INSTRUMENT_NAME") == "EQUITY"
                and row.get("SEM_SERIES") == "EQ"
            ):
                cash_rows.setdefault(row.get("SEM_TRADING_SYMBOL", "").upper(), []).append(row)
        spot_identities: dict[str, Any] = {}
        for symbol, _, source, _, _ in resolved:
            if source["SEM_INSTRUMENT_NAME"] == "FUTSTK":
                cash_candidates = cash_rows.get(symbol, [])
                if len(cash_candidates) == 1:
                    spot_identity = canonical(cash_candidates[0])
                    if spot_identity is not None:
                        spot_identities[symbol] = spot_identity
            else:
                try:
                    index_rows = available.indexes.candidates(symbol)
                    if len(index_rows) == 1:
                        spot_identity = canonical(index_rows[0])
                        if spot_identity is not None:
                            spot_identities[symbol] = spot_identity
                except MarketDataFailure:
                    pass
        quote_identities = tuple(
            dict.fromkeys([item[3] for item in resolved] + list(spot_identities.values()))
        )
        quotes: dict[str, QuoteSnapshot] = {}
        missing_quotes: tuple[str, ...] = ()
        quote_error = None
        if quote_identities:
            try:
                async with asyncio.timeout(20):
                    batch, missing_quotes = await provider.get_quotes_partial(quote_identities)
                quotes = {q.instrument.native.native_id: q for q in batch}
            except (MarketDataFailure, TimeoutError) as exc:
                quote_error = "TIMEOUT" if isinstance(exc, TimeoutError) else exc.code.value
        prior: dict[str, dict[str, Any]] = {}
        with self.factory() as db:
            archived = db.scalars(
                select(ScannerRunRow)
                .where(
                    ScannerRunRow.owner_id == self.owner,
                    ScannerRunRow.payload["config"]["instrument_scope"].as_string() == "FUTURES",
                )
                .order_by(ScannerRunRow.created_at.desc())
                .limit(10)
            )
            for execution in archived:
                for row in execution.payload.get("rows", []):
                    native = row.get("contract", {}).get("provider_native_id")
                    if native and native not in prior:
                        prior[native] = row
        observations: list[dict[str, Any]] = []
        for symbol, expiry, source, identity, status in resolved:
            future = quotes.get(identity.native.native_id)
            spot = (
                quotes.get(spot_identities[symbol].native.native_id)
                if symbol in spot_identities
                else None
            )
            previous = prior.get(identity.native.native_id)
            previous_oi = None
            previous_price = None
            comparison_window = None
            if future and previous:
                try:
                    previous_at = datetime.fromisoformat(previous["quote"]["received_at"])
                    current_at = future.received_at
                    old_source_text = previous.get("quote", {}).get("provider_source_time")
                    old_source = (
                        datetime.fromisoformat(old_source_text) if old_source_text else None
                    )
                    new_source = future.provider_source_time
                    if (
                        timedelta(0) < current_at - previous_at <= MAX_COMPARISON_AGE
                        and previous_at.astimezone(IST).date() == today
                        and previous.get("contract", {}).get("provider_native_id")
                        == identity.native.native_id
                        and old_source is not None
                        and new_source is not None
                        and timedelta(0) < new_source - old_source <= MAX_COMPARISON_AGE
                        and timedelta(0) <= current_at - new_source <= timedelta(minutes=15)
                        and timedelta(0) <= previous_at - old_source <= timedelta(minutes=15)
                    ):
                        previous_oi = _positive_decimal(
                            previous.get("quote", {}).get("open_interest")
                        )
                        previous_price = _positive_decimal(
                            previous.get("quote", {}).get("last_price")
                        )
                        comparison_window = {
                            "from": previous_at.isoformat(),
                            "to": current_at.isoformat(),
                            "seconds": int((current_at - previous_at).total_seconds()),
                        }
                except (KeyError, ValueError, TypeError):
                    pass
            current_oi = future.open_interest if future else None
            oi_change = (
                current_oi - previous_oi
                if current_oi is not None and previous_oi is not None
                else None
            )
            oi_change_percent = (
                oi_change / previous_oi * 100
                if oi_change is not None and previous_oi is not None and previous_oi > 0
                else None
            )
            change_percent = (
                (future.last_price - future.previous_close) / future.previous_close * 100
                if future and future.previous_close
                else None
            )
            trend = None
            spot_change = None
            if spot and spot.previous_close:
                spot_change = (spot.last_price - spot.previous_close) / spot.previous_close * 100
                trend = (
                    "Up"
                    if spot_change >= MIN_DIRECTION_PERCENT
                    else "Down"
                    if spot_change <= -MIN_DIRECTION_PERCENT
                    else "Sideways"
                )
            basis_abs = basis_percent = None
            basis_reason = (
                "Spot/futures source timestamps must be within five minutes "
                "and no more than 15 minutes behind receipt"
            )
            if (
                future
                and spot
                and future.provider_source_time
                and spot.provider_source_time
                and abs(future.provider_source_time - spot.provider_source_time)
                <= MAX_BASIS_SOURCE_GAP
                and timedelta(0)
                <= future.received_at - future.provider_source_time
                <= timedelta(minutes=15)
                and timedelta(0)
                <= spot.received_at - spot.provider_source_time
                <= timedelta(minutes=15)
                and spot.last_price > 0
            ):
                basis_abs = future.last_price - spot.last_price
                basis_percent = basis_abs / spot.last_price * 100
                basis_reason = (
                    "Same quote batch; source timestamps within five minutes "
                    "and no more than 15 minutes behind receipt"
                )
            comparison_price_change = (
                (future.last_price - previous_price) / previous_price * 100
                if future and previous_price is not None
                else None
            )
            interpreted = interpretation(comparison_price_change, oi_change, previous_oi)
            observations.append(
                {
                    "symbol": symbol,
                    "expiry": expiry,
                    "source": source,
                    "identity": identity,
                    "status": status,
                    "future": future,
                    "spot": spot,
                    "change_percent": change_percent,
                    "comparison_price_change_percent": comparison_price_change,
                    "spot_change_percent": spot_change,
                    "trend": trend,
                    "basis_abs": basis_abs,
                    "basis_percent": basis_percent,
                    "basis_reason": basis_reason,
                    "oi_change": oi_change,
                    "oi_change_percent": oi_change_percent,
                    "comparison_window": comparison_window,
                    "interpretation": interpreted,
                }
            )
        volumes = sorted(
            o["future"].volume
            for o in observations
            if o["future"] and o["future"].volume is not None
        )
        interests = sorted(
            o["future"].open_interest
            for o in observations
            if o["future"] and o["future"].open_interest is not None
        )
        rows: list[dict[str, Any]] = []
        for item in observations:
            future = item["future"]
            identity = item["identity"]
            raw = item["source"]
            lot = _positive_decimal(raw.get("SEM_LOT_UNITS"))
            tick = _positive_decimal(raw.get("SEM_TICK_SIZE"))
            contract = {
                "canonical_id": (
                    f"NSE:{identity.instrument_type}:{item['symbol']}:"
                    f"{item['expiry'].isoformat()}:{identity.symbol}"
                ),
                "exchange": "NSE",
                "segment": "NSE_FNO",
                "underlying_symbol": item["symbol"],
                "instrument_type": identity.instrument_type,
                "expiry": item["expiry"].isoformat(),
                "trading_symbol": identity.provider_symbol or identity.symbol,
                "provider": "dhan",
                "provider_native_id": identity.native.native_id,
                "lot_size": int(lot) if lot and lot == int(lot) else None,
                "tick_size": str(tick) if tick else None,
            }
            values = {
                "ltp": future.last_price if future else None,
                "change_percent": item["change_percent"],
                "volume": future.volume if future else None,
                "volume_percentile": percentile(volumes, future.volume if future else None),
                "open_interest": future.open_interest if future else None,
                "oi_percentile": percentile(interests, future.open_interest if future else None),
                "change_in_open_interest": item["oi_change"],
                "oi_change_percent": item["oi_change_percent"],
                "basis_abs": item["basis_abs"],
                "basis_percent": item["basis_percent"],
                "underlying_trend": item["trend"],
                "interpretation": item["interpretation"]["label"]
                if item["interpretation"]["label"] != "Insufficient evidence"
                else None,
                "dte": (item["expiry"] - today).days,
            }
            verdict = evaluate(config.filters, values, future is not None)
            item["status"]["outcome"] = verdict["outcome"]
            if quote_error:
                item["status"]["failure"] = quote_error
            elif identity.native.native_id in missing_quotes:
                item["status"]["failure"] = "FUTURES_QUOTE_MISSING"
            rows.append(
                {
                    "contract": contract,
                    "underlying": item["symbol"],
                    "expiry": item["expiry"].isoformat(),
                    "dte": values["dte"],
                    "quote": future.model_dump(mode="json", exclude={"instrument"})
                    if future
                    else None,
                    "spot_quote": item["spot"].model_dump(mode="json", exclude={"instrument"})
                    if item["spot"]
                    else None,
                    "observed": {
                        k: float(v) if isinstance(v, Decimal) else v for k, v in values.items()
                    },
                    "volume_percentile": values["volume_percentile"],
                    "relative_volume_cohort_size": len(volumes),
                    "oi_percentile": values["oi_percentile"],
                    "relative_oi_cohort_size": len(interests),
                    "basis_reason": item["basis_reason"],
                    "spot_change_percent": float(item["spot_change_percent"])
                    if item["spot_change_percent"] is not None
                    else None,
                    "comparison_window": item["comparison_window"],
                    "comparison_price_change_percent": (
                        float(item["comparison_price_change_percent"])
                        if item["comparison_price_change_percent"] is not None
                        else None
                    ),
                    "futures_interpretation": item["interpretation"],
                    "provider": "dhan",
                    "source_time": future.provider_source_time.isoformat()
                    if future and future.provider_source_time
                    else None,
                    "received_at": future.received_at.isoformat() if future else None,
                    **verdict,
                }
            )
        result: dict[str, Any] = {
            "id": str(uuid4()),
            "created_at": now.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "config": config.model_dump(mode="json"),
            "universe_snapshot": universe_snapshot,
            "market_data_provider": "dhan",
            "generation": generation,
            "underlyings": underlyings,
            "counts": {
                "requested": len(symbols),
                "resolved": len(resolved),
                "contracts_evaluated": sum(r["outcome"] != "NOT_EVALUATED" for r in rows),
                "not_evaluated": sum(r["outcome"] == "NOT_EVALUATED" for r in rows)
                + sum(
                    u["failure"] is not None
                    for u in underlyings
                    if u["symbol"] not in {r["underlying"] for r in rows}
                ),
                "matches": sum(r["outcome"] == "MATCH" for r in rows),
            },
            "rows": rows,
            "performance": {
                "master_reads": 1,
                "quote_batches": int(bool(quote_identities)),
                "technical_history_calls": 0,
                "elapsed_ms": int((datetime.now(UTC) - now).total_seconds() * 1000),
            },
            "methodology": "futures-v1",
        }
        result["config"]["universe"]["symbols"] = list(symbols)
        with self.factory.begin() as db:
            db.add(
                ScannerRunRow(
                    id=UUID(result["id"]), owner_id=self.owner, payload=result, created_at=now
                )
            )
        return result
