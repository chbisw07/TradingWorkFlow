"""Templates are editable filter configurations, never opaque profiles."""

from typing import Any

from twf.scanner_v2.contracts import Filter

DEFINITIONS = (
    ("Bullish Breakout", (("price", ">", "high20"), ("rvol", ">=", 1.5))),
    ("Bearish Breakdown", (("price", "<", "low20"), ("rvol", ">=", 1.5))),
    ("Relative Volume", (("rvol", ">=", 1.5),)),
    ("Momentum", (("roc", ">", 2),)),
    ("Trend Continuation", (("price", ">", "sma20"), ("sma20", ">", "sma50"), ("adx", ">", 25))),
    ("Pullback in Uptrend", (("sma20", ">", "sma50"), ("sma_distance", "between", (-2, 1)))),
    ("RSI Oversold", (("rsi", "<", 30),)),
    ("RSI Overbought", (("rsi", ">", 70),)),
    ("Supertrend Bullish", (("supertrend", "equals", "Up"),)),
    ("Supertrend Bearish", (("supertrend", "equals", "Down"),)),
    ("High Volume", (("volume", ">", 10000000),)),
    ("Top Gainers", (("change", ">", 0),)),
    ("Top Losers", (("change", "<", 0),)),
    ("Near 52W High", (("high252_distance", "between", (-3, 0)),)),
    ("Near 52W Low", (("low252_distance", "between", (0, 3)),)),
    ("Trend Down", (("trend", "equals", "Down"),)),
)


def templates() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "filters": [
                Filter.model_validate({"field": f, "operator": o, "value": v}).model_dump(
                    mode="json"
                )
                for f, o, v in definitions
            ],
        }
        for name, definitions in DEFINITIONS
    ]
