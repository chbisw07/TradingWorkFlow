"""All Kite syntax is confined here. No order-writing endpoints exist."""

import asyncio
import csv
import hashlib
import io
import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from pydantic import SecretStr

from twf.brokers.contracts import (
    Binding,
    BrokerFailure,
    CatalogPage,
    Credentials,
    Funds,
    Holding,
    Instrument,
    Order,
    Position,
    Search,
)


def invalid() -> BrokerFailure:
    return BrokerFailure("PROVIDER_RESPONSE_INVALID", "Broker returned an invalid response.")


def text(value: object) -> str | None:
    return (
        value
        if isinstance(value, str) and 0 < len(value) <= 160 and all(ord(c) >= 32 for c in value)
        else None
    )


def number(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and abs(result) < Decimal("1e25") else None
    except InvalidOperation:
        return None


def rows(value: object) -> list[dict[str, Any]]:
    if (
        not isinstance(value, list)
        or len(value) > 100000
        or not all(isinstance(x, dict) for x in value)
    ):
        raise invalid()
    return value


class ZerodhaAdapter:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport
        self.catalog: list[Instrument] = []
        self.catalog_index: dict[tuple[str, str, str | None], Instrument] = {}
        self.catalog_at: datetime | None = None
        self.catalog_lock = asyncio.Lock()

    async def _request(
        self,
        method: str,
        path: str,
        credentials: Credentials,
        data: dict[str, str] | None = None,
        *,
        csv_response: bool = False,
    ) -> Any:
        headers = {"X-Kite-Version": "3"}
        if credentials.access_token:
            headers["Authorization"] = (
                f"token {credentials.api_key.get_secret_value()}:"
                f"{credentials.access_token.get_secret_value()}"
            )
        # No redirects, environment proxies, SDK logging or credential-bearing URLs.
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(8, connect=4, pool=2),
            ) as client:
                async with client.stream(
                    method, "https://api.kite.trade" + path, headers=headers, data=data
                ) as response:
                    if response.status_code in (401, 403):
                        raise BrokerFailure(
                            "BROKER_REAUTH_REQUIRED", "Reconnect this broker account.", 409
                        )
                    if response.status_code == 429:
                        raise BrokerFailure(
                            "PROVIDER_RATE_LIMITED", "Broker is busy. Try again shortly.", 503
                        )
                    if response.status_code != 200:
                        raise BrokerFailure(
                            "PROVIDER_UNAVAILABLE", "Broker request failed. Please retry.", 502
                        )
                    limit = 40_000_000 if csv_response else 4_000_000
                    body = bytearray()
                    async for chunk in response.aiter_bytes(65536):
                        if len(body) + len(chunk) > limit:
                            raise invalid()
                        body.extend(chunk)
            if csv_response:
                return await asyncio.to_thread(self._parse_catalog, bytes(body))
            parsed = await asyncio.to_thread(json.loads, body)
            if (
                not isinstance(parsed, dict)
                or parsed.get("status") != "success"
                or "data" not in parsed
            ):
                raise invalid()
            return parsed["data"]
        except httpx.TimeoutException:
            raise BrokerFailure("PROVIDER_TIMEOUT", "Broker request timed out.", 504) from None
        except (httpx.HTTPError, ValueError, UnicodeError, csv.Error):
            raise invalid() from None

    async def authenticate(self, credentials: Credentials, request_token: str) -> Binding:
        checksum = hashlib.sha256(
            (
                credentials.api_key.get_secret_value()
                + request_token
                + credentials.api_secret.get_secret_value()
            ).encode()
        ).hexdigest()
        result = await self._request(
            "POST",
            "/session/token",
            credentials,
            {
                "api_key": credentials.api_key.get_secret_value(),
                "request_token": request_token,
                "checksum": checksum,
            },
        )
        if not isinstance(result, dict):
            raise invalid()
        token, identity = text(result.get("access_token")), text(result.get("user_id"))
        if (
            not token
            or not identity
            or result.get("api_key") != credentials.api_key.get_secret_value()
        ):
            raise invalid()
        authenticated = credentials.model_copy(update={"access_token": SecretStr(token)})
        verified = await self.get_profile(authenticated)
        if verified != identity:
            raise BrokerFailure("ACCOUNT_MISMATCH", "Broker account verification failed.", 409)
        return Binding(identity=identity, access_token=SecretStr(token))

    async def get_profile(self, credentials: Credentials) -> str:
        value = await self._request("GET", "/user/profile", credentials)
        identity = text(value.get("user_id")) if isinstance(value, dict) else None
        if (
            not identity
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", identity)
            or value.get("broker") != "ZERODHA"
        ):
            raise invalid()
        return identity

    def _instrument(self, row: dict[str, Any]) -> Instrument:
        symbol, exchange = text(row.get("tradingsymbol")), text(row.get("exchange"))
        if not symbol or not exchange:
            raise invalid()
        token = str(row["instrument_token"]) if row.get("instrument_token") is not None else None
        match = self.catalog_index.get((exchange, symbol, token))
        return match or Instrument(
            symbol=symbol,
            exchange=exchange,
            reference=f"ZERODHA:{exchange}:{symbol}",
            native_token=token,
        )

    async def get_holdings(self, credentials: Credentials) -> list[Holding]:
        result = []
        for row in rows(await self._request("GET", "/portfolio/holdings", credentials)):
            # Kite ownership components are disjoint. Collateral/authorised/used
            # quantities are not additional ownership and must not be added.
            mtf = row.get("mtf")
            components = [
                number(row.get("quantity")),
                number(row.get("t1_quantity")),
                number(mtf.get("quantity")) if isinstance(mtf, dict) else None,
            ]
            quantity = (
                sum((x for x in components if x is not None), Decimal(0))
                if all(x is not None and x >= 0 and x == x.to_integral_value() for x in components)
                else None
            )
            average, last, pnl = (
                number(row.get(k)) for k in ("average_price", "last_price", "pnl")
            )
            # Published MTF fields do not establish a combined cost/P&L basis.
            # Keep known ownership/value and provider P&L, but never invent a
            # combined average or divide that P&L by a partial cost basis.
            if quantity is None or components[2] != 0:
                average = None
            cost = quantity * average if quantity is not None and average is not None else None
            result.append(
                Holding(
                    instrument=self._instrument(row),
                    quantity=quantity,
                    average=average,
                    last_price=last,
                    value=quantity * last if quantity is not None and last is not None else None,
                    pnl=pnl,
                    pnl_percent=pnl / cost * 100 if pnl is not None and cost else None,
                )
            )
        return result

    async def get_positions(self, credentials: Credentials) -> list[Position]:
        payload = await self._request("GET", "/portfolio/positions", credentials)
        if not isinstance(payload, dict):
            raise invalid()
        return [
            Position(
                instrument=self._instrument(row),
                product=text(row.get("product")),
                quantity=number(row.get("quantity")),
                average=number(row.get("average_price")),
                last_price=number(row.get("last_price")),
                realized=number(row.get("realised")),
                unrealized=number(row.get("unrealised")),
                pnl=number(row.get("pnl")),
            )
            for row in rows(payload.get("net"))
        ]

    async def get_orders(self, credentials: Credentials) -> list[Order]:
        result = []
        for row in rows(await self._request("GET", "/orders", credentials)):
            order_id = text(row.get("order_id"))
            if not order_id:
                raise invalid()
            result.append(
                Order(
                    id=order_id,
                    instrument=self._instrument(row),
                    time=text(row.get("order_timestamp")),
                    side=text(row.get("transaction_type")),
                    quantity=number(row.get("quantity")),
                    kind=text(row.get("order_type")),
                    price=number(row.get("price")),
                    status=text(row.get("status")),
                )
            )
        return result

    async def get_funds(self, credentials: Credentials) -> list[Funds]:
        payload = await self._request("GET", "/user/margins", credentials)
        if not isinstance(payload, dict) or not payload:
            raise invalid()
        result = []
        for segment in ("equity", "commodity"):
            row = payload.get(segment)
            if row is None:
                continue
            if not isinstance(row, dict) or not isinstance(row.get("enabled"), bool):
                raise invalid()
            available, used = row.get("available") or {}, row.get("utilised") or {}
            if not isinstance(available, dict) or not isinstance(used, dict):
                raise invalid()
            result.append(
                Funds(
                    segment=segment,
                    enabled=row["enabled"],
                    cash=number(available.get("cash")),
                    used_margin=number(used.get("debits")),
                    available_margin=number(row.get("net")),
                    collateral=number(available.get("collateral")),
                )
            )
        if not result:
            raise invalid()
        return result

    @staticmethod
    def _parse_catalog(body: bytes) -> list[Instrument]:
        reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
        required = {
            "instrument_token",
            "tradingsymbol",
            "exchange",
            "segment",
            "instrument_type",
            "expiry",
            "strike",
            "name",
            "lot_size",
        }
        if not required.issubset(reader.fieldnames or []):
            raise invalid()
        result: list[Instrument] = []
        identities: set[tuple[str, str]] = set()
        for row in reader:
            symbol, exchange = text(row.get("tradingsymbol")), text(row.get("exchange"))
            token, kind = row.get("instrument_token", ""), text(row.get("instrument_type"))
            if (
                not symbol
                or not exchange
                or not token.isdigit()
                or len(result) >= 250000
                or (exchange, symbol) in identities
            ):
                raise invalid()
            identities.add((exchange, symbol))
            expiry = row.get("expiry") or None
            if expiry:
                datetime.strptime(expiry, "%Y-%m-%d")
            # Retain official derivative fields; do not parse identity from display symbols.
            result.append(
                Instrument(
                    symbol=symbol,
                    exchange=exchange,
                    reference=f"ZERODHA:{exchange}:{symbol}",
                    native_token=token,
                    name=text(row.get("name")),
                    underlying=text(row.get("name")) if kind in ("CE", "PE", "FUT") else None,
                    expiry=expiry,
                    strike=number(row.get("strike")) if kind in ("CE", "PE") else None,
                    kind=kind,
                    segment=text(row.get("segment")),
                    lot_size=number(row.get("lot_size")),
                )
            )
        if not result:
            raise invalid()
        return sorted(result, key=lambda x: (x.exchange, x.symbol))

    async def search_instruments(self, credentials: Credentials, query: Search) -> CatalogPage:
        async with self.catalog_lock:
            if not self.catalog_at or datetime.now(UTC) - self.catalog_at > timedelta(hours=24):
                catalog = await self._request("GET", "/instruments", credentials, csv_response=True)
                self.catalog, self.catalog_at = catalog, datetime.now(UTC)
                self.catalog_index = {(x.exchange, x.symbol, x.native_token): x for x in catalog}
        matches = [
            x
            for x in self.catalog
            if (not query.q or query.q.upper() in f"{x.symbol} {x.name or ''}".upper())
            and (not query.underlying or query.underlying.upper() == (x.underlying or "").upper())
            and (not query.expiry or query.expiry == x.expiry)
            and (query.strike is None or query.strike == x.strike)
            and (not query.kind or query.kind == x.kind)
        ]
        start = (query.page - 1) * query.limit
        return CatalogPage(
            items=matches[start : start + query.limit],
            total=len(matches),
            page=query.page,
            limit=query.limit,
            fetched_at=self.catalog_at,
        )

    async def disconnect(self, credentials: Credentials) -> None:
        # Local token destruction is authoritative. No tokens in URL; remote invalidation is
        # deliberately not claimed (Kite documents query-token DELETE). User can revoke in Kite.
        return None
