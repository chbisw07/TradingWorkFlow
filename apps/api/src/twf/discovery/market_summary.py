"""Owner-scoped, provider-neutral global market summary."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field

from twf.discovery.domain import InstrumentIdentity
from twf.discovery.internal_scanner.market_series import Bar
from twf.discovery.market_data import (
    MarketDataErrorCode,
    MarketDataFailure,
    MarketDataProvider,
    QuoteSnapshot,
)
from twf.integrations.contracts import Contract, Identifier
from twf.watchlists.market import WatchlistHistoryCache, WatchlistQuoteCache

IST = ZoneInfo("Asia/Kolkata")


class SummaryAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class SummaryFreshness(StrEnum):
    CURRENT = "CURRENT"
    DELAYED = "DELAYED"
    LAST_SESSION = "LAST_SESSION"
    STALE = "STALE"
    RECEIVED_TIME_ONLY = "RECEIVED_TIME_ONLY"
    UNKNOWN = "UNKNOWN"


class SummaryReason(StrEnum):
    PROVIDER_NOT_READY = "PROVIDER_NOT_READY"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    RATE_LIMITED = "RATE_LIMITED"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"


class MarketSummaryItem(Contract):
    code: Identifier
    display_name: str = Field(min_length=1, max_length=32)
    instrument_identity: UUID | None = None
    value: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    previous_close: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    change_percent: Decimal | None = Field(default=None, allow_inf_nan=False)
    source: Identifier | None = None
    source_time: AwareDatetime | None = None
    received_at: AwareDatetime | None = None
    freshness: SummaryFreshness
    availability: SummaryAvailability
    reason: SummaryReason | None = None


class GlobalMarketSummary(Contract):
    nifty: MarketSummaryItem
    banknifty: MarketSummaryItem
    india_vix: MarketSummaryItem
    generated_at: AwareDatetime
    refresh_after_seconds: int = Field(ge=15, le=300)


_SPECS = (
    ("nifty", "NIFTY", "NIFTY", "NIFTY"),
    ("banknifty", "BANKNIFTY", "BANKNIFTY", "BANKNIFTY"),
    ("india_vix", "INDIA_VIX", "INDIA VIX", "INDIA VIX"),
)


def _regular_market_window(now: datetime) -> bool:
    local = now.astimezone(IST)
    return local.weekday() < 5 and time(9, 15) <= local.time() <= time(15, 30)


def _refresh_seconds(now: datetime) -> int:
    return 30 if _regular_market_window(now) else 300


def _freshness(source_time: datetime | None, now: datetime) -> SummaryFreshness:
    if source_time is None:
        return SummaryFreshness.RECEIVED_TIME_ONLY
    age = now - source_time.astimezone(UTC)
    if age < timedelta(minutes=-5):
        return SummaryFreshness.UNKNOWN
    if _regular_market_window(now):
        if age <= timedelta(minutes=5):
            return SummaryFreshness.CURRENT
        if age <= timedelta(minutes=30):
            return SummaryFreshness.DELAYED
        return SummaryFreshness.STALE
    return SummaryFreshness.LAST_SESSION if age <= timedelta(days=4) else SummaryFreshness.STALE


def _reason(code: str | None) -> SummaryReason:
    return {
        MarketDataErrorCode.AUTH_REQUIRED.value: SummaryReason.PROVIDER_NOT_READY,
        MarketDataErrorCode.INSTRUMENT_NOT_FOUND.value: SummaryReason.NOT_SUPPORTED,
        MarketDataErrorCode.AMBIGUOUS_INSTRUMENT.value: SummaryReason.NOT_SUPPORTED,
        MarketDataErrorCode.RATE_LIMITED.value: SummaryReason.RATE_LIMITED,
    }.get(code or "", SummaryReason.TEMPORARILY_UNAVAILABLE)


def _unavailable(
    code: str, display_name: str, reason: SummaryReason, identity: UUID | None = None
) -> MarketSummaryItem:
    return MarketSummaryItem(
        code=code,
        display_name=display_name,
        instrument_identity=identity,
        freshness=SummaryFreshness.UNKNOWN,
        availability=SummaryAvailability.UNAVAILABLE,
        reason=reason,
    )


def _available(
    code: str,
    display_name: str,
    quote: QuoteSnapshot,
    now: datetime,
    historical_previous_close: Decimal | None = None,
) -> MarketSummaryItem:
    previous = quote.previous_close or historical_previous_close
    change = None if previous is None else (quote.last_price - previous) / previous * Decimal(100)
    return MarketSummaryItem(
        code=code,
        display_name=display_name,
        instrument_identity=quote.instrument.instrument_id,
        value=quote.last_price,
        previous_close=previous,
        change_percent=change,
        source=quote.provider,
        source_time=quote.provider_source_time,
        received_at=quote.received_at,
        freshness=_freshness(quote.provider_source_time, now),
        availability=SummaryAvailability.AVAILABLE,
    )


class MarketSummaryCache:
    """Bounded owner/generation cache with one loader active per key."""

    def __init__(self, *, max_entries: int = 128) -> None:
        self.max_entries = max_entries
        self._items: OrderedDict[tuple[UUID, int, bool], tuple[datetime, GlobalMarketSummary]] = (
            OrderedDict()
        )
        self._locks: dict[tuple[UUID, int, bool], asyncio.Lock] = {}
        self._guard = asyncio.Lock()
        self.hits = 0
        self.misses = 0

    async def read(
        self,
        key: tuple[UUID, int, bool],
        now: datetime,
        ttl_seconds: int,
        loader: Callable[[], Awaitable[GlobalMarketSummary]],
    ) -> GlobalMarketSummary:
        async with self._guard:
            cached = self._items.get(key)
            if cached is not None and cached[0] > now:
                self.hits += 1
                self._items.move_to_end(key)
                return cached[1].model_copy(deep=True)
            lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            async with self._guard:
                cached = self._items.get(key)
                if cached is not None and cached[0] > now:
                    self.hits += 1
                    self._items.move_to_end(key)
                    return cached[1].model_copy(deep=True)
                self.misses += 1
            value = await loader()
            async with self._guard:
                self._items[key] = (now + timedelta(seconds=ttl_seconds), value)
                self._items.move_to_end(key)
                while len(self._items) > self.max_entries:
                    evicted, _ = self._items.popitem(last=False)
                    self._locks.pop(evicted, None)
            return value.model_copy(deep=True)


class GlobalMarketSummaryService:
    def __init__(
        self,
        owner_id: UUID,
        generation: int,
        provider: MarketDataProvider | None,
        quote_cache: WatchlistQuoteCache,
        history_cache: WatchlistHistoryCache,
        summary_cache: MarketSummaryCache,
    ) -> None:
        self.owner_id = owner_id
        self.generation = generation
        self.provider = provider
        self.quote_cache = quote_cache
        self.history_cache = history_cache
        self.summary_cache = summary_cache

    async def summary(self, *, now: datetime | None = None) -> GlobalMarketSummary:
        at = (now or datetime.now(UTC)).astimezone(UTC)
        refresh = _refresh_seconds(at)
        return await self.summary_cache.read(
            (self.owner_id, self.generation, self.provider is not None),
            at,
            refresh,
            lambda: self._load(at, refresh),
        )

    async def _resolve(self) -> tuple[dict[str, InstrumentIdentity], dict[str, SummaryReason]]:
        assert self.provider is not None
        symbols = tuple(spec[2] for spec in _SPECS)
        try:
            resolved = await self.provider.resolve_instruments(symbols)
            return {item.symbol: item for item in resolved}, {}
        except MarketDataFailure:
            output: dict[str, InstrumentIdentity] = {}
            failures: dict[str, SummaryReason] = {}
            for _, _, symbol, _ in _SPECS:
                try:
                    output[symbol] = (await self.provider.resolve_instruments((symbol,)))[0]
                except MarketDataFailure as exc:
                    failures[symbol] = _reason(exc.code.value)
            return output, failures

    async def _quotes(
        self, instruments: tuple[InstrumentIdentity, ...]
    ) -> tuple[dict[UUID, QuoteSnapshot], dict[UUID, SummaryReason]]:
        assert self.provider is not None
        result = await self.quote_cache.read(
            self.owner_id, self.generation, self.provider, instruments
        )
        if result["error"] is None:
            batch = tuple(QuoteSnapshot.model_validate(item) for item in result["quotes"])
            return {item.instrument.instrument_id: item for item in batch}, {}
        if result["error"] != MarketDataErrorCode.PARTIAL_RESPONSE.value:
            reason = _reason(str(result["error"]))
            return {}, {item.instrument_id: reason for item in instruments}
        quotes: dict[UUID, QuoteSnapshot] = {}
        failures: dict[UUID, SummaryReason] = {}
        for instrument in instruments:
            item = await self.quote_cache.read(
                self.owner_id, self.generation, self.provider, (instrument,)
            )
            if item["error"] is None and item["quotes"]:
                quote = QuoteSnapshot.model_validate(item["quotes"][0])
                quotes[instrument.instrument_id] = quote
            else:
                failures[instrument.instrument_id] = _reason(
                    None if item["error"] is None else str(item["error"])
                )
        return quotes, failures

    async def _historical_previous_close(self, quote: QuoteSnapshot) -> Decimal | None:
        """Recover a closing-snapshot baseline from completed daily Dhan bars.

        A Dhan closing quote may reset ``net_change`` to zero. Only a bar from a
        session strictly before the quote's provider-supplied trading date can
        establish the previous close. Missing source time or stale history stays
        unavailable rather than manufacturing a zero return.
        """

        if self.provider is None or quote.provider_source_time is None:
            return None
        result = await self.history_cache.read(
            self.owner_id,
            self.generation,
            self.provider,
            quote.instrument,
            "1d",
            5,
        )
        if result.get("error") is not None:
            return None
        raw_bars = result.get("bars")
        if not isinstance(raw_bars, list):
            return None
        try:
            bars = tuple(Bar.model_validate(item) for item in raw_bars)
        except (TypeError, ValueError):
            return None
        source_time = quote.provider_source_time.astimezone(UTC)
        source_session = quote.provider_source_time.astimezone(IST).date()
        prior = [
            bar
            for bar in bars
            if bar.timestamp.astimezone(IST).date() < source_session
            and timedelta(0) <= source_time - bar.timestamp.astimezone(UTC) <= timedelta(days=7)
        ]
        if not prior:
            return None
        close = Decimal(str(max(prior, key=lambda item: item.timestamp).close))
        return close if close.is_finite() and close > 0 else None

    async def _historical_previous_closes(
        self, quotes: dict[UUID, QuoteSnapshot]
    ) -> dict[UUID, Decimal]:
        missing = tuple(
            quote
            for quote in quotes.values()
            if quote.previous_close is None and quote.provider_source_time is not None
        )
        if not missing:
            return {}
        resolved = await asyncio.gather(
            *(self._historical_previous_close(quote) for quote in missing),
            return_exceptions=True,
        )
        return {
            quote.instrument.instrument_id: value
            for quote, value in zip(missing, resolved, strict=True)
            if isinstance(value, Decimal)
        }

    async def _load(self, now: datetime, refresh: int) -> GlobalMarketSummary:
        values: dict[str, MarketSummaryItem] = {}
        if self.provider is None:
            for field, code, _, display in _SPECS:
                values[field] = _unavailable(code, display, SummaryReason.PROVIDER_NOT_READY)
        else:
            instruments, resolution_failures = await self._resolve()
            ordered = tuple(
                instruments[symbol] for _, _, symbol, _ in _SPECS if symbol in instruments
            )
            quotes, quote_failures = await self._quotes(ordered) if ordered else ({}, {})
            historical_previous = await self._historical_previous_closes(quotes)
            for field, code, symbol, display in _SPECS:
                instrument = instruments.get(symbol)
                quote = quotes.get(instrument.instrument_id) if instrument is not None else None
                if quote is not None:
                    values[field] = _available(
                        code,
                        display,
                        quote,
                        now,
                        historical_previous.get(quote.instrument.instrument_id),
                    )
                else:
                    values[field] = _unavailable(
                        code,
                        display,
                        resolution_failures.get(
                            symbol,
                            quote_failures.get(
                                instrument.instrument_id if instrument else UUID(int=0),
                                SummaryReason.TEMPORARILY_UNAVAILABLE,
                            ),
                        ),
                        instrument.instrument_id if instrument else None,
                    )
        return GlobalMarketSummary(
            nifty=values["nifty"],
            banknifty=values["banknifty"],
            india_vix=values["india_vix"],
            generated_at=now,
            refresh_after_seconds=refresh,
        )
