"""Dhan option-chain boundary; only verified listed identities enter the domain."""

import asyncio
import csv
import io
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from twf.discovery.market_data import DhanMarketDataProvider, MarketDataFailure
from twf.options.chain_contracts import OptionChainCapabilities, OptionMarketSnapshot
from twf.options.chain_service import ChainFailure, ChainMarketBatch
from twf.options.contracts import OptionContract, OptionType, UnderlyingType, option_contract_id

MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
CAPABILITIES = OptionChainCapabilities(
    provider="dhan",
    contracts="SUPPORTED",
    quotes="SUPPORTED",
    bid_ask="SUPPORTED",
    volume="SUPPORTED",
    open_interest="SUPPORTED",
    oi_change="SUPPORTED",
    iv="PARTIAL",
    greeks="PARTIAL",
)


def number(value: object, *, signed: bool = False) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        result = Decimal(str(value))
        if not result.is_finite() or abs(result) > Decimal("1e20") or (not signed and result < 0):
            return None
        return result
    except InvalidOperation:
        return None


def normalize_market(raw: dict[str, Any]) -> OptionMarketSnapshot:
    bid, ask = number(raw.get("top_bid_price")), number(raw.get("top_ask_price"))
    spread = ask - bid if bid is not None and ask is not None and 0 < bid <= ask else None
    oi, previous = number(raw.get("oi")), number(raw.get("previous_oi"))
    change = number(raw.get("oi_change"), signed=True)
    if change is None and oi is not None and previous is not None:
        change = oi - previous
    greeks = raw.get("greeks")
    greeks = greeks if isinstance(greeks, dict) else {}
    iv = number(raw.get("implied_volatility"))
    # Provider zero IV is an unavailable calculation, not a verified 0% volatility.
    iv = iv if iv is not None and iv > 0 else None
    return OptionMarketSnapshot(
        ltp=number(raw.get("last_price")),
        bid=bid,
        ask=ask,
        bid_quantity=number(raw.get("top_bid_quantity")),
        ask_quantity=number(raw.get("top_ask_quantity")),
        spread=spread,
        spread_percent=spread / ((bid + ask) / 2) * 100
        if spread is not None and bid is not None and ask is not None
        else None,
        volume=number(raw.get("volume")),
        open_interest=oi,
        previous_open_interest=previous,
        change_in_open_interest=change,
        implied_volatility=iv,
        delta=number(greeks.get("delta"), signed=True) if iv else None,
        gamma=number(greeks.get("gamma")) if iv else None,
        theta=number(greeks.get("theta"), signed=True) if iv else None,
        vega=number(greeks.get("vega")) if iv else None,
    )


