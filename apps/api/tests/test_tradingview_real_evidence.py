"""Real evidence normalization, bounded calls, and provider timestamp regressions."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from twf.discovery.product_service import identity
from twf.discovery.tradingview.config import TradingViewSettings
from twf.discovery.tradingview.evidence import (
    GET_OHLCV_TOOL,
    EvidenceOutcome,
    TradingViewEvidenceGateway,
    interval_for,
    provider_bars,
    quote_rows,
)
from twf.discovery.tradingview.provider import GET_BATCH_TOOL
from twf.integrations.contracts import Health, RequestContext
from twf.integrations.mcp.contracts import Code, Context, Failure, State


def context() -> Context:
    return Context(
        owner_id=uuid4(),
        session_hash="a" * 64,
        correlation=RequestContext(request_id="real-evidence-test"),
    )


def test_symbol_keyed_exact_shape_and_missing_lineage() -> None:
    received = datetime.now(UTC)
    rows, missing = quote_rows(
        {
            "success": True,
            "NSE:RELIANCE": {"close": 2875.5, "volume": 12345},
            "missing": ["NSE:TCS"],
        },
        ("NSE:RELIANCE", "NSE:TCS"),
        2,
        received,
    )
    assert tuple(rows) == ("NSE:RELIANCE",)
    assert rows["NSE:RELIANCE"].chunk_index == 2
    assert missing == ("NSE:TCS",)


def test_ohlcv_source_timestamp_and_finality_absence_are_preserved() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = provider_bars(
        {
            "success": True,
            "bars": [
                {
                    "t": int((start + timedelta(days=index)).timestamp()),
                    "o": 100 + index,
                    "h": 102 + index,
                    "l": 99 + index,
                    "c": 101 + index,
                    "v": 1000 + index,
                }
                for index in range(3)
            ],
        }
    )
    assert bars[0].source_time == start
    assert not hasattr(bars[0], "final")
    assert interval_for("intraday") == ("15m", "15m", 260)
    assert interval_for("15d") == ("1D", "1d", 320)


class FakeManager:
    def __init__(self, *, fail_second_chunk: bool = False) -> None:
        self.identity = uuid4()
        self.fail_second_chunk = fail_second_chunk
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.batch_calls = 0

    def connections(self, who: Context, provider_id: str) -> list[Any]:
        assert provider_id == "tradingview"
        return [
            SimpleNamespace(
                id=self.identity,
                enabled=True,
                generation=7,
                state=State.CONNECTED,
                health=Health.AVAILABLE,
            )
        ]

    def status(self, who: Context, identity_value: Any) -> Any:
        assert identity_value == self.identity
        return SimpleNamespace(last_success_at=datetime.now(UTC))

    async def tools(
        self,
        who: Context,
        identity_value: Any,
        generation: int,
        *,
        policy: Any,
        name: str,
        arguments: dict[str, Any],
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        assert identity_value == self.identity and generation == 7
        self.calls.append((name, arguments))
        if name == GET_BATCH_TOOL:
            self.batch_calls += 1
            if self.fail_second_chunk and self.batch_calls == 2:
                raise Failure(Code.UNAVAILABLE)
            data = {
                symbol: {"close": 100 + index, "volume": 1000 + index}
                for index, symbol in enumerate(arguments["symbols"])
            }
            result = {"success": True, "data": data, "missing": []}
        else:
            assert name == GET_OHLCV_TOOL
            start = datetime(2025, 1, 1, tzinfo=UTC)
            result = {
                "success": True,
                "bars": [
                    {
                        "t": int((start + timedelta(days=index)).timestamp()),
                        "o": 100 + index,
                        "h": 102 + index,
                        "l": 99 + index,
                        "c": 101 + index,
                        "v": 1000 + index,
                    }
                    for index in range(220)
                ],
            }
        return (), {"structuredContent": result, "isError": False}


def test_gateway_chunks_exact_matches_and_never_calls_broad_screener() -> None:
    async def run() -> None:
        manager = FakeManager()
        gateway = TradingViewEvidenceGateway(
            cast(Any, manager),
            TradingViewSettings(enabled=True, response_contract_verified=True),
            context(),
        )
        instruments = tuple(identity(f"SYM{index:03d}") for index in range(51))
        result = await gateway.enrich(instruments, "5d")
        batches = [arguments for name, arguments in manager.calls if name == GET_BATCH_TOOL]
        assert [len(item["symbols"]) for item in batches] == [50, 1]
        assert result.chunk_count == 2
        assert len(result.returned_symbols) == 51
        assert all(item.outcome == EvidenceOutcome.AVAILABLE for item in result.symbols)
        assert not any("screener" in name for name, _ in manager.calls)
        assert all(
            set(arguments) == {"symbol", "interval", "count", "summary"}
            for name, arguments in manager.calls
            if name == GET_OHLCV_TOOL
        )

    asyncio.run(run())


def test_partial_batch_failure_is_typed_and_has_no_individual_fallback_fanout() -> None:
    async def run() -> None:
        manager = FakeManager(fail_second_chunk=True)
        gateway = TradingViewEvidenceGateway(
            cast(Any, manager),
            TradingViewSettings(enabled=True, response_contract_verified=True),
            context(),
        )
        instruments = tuple(identity(f"SYM{index:03d}") for index in range(51))
        result = await gateway.enrich(instruments, "5d")
        assert result.chunk_count == 2
        assert len(result.returned_symbols) == 50
        assert result.missing_symbols == ("NSE:SYM050",)
        assert result.symbols[-1].outcome == EvidenceOutcome.UNAVAILABLE
        assert sum(name == GET_BATCH_TOOL for name, _ in manager.calls) == 2
        assert not any(name == "mcp-tv-get-symbol-data" for name, _ in manager.calls)

    asyncio.run(run())
