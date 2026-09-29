"""Pure float64 arithmetic, finite bounded inputs, explicit seed/window policies."""

from collections.abc import Sequence
from math import fsum, isfinite

from twf.discovery.internal_scanner.market_series import Bar, DataReason, DataUnavailable


def require_finite(values: Sequence[float]) -> None:
    """Reject invalid numeric state before it can become a match or nonmatch."""
    if any(not isfinite(v) for v in values):
        raise DataUnavailable(DataReason.MALFORMED_SERIES)


def require(values: Sequence[float], period: int, extra: int = 0) -> None:
    if type(period) is not int or not 1 <= period <= 252:
        raise ValueError("Period must be an integer in [1, 252]")
    if len(values) < period + extra:
        raise DataUnavailable(DataReason.INSUFFICIENT_HISTORY)
    require_finite(values)


def sma(values: Sequence[float], period: int) -> float:
    require(values, period)
    return fsum(values[-period:]) / period


def ema(values: Sequence[float], period: int) -> float:
    require(values, period)
    result = fsum(values[:period]) / period
    alpha = 2 / (period + 1)
    for value in values[period:]:
        result += alpha * (value - result)
    return result


def rsi(values: Sequence[float], period: int) -> float:
    require(values, period, 1)
    deltas = [b - a for a, b in zip(values, values[1:], strict=False)]
    gain = fsum(max(d, 0) for d in deltas[:period]) / period
    loss = fsum(max(-d, 0) for d in deltas[:period]) / period
    for delta in deltas[period:]:
        gain = (gain * (period - 1) + max(delta, 0)) / period
        loss = (loss * (period - 1) + max(-delta, 0)) / period
    if gain == loss == 0:
        return 50.0  # Explicit neutral flat-series convention.
    return 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)


def atr(bars: Sequence[Bar], period: int) -> float:
    require([b.close for b in bars], period, 1)
    ranges = [
        max(b.high - b.low, abs(b.high - a.close), abs(b.low - a.close))
        for a, b in zip(bars, bars[1:], strict=False)
    ]
    result = fsum(ranges[:period]) / period
    for value in ranges[period:]:
        result = (result * (period - 1) + value) / period
    return result


def average_volume(bars: Sequence[Bar], period: int) -> float:
    require([b.close for b in bars], period, 1)
    volumes = [b.volume for b in bars[-period - 1 : -1]]
    if any(v is None for v in volumes):
        raise DataUnavailable(DataReason.MISSING_VOLUME)
    return fsum(v for v in volumes if v is not None) / period


def relative_volume(bars: Sequence[Bar], period: int) -> float:
    baseline = average_volume(bars, period)
    current = bars[-1].volume
    if current is None:
        raise DataUnavailable(DataReason.MISSING_VOLUME)
    if baseline == 0:
        raise DataUnavailable(DataReason.ZERO_BASELINE)
    return current / baseline


def roc(values: Sequence[float], period: int) -> float:
    require(values, period, 1)
    if values[-period - 1] == 0:
        raise DataUnavailable(DataReason.ZERO_BASELINE)
    return 100 * (values[-1] / values[-period - 1] - 1)


def momentum(values: Sequence[float], period: int) -> float:
    require(values, period, 1)
    return values[-1] - values[-period - 1]


def rolling_high(bars: Sequence[Bar], period: int) -> float:
    require([b.close for b in bars], period, 1)
    return max(b.high for b in bars[-period - 1 : -1])


def rolling_low(bars: Sequence[Bar], period: int) -> float:
    require([b.close for b in bars], period, 1)
    return min(b.low for b in bars[-period - 1 : -1])


def cross_above(previous_lhs: float, previous_rhs: float, lhs: float, rhs: float) -> bool:
    require_finite((previous_lhs, previous_rhs, lhs, rhs))
    return previous_lhs <= previous_rhs and lhs > rhs


def cross_below(previous_lhs: float, previous_rhs: float, lhs: float, rhs: float) -> bool:
    require_finite((previous_lhs, previous_rhs, lhs, rhs))
    return previous_lhs >= previous_rhs and lhs < rhs
