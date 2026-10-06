"""Provider-neutral authoritative market-data contracts and Dhan implementation."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import math
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

import httpx
from pydantic import Field, SecretStr, ValidationError, model_validator

from twf.discovery.domain import (
    InstrumentIdentity,
    ProducerIdentity,
    Provenance,
    RevisionRef,
    SourceMode,
    SourceReference,
    UnderlyingIdentity,
    digest,
)
from twf.discovery.internal_scanner.market_series import (
    INTERVAL_SECONDS,
    MAX_BARS,
    Bar,
    DataReason,
    DataUnavailable,
    MarketSeries,
)
from twf.discovery.providers import OperationContext
from twf.integrations.contracts import Contract, Identifier

DHAN_IDENTITY = ProducerIdentity(
    service_id="dhan-market-data",
    provider="dhan",
    service_version="1",
    contract_version="market-data.v1",
)
SYNTHETIC_MARKET_DATA_IDENTITY = ProducerIdentity(
    service_id="synthetic-market-data",
    provider="twf-fixture",
    service_version="1",
    contract_version="market-data.v1",
)
IST = ZoneInfo("Asia/Kolkata")
DHAN_INTERVALS = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "1d": "1D"}
MASTER_COLUMNS = {
    "SEM_EXM_EXCH_ID",
    "SEM_SEGMENT",
    "SEM_SMST_SECURITY_ID",
    "SEM_INSTRUMENT_NAME",
    "SEM_TRADING_SYMBOL",
    "SEM_CUSTOM_SYMBOL",
    "SEM_EXCH_INSTRUMENT_TYPE",
    "SEM_SERIES",
    "SM_SYMBOL_NAME",
}


class MarketDataErrorCode(StrEnum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    INSTRUMENT_NOT_FOUND = "INSTRUMENT_NOT_FOUND"
    AMBIGUOUS_INSTRUMENT = "AMBIGUOUS_INSTRUMENT"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    PARTIAL_RESPONSE = "PARTIAL_RESPONSE"
    TIMEOUT = "TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    UNSUPPORTED_INTERVAL = "UNSUPPORTED_INTERVAL"


class MarketDataFailure(Exception):
    def __init__(self, code: MarketDataErrorCode, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(code.value)


class MarketDataCapabilities(Contract):
    provider: Identifier
    instrument_resolution: bool
    batch_quotes: bool
    historical_ohlcv: bool
    intraday_ohlcv: bool
    intervals: tuple[str, ...]
    max_quote_batch: int = Field(ge=1, le=1000)
    max_bars: int = Field(ge=1, le=MAX_BARS)


class MarketDataHealth(Contract):
    provider: Identifier
    state: Literal["READY", "AUTH_REQUIRED", "RATE_LIMITED", "ERROR"]
    checked_at: datetime
    detail: str


class QuoteSnapshot(Contract):
    instrument: InstrumentIdentity
    last_price: Decimal = Field(gt=0, allow_inf_nan=False)
    open: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    high: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    low: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    previous_close: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    volume: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    open_interest: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    provider_source_time: datetime | None = None
    received_at: datetime
    provider: Literal["dhan", "twf-fixture"]


class DhanMarketDataSettings(Contract):
    enabled: bool = False
    client_id: SecretStr | None = Field(default=None, repr=False)
    access_token: SecretStr | None = Field(default=None, repr=False)
    api_base_url: Literal["https://api.dhan.co/v2"] = "https://api.dhan.co/v2"
    instrument_master_url: Literal["https://images.dhan.co/api-data/api-scrip-master.csv"] = (
        "https://images.dhan.co/api-data/api-scrip-master.csv"
    )
    timeout_seconds: float = Field(default=10, ge=0.1, le=30)
    max_response_bytes: int = Field(default=8_000_000, ge=65_536, le=40_000_000)
    master_cache_seconds: int = Field(default=21_600, ge=300, le=86_400)
    retain_scan_bars: bool = True

    @model_validator(mode="after")
    def credentials_are_paired(self) -> DhanMarketDataSettings:
        if (self.client_id is None) != (self.access_token is None):
            raise ValueError("Dhan client_id and access_token must be configured together")
        return self

    @property
    def configured(self) -> bool:
        return self.enabled and self.client_id is not None and self.access_token is not None


class MarketDataProvider(Protocol):
    @property
    def capabilities(self) -> MarketDataCapabilities: ...

    async def health(self) -> MarketDataHealth: ...

    async def resolve_instruments(
        self, symbols: tuple[str, ...]
    ) -> tuple[InstrumentIdentity, ...]: ...

    async def get_quotes(
        self, instruments: tuple[InstrumentIdentity, ...]
    ) -> tuple[QuoteSnapshot, ...]: ...

    async def get_ohlcv(
        self,
        instrument: InstrumentIdentity,
        interval: str,
        *,
        as_of: datetime,
        count: int,
    ) -> MarketSeries: ...

    async def read(
        self, context: OperationContext, instrument: InstrumentIdentity, interval: str
    ) -> MarketSeries: ...


def _stable(kind: str, value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"twf-market-data:{kind}:{value}")


def _decimal(value: object, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("invalid numeric value")
    number = Decimal(str(value))
    if not number.is_finite() or abs(number) > Decimal("1e20"):
        raise ValueError("invalid numeric value")
    if positive and number <= 0:
        raise ValueError("invalid positive value")
    return number


def _exchange_segment(row: dict[str, str]) -> str:
    exchange, segment = row["SEM_EXM_EXCH_ID"], row["SEM_SEGMENT"]
    if segment == "I":
        return "IDX_I"
    return f"{exchange}_{'EQ' if segment == 'E' else 'FNO'}"


def _identity(row: dict[str, str]) -> InstrumentIdentity:
    native_id = f"{_exchange_segment(row)}:{row['SEM_SMST_SECURITY_ID']}"
    symbol = row["SEM_TRADING_SYMBOL"].strip().upper()
    instrument_type = row["SEM_INSTRUMENT_NAME"].strip().upper()
    source = SourceReference(namespace="dhan", native_id=native_id, revision="scrip-master-v1")
    return InstrumentIdentity(
        instrument_id=_stable("instrument", native_id),
        underlying=UnderlyingIdentity(
            underlying_id=_stable("underlying", f"{row['SEM_EXM_EXCH_ID']}:{symbol}"),
            source=source,
            mapping=RevisionRef(id="dhan-scrip-master", version="1"),
        ),
        native=source,
        symbol=symbol,
        exchange=row["SEM_EXM_EXCH_ID"],
        segment="INDEX" if row["SEM_SEGMENT"] == "I" else "EQ",
        instrument_type=instrument_type,
        provider_symbol=row["SEM_TRADING_SYMBOL"].strip(),
    )


class DhanMarketDataProvider:
    """Bounded REST adapter. Native Dhan payloads do not escape this module."""

    capabilities = MarketDataCapabilities(
        provider="dhan",
        instrument_resolution=True,
        batch_quotes=True,
        historical_ohlcv=True,
        intraday_ohlcv=True,
        intervals=tuple(DHAN_INTERVALS),
        max_quote_batch=1000,
        max_bars=MAX_BARS,
    )

    def __init__(
        self,
        settings: DhanMarketDataSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self._master: tuple[dict[str, str], ...] = ()
        self._master_at: datetime | None = None
        self._master_lock = asyncio.Lock()

    def _headers(self) -> dict[str, str]:
        if not self.settings.configured:
            raise MarketDataFailure(MarketDataErrorCode.AUTH_REQUIRED)
        assert self.settings.access_token is not None
        assert self.settings.client_id is not None
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "access-token": self.settings.access_token.get_secret_value(),
            "client-id": self.settings.client_id.get_secret_value(),
        }

    async def _body(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        payload: dict[str, object] | None = None,
        limit: int | None = None,
    ) -> bytes:
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(self.settings.timeout_seconds, connect=4, pool=2),
                ) as client:
                    async with client.stream(
                        method, url, headers=headers, json=payload
                    ) as response:
                        if response.status_code in {401, 403}:
                            raise MarketDataFailure(MarketDataErrorCode.AUTH_REQUIRED)
                        if response.status_code == 429:
                            raise MarketDataFailure(
                                MarketDataErrorCode.RATE_LIMITED, retryable=True
                            )
                        if response.status_code != 200:
                            raise MarketDataFailure(
                                MarketDataErrorCode.PROVIDER_ERROR, retryable=True
                            )
                        maximum = limit or self.settings.max_response_bytes
                        body = bytearray()
                        async for chunk in response.aiter_bytes(65_536):
                            if len(body) + len(chunk) > maximum:
                                raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE)
                            body.extend(chunk)
                        return bytes(body)
        except TimeoutError:
            raise MarketDataFailure(MarketDataErrorCode.TIMEOUT, retryable=True) from None
        except httpx.TimeoutException:
            raise MarketDataFailure(MarketDataErrorCode.TIMEOUT, retryable=True) from None
        except httpx.HTTPError:
            raise MarketDataFailure(MarketDataErrorCode.PROVIDER_ERROR, retryable=True) from None

    async def _json(self, path: str, payload: dict[str, object]) -> dict[str, Any]:
        raw = await self._body(
            "POST",
            self.settings.api_base_url + path,
            headers=self._headers(),
            payload=payload,
        )
        try:
            value = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError):
            raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE) from None
        if not isinstance(value, dict):
            raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE)
        return cast(dict[str, Any], value)

    async def _load_master(self) -> tuple[dict[str, str], ...]:
        now = datetime.now(UTC)
        if (
            self._master
            and self._master_at is not None
            and (now - self._master_at).total_seconds() < self.settings.master_cache_seconds
        ):
            return self._master
        async with self._master_lock:
            now = datetime.now(UTC)
            if (
                self._master
                and self._master_at is not None
                and (now - self._master_at).total_seconds() < self.settings.master_cache_seconds
            ):
                return self._master
            raw = await self._body(
                "GET",
                self.settings.instrument_master_url,
                limit=40_000_000,
            )
            try:
                reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
                if reader.fieldnames is None or not MASTER_COLUMNS.issubset(reader.fieldnames):
                    raise ValueError
                rows = tuple(
                    {key: (value or "").strip() for key, value in row.items() if key}
                    for row in reader
                    if row.get("SEM_SMST_SECURITY_ID")
                    and row.get("SEM_TRADING_SYMBOL")
                    and row.get("SEM_INSTRUMENT_NAME")
                )
            except (UnicodeError, csv.Error, ValueError):
                raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE) from None
            if not rows or len(rows) > 250_000:
                raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE)
            self._master, self._master_at = rows, now
            return rows

    async def health(self) -> MarketDataHealth:
        now = datetime.now(UTC)
        if not self.settings.configured:
            return MarketDataHealth(
                provider="dhan",
                state="AUTH_REQUIRED",
                checked_at=now,
                detail="Configure Dhan client ID and a current access token.",
            )
        return MarketDataHealth(
            provider="dhan",
            state="READY",
            checked_at=now,
            detail="Credentials configured; provider calls remain on demand.",
        )

    async def resolve_instruments(self, symbols: tuple[str, ...]) -> tuple[InstrumentIdentity, ...]:
        if len(symbols) > 64 or len(set(symbols)) != len(symbols):
            raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE)
        rows = await self._load_master()
        output: list[InstrumentIdentity] = []
        for requested in symbols:
            symbol = requested.strip().upper()
            candidates = [
                row
                for row in rows
                if row["SEM_TRADING_SYMBOL"].upper() == symbol
                and row["SEM_INSTRUMENT_NAME"].upper() in {"EQUITY", "INDEX"}
                and row["SEM_SEGMENT"] in {"E", "I"}
            ]
            if not candidates:
                raise MarketDataFailure(MarketDataErrorCode.INSTRUMENT_NOT_FOUND)
            ranked = sorted(
                candidates,
                key=lambda row: (
                    0 if row["SEM_EXM_EXCH_ID"] == "NSE" else 1,
                    0 if row["SEM_SEGMENT"] == "I" else 1,
                    0 if row["SEM_SERIES"] in {"EQ", "X"} else 1,
                    row["SEM_SMST_SECURITY_ID"],
                ),
            )
            best = ranked[0]
            best_rank = (
                best["SEM_EXM_EXCH_ID"] == "NSE",
                best["SEM_SEGMENT"] == "I",
                best["SEM_SERIES"] in {"EQ", "X"},
            )
            tied = [
                row
                for row in ranked
                if (
                    row["SEM_EXM_EXCH_ID"] == "NSE",
                    row["SEM_SEGMENT"] == "I",
                    row["SEM_SERIES"] in {"EQ", "X"},
                )
                == best_rank
            ]
            if len(tied) > 1:
                raise MarketDataFailure(MarketDataErrorCode.AMBIGUOUS_INSTRUMENT)
            try:
                output.append(_identity(best))
            except (ValueError, ValidationError):
                raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE) from None
        return tuple(output)

    async def get_quotes(
        self, instruments: tuple[InstrumentIdentity, ...]
    ) -> tuple[QuoteSnapshot, ...]:
        if not 1 <= len(instruments) <= self.capabilities.max_quote_batch:
            raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE)
        request: dict[str, list[int]] = {}
        for item in instruments:
            try:
                segment, security_id = item.native.native_id.split(":", 1)
                request.setdefault(segment, []).append(int(security_id))
            except (ValueError, TypeError):
                raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE) from None
        payload = await self._json("/marketfeed/quote", cast(dict[str, object], request))
        data = payload.get("data")
        if payload.get("status") != "success" or not isinstance(data, dict):
            raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE)
        received = datetime.now(UTC)
        output: list[QuoteSnapshot] = []
        for item in instruments:
            segment, security_id = item.native.native_id.split(":", 1)
            segment_rows = data.get(segment)
            row = segment_rows.get(security_id) if isinstance(segment_rows, dict) else None
            if not isinstance(row, dict):
                raise MarketDataFailure(MarketDataErrorCode.PARTIAL_RESPONSE)
            ohlc_raw = row.get("ohlc")
            ohlc: dict[str, object] = (
                cast(dict[str, object], ohlc_raw) if isinstance(ohlc_raw, dict) else {}
            )
            try:
                last = _decimal(row.get("last_price"), positive=True)
                # Dhan ohlc.close is the day's closing price, not previous close.
                # Closing snapshots can reset net_change to zero. Such a zero is
                # ambiguous until Watchlists can compare dated daily history.
                net = _decimal(row["net_change"]) if row.get("net_change") is not None else None
                previous = last - net if net is not None and net != 0 else None
                source_time = None
                raw_time = row.get("last_trade_time")
                if isinstance(raw_time, str):
                    for pattern in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                        try:
                            source_time = datetime.strptime(raw_time, pattern).replace(tzinfo=IST)
                            break
                        except ValueError:
                            continue
                output.append(
                    QuoteSnapshot(
                        instrument=item,
                        last_price=_decimal(row.get("last_price"), positive=True),
                        open=None
                        if ohlc.get("open") in {None, 0}
                        else _decimal(ohlc["open"], positive=True),
                        high=None
                        if ohlc.get("high") in {None, 0}
                        else _decimal(ohlc["high"], positive=True),
                        low=None
                        if ohlc.get("low") in {None, 0}
                        else _decimal(ohlc["low"], positive=True),
                        previous_close=previous if previous is not None and previous > 0 else None,
                        provider_source_time=source_time,
                        volume=None if row.get("volume") is None else _decimal(row["volume"]),
                        open_interest=None if row.get("oi") is None else _decimal(row["oi"]),
                        received_at=received,
                        provider="dhan",
                    )
                )
            except (ValueError, ValidationError):
                raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE) from None
        return tuple(output)

    @staticmethod
    def _available_at(timestamp: datetime, interval: str) -> datetime:
        if interval != "1d":
            return timestamp + timedelta(seconds=INTERVAL_SECONDS[interval])
        local_date = timestamp.astimezone(IST).date()
        return datetime.combine(local_date, time(15, 30), tzinfo=IST).astimezone(UTC)

    async def get_ohlcv(
        self,
        instrument: InstrumentIdentity,
        interval: str,
        *,
        as_of: datetime,
        count: int,
    ) -> MarketSeries:
        if interval not in DHAN_INTERVALS:
            raise MarketDataFailure(MarketDataErrorCode.UNSUPPORTED_INTERVAL)
        if not 1 <= count <= MAX_BARS:
            raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE)
        as_of = as_of.astimezone(UTC)
        try:
            exchange_segment, security_id = instrument.native.native_id.split(":", 1)
        except ValueError:
            raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE) from None
        instrument_type = instrument.instrument_type or (
            "INDEX" if instrument.segment == "INDEX" else "EQUITY"
        )
        days = max(30, math.ceil(count * (2.2 if interval == "1d" else 0.35)))
        start = as_of - timedelta(days=days)
        request: dict[str, object] = {
            "securityId": security_id,
            "exchangeSegment": exchange_segment,
            "instrument": instrument_type,
            "oi": instrument_type not in {"EQUITY", "INDEX"},
            "fromDate": start.astimezone(IST).strftime(
                "%Y-%m-%d" if interval == "1d" else "%Y-%m-%d %H:%M:%S"
            ),
            "toDate": (as_of + timedelta(days=1))
            .astimezone(IST)
            .strftime("%Y-%m-%d" if interval == "1d" else "%Y-%m-%d %H:%M:%S"),
        }
        if interval == "1d":
            request["expiryCode"] = 0
            path = "/charts/historical"
        else:
            request["interval"] = DHAN_INTERVALS[interval]
            path = "/charts/intraday"
        payload = await self._json(path, request)
        arrays = [
            payload.get(key) for key in ("timestamp", "open", "high", "low", "close", "volume")
        ]
        if not all(isinstance(value, list) for value in arrays):
            raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE)
        lengths = {len(cast(list[object], value)) for value in arrays}
        if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
            raise MarketDataFailure(MarketDataErrorCode.DATA_UNAVAILABLE)
        timestamps, opens, highs, lows, closes, volumes = cast(
            tuple[
                list[object], list[object], list[object], list[object], list[object], list[object]
            ],
            tuple(arrays),
        )
        oi_values = payload.get("open_interest")
        if oi_values is not None and (
            not isinstance(oi_values, list) or len(oi_values) != len(timestamps)
        ):
            raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE)
        parsed: list[Bar] = []
        excluded = False
        try:
            for index, raw_time in enumerate(timestamps):
                if isinstance(raw_time, bool) or not isinstance(raw_time, (int, float)):
                    raise ValueError
                timestamp = datetime.fromtimestamp(float(raw_time), UTC)
                available = self._available_at(timestamp, interval)
                if available > as_of:
                    excluded = True
                    continue
                parsed.append(
                    Bar(
                        timestamp=timestamp,
                        available_at=available,
                        open=float(_decimal(opens[index], positive=True)),
                        high=float(_decimal(highs[index], positive=True)),
                        low=float(_decimal(lows[index], positive=True)),
                        close=float(_decimal(closes[index], positive=True)),
                        volume=float(_decimal(volumes[index])),
                        open_interest=(
                            None
                            if oi_values is None
                            else float(_decimal(cast(list[object], oi_values)[index]))
                        ),
                        finality="COMPLETED",
                    )
                )
        except (ValueError, OverflowError, OSError):
            raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE) from None
        parsed.sort(key=lambda item: item.timestamp)
        if not parsed or any(
            a.timestamp >= b.timestamp for a, b in zip(parsed, parsed[1:], strict=False)
        ):
            raise MarketDataFailure(MarketDataErrorCode.DATA_UNAVAILABLE)
        bars = tuple(parsed[-count:])
        received = datetime.now(UTC)
        provenance = Provenance(
            producer=DHAN_IDENTITY,
            source=instrument.native,
            mode=SourceMode.EOD if interval == "1d" else SourceMode.LIVE_SNAPSHOT,
            observation_key=digest(
                {
                    "instrument": instrument.native.native_id,
                    "interval": interval,
                    "as_of": as_of.isoformat(),
                    "last": bars[-1].timestamp.isoformat(),
                    "count": len(bars),
                }
            ),
            transformation=RevisionRef(id="dhan-v2-ohlcv-normalization", version="1"),
            dependence_group="dhan-authoritative-market-data",
        )
        try:
            return MarketSeries(
                instrument=instrument,
                interval=interval,
                price_unit="INR",
                adjustment=RevisionRef(id="dhan-provider-unadjusted", version="1"),
                session_basis=RevisionRef(id="india-cash-market", version="1"),
                provenance=provenance,
                received_at=received,
                requested_count=count,
                completeness="COMPLETE" if len(bars) == count else "PARTIAL",
                live_bar_excluded=excluded,
                bars=bars,
            )
        except (ValueError, ValidationError):
            raise MarketDataFailure(MarketDataErrorCode.INVALID_RESPONSE) from None

    async def read(
        self, context: OperationContext, instrument: InstrumentIdentity, interval: str
    ) -> MarketSeries:
        return await self.get_ohlcv(instrument, interval, as_of=context.as_of, count=320)


class FixtureMarketDataProvider:
    """Deterministic provider using the same contracts and scanner path as Dhan."""

    capabilities = MarketDataCapabilities(
        provider="twf-fixture",
        instrument_resolution=True,
        batch_quotes=True,
        historical_ohlcv=True,
        intraday_ohlcv=True,
        intervals=tuple(INTERVAL_SECONDS),
        max_quote_batch=64,
        max_bars=MAX_BARS,
    )

    def __init__(self, series: tuple[MarketSeries, ...]) -> None:
        self.series = tuple(MarketSeries.model_validate(item.model_dump()) for item in series)

    async def health(self) -> MarketDataHealth:
        return MarketDataHealth(
            provider="twf-fixture",
            state="READY",
            checked_at=datetime.now(UTC),
            detail="Deterministic validation fixtures.",
        )

    async def resolve_instruments(self, symbols: tuple[str, ...]) -> tuple[InstrumentIdentity, ...]:
        result: list[InstrumentIdentity] = []
        for symbol in symbols:
            matches = [item.instrument for item in self.series if item.instrument.symbol == symbol]
            unique = {item.instrument_id: item for item in matches}
            if len(unique) != 1:
                raise MarketDataFailure(MarketDataErrorCode.INSTRUMENT_NOT_FOUND)
            result.append(next(iter(unique.values())))
        return tuple(result)

    async def get_quotes(
        self, instruments: tuple[InstrumentIdentity, ...]
    ) -> tuple[QuoteSnapshot, ...]:
        received = datetime.now(UTC)
        return tuple(
            QuoteSnapshot(
                instrument=instrument,
                last_price=Decimal(
                    str(
                        next(
                            item.bars[-1].close
                            for item in self.series
                            if item.instrument == instrument
                        )
                    )
                ),
                received_at=received,
                provider="twf-fixture",
            )
            for instrument in instruments
        )

    async def get_ohlcv(
        self,
        instrument: InstrumentIdentity,
        interval: str,
        *,
        as_of: datetime,
        count: int,
    ) -> MarketSeries:
        del as_of
        for item in self.series:
            if item.instrument == instrument and item.interval == interval:
                return item.model_copy(
                    update={"bars": item.bars[-count:], "requested_count": count}
                )
        raise MarketDataFailure(MarketDataErrorCode.DATA_UNAVAILABLE)

    async def read(
        self, context: OperationContext, instrument: InstrumentIdentity, interval: str
    ) -> MarketSeries:
        try:
            return await self.get_ohlcv(instrument, interval, as_of=context.as_of, count=320)
        except MarketDataFailure:
            raise DataUnavailable(DataReason.SERIES_UNAVAILABLE) from None
