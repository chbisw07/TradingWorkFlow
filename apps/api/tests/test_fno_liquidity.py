"""Governed F&O liquidity ranking; no live provider calls in these tests."""

import asyncio
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from twf.discovery.market_data import MarketDataErrorCode, MarketDataFailure
from twf.infrastructure.database import Base
from twf.watchlists.fno_liquidity import (
    FNO_LIQUIDITY_METHOD_VERSION,
    WEIGHTS,
    FnoLiquidityCache,
    _eligible_futures,
    rank_observations,
)
from twf.watchlists.system import SystemUniverseCatalog

IST = ZoneInfo("Asia/Kolkata")


def master_row(symbol: str, asset: str, identifier: int) -> dict[str, str]:
    return {
        "SEM_EXM_EXCH_ID": "NSE",
        "SEM_SEGMENT": "E" if asset == "EQUITY" else "D",
        "SEM_SMST_SECURITY_ID": str(identifier),
        "SEM_INSTRUMENT_NAME": asset,
        "SEM_TRADING_SYMBOL": symbol if asset == "EQUITY" else f"{symbol}26OCT{asset}",
        "SEM_CUSTOM_SYMBOL": symbol,
        "SEM_EXCH_INSTRUMENT_TYPE": "",
        "SEM_SERIES": "EQ" if asset == "EQUITY" else "",
        "SM_SYMBOL_NAME": symbol,
        "SEM_EXPIRY_DATE": "2099-12-30",
        "SEM_STRIKE_PRICE": "100",
        "SEM_OPTION_TYPE": "CE",
    }


def test_eligibility_requires_equity_future_and_active_option() -> None:
    rows = (
        master_row("AAA", "EQUITY", 1),
        master_row("AAA", "FUTSTK", 2),
        master_row("AAA", "OPTSTK", 3),
        master_row("CASH", "EQUITY", 4),
        master_row("NOOPT", "EQUITY", 5),
        master_row("NOOPT", "FUTSTK", 6),
    )
    assert tuple(_eligible_futures(rows, date(2026, 10, 12))) == ("AAA",)


def test_deterministic_rank_nesting_and_bounded_sizes() -> None:
    assert sum(WEIGHTS.values()) == 1
    assert FNO_LIQUIDITY_METHOD_VERSION == "v1"
    observations = [
        {
            "date": f"2026-10-{day:02d}",
            "metrics": {
                f"S{index:03d}": {
                    "volume": str(index + 1),
                    "open_interest": str(index + 1),
                }
                for index in range(205)
            },
        }
        for day in (8, 9, 12)
    ]
    ranked = rank_observations(observations, {f"S{index:03d}" for index in range(205)})
    assert len(ranked) == 205
    assert ranked == rank_observations(observations, {f"S{index:03d}" for index in range(205)})
    assert ranked[0]["symbol"] == "S204" and ranked[-1]["symbol"] == "S000"
    fifty = {row["symbol"] for row in ranked[:50]}
    hundred = {row["symbol"] for row in ranked[:100]}
    two_hundred = {row["symbol"] for row in ranked[:200]}
    assert len(fifty) == 50 and len(hundred) == 100 and len(two_hundred) == 200
    assert fifty <= hundred <= two_hundred
    assert rank_observations(observations[:2], {"S204"}) == []
    assert len(rank_observations(observations, {"S204", "S203"})) == 2


