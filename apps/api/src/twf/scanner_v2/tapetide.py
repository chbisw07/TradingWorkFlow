"""Separate bounded ScanProvider adapter using empirically inspected MCP schemas."""

from datetime import UTC, datetime
from math import isfinite
from typing import Any

from pydantic import JsonValue

from twf.discovery.market_intelligence import TapTideMarketIntelligence, _payload
from twf.integrations.mcp.contracts import Failure, ToolPolicy
from twf.scanner_v2.contracts import ScanConfig
from twf.watchlists.service import WatchlistFailure

FIELD_MAP = {
    "price": "close",
    "change": "change",
    "volume": "volume",
    "rsi": "RSI",
    "sma20": "SMA20",
    "sma50": "SMA50",
    "ema20": "EMA20",
    "macd": "MACD.macd",
    "adx": "ADX",
    "atr": "ATR",
    "bb_upper": "BB.upper",
    "bb_lower": "BB.lower",
}
OPS = {
    ">": "greater",
    "<": "less",
    "equals": "equal",
    "between": "in_range",
    "crosses_above": "crosses_above",
    "crosses_below": "crosses_below",
}


def number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value):
        return float(value)
    return None


def normalize(payload: dict[str, JsonValue], tool: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    groups: Any = (
        payload.get("buckets", {})
        if tool == "get_trending_stocks"
        else {"technical": payload.get("results", [])}
    )
    if not isinstance(groups, dict):
        return rows
    for bucket, items in groups.items():
        if bucket not in {"technical", "bullish", "bearish", "near_52w_high", "near_52w_low"}:
            continue
        if not isinstance(items, list):
            continue
        for item in items[:20]:
            if not isinstance(item, dict) or not isinstance(item.get("symbol"), str):
                continue
            symbol = item["symbol"]
            if len(symbol) > 50 or item.get("exchange", "NSE") != "NSE":
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "provider": "tapetide",
                    "tool": tool,
                    "bucket": bucket,
                    "metrics": {
                        "price": number(item.get("close", item.get("ltp"))),
                        "change": number(
                            item.get(
                                "change" if tool == "screen_stocks_technical" else "change_pct"
                            )
                        ),
                        "volume": number(item.get("volume")),
                        "rsi": number(item.get("RSI")),
                    },
                    "reason": str(item.get("signal", "Explicit technical predicates"))[:100],
                }
            )
    # Same symbol may belong to several mover buckets. Preserve reasons without duplicate rows.
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["symbol"] in unique:
            unique[row["symbol"]]["reasons"].append(row["reason"])
            unique[row["symbol"]]["buckets"].append(row["bucket"])
        else:
            unique[row["symbol"]] = {**row, "reasons": [row["reason"]], "buckets": [row["bucket"]]}
    return list(unique.values())[:80]


class TapTideScanner:
    def __init__(self, intelligence: TapTideMarketIntelligence) -> None:
        self.intelligence = intelligence

    async def read(self, config: ScanConfig | None = None) -> dict[str, Any]:
        tool = "screen_stocks_technical" if config else "get_trending_stocks"
        args: dict[str, JsonValue] = {}
        if config:
            expressions: list[JsonValue] = []
            for f in config.filters:
                if f.field not in FIELD_MAP or f.operator not in OPS:
                    raise WatchlistFailure("TAPTIDE_FILTER_NOT_SUPPORTED", 422)
                rhs: JsonValue = list(f.value) if isinstance(f.value, tuple) else f.value
                if isinstance(rhs, str):
                    if rhs not in FIELD_MAP:
                        raise WatchlistFailure("TAPTIDE_FILTER_NOT_SUPPORTED", 422)
                    rhs = FIELD_MAP[rhs]
                expressions.append(
                    {"left": FIELD_MAP[f.field], "operation": OPS[f.operator], "right": rhs}
                )
            args = {
                "filters": expressions,
                "columns": ["name", "close", "change", "volume", "RSI"],
                "limit": 20,
            }
        try:
            identity, generation, tools = self.intelligence.connection()
            if tool not in tools:
                raise WatchlistFailure("TAPTIDE_TOOL_UNAVAILABLE", 503)
            _, reply = await self.intelligence.manager.tools(
                self.intelligence.who,
                identity,
                generation,
                policy=ToolPolicy(allowed=frozenset({tool})),
                name=tool,
                arguments=args,
            )
            payload = _payload(reply)
            expected = payload.get("buckets" if tool == "get_trending_stocks" else "results")
            if not isinstance(expected, dict if tool == "get_trending_stocks" else list):
                raise ValueError("Invalid provider envelope")
            rows = normalize(payload, tool)
            return {
                "state": "AVAILABLE",
                "provider": "tapetide",
                "tool": tool,
                "rows": rows,
                "received_at": datetime.now(UTC).isoformat(),
                "source_time": None,
                "freshness": "SOURCE_TIME_UNAVAILABLE",
                "generation": generation,
                "coverage": (
                    "Bounded provider-wide sample; not your selected universe; "
                    "not an exhaustive ranking"
                ),
                "filters": [f.model_dump(mode="json") for f in config.filters] if config else [],
            }
        except (Failure, WatchlistFailure, ValueError) as exc:
            return {
                "state": "UNAVAILABLE",
                "provider": "tapetide",
                "tool": tool,
                "rows": [],
                "failure": str(exc.code)
                if isinstance(exc, (Failure, WatchlistFailure))
                else "INVALID_PROVIDER_RESPONSE",
            }
