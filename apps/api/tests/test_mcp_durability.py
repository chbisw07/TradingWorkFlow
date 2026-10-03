"""Faults after real commit, durable intent, and restart without provider replay."""

import asyncio
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_mcp_finalization import Fixture, api_key
from test_mcp_remediation import fixture as fixture

from twf.infrastructure.mcp import MCPOperation
from twf.integrations.contracts import Health
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import Code, Failure, State


@pytest.mark.parametrize("iteration", range(3))
@pytest.mark.parametrize("phase", ["before_fence", "after_fence", "intent_failure"])
def test_auth_intent_blocks_recreated_worker(fixture: Fixture, phase: str, iteration: int) -> None:
    m, who, server, _ = fixture
    api_key(m)

    async def run() -> None:
        row = await m.create(who, "fixture", f"auth-intent-{iteration}")
        row = await m.connect(who, row.id, 0, SecretStr("synthetic-key"))
        tx = m.transaction
        hit = False

        def fault(fn: Callable[[Session], Any]) -> Any:
            nonlocal hit
            target = "invalidate" if phase == "intent_failure" else "save"
            if fn.__name__ == target and not hit:
                hit = True
                if phase == "after_fence":
                    tx(fn)
                raise Failure(Code.STORAGE)
            return tx(fn)

        m.transaction = fault  # type: ignore[method-assign, assignment]
        server.status = 401
        with pytest.raises(Failure):
            await m.tools(who, row.id, row.generation)
        assert hit
        peer = ConnectionManager(m.factory, m.settings, tuple(m.providers.values()), http=m.http)
        before = len(server.calls)
        with pytest.raises(Failure):
            await peer.tools(who, row.id, row.generation)
        assert len(server.calls) == before
        state = peer.status(who, row.id)
        assert state.recovery_required or state.state == State.REAUTH_REQUIRED
        result = await peer.recover(who, row.id)
        again = await peer.recover(who, row.id)
        assert result == again
        assert result.state == State.REAUTH_REQUIRED
        assert result.secret_ref is None and not result.enabled
        assert len(server.calls) == before  # Recovery is exclusively local DB work.

    asyncio.run(run())


@pytest.mark.parametrize("iteration", range(3))
def test_lost_commit_ack_reconciles_committed_success_without_replay(
    fixture: Fixture, iteration: int
) -> None:
    m, who, server, _ = fixture
    api_key(m)

    async def run() -> None:
        row = await m.create(who, "fixture", f"ambiguous-{iteration}")
        row = await m.connect(who, row.id, 0, SecretStr("synthetic-key"))
        tx = m.transaction
        hit = False

        def fault(fn: Callable[[Session], Any]) -> Any:
            nonlocal hit
            if fn.__name__ == "settle" and not hit:
                hit = True
                tx(fn)
                raise Failure(Code.STORAGE)
            if fn.__name__ == "unresolved":
                raise Failure(Code.STORAGE)
            return tx(fn)

        m.transaction = fault  # type: ignore[method-assign, assignment]
        with pytest.raises(Failure) as failed:
            await m.tools(who, row.id, row.generation)
        assert failed.value.code == Code.STORAGE
        peer = ConnectionManager(m.factory, m.settings, tuple(m.providers.values()), http=m.http)
        state = peer.status(who, row.id)
        assert state.recovery_required and state.operations_pending == 1
        before = len(server.calls)
        with pytest.raises(Failure):
            await peer.tools(who, row.id, row.generation)
        with m.factory() as db:
            p = db.scalar(select(MCPOperation).where(MCPOperation.connection_id == row.id))
            assert p and p.reconciliation_required and p.provider_outcome == "SUCCESS"
            p.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
        recovered = await peer.recover(who, row.id)
        assert not recovered.recovery_required and recovered.operations_pending == 0
        assert await peer.recover(who, row.id) == recovered
        with m.factory() as db:
            p = db.scalar(select(MCPOperation).where(MCPOperation.connection_id == row.id))
            assert p and p.state == "COMPLETE" and p.outcome == "SUCCESS"
            assert not p.reconciliation_required and p.provider_outcome == "SUCCESS"
        assert len(server.calls) == before

    asyncio.run(run())