def test_daily_cache_reuse_refresh_and_last_valid_fallback() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    cache = FnoLiquidityCache(factory)
    rows = tuple(
        master_row(symbol, asset, index * 3 + offset)
        for index, symbol in enumerate(("AAA", "BBB"), 1)
        for offset, asset in enumerate(("EQUITY", "FUTSTK", "OPTSTK"), 1)
    )
    current = date(2026, 10, 8)
    calls = 0
    fail = False
    history_calls = 0

    class Provider:
        async def get_ohlcv(self, *args: object, **kwargs: object) -> None:
            nonlocal history_calls
            history_calls += 1
            raise AssertionError(
                "Historical bootstrap is unsupported without expiry-safe resolution"
            )

        async def _load_master(self) -> tuple[dict[str, str], ...]:
            return rows

        async def get_quotes(self, instruments: tuple[object, ...]) -> tuple[object, ...]:
            nonlocal calls
            calls += 1
            if fail:
                raise MarketDataFailure(MarketDataErrorCode.PROVIDER_ERROR)
            return tuple(
                SimpleNamespace(
                    provider="dhan",
                    provider_source_time=datetime(
                        current.year, current.month, current.day, 15, 35, tzinfo=IST
                    ),
                    volume=Decimal("100") if i == 0 else Decimal("50"),
                    open_interest=Decimal("1000") if i == 0 else Decimal("500"),
                )
                for i, _ in enumerate(instruments)
            )

    provider = Provider()

    def completed(_: datetime) -> date:
        return current

    cache.completed_date = completed  # type: ignore[assignment]

    async def run() -> None:
        nonlocal current, fail
        for day in (date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 12)):
            current = day
            await cache.refresh(provider)  # type: ignore[arg-type]
            await cache.refresh(provider)  # type: ignore[arg-type]
        assert calls == 3
        assert history_calls == 0
        stored = cache.load()
        assert len(stored["observations"]) == 3
        assert stored["earliest_session"] == "2026-10-08"
        assert stored["latest_session"] == "2026-10-12"
        assert stored["observation_count_used"] == 3
        assert stored["last_success_at"]
        assert stored["as_of_date"] == "2026-10-12"
        assert [row["symbol"] for row in stored["ranked"]] == ["AAA", "BBB"]
        catalog = SystemUniverseCatalog(liquidity=cache)
        for size in (50, 100, 200):
            definition, membership = await catalog.membership(f"FNO_LIQUIDITY_{size}")
            assert definition.expected_count == size
            assert membership.symbols == ("AAA", "BBB")
        current = date(2026, 10, 13)
        fail = True
        await cache.refresh(provider)  # type: ignore[arg-type]
        assert cache.load()["ranked"] == stored["ranked"]
        assert calls == 4
        assert history_calls == 0
        assert cache.load()["last_error_category"] == "PROVIDER_FAILURE"

    try:
        asyncio.run(run())
    finally:
        engine.dispose()


def test_readiness_distinguishes_history_credentials_provider_and_stale() -> None:
    now = datetime(2026, 10, 12, 16, tzinfo=IST)
    empty: dict[str, object] = {"observations": [], "ranked": []}
    assert (
        FnoLiquidityCache.readiness(empty, credential_available=False, now=now)["state"]
        == "CREDENTIAL_UNAVAILABLE"
    )
    assert (
        FnoLiquidityCache.readiness(empty, credential_available=True, now=now)["state"]
        == "INSUFFICIENT_HISTORY"
    )
    for count in (1, 2):
        payload = {
            "observations": [
                {"date": f"2026-10-{day:02d}", "metrics": {"AAA": {}}}
                for day in range(8, 8 + count)
            ],
            "ranked": [],
        }
        readiness = FnoLiquidityCache.readiness(payload, credential_available=True, now=now)
        assert readiness["state"] == "BUILDING_HISTORY"
        assert readiness["completed_sessions_collected"] == count
        assert readiness["minimum_sessions_required"] == 3
        assert readiness["lookback_sessions_target"] == 20
    patchy = {
        "observations": [
            {"date": f"2026-10-{day:02d}", "metrics": {f"S{day}": {}}} for day in (8, 9, 12)
        ],
        "ranked": [],
    }
    patchy_readiness = FnoLiquidityCache.readiness(patchy, credential_available=True, now=now)
    assert patchy_readiness["state"] == "BUILDING_HISTORY"
    assert patchy_readiness["completed_sessions_collected"] == 1
    failure = {**empty, "last_error_category": "PROVIDER_FAILURE"}
    assert (
        FnoLiquidityCache.readiness(failure, credential_available=True, now=now)["state"]
        == "PROVIDER_UNAVAILABLE"
    )
    ready = {
        "observations": [{"date": "2026-10-12", "metrics": {"AAA": {}}}],
        "ranked": [{"symbol": "AAA", "rank": 1}],
        "generated_at": now.isoformat(),
        "as_of_date": "2026-10-12",
    }
    assert (
        FnoLiquidityCache.readiness(ready, credential_available=True, now=now)["state"] == "READY"
    )
    tomorrow = datetime(2026, 10, 13, 16, tzinfo=IST)
    stale = FnoLiquidityCache.readiness(ready, credential_available=True, now=tomorrow)
    assert stale["state"] == "STALE" and stale["stale"]
    unavailable = FnoLiquidityCache.readiness(ready, credential_available=False, now=tomorrow)
    assert unavailable["state"] == "CREDENTIAL_UNAVAILABLE"
    assert unavailable["stale"]


def test_expired_contract_is_not_used_for_prospective_session() -> None:
    expired = {**master_row("AAA", "FUTSTK", 2), "SEM_EXPIRY_DATE": "2026-10-09"}
    rows = (
        master_row("AAA", "EQUITY", 1),
        expired,
        master_row("AAA", "FUTSTK", 3),
        master_row("AAA", "OPTSTK", 4),
    )
    chosen = _eligible_futures(rows, date(2026, 10, 12))["AAA"]
    assert chosen.native.native_id.endswith(":3")
