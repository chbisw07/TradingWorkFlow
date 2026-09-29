"""Small fabricated OHLCV series; no historic prices, credentials or network."""

from collections.abc import Sequence
from datetime import timedelta
from uuid import UUID

from discovery_support import NOW, context, replace, scan_run

from twf.discovery.domain import InstrumentIdentity, RevisionRef, ScanDefinition, ScanRun
from twf.discovery.internal_scanner.market_series import Bar, MarketSeries
from twf.discovery.synthetic import SyntheticCandidateSource, fixture_instruments


def series(
    closes: Sequence[float],
    *,
    volumes: Sequence[float | None] | None = None,
    instrument: InstrumentIdentity | None = None,
    step: int = 60,
    interval: str = "1m",
    end_seconds: int = 0,
) -> MarketSeries:
    instrument = instrument or fixture_instruments()[0]
    source = SyntheticCandidateSource()
    return MarketSeries(
        instrument=instrument,
        interval=interval,
        price_unit="FIXTURE",
        adjustment=RevisionRef(id="fabricated-unadjusted", version="1"),
        session_basis=RevisionRef(id="continuous-fixture-clock", version="1"),
        provenance=source.provenance(instrument, NOW),
        bars=tuple(
            Bar(
                timestamp=NOW + timedelta(seconds=end_seconds - step * (len(closes) - 1 - i)),
                available_at=NOW + timedelta(seconds=end_seconds - step * (len(closes) - 1 - i)),
                open=value,
                high=value + 0.1,
                low=value - 0.1,
                close=value,
                volume=100 if volumes is None else volumes[i],
            )
            for i, value in enumerate(closes)
        ),
    )


def run_for(definition: ScanDefinition, seconds: int = 0, owner: UUID | None = None) -> ScanRun:
    ctx = context(seconds) if owner is None else context(seconds, owner)
    return replace(scan_run(ctx), definition=definition)


def with_last(original: MarketSeries, close: float, *, seconds: int = 60) -> MarketSeries:
    last = original.bars[-1]
    new = replace(
        last,
        timestamp=NOW + timedelta(seconds=seconds),
        available_at=NOW + timedelta(seconds=seconds),
        open=close,
        high=close + 0.1,
        low=close - 0.1,
        close=close,
    )
    return replace(original, bars=(*original.bars, new))
