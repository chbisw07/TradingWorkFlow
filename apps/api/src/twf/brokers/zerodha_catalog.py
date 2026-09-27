"""Kite CSV translation. Raw provider columns never leave this adapter."""

import asyncio
import csv
import hashlib
import io
import json
import re
import zlib
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from time import monotonic
from typing import cast

import httpx

from twf.brokers.catalog_contracts import CatalogFailure, CatalogPayload, Kind, NativeInstrument
from twf.secrets import SecretValue


class KiteCatalogClient:
    TOTAL_DEADLINE_SECONDS = 30.0
    MAX_WIRE_BYTES = 16 * 1024 * 1024
    MAX_BYTES = 64 * 1024 * 1024
    MAX_ROWS = 250000
    COLUMNS = {
        "instrument_token",
        "exchange_token",
        "tradingsymbol",
        "name",
        "expiry",
        "strike",
        "tick_size",
        "lot_size",
        "instrument_type",
        "segment",
        "exchange",
    }

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    @staticmethod
    def _check(deadline: float) -> None:
        if monotonic() >= deadline:
            raise CatalogFailure("TIMEOUT")

    def fetch(self, api_key: str, token: SecretValue) -> CatalogPayload:
        deadline = monotonic() + self.TOTAL_DEADLINE_SECONDS
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._fetch(api_key, token, deadline))
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()

    async def _fetch(self, api_key: str, token: SecretValue, deadline: float) -> CatalogPayload:
        try:
            async with asyncio.timeout(max(0.0, deadline - monotonic())):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    timeout=httpx.Timeout(5.0),
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    async with client.stream(
                        "GET",
                        "https://api.kite.trade/instruments",
                        headers={
                            "X-Kite-Version": "3",
                            "Authorization": f"token {api_key}:{token.reveal()}",
                            "Accept": "text/csv",
                            "Accept-Encoding": "gzip",
                        },
                    ) as response:
                        self._check(deadline)
                        if response.status_code in (401, 403):
                            raise CatalogFailure("AUTH_REQUIRED")
                        if response.status_code == 429:
                            raise CatalogFailure("RATE_LIMITED")
                        if response.status_code != 200:
                            raise CatalogFailure("UNAVAILABLE")
                        encoding = response.headers.get("content-encoding", "identity").lower()
                        if encoding not in ("identity", "gzip"):
                            raise CatalogFailure("INVALID_RESPONSE")
                        decoder = (
                            zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
                        )
                        body, wire = bytearray(), 0
                        async for chunk in response.aiter_raw(chunk_size=16384):
                            self._check(deadline)
                            wire += len(chunk)
                            if wire > self.MAX_WIRE_BYTES:
                                raise CatalogFailure("TOO_LARGE")
                            decoded = (
                                decoder.decompress(chunk, self.MAX_BYTES - len(body) + 1)
                                if decoder
                                else chunk
                            )
                            if len(body) + len(decoded) > self.MAX_BYTES:
                                raise CatalogFailure("TOO_LARGE")
                            body.extend(decoded)
                        if decoder and (not decoder.eof or decoder.unused_data):
                            raise CatalogFailure("INVALID_RESPONSE")
                        self._check(deadline)
                        result = self.parse(bytes(body), deadline)
                self._check(deadline)
                return result
        except (TimeoutError, httpx.TimeoutException):
            raise CatalogFailure("TIMEOUT") from None
        except CatalogFailure:
            raise
        except httpx.HTTPError:
            self._check(deadline)
            raise CatalogFailure("UNAVAILABLE") from None
        except (zlib.error, UnicodeError, csv.Error, ValueError):
            self._check(deadline)
            raise CatalogFailure("INVALID_RESPONSE") from None

    @staticmethod
    def _text(value: str, limit: int = 128) -> str:
        if (
            not value
            or value != value.strip()
            or len(value) > limit
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise ValueError
        return value

    @staticmethod
    def _decimal(value: str, *, positive: bool = False) -> Decimal:
        if not re.fullmatch(r"\d{1,13}(?:\.\d{1,8})?", value):
            raise ValueError
        result = Decimal(value)
        if (
            not result.is_finite()
            or result > Decimal("1000000000000")
            or (positive and result <= 0)
        ):
            raise ValueError
        return result.normalize()

    def parse(self, body: bytes, deadline: float) -> CatalogPayload:
        if len(body) > self.MAX_BYTES:
            raise CatalogFailure("TOO_LARGE")
        reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")), strict=True)
        if (
            not reader.fieldnames
            or not self.COLUMNS.issubset(reader.fieldnames)
            or len(set(reader.fieldnames)) != len(reader.fieldnames)
        ):
            raise CatalogFailure("INVALID_RESPONSE")
        rows: list[NativeInstrument] = []
        tokens: set[str] = set()
        symbols: set[tuple[str, str]] = set()
        total = rejected = 0
        try:
            for source in reader:
                total += 1
                self._check(deadline)
                if total > self.MAX_ROWS:
                    raise CatalogFailure("TOO_LARGE", total, len(rows), rejected)
                try:
                    if None in source or any(v is None for v in source.values()):
                        raise ValueError
                    native_id = self._text(source["instrument_token"], 64)
                    exchange_id = source["exchange_token"] or None
                    if (
                        not native_id.isascii()
                        or not native_id.isdigit()
                        or (
                            exchange_id
                            and (
                                not exchange_id.isascii()
                                or not exchange_id.isdigit()
                                or len(exchange_id) > 64
                            )
                        )
                    ):
                        raise ValueError
                    symbol = self._text(source["tradingsymbol"])
                    exchange = self._text(source["exchange"], 32)
                    kind = self._text(source["instrument_type"], 32)
                    expiry = date.fromisoformat(source["expiry"]) if source["expiry"] else None
                    strike = self._decimal(source["strike"]) if source["strike"] else None
                    if kind in ("CE", "PE", "FUT") and expiry is None:
                        raise ValueError
                    if kind in ("CE", "PE") and strike is None:
                        raise ValueError
                    if not re.fullmatch(r"[1-9]\d{0,8}", source["lot_size"]):
                        raise ValueError
                    if native_id in tokens or (exchange, symbol) in symbols:
                        raise ValueError
                    row = NativeInstrument(
                        native_id=native_id,
                        exchange_id=exchange_id,
                        symbol=symbol,
                        name=self._text(source["name"], 256) if source["name"] else None,
                        exchange=exchange,
                        segment=self._text(source["segment"], 32),
                        instrument_type=kind,
                        expiry=expiry,
                        strike=strike,
                        derivative_kind=cast(Kind, kind) if kind in ("CE", "PE", "FUT") else None,
                        lot_size=int(source["lot_size"]),
                        tick_size=self._decimal(source["tick_size"], positive=True),
                        fingerprint="",
                    )
                    digest = hashlib.sha256(
                        json.dumps(
                            row.model_dump(mode="json", exclude={"fingerprint"}),
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest()
                    rows.append(row.model_copy(update={"fingerprint": digest}))
                    tokens.add(native_id)
                    symbols.add((exchange, symbol))
                except (ValueError, InvalidOperation):
                    rejected += 1
        except (csv.Error, UnicodeError):
            raise CatalogFailure("INVALID_RESPONSE", total, len(rows), rejected + 1) from None
        if rejected:
            raise CatalogFailure("PARTIAL_RESPONSE", total, len(rows), rejected)
        if not rows:
            raise CatalogFailure("EMPTY")
        rows.sort(key=lambda row: (row.exchange, row.segment, row.symbol, row.native_id))
        digest = hashlib.sha256("".join(row.fingerprint for row in rows).encode()).hexdigest()
        self._check(deadline)
        return CatalogPayload(
            instruments=tuple(rows),
            fingerprint=digest,
            fetched_at=datetime.now(UTC),
            total_rows=total,
        )
