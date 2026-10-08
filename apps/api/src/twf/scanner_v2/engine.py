"""Deterministic AND predicates; missing inputs never become a non-match."""

from collections.abc import Callable
from typing import Any

from twf.discovery.internal_scanner import indicators as ind
from twf.discovery.internal_scanner.market_series import Bar, DataUnavailable
from twf.scanner_v2.contracts import FIELDS, Filter


def metrics(bars: tuple[Bar, ...]) -> dict[str, float | str | None]:
    if len(bars) < 2:
        return {}
    close = [b.close for b in bars]
    last, prior = bars[-1], bars[-2]
    out: dict[str, float | str | None] = {
        "price": last.close,
        "volume": last.volume,
        "change": 100 * (last.close / prior.close - 1),
        "gap": 100 * (last.open / prior.close - 1),
        "pivot": (prior.high + prior.low + prior.close) / 3,
    }
    out["resistance"] = 2 * float(out["pivot"] or 0) - prior.low
    out["support"] = 2 * float(out["pivot"] or 0) - prior.high
    calculations: dict[str, Callable[[], float | str]] = {
        "rsi": lambda: ind.rsi(close, 14),
        "sma20": lambda: ind.sma(close, 20),
        "sma50": lambda: ind.sma(close, 50),
        "ema20": lambda: ind.ema(close, 20),
        "macd": lambda: ind.macd(close)[0],
        "macd_signal": lambda: ind.macd(close)[1],
        "adx": lambda: ind.adx(bars),
        "atr": lambda: ind.atr(bars, 14),
        "bb_upper": lambda: ind.bollinger(close)[0],
        "bb_lower": lambda: ind.bollinger(close)[1],
        "roc": lambda: ind.roc(close, 10),
        "rvol": lambda: ind.relative_volume(bars, 20),
        "average_volume": lambda: ind.average_volume(bars, 20),
        "high20": lambda: ind.rolling_high(bars, 20),
        "low20": lambda: ind.rolling_low(bars, 20),
        "high252": lambda: ind.rolling_high(bars, 252),
        "low252": lambda: ind.rolling_low(bars, 252),
        "high252_distance": lambda: 100 * (last.close / ind.rolling_high(bars, 252) - 1),
        "low252_distance": lambda: 100 * (last.close / ind.rolling_low(bars, 252) - 1),
        "trend": lambda: (
            "Up"
            if close[-1] > ind.sma(close, 20)
            else "Down"
            if close[-1] < ind.sma(close, 20)
            else "Sideways"
        ),
        "supertrend": lambda: ind.supertrend(bars),
        "range_ratio": lambda: (last.high - last.low) / ind.atr(bars, 14),
        "sma_distance": lambda: 100 * (last.close / ind.sma(close, 20) - 1),
        "stochastic": lambda: (
            100
            * (last.close - min(b.low for b in bars[-14:]))
            / (max(b.high for b in bars[-14:]) - min(b.low for b in bars[-14:]))
        ),
    }
    for key, fn in calculations.items():
        try:
            out[key] = fn() if key != "stochastic" or len(bars) >= 14 else None
        except (DataUnavailable, ZeroDivisionError):
            out[key] = None
    return out


def evaluate(
    bars: tuple[Bar, ...],
    filters: tuple[Filter, ...],
    extra: dict[str, float | str | None] | None = None,
) -> dict[str, Any]:
    current, previous = metrics(bars), metrics(bars[:-1])
    current.update(extra or {})
    diagnostics = []
    for f in filters:
        lhs = current.get(f.field)
        rhs = current.get(f.value) if isinstance(f.value, str) and f.value in FIELDS else f.value
        passed: bool | None = None
        if lhs is not None and rhs is not None:
            if f.operator in {"equals", "not_equals"}:
                passed = lhs == rhs if f.operator == "equals" else lhs != rhs
            elif isinstance(lhs, (float, int)):
                if f.operator == "between" and isinstance(rhs, tuple):
                    passed = rhs[0] <= lhs <= rhs[1]
                elif isinstance(rhs, (int, float)):
                    if f.operator in {"crosses_above", "crosses_below"}:
                        pl = previous.get(f.field)
                        pr = previous.get(f.value) if isinstance(f.value, str) else f.value
                        if isinstance(pl, (float, int)) and isinstance(pr, (float, int)):
                            passed = (
                                ind.cross_above(pl, pr, lhs, rhs)
                                if f.operator == "crosses_above"
                                else ind.cross_below(pl, pr, lhs, rhs)
                            )
                    else:
                        passed = {
                            ">": lhs > rhs,
                            ">=": lhs >= rhs,
                            "<": lhs < rhs,
                            "<=": lhs <= rhs,
                        }[f.operator]
        diagnostics.append(
            {
                "filter": f.model_dump(mode="json"),
                "observed": lhs,
                "threshold": rhs,
                "passed": passed,
                "reason": f"{FIELDS[f.field][1]} {f.operator} {f.value}",
            }
        )
    outcome = (
        "NOT_EVALUATED"
        if any(d["passed"] is None for d in diagnostics)
        else "MATCH"
        if all(d["passed"] for d in diagnostics)
        else "NON_MATCH"
    )
    return {
        "metrics": current,
        "diagnostics": diagnostics,
        "outcome": outcome,
        "failure": "INSUFFICIENT_OR_UNAVAILABLE_INPUT" if outcome == "NOT_EVALUATED" else None,
    }
