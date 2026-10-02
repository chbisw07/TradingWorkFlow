"""Bounded TradingView exact-symbol and OHLCV evidence over secure MCP permits."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from twf.discovery.domain import InstrumentIdentity
from twf.discovery.tradingview.config import TradingViewSettings
from twf.discovery.tradingview.provider import BATCH_LIMIT, GET_BATCH_TOOL, payload, successful
from twf.integrations.contracts import Contract, Health
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import Code, Context, Failure, State, ToolPolicy

GET_OHLCV_TOOL = "mcp-tv-get-ohlcv"
EVIDENCE_TOOLS = frozenset({GET_BATCH_TOOL, GET_OHLCV_TOOL})
MINIMUM_COLUMNS = ("close", "volume")


class EvidenceOutcome(StrEnum):
    AVAILABLE = "AVAILABLE"
    EXACT_MISSING = "EXACT_MISSING"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID_RESPONSE = "INVALID_RESPONSE"


class ExactQuote(Contract):
    symbol: str
    close: Decimal = Field(gt=0, allow_inf_nan=False)
    volume: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    received_at: AwareDatetime
    chunk_index: int = Field(ge=0)


class ProviderBar(Contract):
    source_time: AwareDatetime
    open: Decimal = Field(gt=0, allow_inf_nan=False)
    high: Decimal = Field(gt=0, allow_inf_nan=False)
    low: Decimal = Field(gt=0, allow_inf_nan=False)
    close: Decimal = Field(gt=0, allow_inf_nan=False)
    volume: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def coherent(self) -> ProviderBar:
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("Invalid OHLC relationship")
        return self


class SymbolEvidence(Contract):
    instrument: InstrumentIdentity
    outcome: EvidenceOutcome
    quote: ExactQuote | None = None
    bars: tuple[ProviderBar, ...] = Field(default=(), max_length=1024)
    interval: str
    received_at: AwareDatetime
    limitation: str | None = None


class EnrichmentBatch(Contract):
    connection_id: UUID | None
    generation: int | None
    requested_symbols: tuple[str, ...]
    returned_symbols: tuple[str, ...]
    missing_symbols: tuple[str, ...]
    chunk_count: int = Field(ge=0)
    symbols: tuple[SymbolEvidence, ...]
    received_at: AwareDatetime


def interval_for(horizon: str) -> tuple[str, str, int]:
    """Return provider interval, normalized interval, and bounded history count."""
    return {
        "intraday": ("15m", "15m", 260),
        "1d": ("1h", "1h", 260),
        "5d": ("1D", "1d", 260),
        "15d": ("1D", "1d", 320),
    }[horizon]


def _time(value: object) -> datetime:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        seconds = float(value) / 1000 if value > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds, UTC)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Provider timestamp must include a timezone")
        return parsed.astimezone(UTC)
    raise ValueError("Invalid provider timestamp")


def _decimal(value: object, *, positive: bool = False) -> Decimal:
    if type(value) not in {int, float, str}:
        raise ValueError("Invalid numeric provider value")
    result = Decimal(str(value))
    if not result.is_finite() or (positive and result <= 0) or abs(result) > Decimal("1e18"):
        raise ValueError("Invalid numeric provider value")
    return result


def quote_rows(
    result: dict[str, JsonValue], requested: tuple[str, ...], chunk_index: int, received: datetime
) -> tuple[dict[str, ExactQuote], tuple[str, ...]]:
    """Accept documented row arrays and the observed symbol-keyed exact-batch shape."""
    data: object = result.get("data", result)
    explicit_missing = result.get("missing", [])
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        rows: object = data["rows"]
        explicit_missing = data.get("missing", explicit_missing)
    elif isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = [
            {"symbol": key, **cast(dict[str, Any], value)}
            for key, value in data.items()
            if key in requested and isinstance(value, dict)
        ]
    else:
        raise ValueError("Invalid exact-batch envelope")
    if not isinstance(rows, list) or not isinstance(explicit_missing, list):
        raise ValueError("Invalid exact-batch rows")
    requested_set = set(requested)
    output: dict[str, ExactQuote] = {}
    for raw in rows:
        if not isinstance(raw, dict) or not isinstance(raw.get("symbol"), str):
            raise ValueError("Invalid exact-batch row")
        symbol = cast(str, raw["symbol"])
        if symbol not in requested_set or symbol in output:
            raise ValueError("Unexpected or duplicate exact-batch identity")
        output[symbol] = ExactQuote(
            symbol=symbol,
            close=_decimal(raw.get("close"), positive=True),
            volume=None if raw.get("volume") is None else _decimal(raw["volume"]),
            received_at=received,
            chunk_index=chunk_index,
        )
    declared = {item for item in explicit_missing if isinstance(item, str)}
    if len(declared) != len(explicit_missing) or not declared.issubset(requested_set):
        raise ValueError("Invalid exact-batch missing identities")
    missing = tuple(symbol for symbol in requested if symbol not in output)
    if not declared.issubset(set(missing)):
        raise ValueError("Identity returned and missing")
    return output, missing


def provider_bars(result: dict[str, JsonValue]) -> tuple[ProviderBar, ...]:
    raw: object = result.get("bars")
    if raw is None and isinstance(result.get("data"), dict):
        raw = cast(dict[str, JsonValue], result["data"]).get("bars")
    if not isinstance(raw, list) or not raw or len(raw) > 1024:
        raise ValueError("Invalid OHLCV bars")
    bars = tuple(
        ProviderBar(
            source_time=_time(item.get("t")),
            open=_decimal(item.get("o"), positive=True),
            high=_decimal(item.get("h"), positive=True),
            low=_decimal(item.get("l"), positive=True),
            close=_decimal(item.get("c"), positive=True),
            volume=None if item.get("v") is None else _decimal(item.get("v")),
        )
        for item in raw
        if isinstance(item, dict)
    )
    if len(bars) != len(raw) or any(
        left.source_time >= right.source_time for left, right in zip(bars, bars[1:], strict=False)
    ):
        raise ValueError("Invalid OHLCV ordering")
    return bars


def failure_outcome(error: Failure) -> EvidenceOutcome:
    return {
        Code.AUTH_REQUIRED: EvidenceOutcome.AUTH_REQUIRED,
        Code.REAUTH_REQUIRED: EvidenceOutcome.AUTH_REQUIRED,
        Code.RATE_LIMITED: EvidenceOutcome.RATE_LIMITED,
        Code.TIMEOUT: EvidenceOutcome.TIMEOUT,
        Code.SCHEMA_MISMATCH: EvidenceOutcome.INVALID_RESPONSE,
    }.get(error.code, EvidenceOutcome.UNAVAILABLE)


class TradingViewEvidenceGateway:
    def __init__(
        self, manager: ConnectionManager, settings: TradingViewSettings, who: Context
    ) -> None:
        self.manager, self.settings, self.who = manager, settings, who

    def connection(self) -> tuple[UUID, int]:
        if not self.settings.enabled or not self.settings.response_contract_verified:
            raise Failure(Code.NOT_CONFIGURED)
        eligible = [
            item
            for item in self.manager.connections(self.who, "tradingview")
            if item.enabled and item.state == State.CONNECTED and item.health == Health.AVAILABLE
        ]
        if not eligible:
            raise Failure(Code.AUTH_REQUIRED)
        return eligible[0].id, eligible[0].generation

    def readiness(self) -> tuple[bool, str, datetime | None]:
        try:
            identity, _ = self.connection()
            view = self.manager.status(self.who, identity)
            return True, "AVAILABLE", view.last_success_at
        except Failure as error:
            health = (
                "AUTH_REQUIRED"
                if error.code in {Code.AUTH_REQUIRED, Code.REAUTH_REQUIRED}
                else "DEGRADED"
            )
            return False, health, None

    async def enrich(
        self, instruments: tuple[InstrumentIdentity, ...], horizon: str
    ) -> EnrichmentBatch:
        received = datetime.now(UTC)
        requested = tuple(f"{item.exchange}:{item.symbol}" for item in instruments)
        provider_interval, normalized_interval, count = interval_for(horizon)
        if not instruments:
            return EnrichmentBatch(
                connection_id=None,
                generation=None,
                requested_symbols=(),
                returned_symbols=(),
                missing_symbols=(),
                chunk_count=0,
                symbols=(),
                received_at=received,
            )
        try:
            identity, generation = self.connection()
        except Failure as error:
            outcome = failure_outcome(error)
            return EnrichmentBatch(
                connection_id=None,
                generation=None,
                requested_symbols=requested,
                returned_symbols=(),
                missing_symbols=requested,
                chunk_count=0,
                symbols=tuple(
                    SymbolEvidence(
                        instrument=item,
                        outcome=outcome,
                        interval=normalized_interval,
                        received_at=received,
                        limitation=outcome.value.lower(),
                    )
                    for item in instruments
                ),
                received_at=received,
            )
        quotes: dict[str, ExactQuote] = {}
        failed: dict[str, EvidenceOutcome] = {}
        chunks = tuple(
            requested[start : start + BATCH_LIMIT]
            for start in range(0, len(requested), BATCH_LIMIT)
        )
        for index, chunk in enumerate(chunks):
            try:
                _, reply = await self.manager.tools(
                    self.who,
                    identity,
                    generation,
                    policy=ToolPolicy(allowed=EVIDENCE_TOOLS),
                    name=GET_BATCH_TOOL,
                    arguments={"symbols": list(chunk), "columns": list(MINIMUM_COLUMNS)},
                )
                rows, _ = quote_rows(successful(payload(reply)), chunk, index, datetime.now(UTC))
                quotes.update(rows)
            except Failure as error:
                outcome = failure_outcome(error)
                failed.update(dict.fromkeys(chunk, outcome))
                if outcome in {EvidenceOutcome.AUTH_REQUIRED, EvidenceOutcome.RATE_LIMITED}:
                    for later in chunks[index + 1 :]:
                        failed.update(dict.fromkeys(later, outcome))
                    break
            except (ValueError, TypeError):
                failed.update(dict.fromkeys(chunk, EvidenceOutcome.INVALID_RESPONSE))

        output: list[SymbolEvidence] = []
        by_symbol = dict(zip(requested, instruments, strict=True))
        for symbol in requested:
            quote = quotes.get(symbol)
            if quote is None:
                outcome = failed.get(symbol, EvidenceOutcome.EXACT_MISSING)
                output.append(
                    SymbolEvidence(
                        instrument=by_symbol[symbol],
                        outcome=outcome,
                        interval=normalized_interval,
                        received_at=datetime.now(UTC),
                        limitation=outcome.value.lower(),
                    )
                )
                continue
            try:
                _, reply = await self.manager.tools(
                    self.who,
                    identity,
                    generation,
                    policy=ToolPolicy(allowed=EVIDENCE_TOOLS),
                    name=GET_OHLCV_TOOL,
                    arguments={
                        "symbol": symbol,
                        "interval": provider_interval,
                        "count": count,
                        "summary": False,
                    },
                )
                bars = provider_bars(successful(payload(reply)))
                output.append(
                    SymbolEvidence(
                        instrument=by_symbol[symbol],
                        outcome=EvidenceOutcome.AVAILABLE,
                        quote=quote,
                        bars=bars,
                        interval=normalized_interval,
                        received_at=datetime.now(UTC),
                        limitation="bar-finality-provider-unspecified;retention-rights-unknown",
                    )
                )
            except Failure as error:
                outcome = failure_outcome(error)
                output.append(
                    SymbolEvidence(
                        instrument=by_symbol[symbol],
                        outcome=outcome,
                        quote=quote,
                        interval=normalized_interval,
                        received_at=datetime.now(UTC),
                        limitation=outcome.value.lower(),
                    )
                )
            except (ValueError, TypeError):
                output.append(
                    SymbolEvidence(
                        instrument=by_symbol[symbol],
                        outcome=EvidenceOutcome.INVALID_RESPONSE,
                        quote=quote,
                        interval=normalized_interval,
                        received_at=datetime.now(UTC),
                        limitation="invalid-response",
                    )
                )
        returned = tuple(item for item in requested if item in quotes)
        return EnrichmentBatch(
            connection_id=identity,
            generation=generation,
            requested_symbols=requested,
            returned_symbols=returned,
            missing_symbols=tuple(item for item in requested if item not in quotes),
            chunk_count=len(chunks),
            symbols=tuple(output),
            received_at=datetime.now(UTC),
        )