def parse_contracts(
    content: bytes,
) -> tuple[tuple[OptionContract, ...], dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    required = {
        "EXCH_ID",
        "SEGMENT",
        "SECURITY_ID",
        "INSTRUMENT",
        "UNDERLYING_SYMBOL",
        "LOT_SIZE",
        "SM_EXPIRY_DATE",
        "STRIKE_PRICE",
        "OPTION_TYPE",
        "TICK_SIZE",
    }
    if not required.issubset(reader.fieldnames or []):
        raise ChainFailure("provider_unavailable", 503)
    contracts: dict[str, OptionContract] = {}
    tokens: dict[str, str] = {}
    for index, row in enumerate(reader):
        if index >= 250_000:
            raise ChainFailure("provider_unavailable", 503)
        if row.get("EXCH_ID") != "NSE" or row.get("INSTRUMENT") not in {"OPTIDX", "OPTSTK"}:
            continue
        if row.get("OPTION_TYPE") not in {"CE", "PE"}:
            continue
        try:
            expiry = date.fromisoformat(row["SM_EXPIRY_DATE"][:10])
            strike = Decimal(row["STRIKE_PRICE"])
            lot = Decimal(row["LOT_SIZE"])
            tick = Decimal(row["TICK_SIZE"]) / 100  # Dhan master uses paise; domain uses INR.
            if lot != lot.to_integral_value() or not row["SECURITY_ID"].isdigit():
                raise ValueError
            symbol = row["UNDERLYING_SYMBOL"].strip().upper()
            side = OptionType(row["OPTION_TYPE"])
            canonical_id = option_contract_id("NFO", symbol, expiry, strike, side)
            contract = OptionContract(
                canonical_id=canonical_id,
                exchange="NFO",
                segment="NFO-OPT",
                underlying_symbol=symbol,
                underlying_type=UnderlyingType.INDEX
                if row["INSTRUMENT"] == "OPTIDX"
                else UnderlyingType.EQUITY,
                expiry=expiry,
                strike=strike,
                option_type=side,
                lot_size=int(lot),
                tick_size=tick,
                display_symbol=f"{symbol} {expiry.isoformat()} {strike} {side.value}",
                last_trading_date=expiry,
            )
        except (ValueError, InvalidOperation, KeyError):
            raise ChainFailure("provider_unavailable", 503) from None
        if canonical_id in contracts:
            raise ChainFailure("partial_chain", 503)
        contracts[canonical_id], tokens[canonical_id] = contract, row["SECURITY_ID"]
    if not contracts:
        raise ChainFailure("no_option_contracts", 404)
    return tuple(contracts.values()), tokens


class DhanOptionChainSource:
    capabilities = CAPABILITIES
    quote_ttl_seconds = 5

    def __init__(self, provider: DhanMarketDataProvider) -> None:
        self.provider = provider
        self.master_received_at = datetime.min.replace(tzinfo=UTC)
        self._contracts: tuple[OptionContract, ...] = ()
        self._tokens: dict[str, str] = {}
        self._master_lock = asyncio.Lock()
        self._market_lock = asyncio.Lock()
        self._quotes: dict[tuple[str, date], ChainMarketBatch] = {}
        self._last_call = 0.0

    async def contracts(self) -> tuple[OptionContract, ...]:
        async with self._master_lock:
            if (
                self._contracts
                and (datetime.now(UTC) - self.master_received_at).total_seconds()
                < self.provider.settings.master_cache_seconds
            ):
                return self._contracts
            try:
                raw = await self.provider._body("GET", MASTER_URL, limit=40_000_000)
                contracts, tokens = parse_contracts(raw)
            except (MarketDataFailure, UnicodeError, csv.Error):
                raise ChainFailure("provider_unavailable", 503) from None
            self._contracts, self._tokens = contracts, tokens
            self.master_received_at = datetime.now(UTC)
            self._quotes.clear()
            return contracts

    async def market(
        self, underlying: str, expiry: date, contracts: tuple[OptionContract, ...]
    ) -> ChainMarketBatch:
        key = underlying, expiry
        async with self._market_lock:
            cached = self._quotes.get(key)
            if (
                cached
                and (datetime.now(UTC) - cached.received_at).total_seconds()
                < self.quote_ttl_seconds
            ):
                return replace(cached, cached=True)
            loop = asyncio.get_running_loop()
            # Respect provider spacing, with no retries and no busy loop.
            await asyncio.sleep(max(0, 3.1 - (loop.time() - self._last_call)))
            try:
                instruments = await self.provider.resolve_instruments((underlying,))
                if len(instruments) != 1:
                    raise ChainFailure("underlying_not_found", 404)
                segment, security_id = instruments[0].native.native_id.split(":", 1)
                self._last_call = loop.time()
                raw = await self.provider._json(
                    "/optionchain",
                    {
                        "UnderlyingScrip": int(security_id),
                        "UnderlyingSeg": segment,
                        "Expiry": expiry.isoformat(),
                    },
                )
            except (MarketDataFailure, ValueError):
                raise ChainFailure("provider_unavailable", 503) from None
            if raw.get("status") != "success" or not isinstance(raw.get("data"), dict):
                raise ChainFailure("quote_unavailable", 503)
            data = raw["data"]
            chain = data.get("oc")
            if not isinstance(chain, dict) or len(chain) > 5000:
                raise ChainFailure("quote_unavailable", 503)
            quotes: dict[str, OptionMarketSnapshot] = {}
            warnings: list[str] = []
            listed = {(c.strike, c.option_type): c for c in contracts}
            for strike_text, sides in chain.items():
                strike = number(strike_text)
                if strike is None or not isinstance(sides, dict):
                    warnings.append("partial_chain")
                    continue
                for side in OptionType:
                    contract = listed.get((strike, side))
                    value = sides.get(side.value.lower())
                    if contract is None or not isinstance(value, dict):
                        continue
                    if str(value.get("security_id")) != self._tokens.get(contract.canonical_id):
                        warnings.append("partial_chain")
                        continue
                    if contract.canonical_id in quotes:
                        raise ChainFailure("partial_chain", 503)
                    quotes[contract.canonical_id] = normalize_market(value)
            spot = number(data.get("last_price"))
            batch = ChainMarketBatch(
                spot=spot if spot and spot > 0 else None,
                quotes=quotes,
                received_at=datetime.now(UTC),
                warnings=tuple(dict.fromkeys(warnings)),
            )
            if len(self._quotes) >= 32:
                del self._quotes[next(iter(self._quotes))]
            self._quotes[key] = batch
            return batch
