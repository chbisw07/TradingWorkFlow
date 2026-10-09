"""One bounded chain builder shared by future product consumers."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from twf.options.chain_contracts import (
    Moneyness,
    OptionChainCapabilities,
    OptionChainProvenance,
    OptionChainRequest,
    OptionChainRow,
    OptionChainSnapshot,
    OptionLegSnapshot,
    OptionMarketSnapshot,
)
from twf.options.contracts import OptionContract, OptionType

IST = ZoneInfo("Asia/Kolkata")


class ChainFailure(Exception):
    def __init__(self, code: str, status: int = 422) -> None:
        self.code, self.status = code, status
        super().__init__(code)


@dataclass(frozen=True)
class ChainMarketBatch:
    spot: Decimal | None
    quotes: dict[str, OptionMarketSnapshot]
    received_at: datetime
    source_time: datetime | None = None
    cached: bool = False
    warnings: tuple[str, ...] = ()


class OptionChainSource(Protocol):
    capabilities: OptionChainCapabilities
    master_received_at: datetime
    quote_ttl_seconds: int

    async def contracts(self) -> tuple[OptionContract, ...]: ...

    async def market(
        self, underlying: str, expiry: date, contracts: tuple[OptionContract, ...]
    ) -> ChainMarketBatch: ...


class OptionChainService:
    def __init__(self, source: OptionChainSource) -> None:
        self.source = source

    async def active(self, now: datetime) -> tuple[OptionContract, ...]:
        today = now.astimezone(IST).date()
        return tuple(
            c
            for c in await self.source.contracts()
            if c.is_active
            and c.expiry >= today
            and (c.last_trading_date is None or c.last_trading_date >= today)
        )

    async def underlyings(self, query: str, limit: int = 50) -> tuple[str, ...]:
        if not 1 <= limit <= 100 or len(query) > 80:
            raise ChainFailure("invalid_request")
        return tuple(
            sorted(
                {
                    c.underlying_symbol
                    for c in await self.active(datetime.now(UTC))
                    if query.strip().upper() in c.underlying_symbol
                }
            )[:limit]
        )

    async def expiries(self, underlying: str) -> tuple[date, ...]:
        contracts = await self.active(datetime.now(UTC))
        result = tuple(sorted({c.expiry for c in contracts if c.underlying_symbol == underlying}))
        if not result:
            raise ChainFailure("no_option_contracts", 404)
        return result

    async def snapshot(
        self, request: OptionChainRequest, *, now: datetime | None = None
    ) -> OptionChainSnapshot:
        now = now or datetime.now(UTC)
        today = now.astimezone(IST).date()
        if request.expiry < today:
            raise ChainFailure("expiry_not_found", 404)
        universe = [c for c in await self.active(now) if c.underlying_symbol == request.underlying]
        if not universe:
            known = any(
                c.underlying_symbol == request.underlying for c in await self.source.contracts()
            )
            raise ChainFailure("no_option_contracts" if known else "underlying_not_found", 404)
        contracts = tuple(c for c in universe if c.expiry == request.expiry)
        if not contracts:
            raise ChainFailure("expiry_not_found", 404)
        identity = {(c.strike, c.option_type) for c in contracts}
        if len(identity) != len(contracts):
            raise ChainFailure("partial_chain", 503)
        warnings: list[str] = []
        try:
            batch = await self.source.market(request.underlying, request.expiry, contracts)
        except ChainFailure as exc:
            batch = ChainMarketBatch(None, {}, datetime.now(UTC))
            warnings.append(exc.code)
        warnings.extend(batch.warnings)
        spot = batch.spot if batch.spot is not None and batch.spot > 0 else None
        strikes = sorted({c.strike for c in contracts})
        atm = min(strikes, key=lambda strike: (abs(strike - spot), strike)) if spot else None
        side_strikes = {
            c.strike for c in contracts if request.side is None or c.option_type == request.side
        }
        eligible = [
            s
            for s in strikes
            if (request.strike_min is None or s >= request.strike_min)
            and (request.strike_max is None or s <= request.strike_max)
            and s in side_strikes
        ]
        if not eligible:
            raise ChainFailure("no_option_contracts", 404)
        size = 2 * request.around_atm + 1
        if atm is not None:
            center = min(range(len(eligible)), key=lambda i: (abs(eligible[i] - atm), eligible[i]))
            selected = eligible[
                max(0, center - request.around_atm) : center + request.around_atm + 1
            ]
        else:
            selected = eligible[:size]
            warnings.append("spot_unavailable")
        by_strike = {(c.strike, c.option_type): c for c in contracts}
        caps = self.source.capabilities
        rows: list[OptionChainRow] = []
        for strike in selected:
            legs: dict[OptionType, OptionLegSnapshot] = {}
            for side in OptionType:
                contract = by_strike.get((strike, side))
                if contract is None or (request.side is not None and side != request.side):
                    continue
                market = batch.quotes.get(contract.canonical_id)
                if market is not None:
                    suppressed: dict[str, None] = {}
                    capability_fields = {
                        "quotes": ("ltp",),
                        "bid_ask": (
                            "bid",
                            "ask",
                            "bid_quantity",
                            "ask_quantity",
                            "spread",
                            "spread_percent",
                        ),
                        "volume": ("volume",),
                        "open_interest": ("open_interest",),
                        "oi_change": ("previous_open_interest", "change_in_open_interest"),
                        "iv": ("implied_volatility",),
                        "greeks": ("delta", "gamma", "theta", "vega"),
                    }
                    for capability, fields in capability_fields.items():
                        if getattr(caps, capability) == "UNSUPPORTED":
                            suppressed.update({field: None for field in fields})
                    market = market.model_copy(update=suppressed)
                available = market is not None and market.ltp is not None
                incomplete = market is not None and any(
                    getattr(market, field) is None
                    for field, capability in (
                        ("bid", "bid_ask"),
                        ("ask", "bid_ask"),
                        ("volume", "volume"),
                        ("open_interest", "open_interest"),
                    )
                    if getattr(caps, capability) != "UNSUPPORTED"
                )
                if not available:
                    warnings.append("quote_unavailable")
                elif incomplete:
                    warnings.append("partial_chain")
                moneyness: Moneyness | None = None
                if spot is not None:
                    moneyness = (
                        "ATM"
                        if strike == atm
                        else ("ITM" if (strike < spot) == (side == OptionType.CE) else "OTM")
                    )
                legs[side] = OptionLegSnapshot(
                    contract=contract,
                    moneyness=moneyness,
                    market=market or OptionMarketSnapshot(),
                    availability="UNAVAILABLE"
                    if not available
                    else "PARTIAL"
                    if incomplete
                    else "AVAILABLE",
                    warnings=("quote_unavailable",)
                    if not available
                    else ("partial_chain",)
                    if incomplete
                    else (),
                )
            rows.append(
                OptionChainRow(
                    strike=strike,
                    is_atm=strike == atm if atm is not None else None,
                    distance_from_spot=strike - spot if spot else None,
                    distance_percent=(strike - spot) / spot * 100 if spot else None,
                    ce=legs.get(OptionType.CE),
                    pe=legs.get(OptionType.PE),
                )
            )
        missing = tuple(
            k for k, v in caps.model_dump().items() if k != "provider" and v == "UNSUPPORTED"
        )
        if missing:
            warnings.append("unsupported_capability")
        return OptionChainSnapshot(
            underlying=request.underlying,
            spot=spot,
            expiry=request.expiry,
            dte=(request.expiry - today).days,
            as_of=batch.received_at,
            atm_strike=atm,
            rows=tuple(rows),
            status="PARTIAL" if warnings else "COMPLETE",
            capabilities=caps,
            warnings=tuple(dict.fromkeys(warnings)),
            missing_capabilities=missing,
            provenance=OptionChainProvenance(
                provider=caps.provider,
                contract_source="instrument-master",
                market_source="option-chain",
                master_received_at=self.source.master_received_at,
                received_at=batch.received_at,
                source_time=batch.source_time,
                freshness=(
                    "UNAVAILABLE"
                    if not batch.quotes
                    else "SOURCE_TIME_UNAVAILABLE"
                    if batch.source_time is None
                    else "STALE"
                    if (now - batch.source_time).total_seconds() > 30
                    else "FRESH"
                ),
                quote_ttl_seconds=self.source.quote_ttl_seconds,
                cached=batch.cached,
            ),
        )
