"""Bounded provider-neutral Market Intelligence claims with a TapTide MCP adapter."""

from __future__ import annotations

import json
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol, cast
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue

from twf.discovery.domain import InstrumentIdentity
from twf.integrations.contracts import Contract, Health, Identifier
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import Code, Context, Failure, State, ToolPolicy

TAPTIDE_PROVIDER_ID = "tapetide"
TAPTIDE_TOOLS = frozenset(
    {
        "get_market_pulse",
        "get_india_vix",
        "get_fii_dii_detail",
        "get_fpi_sectors",
        "get_index_performance",
        "get_market_news",
        "get_stock_events",
    }
)

_LIMITATION_SUBJECTS = {
    "get_market_pulse": "market-pulse",
    "get_india_vix": "vix",
    "get_fii_dii_detail": "fii-dii",
    "get_fpi_sectors": "sector",
    "get_index_performance": "sector-index",
    "get_market_news": "news",
    "get_stock_events": "corporate-event",
}
_LIMITATION_FAILURES = {
    **{code.value.lower(): code.value.lower().replace("_", "-") for code in Code},
    "provider-error": "provider-error",
    "invalid-response": "invalid-response",
    "bounded-intelligence-tools-not-discovered": "tools-not-discovered",
}


def tapetide_limitation_codes(failures: tuple[str, ...]) -> tuple[str, ...]:
    """Classify provider failures without leaking raw strings into domain identifiers."""
    normalized: list[str] = []
    for failure in failures:
        tool, separator, raw_code = failure.partition(":")
        subject = _LIMITATION_SUBJECTS.get(tool, "provider") if separator else "provider"
        code = _LIMITATION_FAILURES.get(raw_code if separator else failure, "provider-error")
        limitation = f"tapetide-{subject}-{code}"
        if limitation not in normalized:
            normalized.append(limitation)
    return tuple(normalized[:16])


class IntelligenceKind(StrEnum):
    MARKET_PULSE = "MARKET_PULSE"
    MARKET_VOLATILITY = "MARKET_VOLATILITY"
    MARKET_FLOW = "MARKET_FLOW"
    SECTOR_FLOW = "SECTOR_FLOW"
    INDEX_STRENGTH = "INDEX_STRENGTH"
    NEWS_SENTIMENT = "NEWS_SENTIMENT"
    CORPORATE_EVENT = "CORPORATE_EVENT"


class IntelligenceState(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    PROVIDER_ERROR = "PROVIDER_ERROR"


class IntelligenceClaim(Contract):
    kind: IntelligenceKind
    subject: str = Field(min_length=1, max_length=96)
    scope: str = Field(min_length=1, max_length=96)
    values: dict[str, JsonValue] = Field(max_length=24)
    provider: Identifier
    provider_tool: Identifier
    source_time: AwareDatetime | None = None
    received_at: AwareDatetime
    freshness: str = Field(min_length=1, max_length=64)
    source_reference: str = Field(min_length=1, max_length=240)


class MarketIntelligenceBatch(Contract):
    provider: Identifier
    state: IntelligenceState
    claims: tuple[IntelligenceClaim, ...] = Field(max_length=32)
    received_at: AwareDatetime
    failures: tuple[str, ...] = Field(default=(), max_length=16)


class MarketIntelligenceProvider(Protocol):
    def readiness(self) -> tuple[bool, IntelligenceState, datetime | None]: ...

    async def observe(
        self, instruments: tuple[InstrumentIdentity, ...]
    ) -> MarketIntelligenceBatch: ...


class TapTideSnapshotCache:
    """Bounded per-process cache; keys retain owner and credential generation fences."""

    def __init__(self, *, ttl_seconds: int = 300, max_entries: int = 128) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self.max_entries = max_entries
        self._items: OrderedDict[
            tuple[UUID, UUID, int, str], tuple[datetime, MarketIntelligenceBatch]
        ] = OrderedDict()

    def get(self, key: tuple[UUID, UUID, int, str], at: datetime) -> MarketIntelligenceBatch | None:
        item = self._items.get(key)
        if item is None:
            return None
        stored_at, batch = item
        if at - stored_at > self.ttl:
            del self._items[key]
            return None
        self._items.move_to_end(key)
        return batch.model_copy(deep=True)

    def put(
        self, key: tuple[UUID, UUID, int, str], at: datetime, batch: MarketIntelligenceBatch
    ) -> None:
        self._items[key] = (at, batch.model_copy(deep=True))
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)