@pytest.mark.parametrize("terminal", [Code.TIMEOUT, Code.CANCELLED])
@pytest.mark.parametrize("iteration", range(3))
def test_negative_after_commit_retains_marker_until_reconciled(
    fixture: Fixture, terminal: Code, iteration: int
) -> None:
    m, who, server, _ = fixture
    api_key(m, 0.4 if terminal == Code.TIMEOUT else 3)

    async def run() -> None:
        row = await m.create(who, "fixture", f"negative-{iteration}")
        row = await m.connect(who, row.id, 0, SecretStr("synthetic-key"))
        reached, release = asyncio.Event(), threading.Event()
        tx, loop = m.transaction, asyncio.get_running_loop()
        hit = False

        def fault(fn: Callable[[Session], Any]) -> Any:
            nonlocal hit
            result = tx(fn)
            if fn.__name__ == "settle" and not hit:
                hit = True
                loop.call_soon_threadsafe(reached.set)
                assert release.wait(5)
            return result

        m.transaction = fault  # type: ignore[method-assign, assignment]
        task = asyncio.create_task(m.tools(who, row.id, row.generation))
        try:
            await asyncio.wait_for(reached.wait(), 2)
            if terminal == Code.CANCELLED:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                with pytest.raises(Failure) as error:
                    await task
                assert error.value.code == Code.TIMEOUT
            peer = ConnectionManager(
                m.factory, m.settings, tuple(m.providers.values()), http=m.http
            )
            assert peer.status(who, row.id).recovery_required
            before = len(server.calls)
            with pytest.raises(Failure):
                await peer.tools(who, row.id, row.generation)
            assert len(server.calls) == before
        finally:
            release.set()
        assert await m.operations.drain(2)
        with m.factory() as db:
            p = db.scalar(select(MCPOperation).where(MCPOperation.connection_id == row.id))
            assert p and p.outcome == terminal and p.provider_outcome == "SUCCESS"
            assert not p.reconciliation_required

    asyncio.run(run())


def _lost_worker(
    settings: Any, who: Any, providers: Any, identity: Any, terminal: str, pipe: Any
) -> None:
    """Separate process, real commit, then die before acknowledgment reconciliation."""
    import os

    import httpx2
    from mcp_support import SyntheticServer, public_ip

    from twf.infrastructure.database import create_database_engine, create_session_factory
    from twf.integrations.mcp.http import HTTPFactory

    engine = create_database_engine(settings)
    server = SyntheticServer()
    if terminal == "AUTH_LOSS":
        server.status = 401
    m = ConnectionManager(
        create_session_factory(engine),
        settings,
        providers,
        http=HTTPFactory(lambda: httpx2.MockTransport(server.handle), public_ip),
    )

    async def run() -> None:
        reached = asyncio.Event()
        loop, tx = asyncio.get_running_loop(), m.transaction

        def held(fn: Callable[[Session], Any]) -> Any:
            if terminal == "AUTH_LOSS" and fn.__name__ == "save":
                pipe.send(("AUTH_LOSS", 0))
                os._exit(73)
            result = tx(fn)
            if fn.__name__ == "settle":
                loop.call_soon_threadsafe(reached.set)
                threading.Event().wait(30)
            return result

        m.transaction = held  # type: ignore[method-assign, assignment]
        row = m.status(who, identity)
        task = asyncio.create_task(m.tools(who, identity, row.generation))
        await asyncio.wait_for(reached.wait(), 3)
        if terminal == "CANCELLED":
            task.cancel()
        try:
            await task
            outcome = "SUCCESS"
        except Failure as error:
            outcome = error.code.value
        except asyncio.CancelledError:
            outcome = "CANCELLED"
        pipe.send((outcome, len(server.calls)))
        os._exit(73)

    asyncio.run(run())


