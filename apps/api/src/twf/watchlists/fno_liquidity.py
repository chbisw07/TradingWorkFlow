"""Governed F&O underlying ranking from completed Dhan futures quote snapshots.

No option-chain fan-out or cash-volume proxy is used. One cached master and one
batched futures quote request supply each completed day's observation.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from twf.discovery.dhan_credentials import DhanCredentialManager
from twf.discovery.market_data import DhanMarketDataProvider, MarketDataFailure
from twf.infrastructure.dhan import DhanMarketDataConnection
from twf.infrastructure.fno_liquidity import FnoLiquidityRow
from twf.watchlists.catalog import canonical

FNO_LIQUIDITY_METHOD_VERSION = "v1"
LIQUIDITY_LOOKBACK_DAYS = 20
MIN_COMPLETED_SESSIONS = 3
WEIGHTS = {"futures_volume": Decimal("0.60"), "futures_open_interest": Decimal("0.40")}
_SOURCE = "Dhan NSE FUTSTK batched completed-session quote; TWF percentile rank v1"
_IST = ZoneInfo("Asia/Kolkata")
_CUTOFF = time(15, 45)
_RETRY_AFTER = timedelta(minutes=15)
logger = logging.getLogger(__name__)


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


def _valid_metrics(metrics: dict[str, Any], session_date: str) -> bool:
    try:
        volume = Decimal(str(metrics["volume"]))
        interest = Decimal(str(metrics["open_interest"]))
        source_time = datetime.fromisoformat(str(metrics["source_time"]))
        return (
            volume.is_finite()
            and volume > 0
            and interest.is_finite()
            and interest > 0
            and source_time.tzinfo is not None
            and source_time.astimezone(_IST).date().isoformat() == session_date
        )
    except (KeyError, ValueError, TypeError, ArithmeticError):
        return False


def rank_observations(
    observations: list[dict[str, Any]], eligible: set[str]
) -> list[dict[str, Any]]:
    """Median of up to 20 completed sessions, then cross-sectional midrank."""
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_dates: set[str] = set()
    for day in observations[-LIQUIDITY_LOOKBACK_DAYS:]:
        session_date = str(day.get("date", ""))
        if session_date in seen_dates:
            continue
        seen_dates.add(session_date)
        for symbol, metrics in day.get("metrics", {}).items():
            if symbol in eligible and _valid_metrics(metrics, session_date):
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

    def load(self) -> dict[str, Any]:
        with self.factory() as db:
            row = db.get(FnoLiquidityRow, "ranked")
            return dict(row.payload) if row else {"observations": [], "ranked": []}

    @staticmethod
    def completed_date(now: datetime) -> date | None:
        local = now.astimezone(_IST)
        return local.date() if local.weekday() < 5 and local.time() >= _CUTOFF else None

    @staticmethod
    def readiness(
        payload: dict[str, Any], *, credential_available: bool, now: datetime | None = None
    ) -> dict[str, Any]:
        """Count distinct valid completed sessions; do not infer readiness from calendar days."""
        now = now or datetime.now(UTC)
        coverage: dict[str, set[str]] = defaultdict(set)
        for day in payload.get("observations", []):
            session_date = day.get("date", "")
            for symbol, metrics in day.get("metrics", {}).items():
                if _valid_metrics(metrics, session_date):
                    coverage[symbol].add(session_date)
        sessions = max((len(days) for days in coverage.values()), default=0)
        ranked = payload.get("ranked", [])
        generated_text = payload.get("generated_at")
        generated = datetime.fromisoformat(generated_text) if generated_text else None
        age = now - generated if generated else None
        usable = bool(
            ranked
            and sessions >= MIN_COMPLETED_SESSIONS
            and age is not None
            and age <= timedelta(days=7)
        )
        completed = FnoLiquidityCache.completed_date(now)
        error = payload.get("last_error_category")
        stale = bool(
            (ranked and age is not None and age > timedelta(days=7))
            or usable
            and (
                bool(error)
                or (age is not None and age > timedelta(hours=24))
                or (completed is not None and payload.get("as_of_date", "") < completed.isoformat())
            )
        )
        if not credential_available:
            state, reason = "CREDENTIAL_UNAVAILABLE", "Dhan credentials unavailable"
        elif usable:
            state = "STALE" if stale else "READY"
            reason = (
                f"Last good universe from {payload.get('as_of_date', 'unknown')}"
                if stale
                else f"{sessions} completed sessions; universe ready"
            )
        elif ranked and age is not None and age > timedelta(days=7):
            state, reason = "STALE", "Last good universe is older than seven days"
        elif sessions >= MIN_COMPLETED_SESSIONS and not ranked:
            state, reason = "ERROR", "Ranking unavailable despite three valid completed sessions"
        elif error == "PROVIDER_FAILURE":
            state, reason = (
                "PROVIDER_UNAVAILABLE",
                "Latest completed-session capture failed at Dhan",
            )
        elif error == "NO_ELIGIBLE_FUTURES":
            state, reason = (
                "ERROR",
                "No current NSE equity with active stock futures and options resolved",
            )
        elif error == "NO_COMPLETED_QUOTE":
            state, reason = "ACCUMULATING", "Latest completed-session quote had no valid volume/OI"
        elif error == "PARTIAL_COMPLETED_QUOTE":
            state = "ACCUMULATING"
            reason = (
                f"{sessions}/{MIN_COMPLETED_SESSIONS} sessions; latest capture partial "
                f"({payload.get('quoted_count', 0)}/{payload.get('eligible_count', 0)} contracts)"
            )
        else:
            state = "ACCUMULATING"
            reason = f"{sessions}/{MIN_COMPLETED_SESSIONS} completed sessions collected"
        return {
            "state": state,
            "reason": reason,
            "completed_sessions_collected": sessions,
            "minimum_sessions_required": MIN_COMPLETED_SESSIONS,
            "lookback_sessions_target": LIQUIDITY_LOOKBACK_DAYS,
            "as_of_date": payload.get("as_of_date"),
            "generated_at": generated_text,
            "stale": stale,
            "methodology_version": FNO_LIQUIDITY_METHOD_VERSION,
            "last_error_category": error,
            "last_refresh_attempt_at": payload.get("last_refresh_attempt_at"),
            "last_success_at": payload.get("last_success_at", generated_text),
            "earliest_session": payload.get("earliest_session"),
            "latest_session": payload.get("latest_session"),
            "observation_count_used": payload.get("observation_count_used"),
            "eligible_count": payload.get("eligible_count"),
            "quoted_count": payload.get("quoted_count"),
        }

    def _update(self, transform: Any) -> None:
        """Serialize merges against the persisted payload; preserve last-known-good ranking."""
        for attempt in range(2):
            try:
                with self.factory.begin() as db:
                    row = db.get(FnoLiquidityRow, "ranked", with_for_update=True)
                    payload = dict(row.payload) if row else {"observations": [], "ranked": []}
                    updated = transform(payload)
                    now = datetime.now(UTC)
                    if row is None:
                        db.add(FnoLiquidityRow(key="ranked", payload=updated, updated_at=now))
                    else:
                        row.payload = updated
                        row.updated_at = now
                return
            except IntegrityError:
                if attempt:
                    raise

    def _record_failure(self, day: date, category: str) -> None:
        def change(payload: dict[str, Any]) -> dict[str, Any]:
            payload["last_error_category"] = category
            payload["last_refresh_attempt_at"] = datetime.now(UTC).isoformat()
            payload["last_attempted_session"] = day.isoformat()
            return payload

        self._update(change)
        logger.warning("fno_liquidity_capture_failed session=%s reason=%s", day, category)

    def _save_daily(
        self,
        day: date,
        metrics: dict[str, dict[str, str]],
        eligible: set[str],
        failures: dict[str, str],
    ) -> None:
        def change(payload: dict[str, Any]) -> dict[str, Any]:
            observations = list(payload.get("observations", []))
            same = next((item for item in observations if item["date"] == day.isoformat()), None)
            merged = dict(same.get("metrics", {})) if same else {}
            # A previously valid session observation is immutable on retry.
            for symbol, sample in metrics.items():
                if symbol not in merged:
                    merged[symbol] = sample
            observations = [item for item in observations if item["date"] != day.isoformat()]
            unresolved = dict(same.get("failures", {})) if same else {}
            unresolved.update(failures)
            for symbol in merged:
                unresolved.pop(symbol, None)
            observations.append(
                {
                    "date": day.isoformat(),
                    "metrics": merged,
                    "failures": unresolved,
                    "attempted_count": len(eligible),
                    "quoted_count": len(merged),
                }
            )
            observations = sorted(observations, key=lambda item: item["date"])[
                -LIQUIDITY_LOOKBACK_DAYS:
            ]
            ranked = rank_observations(observations, eligible)
            now = datetime.now(UTC).isoformat()
            payload.update(
                observations=observations,
                last_observed_date=day.isoformat(),
                last_attempted_session=day.isoformat(),
                last_refresh_attempt_at=now,
                last_success_at=now,
                last_error_category=None if not unresolved else "PARTIAL_COMPLETED_QUOTE",
                eligible_count=len(eligible),
                quoted_count=len(merged),
                missing_count=len(unresolved),
                methodology_version=FNO_LIQUIDITY_METHOD_VERSION,
                source=_SOURCE,
                provider_calls={"detailed_master": 1, "batch_quotes": 1},
            )
            if ranked:
                payload.update(
                    ranked=ranked,
                    as_of_date=day.isoformat(),
                    generated_at=now,
                    earliest_session=observations[0]["date"],
                    latest_session=observations[-1]["date"],
                    observation_count_used=len(observations),
                )
            return payload

        self._update(change)
        logger.info(
            "fno_liquidity_capture session=%s eligible=%d succeeded=%d missing=%d",
            day,
            len(eligible),
            len(metrics),
            len(failures),
        )

    async def refresh(self, provider: DhanMarketDataProvider) -> None:
        now = datetime.now(UTC)
        today = self.completed_date(now)
        if today is None:
            # Repair a persisted pre-fix eligibility error using current structured
            # master truth, without treating an open session as completed evidence.
            if self.load().get("last_error_category") == "NO_ELIGIBLE_FUTURES":
                async with self.lock:
                    if self.load().get("last_error_category") == "NO_ELIGIBLE_FUTURES":
                        try:
                            rows = await provider._load_liquidity_master()
                            eligible = _eligible_futures(rows, datetime.now(_IST).date())
                            if eligible:

                                def clear(payload: dict[str, Any]) -> dict[str, Any]:
                                    payload["eligible_count"] = len(eligible)
                                    payload["last_error_category"] = None
                                    payload["eligibility_verified_at"] = datetime.now(
                                        UTC
                                    ).isoformat()
                                    return payload

                                self._update(clear)
                        except (MarketDataFailure, TimeoutError):
                            pass
            return
        async with self.lock:
            cached = self.load()
            if cached.get("last_observed_date") == today.isoformat() and cached.get(
                "quoted_count", 0
            ) >= cached.get("eligible_count", 1):
                return
            attempted_at = cached.get("last_refresh_attempt_at")
            if cached.get("last_attempted_session") == today.isoformat() and attempted_at:
                try:
                    if now - datetime.fromisoformat(attempted_at) < _RETRY_AFTER:
                        return
                except ValueError:
                    pass
            try:
                rows = await provider._load_liquidity_master()
                eligible = _eligible_futures(rows, today)
                if not eligible or len(eligible) > 1000:
                    self._record_failure(today, "NO_ELIGIBLE_FUTURES")
                    return
                contract_dates = {
                    row["SEM_SMST_SECURITY_ID"]: row["SEM_EXPIRY_DATE"][:10]
                    for row in rows
                    if row["SEM_INSTRUMENT_NAME"] == "FUTSTK"
                }
                quotes, missing = await provider.get_quotes_partial(tuple(eligible.values()))
                by_id = {quote.instrument.native.native_id: quote for quote in quotes}
                metrics: dict[str, dict[str, str]] = {}
                failures: dict[str, str] = {}
                for symbol, identity in eligible.items():
                    quote = by_id.get(identity.native.native_id)
                    if quote is None:
                        failures[symbol] = "QUOTE_MISSING"
                    elif quote.provider != "dhan" or quote.provider_source_time is None:
                        failures[symbol] = "SOURCE_TIME_MISSING"
                    elif quote.provider_source_time.astimezone(_IST).date() != today:
                        failures[symbol] = "SOURCE_SESSION_MISMATCH"
                    elif quote.volume is None or quote.volume <= 0:
                        failures[symbol] = "VOLUME_INVALID"
                    elif quote.open_interest is None or quote.open_interest <= 0:
                        failures[symbol] = "OI_INVALID"
                    else:
                        metrics[symbol] = {
                            "volume": str(quote.volume),
                            "open_interest": str(quote.open_interest),
                            "source_time": quote.provider_source_time.isoformat(),
                            "contract_id": identity.native.native_id,
                            "expiry": contract_dates[identity.native.native_id.split(":")[-1]],
                        }
                if not metrics:
                    self._record_failure(today, "NO_COMPLETED_QUOTE")
                    return
                self._save_daily(today, metrics, set(eligible), failures)
                logger.info("fno_liquidity_quote_batch missing_ids=%d", len(missing))
            except (MarketDataFailure, TimeoutError) as exc:
                logger.warning("fno_liquidity_provider_error type=%s", type(exc).__name__)
                self._record_failure(today, "PROVIDER_FAILURE")


async def collect_completed_sessions(
    cache: FnoLiquidityCache,
    credentials: DhanCredentialManager,
    factory: sessionmaker[Session],
) -> None:
    """Background completed-session collector, independent of watchlist page visits.

    Persisted session/cooldown state makes API restarts harmless. This process
    never backfills a date using a later quote or counts a market holiday.
    """
    while True:
        await asyncio.sleep(60)
        if cache.completed_date(datetime.now(UTC)) is None:
            continue
        try:
            with factory() as db:
                owners = db.scalars(
                    select(DhanMarketDataConnection.owner_id).where(
                        DhanMarketDataConnection.enabled.is_(True)
                    )
                ).all()
            for owner in owners:
                capture = credentials.capture(owner, ready_only=True)
                if isinstance(capture.provider, DhanMarketDataProvider):
                    await cache.refresh(capture.provider)
                    break
        except Exception:
            logger.exception("fno_liquidity_background_capture_failed")
        await asyncio.sleep(240)
