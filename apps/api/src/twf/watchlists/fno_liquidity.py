"""Governed F&O underlying ranking from completed Dhan futures quote snapshots.

No option-chain fan-out or cash-volume proxy is used. One cached master and one
batched futures quote request supply each completed day's observation.
"""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from twf.discovery.market_data import DhanMarketDataProvider, MarketDataFailure
from twf.infrastructure.fno_liquidity import FnoLiquidityRow
from twf.watchlists.catalog import canonical

FNO_LIQUIDITY_METHOD_VERSION = "v1"
LIQUIDITY_LOOKBACK_DAYS = 20
MIN_COMPLETED_SESSIONS = 3
WEIGHTS = {"futures_volume": Decimal("0.60"), "futures_open_interest": Decimal("0.40")}
_SOURCE = "Dhan NSE FUTSTK batched completed-session quote; TWF percentile rank v1"
_IST = ZoneInfo("Asia/Kolkata")
_CUTOFF = time(15, 45)


def _eligible_futures(rows: tuple[dict[str, str], ...], today: date) -> dict[str, Any]:
    equities = {
        row["SEM_TRADING_SYMBOL"].upper()
        for row in rows
        if row["SEM_EXM_EXCH_ID"] == "NSE"
        and row["SEM_SEGMENT"] == "E"
        and row["SEM_INSTRUMENT_NAME"] == "EQUITY"
        and row["SEM_SERIES"] == "EQ"
    }
    options: set[str] = set()
    futures: dict[str, tuple[date, dict[str, str]]] = {}
    for row in rows:
        if row["SEM_EXM_EXCH_ID"] != "NSE" or row["SEM_SEGMENT"] == "E":
            continue
        symbol = row.get("SM_SYMBOL_NAME", "").strip().upper()
        if symbol not in equities:
            continue
        try:
            expiry = date.fromisoformat(row.get("SEM_EXPIRY_DATE", "")[:10])
        except ValueError:
            continue
        if expiry < today:
            continue
        instrument_name = row["SEM_INSTRUMENT_NAME"]
        if instrument_name == "OPTSTK":
            options.add(symbol)
        elif instrument_name == "FUTSTK":
            prior = futures.get(symbol)
            if prior is None or (expiry, row["SEM_SMST_SECURITY_ID"]) < (
                prior[0],
                prior[1]["SEM_SMST_SECURITY_ID"],
            ):
                futures[symbol] = expiry, row
    result = {}
    for symbol in sorted(equities & options & futures.keys()):
        item = canonical(futures[symbol][1])
        if item is not None and item.instrument_type == "FUTSTK":
            result[symbol] = item
    return result


def _percentiles(values: dict[str, Decimal]) -> dict[str, Decimal]:
    ordered = sorted(values.items(), key=lambda pair: (pair[1], pair[0]))
    if len(ordered) == 1:
        return {ordered[0][0]: Decimal(1)}
    result: dict[str, Decimal] = {}
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        score = Decimal(index + end - 1) / Decimal(2 * (len(ordered) - 1))
        for symbol, _ in ordered[index:end]:
            result[symbol] = score
        index = end
    return result


def rank_observations(
    observations: list[dict[str, Any]], eligible: set[str]
) -> list[dict[str, Any]]:
    """Median of up to 20 completed sessions, then cross-sectional midrank."""
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for day in observations[-LIQUIDITY_LOOKBACK_DAYS:]:
        for symbol, metrics in day["metrics"].items():
            if symbol in eligible:
                by_symbol[symbol].append(metrics)
    metrics_by_symbol: dict[str, tuple[Decimal, Decimal, int]] = {}
    for symbol, samples in by_symbol.items():
        if len(samples) < MIN_COMPLETED_SESSIONS:
            continue
        metrics_by_symbol[symbol] = (
            median(Decimal(str(sample["volume"])) for sample in samples),
            median(Decimal(str(sample["open_interest"])) for sample in samples),
            len(samples),
        )
    if not metrics_by_symbol:
        return []
    volume = _percentiles({s: metrics[0] for s, metrics in metrics_by_symbol.items()})
    oi = _percentiles({s: metrics[1] for s, metrics in metrics_by_symbol.items()})
    scored: list[dict[str, Any]] = [
        {
            "symbol": symbol,
            "score": float(
                WEIGHTS["futures_volume"] * volume[symbol]
                + WEIGHTS["futures_open_interest"] * oi[symbol]
            ),
            "futures_volume_median": str(metrics[0]),
            "futures_open_interest_median": str(metrics[1]),
            "coverage_sessions": metrics[2],
        }
        for symbol, metrics in metrics_by_symbol.items()
    ]
    scored.sort(
        key=lambda row: (-row["score"], -float(row["futures_volume_median"]), row["symbol"])
    )
    for index, row in enumerate(scored, 1):
        row["rank"] = index
    return scored


