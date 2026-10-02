"""Immutable, bounded completed-bar input; fixtures only in S2-2."""

from enum import StrEnum
from typing import Annotated, Protocol, Self

from pydantic import Field, model_validator

from twf.discovery.domain import Instant, InstrumentIdentity, Provenance, RevisionRef, SourceMode
from twf.discovery.providers import OperationContext
from twf.integrations.contracts import Contract, Identifier

INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}
MAX_BARS = 1024
MAX_INSTRUMENTS = 64
Price = Annotated[float, Field(gt=0, le=1e12, allow_inf_nan=False)]
Volume = Annotated[float, Field(ge=0, le=1e18, allow_inf_nan=False)]


class DataReason(StrEnum):
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    MISSING_VOLUME = "MISSING_VOLUME"
    ZERO_BASELINE = "ZERO_BASELINE"
    MALFORMED_SERIES = "MALFORMED_SERIES"
    SERIES_UNAVAILABLE = "SERIES_UNAVAILABLE"


class DataUnavailable(ValueError):
    def __init__(self, reason: DataReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


class Bar(Contract):
    # Timestamp is provider/source time. Completion is asserted only by providers
    # whose contract exposes it; TradingView currently leaves finality unspecified.
    timestamp: Instant
    available_at: Instant
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Volume | None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("Invalid OHLC relationships")
        if self.available_at < self.timestamp:
            raise ValueError("A completed bar cannot be available before completion")
        return self


class MarketSeries(Contract):
    instrument: InstrumentIdentity
    interval: Identifier
    price_unit: Identifier
    adjustment: RevisionRef
    session_basis: RevisionRef
    provenance: Provenance
    bars: tuple[Bar, ...] = Field(max_length=MAX_BARS)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.interval not in INTERVAL_SECONDS:
            raise ValueError("Unsupported interval")
        if self.provenance.mode not in {
            SourceMode.SYNTHETIC,
            SourceMode.LIVE_SNAPSHOT,
            SourceMode.DELAYED,
            SourceMode.EOD,
        }:
            raise ValueError("Unsupported source mode")
        if any(a.timestamp >= b.timestamp for a, b in zip(self.bars, self.bars[1:], strict=False)):
            raise ValueError("Bar timestamps must be unique and increasing")
        return self

    def at(self, cutoff: Instant) -> tuple[Bar, ...]:
        # Unavailable completed bars are gaps, not permission to use an older window.
        completed = tuple(b for b in self.bars if b.timestamp <= cutoff)
        if any(b.available_at > cutoff for b in completed):
            raise DataUnavailable(DataReason.SERIES_UNAVAILABLE)
        step = INTERVAL_SECONDS[self.interval]
        if any(
            (b.timestamp - a.timestamp).total_seconds() != step
            for a, b in zip(completed, completed[1:], strict=False)
        ):
            raise DataUnavailable(DataReason.MALFORMED_SERIES)
        return completed


class MarketSeriesSource(Protocol):
    async def read(
        self, context: OperationContext, instrument: InstrumentIdentity, interval: str
    ) -> MarketSeries: ...


class FixtureMarketSeriesSource:
    """Immutable snapshot of caller-supplied fixtures; no file/network/env access."""

    def __init__(self, series: tuple[MarketSeries, ...]) -> None:
        if len(series) > MAX_INSTRUMENTS * len(INTERVAL_SECONDS):
            raise ValueError("Fixture source bound exceeded")
        self._series = tuple(MarketSeries.model_validate(s.model_dump()) for s in series)
        keys = {(s.instrument.instrument_id, s.interval) for s in self._series}
        if len(keys) != len(self._series):
            raise ValueError("Duplicate fixture series")

    async def read(
        self, context: OperationContext, instrument: InstrumentIdentity, interval: str
    ) -> MarketSeries:
        for item in self._series:
            if item.instrument == instrument and item.interval == interval:
                return item
        raise DataUnavailable(DataReason.SERIES_UNAVAILABLE)
