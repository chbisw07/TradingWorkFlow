"""Health is an observation, never a substitute for durable admission authority."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2
import pytest
from mcp_support import public_ip, setup
from sqlalchemy import select

from twf.discovery.product_service import identity
from twf.infrastructure.mcp import MCPConnection, MCPOperation
from twf.integrations.contracts import Health
from twf.integrations.mcp.client import SDKClient
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import Code, Failure, State, Tool, ToolPolicy
from twf.integrations.mcp.http import HTTPFactory
from twf.watchlists.reference import WatchlistReferenceCache


def test_tool_failure_isolated_and_normal_call_recovers(tmp_path: Path) -> None:
    m, who, server, engine = setup(tmp_path / "health.db")
    failing = True

    async def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            msg = json.loads(await request.aread())
            if msg["method"] == "tools/call" and failing:
                return httpx2.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": msg["id"],
                        "result": {
                            "isError": True,
                            "content": [{"type": "text", "text": "private"}],
                        },
                    },
                    headers={"mcp-session-id": "test"},
                )
        return await server.handle(request)

    m.client = SDKClient(HTTPFactory(lambda: httpx2.MockTransport(handler), public_ip))

    async def run() -> None:
        nonlocal failing
        row = await m.create(who, "fixture", "health")
        row = await m.connect(who, row.id, 0)
        row = await m.test_connection(who, row.id, row.generation)
        assert row.health == Health.AVAILABLE and row.operations_pending == 0
        for _ in range(5):
            with pytest.raises(Failure) as exc:
                await m.tools(
                    who,
                    row.id,
                    row.generation,
                    policy=ToolPolicy(allowed=frozenset({"read_demo"})),
                    name="read_demo",
                    arguments={"value": 1},
                )
            assert exc.value.code == Code.TOOL_FAILED and "private" not in str(exc.value)
            state = m.status(who, row.id)
            assert state.state == State.CONNECTED and state.health == Health.DEGRADED
            assert state.operations_pending == state.unresolved_cleanup_count == 0
            assert state.consecutive_failure_count == 0
        failing = False
        await m.tools(
            who,
            row.id,
            row.generation,
            policy=ToolPolicy(allowed=frozenset({"read_demo"})),
            name="read_demo",
            arguments={"value": 1},
        )
        await m.operations.wait_receipts()
        state = m.status(who, row.id)
        assert state.health == Health.AVAILABLE and state.last_failure_kind == "TOOL_FAILED"
        assert state.last_failure_at and state.health_since and state.last_success_at
        with m.factory() as db:
            permits = list(db.scalars(select(MCPOperation)))
            assert all(p.state == "COMPLETE" and not p.reconciliation_required for p in permits)
            assert sum(p.tool_name == "read_demo" for p in permits) == 6

    try:
        asyncio.run(run())
    finally:
        engine.dispose()


def test_reference_failure_cache_and_other_capability_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    m, who, _, engine = setup(tmp_path / "reference.db")
    m.providers["tapetide"] = m.providers["fixture"].model_copy(update={"provider_id": "tapetide"})
    tick = 0.0
    monkeypatch.setattr("twf.watchlists.reference.monotonic", lambda: tick)
    failure = False
    calls = 0

    class Client:
        async def execute(self, *args: Any) -> Any:
            nonlocal calls
            await args[2]()
            name = args[4]
            if name == "get_stock_quote":
                calls += 1
                if failure:
                    raise Failure(Code.TOOL_FAILED)
            tools = tuple(
                Tool(name=n, input_schema={"type": "object"})
                for n in ("get_stock_quote", "get_market_news")
            )
            return tools, {
                "structuredContent": {
                    "data": {
                        "found": True,
                        "symbol": "RELIANCE",
                        "market_cap": 100,
                        "pe_ttm": 20,
                        "high_52w": 200,
                        "low_52w": 100,
                    }
                }
            }

    m.client = Client()

    async def run() -> None:
        nonlocal failure, tick
        row = await m.create(who, "tapetide", "reference")
        row = await m.connect(who, row.id, 0)
        await m.test_connection(who, row.id, row.generation)
        cache = WatchlistReferenceCache()
        instrument = identity("RELIANCE").model_copy(update={"instrument_type": "EQUITY"})
        assert (await cache.read(m, who, instrument)).state == "AVAILABLE"
        failure, tick = True, 901
        missing = await cache.read(m, who, instrument)
        assert missing.state == "UNAVAILABLE" and missing.pe_ratio is None
        assert m.status(who, row.id).health == Health.DEGRADED
        await cache.read(m, who, instrument)
        assert calls == 2  # Failure cache prevents retry storms.
        await m.tools(
            who,
            row.id,
            row.generation,
            policy=ToolPolicy(allowed=frozenset({"get_market_news"})),
            name="get_market_news",
            arguments={"limit": 1},
        )
        await m.operations.wait_receipts()
        assert m.status(who, row.id).health == Health.AVAILABLE
        failure, tick = False, 962
        assert (await cache.read(m, who, instrument)).state == "AVAILABLE"
        assert calls == 3
        state = m.status(who, row.id)
        assert state.operations_pending == state.unresolved_cleanup_count == 0

    try:
        asyncio.run(run())
    finally:
        engine.dispose()


def test_transport_escalation_and_recovery_without_test_button(tmp_path: Path) -> None:
    m, who, server, engine = setup(tmp_path / "outage.db")

    async def run() -> None:
        row = await m.create(who, "fixture", "outage")
        row = await m.connect(who, row.id, 0)
        await m.test_connection(who, row.id, row.generation)
        server.status = 503
        for count, health in enumerate([Health.DEGRADED, Health.DEGRADED, Health.UNAVAILABLE], 1):
            with pytest.raises(Failure):
                await m.tools(who, row.id, row.generation)
            state = m.status(who, row.id)
            assert state.health == health and state.consecutive_failure_count == count
            assert state.operations_pending == state.unresolved_cleanup_count == 0
        server.status = 200
        await m.tools(who, row.id, row.generation)
        await m.operations.wait_receipts()
        assert m.status(who, row.id).health == Health.AVAILABLE
        assert m.status(who, row.id).consecutive_failure_count == 0

    try:
        asyncio.run(run())
    finally:
        engine.dispose()


def test_expired_restart_work_is_cleanup_not_active_and_stays_fenced(tmp_path: Path) -> None:
    m, who, server, engine = setup(tmp_path / "restart.db")

    async def run() -> None:
        row = await m.create(who, "fixture", "restart")
        row = await m.connect(who, row.id, 0)
        await m.test_connection(who, row.id, row.generation)
        with m.factory() as db:
            db.add(
                MCPOperation(
                    id=uuid4(),
                    connection_id=row.id,
                    owner_id=who.owner_id,
                    generation=row.generation,
                    session_hash=who.session_hash,
                    worker_id=uuid4(),
                    state="RUNNING",
                    cleanup_state="RUNNING",
                    created_at=datetime.now(UTC) - timedelta(minutes=1),
                    deadline_at=datetime.now(UTC) - timedelta(seconds=1),
                    tool_name="get_stock_quote",
                )
            )
            db.commit()
        peer = ConnectionManager(m.factory, m.settings, tuple(m.providers.values()), http=m.http)
        state = peer.status(who, row.id)
        assert state.operations_pending == 0 and state.unresolved_cleanup_count == 1
        assert state.health == Health.AVAILABLE and state.recovery_required
        before = len(server.calls)
        with pytest.raises(Failure):
            await peer.test_connection(who, row.id, row.generation)
        assert len(server.calls) == before
        state = await peer.recover(who, row.id)
        assert state.operations_pending == 0 and state.unresolved_cleanup_count == 1
        assert state.health == Health.AVAILABLE
        with m.factory() as db:
            stored = db.get(MCPConnection, row.id)
            assert stored
            old = db.scalar(select(MCPOperation).where(MCPOperation.state == "UNRESOLVED"))
            assert old
            stored.generation += 1
            m.operation_health(stored, old, Code.UNAVAILABLE.value)
            assert stored.health == Health.AVAILABLE and stored.consecutive_failure_count == 0

    try:
        asyncio.run(run())
    finally:
        engine.dispose()
