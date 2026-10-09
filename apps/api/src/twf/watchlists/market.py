"""Bounded quote overlay, separate from durable watchlist membership."""

import asyncio
from collections import OrderedDict
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from uuid import UUID

from twf.discovery.domain import InstrumentIdentity
from twf.discovery.internal_scanner.indicators import atr, rsi, sma
from twf.discovery.internal_scanner.market_series import Bar
from twf.discovery.market_data import MarketDataFailure, MarketDataProvider
from twf.watchlists.contracts import WatchlistHistoryMetrics

ATR_PERIOD = 14
WEEK_52_SESSIONS = 252
WEEK_52_MIN_SESSIONS = 200
WATCHLIST_DAILY_HISTORY_SESSIONS = 260


class WatchlistQuoteCache:
    def __init__(self) -> None:
        self.values: OrderedDict[
            tuple[UUID, int, tuple[UUID, ...]], tuple[float, dict[str, Any]]
        ] = OrderedDict()
        self.lock = asyncio.Lock()

    async def read(
        self,
        owner: UUID,
        generation: int,
        provider: MarketDataProvider | None,
        instruments: tuple[InstrumentIdentity, ...],
    ) -> dict[str, Any]:
        key = owner, generation, tuple(i.instrument_id for i in instruments)
        # A single bounded batch, never a provider call for each row.
        async with self.lock:
            at = datetime.now(UTC).timestamp()
            cached = self.values.get(key)
            if cached and at - cached[0] < 15:
                return cached[1]
            result: dict[str, Any] = {"provider": "dhan", "quotes": [], "error": None}
            if not provider:
                result["error"] = "AUTH_REQUIRED"
            elif instruments:
                try:
                    quotes = await provider.get_quotes(instruments)
                    result["quotes"] = [q.model_dump(mode="json") for q in quotes]
                except MarketDataFailure as exc:
                    result["error"] = exc.code.value
            self.values[key] = (at, result)
            self.values.move_to_end(key)
            while len(self.values) > 128:
                self.values.popitem(last=False)
            return result


def history_metrics(bars: tuple[Bar, ...], interval: str) -> dict[str, Any] | None:
    """Shared metrics from the normalized, bounded daily row series."""
    if interval != "1d" or len(bars) < 20:
        return None
    closes = [float(b.close) for b in bars]
    average = sma(closes, 20)
    volumes = [b.volume for b in bars[-20:]]
    atr14 = atr(bars, ATR_PERIOD)
    high_52w = low_52w = None
    if len(bars) >= WEEK_52_MIN_SESSIONS:
        window = bars[-WEEK_52_SESSIONS:]
        high_52w = max(float(bar.high) for bar in window)
        low_52w = min(float(bar.low) for bar in window)
    return WatchlistHistoryMetrics(
        rsi14=rsi(closes, 14),
        trend="Up" if closes[-1] > average else "Down" if closes[-1] < average else "Sideways",
        average_volume20=(
            sum(float(v) for v in volumes if v is not None) / 20
            if all(v is not None for v in volumes)
            else None
        ),
        atr14=atr14,
        atr_percent=atr14 / closes[-1] * 100,
        high_52w=high_52w,
        low_52w=low_52w,
        high_52w_distance_percent=None,
        low_52w_distance_percent=None,
        history_coverage_sessions=len(bars),
        as_of=bars[-1].timestamp,
        basis=(
            "Completed daily bars; Wilder RSI(14) and ATR(14); close versus SMA(20); "
            "52-week range requires at least 200 sessions"
        ),
    ).model_dump(mode="json")


def metrics_for_ltp(
    metrics: dict[str, Any] | None,
    last_price: float | None,
    *,
    market_metrics_supported: bool = True,
) -> dict[str, Any] | None:
    """Attach live-LTP distances without mutating the cached completed-bar metrics."""
    if metrics is None:
        return None
    result = dict(metrics)
    if not market_metrics_supported:
        for field in (
            "atr14",
            "atr_percent",
            "high_52w",
            "low_52w",
            "high_52w_distance_percent",
            "low_52w_distance_percent",
        ):
            result[field] = None
        return result
    high = result.get("high_52w")
    low = result.get("low_52w")
    if last_price is not None and last_price > 0:
        if high is not None and high > 0:
            result["high_52w_distance_percent"] = (high - last_price) / high * 100
        if low is not None and low > 0:
            result["low_52w_distance_percent"] = (last_price - low) / low * 100
    return result


class WatchlistHistoryCache:
    """Owner/generation fenced history, shared by visible rows and detail views.

    Serial provider I/O with at least one second between starts; this is an
    asyncio lock, never a DB lock. Waiting plus I/O has a 12-second budget.
    Successful history lives for five minutes, failures for 30 seconds.
    """

    def __init__(self) -> None:
        self.values: OrderedDict[tuple[UUID, int, UUID, str, int], tuple[float, dict[str, Any]]] = (
            OrderedDict()
        )
        self.lock = asyncio.Lock()
        self.next_start = 0.0
        self.cooldown_until = 0.0

    async def read(
        self,
        owner: UUID,
        generation: int,
        provider: MarketDataProvider | None,
        instrument: InstrumentIdentity,
        interval: str,
        count: int,
    ) -> dict[str, Any]:
        if provider is None:
            return {"provider": "dhan", "bars": [], "error": "AUTH_REQUIRED"}
        key = owner, generation, instrument.instrument_id, interval, count
        try:
            async with asyncio.timeout(12):
                async with self.lock:
                    cached = self.values.get(key)
                    if cached and monotonic() < cached[0]:
                        self.values.move_to_end(key)
                        return cached[1]
                    if monotonic() < self.cooldown_until:
                        return {"provider": "dhan", "bars": [], "error": "RATE_LIMITED"}
                    await asyncio.sleep(max(0, self.next_start - monotonic()))
                    self.next_start = monotonic() + 1
                    try:
                        series = await provider.get_ohlcv(
                            instrument, interval, as_of=datetime.now(UTC), count=count
                        )
                        result: dict[str, Any] = {
                            "provider": "dhan",
                            "interval": interval,
                            "bars": [b.model_dump(mode="json") for b in series.bars],
                            "metrics": history_metrics(series.bars, interval),
                            "received_at": series.received_at.isoformat()
                            if series.received_at
                            else None,
                            "error": None,
                        }
                    except MarketDataFailure as exc:
                        result = {"provider": "dhan", "bars": [], "error": exc.code.value}
                        if exc.code.value == "RATE_LIMITED":
                            self.cooldown_until = monotonic() + 30
                    self.values[key] = (monotonic() + (30 if result["error"] else 300), result)
                    self.values.move_to_end(key)
                    while len(self.values) > 256:
                        self.values.popitem(last=False)
                    return result
        except TimeoutError:
            return {"provider": "dhan", "bars": [], "error": "TIMEOUT"}
