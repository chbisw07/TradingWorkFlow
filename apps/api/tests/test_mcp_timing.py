"""Deterministic SQLite commit/deadline ordering regressions for MCP permits."""

import asyncio
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from test_mcp_finalization import Fixture, api_key
from test_mcp_remediation import fixture as fixture

from twf.infrastructure.mcp import MCPOperation
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import Code, Failure
from twf.integrations.mcp.lifecycle import operation as active_operation


@pytest.mark.parametrize("boundary", ["before_commit", "after_commit"])
def test_timeout_commit_ordering(fixture: Fixture, boundary: str) -> None:
    manager, who, _server, _engine = fixture
    api_key(manager, 3)

    async def run() -> None:
        row = await manager.create(who, "fixture", boundary)
        row = await manager.connect(who, row.id, 0, SecretStr("synthetic-key"))
        await manager.operations.wait_receipts()
        reached = asyncio.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()
        original = manager.transaction
        hit = False
        timeline: list[tuple[str, float]] = []

        def fault(fn: Callable[[Session], Any]) -> Any:
            nonlocal hit
            if fn.__name__ != "settle" or hit:
                return original(fn)
            hit = True
            if boundary == "before_commit":

                def wrapped(db: Session) -> Any:
                    scope = active_operation.get()
                    assert scope is not None

                    def expire_before_commit(_db: Session) -> None:
                        done = threading.Event()

                        def expire() -> None:
                            timeline.append(("expired", time.monotonic()))
                            scope.expire()
                            done.set()

                        loop.call_soon_threadsafe(expire)
                        assert done.wait(2)

                    event.listen(db, "before_commit", expire_before_commit, once=True)
                    return fn(db)

                result = original(wrapped)
            else:
                result = original(fn)
            timeline.append(("committed", time.monotonic()))
            loop.call_soon_threadsafe(reached.set)
            assert release.wait(5)
            return result

        manager.transaction = fault  # type: ignore[method-assign, assignment]
        task = asyncio.create_task(manager.tools(who, row.id, row.generation))
        try:
            await asyncio.wait_for(reached.wait(), 3)
            if boundary == "after_commit":
                scope = next(scope for scope in manager.operations.tasks if scope.is_tool_operation)
                timeline.append(("expired", time.monotonic()))
                scope.expire()
            with pytest.raises(Failure) as failed:
                await task
            assert failed.value.code == Code.TIMEOUT
            peer = ConnectionManager(
                manager.factory,
                manager.settings,
                tuple(manager.providers.values()),
                http=manager.http,
            )
            status = peer.status(who, row.id)
            with manager.factory() as db:
                permit = db.scalar(select(MCPOperation).where(MCPOperation.connection_id == row.id))
                assert permit is not None
                state = (
                    permit.state,
                    permit.outcome,
                    permit.provider_outcome,
                    permit.reconciliation_required,
                    permit.cleanup_state,
                )
            timeline.append(("status", time.monotonic()))
            if boundary == "before_commit":
                assert state == ("COMPLETE", "TIMEOUT", "SUCCESS", False, "COMPLETE")
                assert timeline[0][0] == "expired" and timeline[1][0] == "committed"
                assert not status.recovery_required
            else:
                assert state == ("COMPLETE", "SUCCESS", "SUCCESS", True, "COMPLETE")
                assert timeline[0][0] == "committed" and timeline[1][0] == "expired"
                assert status.recovery_required
        finally:
            release.set()
        assert await manager.operations.drain(2)

    asyncio.run(run())
