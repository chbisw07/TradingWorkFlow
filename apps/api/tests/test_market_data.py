"""Provider-neutral market-data contract and Dhan normalization regressions."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import time
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from twf.discovery.domain import InstrumentIdentity
from twf.discovery.market_data import (
    DhanMarketDataProvider,
    DhanMarketDataSettings,
    MarketDataErrorCode,
    MarketDataFailure,
)

MASTER_FIELDS = (
    "SEM_EXM_EXCH_ID",
    "SEM_SEGMENT",
    "SEM_SMST_SECURITY_ID",
    "SEM_INSTRUMENT_NAME",
    "SEM_TRADING_SYMBOL",
    "SEM_CUSTOM_SYMBOL",
    "SEM_EXCH_INSTRUMENT_TYPE",
    "SEM_SERIES",
    "SM_SYMBOL_NAME",
)


def settings(**changes: Any) -> DhanMarketDataSettings:
    values: dict[str, Any] = {
        "enabled": True,
        "client_id": SecretStr("1000000000"),
        "access_token": SecretStr("test-access-token"),
    }
    values.update(changes)
    return DhanMarketDataSettings(**values)


def master(*rows: tuple[str, ...]) -> bytes:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(MASTER_FIELDS)
    writer.writerows(rows)
    return stream.getvalue().encode()


RELIANCE = (
    "NSE",
    "E",
    "2885",
    "EQUITY",
    "RELIANCE",
    "RELIANCE",
    "ES",
    "EQ",
    "RELIANCE INDUSTRIES LTD",
)
NIFTY = (
    "NSE",
    "I",
    "13",
    "INDEX",
    "NIFTY",
    "NIFTY 50",
    "INDEX",
    "X",
    "NIFTY 50",
)


def resolve(
    provider: DhanMarketDataProvider,
    symbols: tuple[str, ...] = ("RELIANCE",),
) -> tuple[InstrumentIdentity, ...]:
    return asyncio.run(provider.resolve_instruments(symbols))


def test_health_requires_paired_enabled_credentials() -> None:
    provider = DhanMarketDataProvider(DhanMarketDataSettings())
    health = asyncio.run(provider.health())
    assert health.state == "AUTH_REQUIRED"
    assert health.provider == "dhan"
    with pytest.raises(ValueError):
        DhanMarketDataSettings(enabled=True, client_id=SecretStr("only-one"))


def test_dhan_master_resolution_preserves_native_identity_and_caches() -> None:
    calls = 0

    def transport(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.host == "images.dhan.co"
        return httpx.Response(200, content=master(RELIANCE, NIFTY))

    provider = DhanMarketDataProvider(settings(), transport=httpx.MockTransport(transport))
    equity, index = resolve(provider, ("RELIANCE", "NIFTY"))
    assert equity.native.namespace == "dhan"
    assert equity.native.native_id == "NSE_EQ:2885"
    assert equity.provider_symbol == "RELIANCE"
    assert equity.instrument_type == "EQUITY"
    assert equity.exchange == "NSE" and equity.segment == "EQ"
    assert index.native.native_id == "IDX_I:13"
    assert index.instrument_type == "INDEX" and index.segment == "INDEX"
    assert resolve(provider)[0] == equity
    assert calls == 1


def test_dhan_resolution_missing_and_ambiguous_are_typed() -> None:
    duplicate = (*RELIANCE[:2], "9999", *RELIANCE[3:])
    provider = DhanMarketDataProvider(
        settings(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=master(RELIANCE, duplicate))
        ),
    )
    with pytest.raises(MarketDataFailure) as ambiguous:
        resolve(provider)
    assert ambiguous.value.code == MarketDataErrorCode.AMBIGUOUS_INSTRUMENT

    missing_provider = DhanMarketDataProvider(
        settings(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=master(NIFTY))),
    )
    with pytest.raises(MarketDataFailure) as missing:
        resolve(missing_provider)
    assert missing.value.code == MarketDataErrorCode.INSTRUMENT_NOT_FOUND


def provider_with_identity(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[DhanMarketDataProvider, InstrumentIdentity]:
    def transport(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=master(RELIANCE))
        return handler(request)

    provider = DhanMarketDataProvider(settings(), transport=httpx.MockTransport(transport))
    return provider, resolve(provider)[0]


def test_quote_batch_request_and_normalization() -> None:
    captured: dict[str, Any] = {}

    def quote(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "NSE_EQ": {
                        "2885": {
                            "last_price": 2920.5,
                            "ohlc": {"open": 2900, "high": 2930, "low": 2890, "close": 2895},
                            "volume": 123456,
                            "oi": 0,
                        }
                    }
                },
            },
        )

    provider, instrument = provider_with_identity(quote)
    result = asyncio.run(provider.get_quotes((instrument,)))
    assert captured["path"] == "/v2/marketfeed/quote"
    assert captured["body"] == {"NSE_EQ": [2885]}
    assert captured["headers"]["client-id"] == "1000000000"
    assert captured["headers"]["access-token"] == "test-access-token"
    value = result[0]
    assert str(value.last_price) == "2920.5"
    assert str(value.previous_close) == "2895"
    assert str(value.volume) == "123456"
    assert value.provider_source_time is None
    assert value.provider == "dhan"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, MarketDataErrorCode.AUTH_REQUIRED),
        (429, MarketDataErrorCode.RATE_LIMITED),
        (503, MarketDataErrorCode.PROVIDER_ERROR),
    ],
)
def test_dhan_http_failures_are_typed(status: int, code: MarketDataErrorCode) -> None:
    provider, instrument = provider_with_identity(lambda _: httpx.Response(status))
    with pytest.raises(MarketDataFailure) as caught:
        asyncio.run(provider.get_quotes((instrument,)))
    assert caught.value.code == code


def test_quote_partial_response_is_typed() -> None:
    provider, instrument = provider_with_identity(
        lambda _: httpx.Response(200, json={"status": "success", "data": {"NSE_EQ": {}}})
    )
    with pytest.raises(MarketDataFailure) as caught:
        asyncio.run(provider.get_quotes((instrument,)))
    assert caught.value.code == MarketDataErrorCode.PARTIAL_RESPONSE


@pytest.mark.parametrize(
    ("interval", "path", "wire_interval"),
    [("1d", "/v2/charts/historical", None), ("15m", "/v2/charts/intraday", "15")],
)
def test_ohlcv_interval_mapping_ordering_and_latest_bar_exclusion(
    interval: str, path: str, wire_interval: str | None
) -> None:
    captured: dict[str, Any] = {}
    timestamps = [
        datetime(2026, 10, 2, tzinfo=UTC).timestamp(),
        datetime(2026, 9, 30, tzinfo=UTC).timestamp(),
        datetime(2026, 10, 1, tzinfo=UTC).timestamp(),
    ]

    def ohlcv(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "timestamp": timestamps,
                "open": [102, 100, 101],
                "high": [103, 101, 102],
                "low": [101, 99, 100],
                "close": [102.5, 100.5, 101.5],
                "volume": [1200, 1000, 1100],
                "open_interest": [12, 10, 11],
            },
        )

    provider, instrument = provider_with_identity(ohlcv)
    as_of = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    series = asyncio.run(provider.get_ohlcv(instrument, interval, as_of=as_of, count=3))
    assert captured["path"] == path
    assert captured["body"].get("interval") == wire_interval
    assert captured["body"]["securityId"] == "2885"
    assert captured["body"]["exchangeSegment"] == "NSE_EQ"
    assert [bar.timestamp for bar in series.bars] == sorted(bar.timestamp for bar in series.bars)
    if interval == "1d":
        assert len(series.bars) == 2
        assert series.live_bar_excluded is True
        assert series.completeness == "PARTIAL"
    else:
        assert len(series.bars) == 3
    assert all(bar.finality == "COMPLETED" for bar in series.bars)
    assert series.provenance.producer.provider == "dhan"
    assert series.requested_count == 3


def test_daily_warmup_range_is_bounded_to_requested_count() -> None:
    captured: dict[str, Any] = {}

    def ohlcv(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        timestamp = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
        return httpx.Response(
            200,
            json={
                "timestamp": [timestamp],
                "open": [100],
                "high": [102],
                "low": [99],
                "close": [101],
                "volume": [1000],
            },
        )

    provider, instrument = provider_with_identity(ohlcv)
    asyncio.run(
        provider.get_ohlcv(
            instrument,
            "1d",
            as_of=datetime(2026, 1, 2, 12, tzinfo=UTC),
            count=20,
        )
    )
    start = datetime.strptime(captured["fromDate"], "%Y-%m-%d")
    end = datetime.strptime(captured["toDate"], "%Y-%m-%d")
    assert 44 <= (end - start).days <= 46


def test_unsupported_interval_fails_without_http() -> None:
    called = False

    def transport(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    provider = DhanMarketDataProvider(settings(), transport=httpx.MockTransport(transport))
    # Construct identity through a separate valid provider to prove no request is issued here.
    valid, instrument = provider_with_identity(lambda _: httpx.Response(500))
    del valid
    with pytest.raises(MarketDataFailure) as caught:
        asyncio.run(
            provider.get_ohlcv(
                instrument,
                "2m",
                as_of=datetime.now(UTC),
                count=20,
            )
        )
    assert caught.value.code == MarketDataErrorCode.UNSUPPORTED_INTERVAL
    assert called is False


def test_streaming_body_obeys_total_deadline() -> None:
    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            for _ in range(20):
                await asyncio.sleep(0.03)
                yield b" "

    provider, instrument = provider_with_identity(lambda _: httpx.Response(200, stream=SlowBody()))
    provider.settings = settings(timeout_seconds=0.1)
    started = time.monotonic()
    with pytest.raises(MarketDataFailure) as caught:
        asyncio.run(provider.get_quotes((instrument,)))
    assert caught.value.code == MarketDataErrorCode.TIMEOUT
    assert time.monotonic() - started < 0.5


def test_malformed_quote_and_ohlcv_values_are_typed_invalid_responses() -> None:
    quote_provider, instrument = provider_with_identity(
        lambda _: httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"NSE_EQ": {"2885": {"last_price": -1, "volume": -4}}},
            },
        )
    )
    with pytest.raises(MarketDataFailure) as quote_failure:
        asyncio.run(quote_provider.get_quotes((instrument,)))
    assert quote_failure.value.code == MarketDataErrorCode.INVALID_RESPONSE

    timestamp = datetime(2026, 10, 1, tzinfo=UTC).timestamp()
    ohlcv_provider, instrument = provider_with_identity(
        lambda _: httpx.Response(
            200,
            json={
                "timestamp": [timestamp],
                "open": [100],
                "high": [99],
                "low": [98],
                "close": [101],
                "volume": [-1],
            },
        )
    )
    with pytest.raises(MarketDataFailure) as ohlcv_failure:
        asyncio.run(
            ohlcv_provider.get_ohlcv(
                instrument,
                "1d",
                as_of=datetime(2026, 10, 2, 12, tzinfo=UTC),
                count=1,
            )
        )
    assert ohlcv_failure.value.code == MarketDataErrorCode.INVALID_RESPONSE
