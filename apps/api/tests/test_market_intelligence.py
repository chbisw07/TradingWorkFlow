"""Provider-neutral market-intelligence and bounded TapTide adapter regressions."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

from twf.discovery.market_intelligence import (
    TAPTIDE_TOOLS,
    IntelligenceKind,
    IntelligenceState,
    MarketIntelligenceProvider,
    TapTideMarketIntelligence,
    TapTideSnapshotCache,
)
from twf.discovery.product_service import identity
from twf.integrations.contracts import Health
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import Code, Context, Failure, State

CONNECTION_ID = UUID("11111111-1111-1111-1111-111111111111")
WHO = Context(
    owner_id=UUID("22222222-2222-2222-2222-222222222222"),
    session_hash="a" * 64,
)


class FakeManager:
    def __init__(
        self,
        tools: tuple[str, ...],
        payloads: dict[str, dict[str, Any]] | None = None,
        failures: dict[str, Code] | None = None,
    ) -> None:
        self.discovered = tools
        self.payloads = payloads or {}
        self.failures = failures or {}
        self.calls: list[tuple[str, dict[str, Any], frozenset[str]]] = []

    def connections(self, who: Context, provider_id: str) -> tuple[Any, ...]:
        assert who == WHO and provider_id == "tapetide"
        return (
            SimpleNamespace(
                id=CONNECTION_ID,
                enabled=True,
                state=State.CONNECTED,
                health=Health.AVAILABLE,
                generation=4,
                tools=tuple(SimpleNamespace(name=name) for name in self.discovered),
            ),
        )

    def status(self, who: Context, identity_: UUID) -> Any:
        assert who == WHO and identity_ == CONNECTION_ID
        return SimpleNamespace(last_success_at=datetime(2026, 10, 2, 10, tzinfo=UTC))

    async def tools(
        self,
        who: Context,
        connection_id: UUID,
        generation: int,
        *,
        policy: Any,
        name: str,
        arguments: dict[str, Any],
    ) -> tuple[Any, dict[str, Any]]:
        assert who == WHO and connection_id == CONNECTION_ID and generation == 4
        self.calls.append((name, arguments, policy.allowed))
        if name in self.failures:
            raise Failure(self.failures[name])
        return SimpleNamespace(), {"structuredContent": self.payloads[name]}


def adapter(manager: FakeManager) -> TapTideMarketIntelligence:
    value: MarketIntelligenceProvider = TapTideMarketIntelligence(
        cast(ConnectionManager, manager), WHO
    )
    return cast(TapTideMarketIntelligence, value)


def test_tapetide_normalizes_bounded_claims_with_provenance() -> None:
    now = datetime.now(UTC).isoformat()
    payloads: dict[str, dict[str, Any]] = {
        "get_market_pulse": {
            "as_of": now,
            "fii_net_flow": -1250.5,
            "dii_net_flow": 920.2,
            "india_vix": 14.2,
            "provider_private": "MUST_NOT_ESCAPE",
        },
        "get_india_vix": {"timestamp": now, "latest": 14.2, "change_pct": -1.4},
        "get_fii_dii_detail": {
            "date": now,
            "rows": [{"fii_net": -1250.5, "dii_net": 920.2}],
        },
        "get_fpi_sectors": {
            "as_of": now,
            "sectors": [{"sector": "Financial Services", "net_flow": 250.0}],
        },
        "get_index_performance": {
            "as_of": now,
            "indices": [{"index_name": "NIFTY IT", "return_pct": 2.1}],
        },
        "get_market_news": {
            "as_of": now,
            "articles": [{"headline": "Markets steady", "sentiment": "neutral"}],
        },
        "get_stock_events": {
            "as_of": now,
            "events": [{"symbol": "RELIANCE", "type": "dividend", "date": now}],
        },
    }
    manager = FakeManager(tuple(payloads), payloads)
    result = asyncio.run(adapter(manager).observe((identity("RELIANCE"),)))
    assert result.state == IntelligenceState.AVAILABLE
    assert {claim.kind for claim in result.claims} == set(IntelligenceKind)
    assert all(claim.provider == "tapetide" for claim in result.claims)
    assert all(claim.source_reference.startswith("tapetide-mcp:") for claim in result.claims)
    assert all(
        claim.source_time is not None and claim.freshness == "CURRENT" for claim in result.claims
    )
    assert result.claims[0].values == {
        "record_count": 1,
        "fii_net_flow": -1250.5,
        "dii_net_flow": 920.2,
        "india_vix": 14.2,
    }
    serialized = result.model_dump_json()
    assert "provider_private" not in serialized and "MUST_NOT_ESCAPE" not in serialized
    assert len(manager.calls) == 7
    assert all(allowed == TAPTIDE_TOOLS for _, _, allowed in manager.calls)
    call_arguments = {name: arguments for name, arguments, _ in manager.calls}
    assert call_arguments["get_index_performance"] == {
        "category": "sectoral",
        "granularity": "month",
        "periods": 1,
        "limit": 10,
    }
    assert call_arguments["get_market_news"] == {"limit": 10}
    assert call_arguments["get_stock_events"] == {
        "symbol": "RELIANCE",
        "type": "corporate_actions",
        "limit": 5,
    }


def test_tapetide_all_stale_claims_produce_stale_state() -> None:
    manager = FakeManager(
        ("get_india_vix",),
        {
            "get_india_vix": {
                "date": (datetime.now(UTC) - timedelta(days=8)).isoformat(),
                "value": 13.5,
            }
        },
    )
    result = asyncio.run(adapter(manager).observe(()))
    assert result.state == IntelligenceState.STALE
    assert result.claims[0].freshness == "STALE"
    assert result.claims[0].values["level"] == 13.5


def test_tapetide_partial_rate_limit_retains_successful_claims() -> None:
    manager = FakeManager(
        ("get_market_pulse", "get_india_vix"),
        {"get_market_pulse": {"as_of": datetime.now(UTC).isoformat(), "india_vix": 14}},
        {"get_india_vix": Code.RATE_LIMITED},
    )
    result = asyncio.run(adapter(manager).observe(()))
    assert result.state == IntelligenceState.PARTIAL
    assert len(result.claims) == 1
    assert result.failures == ("get_india_vix:rate_limited",)


def test_tapetide_auth_and_provider_failures_are_typed() -> None:
    disconnected = FakeManager(())
    disconnected.connections = lambda *_: ()  # type: ignore[method-assign]
    auth = asyncio.run(adapter(disconnected).observe(()))
    assert auth.state == IntelligenceState.AUTH_REQUIRED
    assert auth.claims == ()

    unavailable = FakeManager(
        ("get_market_pulse",),
        failures={"get_market_pulse": Code.UNAVAILABLE},
    )
    failed = asyncio.run(adapter(unavailable).observe(()))
    assert failed.state == IntelligenceState.UNAVAILABLE
    assert failed.failures == ("get_market_pulse:service_unavailable",)


def test_tapetide_invalid_response_is_provider_error_without_raw_payload() -> None:
    manager = FakeManager(("get_market_pulse",), {"get_market_pulse": {}})

    async def broken(*_: Any, **__: Any) -> tuple[Any, dict[str, Any]]:
        return SimpleNamespace(), {"content": [{"type": "image", "data": "SECRET"}]}

    manager.tools = broken  # type: ignore[method-assign]
    result = asyncio.run(adapter(manager).observe(()))
    assert result.state == IntelligenceState.PROVIDER_ERROR
    assert result.claims == ()
    assert "SECRET" not in result.model_dump_json()


def test_tapetide_readiness_is_generic_connection_health() -> None:
    provider = adapter(FakeManager(tuple(TAPTIDE_TOOLS)))
    ready, state, success = provider.readiness()
    assert ready is True
    assert state == IntelligenceState.AVAILABLE
    assert success == datetime(2026, 10, 2, 10, tzinfo=UTC)


def test_tapetide_readiness_requires_the_bounded_capability_set() -> None:
    provider = adapter(FakeManager(("get_market_pulse",)))
    ready, state, success = provider.readiness()
    assert ready is False
    assert state == IntelligenceState.PARTIAL
    assert success is None


def test_tapetide_unexpected_runtime_failure_is_sanitized_and_degradable() -> None:
    manager = FakeManager(("get_market_pulse",))

    async def crashing(*_: Any, **__: Any) -> tuple[Any, dict[str, Any]]:
        raise RuntimeError("raw provider diagnostic MUST_NOT_ESCAPE")

    manager.tools = crashing  # type: ignore[method-assign]
    result = asyncio.run(adapter(manager).observe(()))
    assert result.state == IntelligenceState.PROVIDER_ERROR
    assert result.claims == ()
    assert result.failures == ("get_market_pulse:provider-error",)
    assert "MUST_NOT_ESCAPE" not in result.model_dump_json()


def test_tapetide_success_cache_is_owner_and_generation_scoped() -> None:
    now = datetime.now(UTC).isoformat()
    manager = FakeManager(
        ("get_market_pulse",),
        {"get_market_pulse": {"as_of": now, "india_vix": 14.0}},
    )
    provider = TapTideMarketIntelligence(
        cast(ConnectionManager, manager), WHO, TapTideSnapshotCache()
    )
    first = asyncio.run(provider.observe(()))
    second = asyncio.run(provider.observe(()))
    assert first == second
    assert first.state == IntelligenceState.AVAILABLE
    assert len(manager.calls) == 1