class FnoLiquidityCache:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory
        self.lock = asyncio.Lock()
        self.attempted: date | None = None

    def load(self) -> dict[str, Any]:
        with self.factory() as db:
            row = db.get(FnoLiquidityRow, "ranked")
            return dict(row.payload) if row else {"observations": [], "ranked": []}

    def _save(self, payload: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        with self.factory() as db:
            row = db.get(FnoLiquidityRow, "ranked")
            if row is None:
                db.add(FnoLiquidityRow(key="ranked", payload=payload, updated_at=now))
            else:
                row.payload = payload
                row.updated_at = now
            db.commit()

    def _record_failure(self, day: date, category: str) -> None:
        """Keep prior observations/rank intact while recording a bounded failure category."""
        try:
            with self.factory.begin() as db:
                row = db.get(FnoLiquidityRow, "ranked", with_for_update=True)
                if row is not None and row.payload.get("last_observed_date", "") >= day.isoformat():
                    return
                now = datetime.now(UTC)
                payload = dict(row.payload) if row else {"observations": [], "ranked": []}
                payload["last_error_category"] = category
                payload["last_refresh_attempt_at"] = now.isoformat()
                if row is None:
                    db.add(FnoLiquidityRow(key="ranked", payload=payload, updated_at=now))
                else:
                    row.payload = payload
                    row.updated_at = now
        except IntegrityError:
            # Another worker created the global cache row first.
            return

    @staticmethod
    def readiness(
        payload: dict[str, Any], *, credential_available: bool, now: datetime | None = None
    ) -> dict[str, Any]:
        """Describe collection progress independently from scanner eligibility."""
        now = now or datetime.now(UTC)
        observations = payload.get("observations", [])
        coverage: Counter[str] = Counter()
        for row in observations:
            coverage.update(row["metrics"].keys())
        sessions = max(coverage.values(), default=0)
        ranked = payload.get("ranked", [])
        generated_text = payload.get("generated_at")
        generated = datetime.fromisoformat(generated_text) if generated_text else None
        age = now - generated if generated else None
        usable = bool(ranked and age is not None and age <= timedelta(days=7))
        completed = FnoLiquidityCache.completed_date(now)
        stale = bool(
            usable
            and (
                (age is not None and age > timedelta(hours=24))
                or (completed is not None and payload.get("as_of_date", "") < completed.isoformat())
            )
        )
        error = payload.get("last_error_category")
        if not credential_available:
            state = "CREDENTIAL_UNAVAILABLE"
            error = "CREDENTIAL_UNAVAILABLE"
        elif usable:
            state = "STALE" if stale else "READY"
        elif error in {"PROVIDER_FAILURE", "NO_COMPLETED_QUOTE", "NO_ELIGIBLE_FUTURES"}:
            state = "PROVIDER_UNAVAILABLE"
        elif 0 < sessions < MIN_COMPLETED_SESSIONS:
            state = "BUILDING_HISTORY"
        else:
            state = "INSUFFICIENT_HISTORY"
        return {
            "state": state,
            "completed_sessions_collected": sessions,
            "minimum_sessions_required": MIN_COMPLETED_SESSIONS,
            "lookback_sessions_target": LIQUIDITY_LOOKBACK_DAYS,
            "as_of_date": payload.get("as_of_date"),
            "generated_at": generated_text,
            "stale": stale,
            "methodology_version": FNO_LIQUIDITY_METHOD_VERSION,
            "last_error_category": error,
            "last_success_at": payload.get("last_success_at", generated_text),
            "earliest_session": payload.get("earliest_session"),
            "latest_session": payload.get("latest_session"),
            "observation_count_used": payload.get("observation_count_used"),
        }

    def _save_daily(self, payload: dict[str, Any], day: date) -> None:
        """Publish once per date; concurrent workers keep the first valid result."""
        try:
            with self.factory.begin() as db:
                row = db.get(FnoLiquidityRow, "ranked", with_for_update=True)
                if row is not None and row.payload.get("last_observed_date", "") >= day.isoformat():
                    return
                now = datetime.now(UTC)
                if row is None:
                    db.add(FnoLiquidityRow(key="ranked", payload=payload, updated_at=now))
                else:
                    row.payload = payload
                    row.updated_at = now
        except IntegrityError:
            # Another worker inserted the same global cache row first.
            return

    @staticmethod
    def completed_date(now: datetime) -> date | None:
        local = now.astimezone(_IST)
        return local.date() if local.weekday() < 5 and local.time() >= _CUTOFF else None

    async def refresh(self, provider: DhanMarketDataProvider) -> None:
        today = self.completed_date(datetime.now(UTC))
        if today is None:
            return
        cached = self.load()
        if cached.get("last_observed_date") == today.isoformat() or self.attempted == today:
            return
        async with self.lock:
            cached = self.load()
            if cached.get("last_observed_date") == today.isoformat() or self.attempted == today:
                return
            self.attempted = today
            try:
                rows = await provider._load_master()
                eligible = _eligible_futures(rows, today)
                if not eligible or len(eligible) > 1000:
                    self._record_failure(today, "NO_ELIGIBLE_FUTURES")
                    return
                quotes = await provider.get_quotes(tuple(eligible.values()))
                metrics: dict[str, dict[str, str]] = {}
                for symbol, quote in zip(eligible, quotes, strict=True):
                    if (
                        quote.provider == "dhan"
                        and quote.provider_source_time is not None
                        and quote.provider_source_time.astimezone(_IST).date() == today
                        and quote.volume is not None
                        and quote.volume > 0
                        and quote.open_interest is not None
                        and quote.open_interest > 0
                    ):
                        metrics[symbol] = {
                            "volume": str(quote.volume),
                            "open_interest": str(quote.open_interest),
                            "source_time": quote.provider_source_time.isoformat(),
                        }
                if not metrics:
                    self._record_failure(today, "NO_COMPLETED_QUOTE")
                    return
                observations = [
                    day
                    for day in cached.get("observations", [])
                    if day["date"] != today.isoformat()
                ]
                observations.append({"date": today.isoformat(), "metrics": metrics})
                observations = sorted(observations, key=lambda day: day["date"])[
                    -LIQUIDITY_LOOKBACK_DAYS:
                ]
                ranked = rank_observations(observations, set(eligible))
                payload = {
                    "observations": observations,
                    "ranked": ranked if ranked else cached.get("ranked", []),
                    "as_of_date": today.isoformat() if ranked else cached.get("as_of_date"),
                    "last_observed_date": today.isoformat(),
                    "generated_at": (
                        datetime.now(UTC).isoformat() if ranked else cached.get("generated_at")
                    ),
                    "methodology_version": FNO_LIQUIDITY_METHOD_VERSION,
                    "source": _SOURCE,
                    "eligible_count": len(eligible),
                    "quoted_count": len(metrics),
                    "provider_calls": {"compact_master": 1, "batch_quotes": 1},
                    "last_success_at": datetime.now(UTC).isoformat(),
                    "last_error_category": None,
                    "earliest_session": observations[0]["date"]
                    if ranked
                    else cached.get("earliest_session"),
                    "latest_session": observations[-1]["date"]
                    if ranked
                    else cached.get("latest_session"),
                    "observation_count_used": len(observations)
                    if ranked
                    else cached.get("observation_count_used"),
                }
                self._save_daily(payload, today)
            except (MarketDataFailure, TimeoutError):
                # A failed provider refresh never replaces the last valid snapshot.
                self._record_failure(today, "PROVIDER_FAILURE")
                return
