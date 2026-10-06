"""Optional normalized reference metrics; no market-price or trading authority."""

import asyncio
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from time import monotonic
from typing import Literal
from uuid import UUID

from pydantic import Field, JsonValue

from twf.discovery.domain import InstrumentIdentity
from twf.discovery.market_intelligence import TapTideMarketIntelligence, _payload, _source_time
from twf.integrations.contracts import Contract
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import Context, Failure, ToolPolicy

TOOL = "get_stock_quote"


class ReferenceSnapshot(Contract):
    symbol: str
    provider: str = "tapetide"
    tool: str = TOOL
    state: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE", "NOT_AVAILABLE"] = "UNAVAILABLE"
    market_cap_inr: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    pe_ratio: Decimal | None = Field(default=None, allow_inf_nan=False)
    high_52_week: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    low_52_week: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    received_at: datetime
    source_time: datetime | None = None
    freshness: str = "UNAVAILABLE"


def numeric(value: JsonValue | None, *, positive: bool = True) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = Decimal(str(value))
        return (
            number
            if number.is_finite() and abs(number) < Decimal("1e24") and (not positive or number > 0)
            else None
        )
    except InvalidOperation:
        return None


def normalize_reference(
    symbol: str, payload: dict[str, JsonValue], received: datetime
) -> ReferenceSnapshot:
    result = ReferenceSnapshot(symbol=symbol, received_at=received)
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("found") is not True or data.get("symbol") != symbol:
        return result
    source = _source_time({"source_time": data.get("updated_at")})
    # TapTide company quote/profile market_cap is INR crore, corroborated by
    # its published Market cap (₹ Cr) table and profile price/share metadata.
    # Convert units only: never derive market cap or PE from incomplete inputs.
    cap = numeric(data.get("market_cap"))
    values = {
        "market_cap_inr": cap * 10_000_000 if cap is not None else None,
        "pe_ratio": numeric(data.get("pe_ttm"), positive=False),
        "high_52_week": numeric(data.get("high_52w")),
        "low_52_week": numeric(data.get("low_52w")),
    }
    if (
        values["high_52_week"] is not None
        and values["low_52_week"] is not None
        and values["high_52_week"] < values["low_52_week"]
    ):
        values["high_52_week"] = values["low_52_week"] = None
    return ReferenceSnapshot(
        symbol=symbol,
        received_at=received,
        source_time=source,
        freshness="SOURCE_TIME_UNAVAILABLE"
        if source is None
        else "FUTURE_SOURCE_TIME"
        if source > received + timedelta(minutes=5)
        else "STALE"
        if received - source > timedelta(days=7)
        else "CURRENT",
        state="AVAILABLE"
        if all(v is not None for v in values.values())
        else "PARTIAL"
        if any(v is not None for v in values.values())
        else "NOT_AVAILABLE",
        market_cap_inr=values["market_cap_inr"],
        pe_ratio=values["pe_ratio"],
        high_52_week=values["high_52_week"],
        low_52_week=values["low_52_week"],
    )


class WatchlistReferenceCache:
    def __init__(self) -> None:
        self.values: OrderedDict[tuple[UUID, UUID, int, UUID], tuple[float, ReferenceSnapshot]] = (
            OrderedDict()
        )
        self.lock = asyncio.Lock()

    async def read(
        self, manager: ConnectionManager, who: Context, instrument: InstrumentIdentity
    ) -> ReferenceSnapshot:
        unavailable = ReferenceSnapshot(symbol=instrument.symbol, received_at=datetime.now(UTC))
        # The discovered tool resolves NSE company symbols, not index/derivative contracts.
        if instrument.exchange != "NSE" or instrument.instrument_type != "EQUITY":
            return unavailable.model_copy(update={"state": "NOT_AVAILABLE"})
        try:
            connection, generation, tools = TapTideMarketIntelligence(manager, who).connection()
            if TOOL not in tools:
                return unavailable
            key = who.owner_id, connection, generation, instrument.instrument_id
            async with asyncio.timeout(25):
                async with self.lock:
                    cached = self.values.get(key)
                    if cached and cached[0] > monotonic():
                        self.values.move_to_end(key)
                        return cached[1]
                    try:
                        _, reply = await manager.tools(
                            who,
                            connection,
                            generation,
                            policy=ToolPolicy(allowed=frozenset({TOOL})),
                            name=TOOL,
                            arguments={"symbol": instrument.symbol},
                        )
                        result = normalize_reference(
                            instrument.symbol, _payload(reply), datetime.now(UTC)
                        )
                    except (Failure, ValueError):
                        result = unavailable
                    finally:
                        await manager.operations.wait_receipts()
                    self.values[key] = (
                        monotonic() + (60 if result.state == "UNAVAILABLE" else 900),
                        result,
                    )
                    while len(self.values) > 128:
                        self.values.popitem(last=False)
                    return result
        except (Failure, TimeoutError):
            return unavailable