def _payload(reply: dict[str, JsonValue] | None) -> dict[str, JsonValue]:
    if reply is None or reply.get("isError"):
        raise ValueError("missing tool result")
    value: object = reply.get("structuredContent")
    if value is None:
        content = reply.get("content")
        if not isinstance(content, list) or len(content) != 1:
            raise ValueError("ambiguous result")
        item = content[0]
        if (
            not isinstance(item, dict)
            or item.get("type") != "text"
            or not isinstance(item.get("text"), str)
        ):
            raise ValueError("invalid result")
        value = json.loads(cast(str, item["text"]))
    if not isinstance(value, dict):
        raise ValueError("invalid result")
    return cast(dict[str, JsonValue], value)


def _key(value: str) -> str:
    return "_".join(
        filter(None, ("".join(char.lower() if char.isalnum() else " " for char in value)).split())
    )


def _first_scalar(value: object, aliases: frozenset[str]) -> JsonValue | None:
    queue: list[object] = [value]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for name, item in current.items():
                if isinstance(name, str) and _key(name) in aliases:
                    if isinstance(item, (str, int, float, bool)) and not (
                        isinstance(item, str) and (not item or len(item) > 160)
                    ):
                        return cast(JsonValue, item)
                if isinstance(item, (dict, list)):
                    queue.append(item)
        elif isinstance(current, list):
            queue.extend(current[:20])
    return None


def _record_count(value: object) -> int:
    queue: list[object] = [value]
    counts: list[int] = []
    while queue:
        current = queue.pop(0)
        if isinstance(current, list):
            counts.append(len(current))
            queue.extend(current[:20])
        elif isinstance(current, dict):
            queue.extend(item for item in current.values() if isinstance(item, (dict, list)))
    return max(counts, default=1 if isinstance(value, dict) and value else 0)