@pytest.mark.parametrize("terminal", ["TIMEOUT", "CANCELLED", "AUTH_LOSS"])
def test_actual_process_loss_after_commit(fixture: Fixture, terminal: str) -> None:
    import multiprocessing

    m, who, server, _ = fixture
    api_key(m, 0.4 if terminal == "TIMEOUT" else 3)

    async def setup_row() -> Any:
        row = await m.create(who, "fixture", "child-loss")
        return await m.connect(who, row.id, 0, SecretStr("synthetic-key"))

    row = asyncio.run(setup_row())
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    child = context.Process(
        target=_lost_worker,
        args=(m.settings, who, tuple(m.providers.values()), row.id, terminal, writer),
    )
    child.start()
    try:
        assert reader.poll(10), "Child never reached the post-commit result boundary"
        outcome, calls = reader.recv()
        child.join(5)
        assert child.exitcode == 73 and outcome == terminal
        if terminal != "AUTH_LOSS":
            assert calls > 0
        peer = ConnectionManager(m.factory, m.settings, tuple(m.providers.values()), http=m.http)
        assert peer.status(who, row.id).recovery_required
        with m.factory() as db:
            p = db.scalar(select(MCPOperation).where(MCPOperation.connection_id == row.id))
            assert p
            if terminal == "AUTH_LOSS":
                state = peer.status(who, row.id)
                assert state.state == State.REAUTH_DRAINING and not state.enabled
                assert p.state == "RUNNING"
            else:
                assert p.state == "COMPLETE" and p.outcome == "SUCCESS"
                assert p.provider_outcome == "SUCCESS" and p.reconciliation_required
            p.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()

        async def restart() -> None:
            before = len(server.calls)
            result = await peer.recover(who, row.id)
            assert await peer.recover(who, row.id) == result
            if terminal == "AUTH_LOSS":
                assert result.recovery_required and result.operations_pending == 1
                with pytest.raises(Failure):
                    await peer.tools(who, row.id, row.generation)
            else:
                # Recovery only acknowledges the durable success receipt. The
                # already-observed TIMEOUT/CANCELLED result above remains final.
                assert not result.recovery_required and result.operations_pending == 0
            assert len(server.calls) == before

        asyncio.run(restart())
        with m.factory() as db:
            p = db.scalar(select(MCPOperation).where(MCPOperation.connection_id == row.id))
            assert p
            if terminal == "AUTH_LOSS":
                assert p.state == "UNRESOLVED" and p.reconciliation_required
                assert p.outcome == "REAUTH_REQUIRED" and p.provider_outcome is None
            else:
                assert p.state == "COMPLETE" and not p.reconciliation_required
                assert p.outcome == "SUCCESS" and p.provider_outcome == "SUCCESS"
    finally:
        if child.is_alive():
            child.terminate()
            child.join(5)
        reader.close()
        writer.close()


def test_sqlite_receipt_contention_is_recoverable_without_provider_replay(
    fixture: Fixture,
) -> None:
    m, who, server, engine = fixture
    if engine.dialect.name != "sqlite":
        pytest.skip("Explicit BEGIN IMMEDIATE contention is SQLite-specific")
    api_key(m)

    async def run() -> None:
        row = await m.create(who, "fixture", "receipt-contention")
        row = await m.connect(who, row.id, 0, SecretStr("synthetic-key"))
        tx = m.transaction
        audits: list[tuple[str, str]] = []
        m.audit = lambda *args: audits.append((args[-2], args[-1]))  # type: ignore[method-assign]

        def contend(fn: Callable[[Session], Any]) -> Any:
            if fn.__name__ != "receipt":
                return tx(fn)
            # Hold SQLite's write reservation for every bounded transaction retry.
            # This deterministic lock replaces scheduler timing as the reproducer.
            with m.factory() as locker:
                locker.connection().exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    return tx(fn)
                finally:
                    locker.rollback()

        m.transaction = contend  # type: ignore[method-assign, assignment]
        await m.tools(who, row.id, row.generation)
        assert await m.operations.drain(2)
        assert ("delivery_receipt", "UNRESOLVED") in audits
        assert not any(outcome == "SUCCESS" for _, outcome in audits)
        blocked = m.status(who, row.id)
        assert blocked.recovery_required and blocked.operations_pending == 1
        assert blocked.health == Health.DEGRADED and blocked.error == Code.STALE
        peer = ConnectionManager(m.factory, m.settings, tuple(m.providers.values()), http=m.http)
        before = len(server.calls)
        with pytest.raises(Failure):
            await peer.tools(who, row.id, row.generation)
        recovered = await peer.recover(who, row.id)
        assert not recovered.recovery_required and recovered.operations_pending == 0
        assert await peer.recover(who, row.id) == recovered
        assert len(server.calls) == before
        with m.factory() as db:
            permit = db.scalar(select(MCPOperation).where(MCPOperation.connection_id == row.id))
            assert permit and permit.state == "COMPLETE"
            assert permit.outcome == permit.provider_outcome == "SUCCESS"
            assert not permit.reconciliation_required

    asyncio.run(run())
