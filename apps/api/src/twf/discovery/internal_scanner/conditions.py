"""Finite derived measures expressed through the existing Criterion contract."""

from collections.abc import Sequence
from math import isclose

from twf.discovery.domain import Comparison, Criterion
from twf.discovery.internal_scanner import indicators as ind
from twf.discovery.internal_scanner.market_series import Bar, DataReason, DataUnavailable

# Units are semantic roles. The actual price currency is separately retained in evidence.
METRICS = {
    "close": "price",
    "volume": "volume",
    "sma.20": "price",
    "sma.50": "price",
    "sma.200": "price",
    "ema.20": "price",
    "rsi.14": "index",
    "atr.14": "price",
    "roc.1": "percent",
    "roc.10": "percent",
    "momentum.10": "price",
    "average_volume.20": "volume",
    "relative_volume.20": "ratio",
    "rolling_high.20": "price",
    "rolling_low.20": "price",
    "rolling_high.252": "price",
    "rolling_low.252": "price",
    "close_sma20_gap": "percent",
    "close_sma50_gap": "percent",
    "sma50_sma200_gap": "percent",
    "breakout.20": "boolean",
    "breakdown.20": "boolean",
    "cross_above_sma.20": "boolean",
    "cross_below_sma.20": "boolean",
}
OPERATORS = tuple(c.value for c in Comparison)


def supported(criterion: Criterion) -> bool:
    return (
        criterion.metric in METRICS
        and criterion.unit == METRICS[criterion.metric]
        and abs(criterion.threshold) <= 1e12
        and (
            criterion.unit != "boolean"
            or (criterion.operator == Comparison.EQ and criterion.threshold in (0, 1))
        )
    )


def measure(metric: str, bars: Sequence[Bar]) -> float:
    """Every metric passes this boundary before profile/scalar evaluation."""
    value = _measure(metric, bars)
    ind.require_finite((value,))
    return value


def _measure(metric: str, bars: Sequence[Bar]) -> float:
    if metric not in METRICS:
        raise ValueError("Unsupported metric")
    ind.require([b.close for b in bars], 1)
    closes = [b.close for b in bars]
    if metric == "close":
        return closes[-1]
    if metric == "volume":
        if bars[-1].volume is None:
            raise DataUnavailable(DataReason.MISSING_VOLUME)
        return bars[-1].volume
    if metric == "close_sma20_gap":
        return 100 * (closes[-1] / ind.sma(closes, 20) - 1)
    if metric == "close_sma50_gap":
        return 100 * (closes[-1] / ind.sma(closes, 50) - 1)
    if metric == "sma50_sma200_gap":
        return 100 * (ind.sma(closes, 50) / ind.sma(closes, 200) - 1)
    family, raw_period = metric.split(".")
    period = int(raw_period)  # Only finite allowlisted metric names reach this branch.
    if family == "sma":
        return ind.sma(closes, period)
    if family == "ema":
        return ind.ema(closes, period)
    if family == "rsi":
        return ind.rsi(closes, period)
    if family == "atr":
        return ind.atr(bars, period)
    if family == "roc":
        return ind.roc(closes, period)
    if family == "momentum":
        return ind.momentum(closes, period)
    if family == "relative_volume":
        return ind.relative_volume(bars, period)
    if family == "average_volume":
        return ind.average_volume(bars, period)
    if family == "rolling_high":
        return ind.rolling_high(bars, period)
    if family == "rolling_low":
        return ind.rolling_low(bars, period)
    if family == "breakout":
        resistance = ind.rolling_high(bars, period)
        ind.require_finite((closes[-1], resistance))
        return float(closes[-1] > resistance)
    if family == "breakdown":
        support = ind.rolling_low(bars, period)
        ind.require_finite((closes[-1], support))
        return float(closes[-1] < support)
    ind.require(closes, period, 1)
    previous = ind.sma(closes[:-1], period)
    current = ind.sma(closes, period)
    cross = ind.cross_above if family == "cross_above_sma" else ind.cross_below
    return float(cross(closes[-2], previous, closes[-1], current))


def compare(value: float, criterion: Criterion) -> bool:
    """1e-9 relative/absolute equality tolerance; strict comparisons exclude that band."""
    target = float(criterion.threshold)
    ind.require_finite((value, target))
    equal = isclose(value, target, rel_tol=1e-9, abs_tol=1e-9)
    match criterion.operator:
        case Comparison.EQ:
            return equal
        case Comparison.GT:
            return value > target and not equal
        case Comparison.GTE:
            return value > target or equal
        case Comparison.LT:
            return value < target and not equal
        case Comparison.LTE:
            return value < target or equal