def _normalized_values(tool: str, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Map provider payloads onto a small stable vocabulary; unknown keys never escape."""

    schemas: dict[str, tuple[tuple[str, frozenset[str]], ...]] = {
        "get_market_pulse": (
            ("fii_net_flow", frozenset({"fii_net", "fii_net_flow", "fii_net_value"})),
            ("dii_net_flow", frozenset({"dii_net", "dii_net_flow", "dii_net_value"})),
            ("india_vix", frozenset({"india_vix", "vix", "vix_level"})),
            ("nifty_50_pe", frozenset({"nifty_50_pe", "nifty_pe"})),
        ),
        "get_india_vix": (
            ("level", frozenset({"level", "latest", "current", "value", "vix", "india_vix"})),
            ("change_percent", frozenset({"change_percent", "change_pct", "percent_change"})),
        ),
        "get_fii_dii_detail": (
            ("fii_net_flow", frozenset({"fii_net", "fii_net_flow", "fii_net_value"})),
            ("dii_net_flow", frozenset({"dii_net", "dii_net_flow", "dii_net_value"})),
        ),
        "get_fpi_sectors": (
            ("leading_sector", frozenset({"sector", "sector_name", "name"})),
            ("net_flow", frozenset({"net_flow", "net_value", "change"})),
        ),
        "get_index_performance": (
            ("leading_index", frozenset({"index", "index_name", "name"})),
            ("return_percent", frozenset({"return_percent", "return_pct", "percent_return"})),
        ),
        "get_market_news": (
            ("latest_headline", frozenset({"headline", "title"})),
            ("sentiment", frozenset({"sentiment", "sentiment_label"})),
        ),
        "get_stock_events": (
            ("symbol", frozenset({"symbol", "ticker"})),
            ("event_type", frozenset({"event_type", "type", "category"})),
            ("event_date", frozenset({"event_date", "date"})),
        ),
    }
    output: dict[str, JsonValue] = {"record_count": _record_count(value)}
    for canonical, aliases in schemas[tool]:
        found = _first_scalar(value, aliases)
        if found is not None:
            output[canonical] = found
    return output


def _source_time(value: dict[str, JsonValue]) -> datetime | None:
    queue: list[object] = [value]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for key, item in current.items():
                if key.casefold() in {
                    "source_time",
                    "source_timestamp",
                    "observed_at",
                    "as_of",
                    "date",
                    "timestamp",
                }:
                    if isinstance(item, str):
                        try:
                            parsed = datetime.fromisoformat(item.replace("Z", "+00:00"))
                            if parsed.tzinfo is not None:
                                return parsed.astimezone(UTC)
                        except ValueError:
                            pass
                    if isinstance(item, (int, float)) and not isinstance(item, bool):
                        try:
                            seconds = item / 1000 if item > 10_000_000_000 else item
                            return datetime.fromtimestamp(seconds, UTC)
                        except (ValueError, OSError, OverflowError):
                            pass
                if isinstance(item, (dict, list)):
                    queue.append(item)
        elif isinstance(current, list):
            queue.extend(item for item in current[:8] if isinstance(item, (dict, list)))
    return None


def _failure_state(error: Failure) -> IntelligenceState:
    if error.code in {Code.AUTH_REQUIRED, Code.REAUTH_REQUIRED, Code.CLOSED}:
        return IntelligenceState.AUTH_REQUIRED
    if error.code == Code.RATE_LIMITED:
        return IntelligenceState.RATE_LIMITED
    if error.code in {Code.UNAVAILABLE, Code.TIMEOUT}:
        return IntelligenceState.UNAVAILABLE
    return IntelligenceState.PROVIDER_ERROR


class TapTideMarketIntelligence:
    """Optional MCP enrichment. Every call is allowlisted, bounded, and degradable."""

    tool_kinds = {
        "get_market_pulse": IntelligenceKind.MARKET_PULSE,
        "get_india_vix": IntelligenceKind.MARKET_VOLATILITY,
        "get_fii_dii_detail": IntelligenceKind.MARKET_FLOW,
        "get_fpi_sectors": IntelligenceKind.SECTOR_FLOW,
        "get_index_performance": IntelligenceKind.INDEX_STRENGTH,
        "get_market_news": IntelligenceKind.NEWS_SENTIMENT,
        "get_stock_events": IntelligenceKind.CORPORATE_EVENT,
    }

    def __init__(
        self,
        manager: ConnectionManager,
        who: Context,
        cache: TapTideSnapshotCache | None = None,
    ) -> None:
        self.manager = manager
        self.who = who
        self.cache = cache

    def connection(self) -> tuple[UUID, int, frozenset[str]]:
        eligible = [
            item
            for item in self.manager.connections(self.who, TAPTIDE_PROVIDER_ID)
            if item.enabled and item.state == State.CONNECTED and item.health == Health.AVAILABLE
        ]
        if not eligible:
            raise Failure(Code.AUTH_REQUIRED)
        row = eligible[0]
        return row.id, row.generation, frozenset(tool.name for tool in row.tools)

    def readiness(self) -> tuple[bool, IntelligenceState, datetime | None]:
        try:
            identity, _, discovered = self.connection()
            if not TAPTIDE_TOOLS.issubset(discovered):
                return False, IntelligenceState.PARTIAL, None
            view = self.manager.status(self.who, identity)
            return True, IntelligenceState.AVAILABLE, view.last_success_at
        except Failure as error:
            return False, _failure_state(error), None
        except Exception:
            return False, IntelligenceState.PROVIDER_ERROR, None

    @staticmethod
    def arguments(tool: str, instruments: tuple[InstrumentIdentity, ...]) -> dict[str, JsonValue]:
        if tool == "get_index_performance":
            return {
                "category": "sectoral",
                "granularity": "month",
                "periods": 1,
                "limit": 10,
            }
        if tool == "get_market_news":
            return {"limit": 10}
        if tool == "get_stock_events":
            return {
                "symbol": instruments[0].symbol if instruments else "NIFTY",
                "type": "corporate_actions",
                "limit": 5,
            }
        return {}

    async def observe(self, instruments: tuple[InstrumentIdentity, ...]) -> MarketIntelligenceBatch:
        received = datetime.now(UTC)
        try:
            connection_id, generation, discovered = self.connection()
        except Failure as error:
            return MarketIntelligenceBatch(
                provider=TAPTIDE_PROVIDER_ID,
                state=_failure_state(error),
                claims=(),
                received_at=received,
                failures=(error.code.value.lower(),),
            )
        except Exception:
            return MarketIntelligenceBatch(
                provider=TAPTIDE_PROVIDER_ID,
                state=IntelligenceState.PROVIDER_ERROR,
                claims=(),
                received_at=received,
                failures=("provider-error",),
            )
        selected = tuple(tool for tool in self.tool_kinds if tool in discovered)
        if not selected:
            return MarketIntelligenceBatch(
                provider=TAPTIDE_PROVIDER_ID,
                state=IntelligenceState.PARTIAL,
                claims=(),
                received_at=received,
                failures=("bounded-intelligence-tools-not-discovered",),
            )
        cache_key = (
            self.who.owner_id,
            connection_id,
            generation,
            f"{instruments[0].symbol if instruments else 'MARKET'}:{','.join(selected)}",
        )
        if self.cache is not None:
            cached = self.cache.get(cache_key, received)
            if cached is not None:
                return cached
        claims: list[IntelligenceClaim] = []
        failures: list[str] = []
        strongest_failure: IntelligenceState | None = None
        for tool in selected[:7]:
            try:
                _, reply = await self.manager.tools(
                    self.who,
                    connection_id,
                    generation,
                    policy=ToolPolicy(allowed=TAPTIDE_TOOLS),
                    name=tool,
                    arguments=self.arguments(tool, instruments),
                )
                value = _payload(reply)
                now = datetime.now(UTC)
                source_time = _source_time(value)
                claims.append(
                    IntelligenceClaim(
                        kind=self.tool_kinds[tool],
                        subject=(
                            instruments[0].symbol
                            if tool == "get_stock_events" and instruments
                            else "INDIA_MARKET"
                        ),
                        scope="INSTRUMENT" if tool == "get_stock_events" else "MARKET",
                        values=_normalized_values(tool, value),
                        provider=TAPTIDE_PROVIDER_ID,
                        provider_tool=tool,
                        source_time=source_time,
                        received_at=now,
                        freshness=(
                            "SOURCE_TIME_UNAVAILABLE"
                            if source_time is None
                            else (
                                "STALE"
                                if now - source_time > timedelta(days=7)
                                else (
                                    "FUTURE_SOURCE_TIME"
                                    if source_time - now > timedelta(minutes=5)
                                    else "CURRENT"
                                )
                            )
                        ),
                        source_reference=f"tapetide-mcp:{tool}",
                    )
                )
            except Failure as error:
                state = _failure_state(error)
                strongest_failure = state
                failures.append(f"{tool}:{error.code.value.lower()}")
                if state in {IntelligenceState.AUTH_REQUIRED, IntelligenceState.RATE_LIMITED}:
                    break
            except (TypeError, ValueError, json.JSONDecodeError):
                strongest_failure = IntelligenceState.PROVIDER_ERROR
                failures.append(f"{tool}:invalid-response")
            except Exception:
                strongest_failure = IntelligenceState.PROVIDER_ERROR
                failures.append(f"{tool}:provider-error")
        stale_claims = tuple(claim for claim in claims if claim.freshness == "STALE")
        state = (
            IntelligenceState.STALE
            if claims and len(stale_claims) == len(claims) and not failures
            else (
                IntelligenceState.AVAILABLE
                if claims and not failures and not stale_claims
                else (
                    IntelligenceState.PARTIAL
                    if claims
                    else (strongest_failure or IntelligenceState.UNAVAILABLE)
                )
            )
        )
        batch = MarketIntelligenceBatch(
            provider=TAPTIDE_PROVIDER_ID,
            state=state,
            claims=tuple(claims),
            received_at=datetime.now(UTC),
            failures=tuple(failures[:16]),
        )
        if self.cache is not None and state in {
            IntelligenceState.AVAILABLE,
            IntelligenceState.STALE,
        }:
            self.cache.put(cache_key, received, batch)
        return batch
