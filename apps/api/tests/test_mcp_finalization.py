"""Transport, commit and caller boundaries for corrected auth-drain finalization."""

import asyncio
import json
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx2
import pytest
from mcp_support import SyntheticServer, public_ip
from pydantic import SecretStr
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_mcp_remediation import fixture as fixture

from twf.infrastructure.mcp import MCPOperation
from twf.integrations.mcp.client import SDKClient
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import AuthMode, Code, Context, Failure, State
from twf.integrations.mcp.http import HTTPFactory

Fixture = tuple[ConnectionManager, Context, SyntheticServer, Engine]


def api_key(m: ConnectionManager, timeout: float = 2) -> None:
    m.providers["fixture"] = m.providers["fixture"].model_copy(
        update={"auth_mode": AuthMode.API_KEY, "oauth": None, "timeout_seconds": timeout}
    )


@pytest.mark.parametrize("iteration", range(3))
@pytest.mark.parametrize("boundary", ["before_send", "in_flight", "provider_success"])
def test_auth_failure_drains_admitted_generation(
    fixture: Fixture, boundary: str, iteration: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    m, who, server, _ = fixture
    api_key(m)
    peer = ConnectionManager(m.factory, m.settings, tuple(m.providers.values()))
    audits: list[str] = []
    monkeypatch.setattr(m, "audit", lambda *args: audits.append(args[-1]))

    async def run() -> None:
        row = await m.create(who, "fixture", f"auth-drain-{iteration}")
        row = await m.connect(who, row.id, 0, SecretStr("synthetic-key"))
        audits.clear()
        reached, release = asyncio.Event(), threading.Event()
        loop = asyncio.get_running_loop()
        original = m.transaction
        checks = 0
        paused = False
        dispatches: list[str] = []

        def transaction(fn: Callable[[Session], Any]) -> Any:
            nonlocal checks, paused
            if fn.__name__ == "check":
                checks += 1
            if boundary == "provider_success" and fn.__name__ == "finish" and not paused:
                paused = True
                loop.call_soon_threadsafe(reached.set)
                assert release.wait(5)
            result = original(fn)
            if boundary == "before_send" and checks == 2 and not paused:
                paused = True
                loop.call_soon_threadsafe(reached.set)
                assert release.wait(5)
            return result

        async def handler(req: httpx2.Request) -> httpx2.Response:
            if req.method == "POST" and req.headers.get("authorization"):
                method = json.loads(await req.aread())["method"]
                dispatches.append(method)
                # A different DB session takes the same authority locks during I/O.
                await asyncio.wait_for(peer.write(lambda db: peer.owned(db, who, row.id).id), 0.5)
                if boundary == "in_flight" and method == "tools/list":
                    reached.set()
                    assert await asyncio.to_thread(release.wait, 5)
            return await server.handle(req)

        async def unauthorized(req: httpx2.Request) -> httpx2.Response:
            assert req.headers.get("authorization")
            return httpx2.Response(401)

        monkeypatch.setattr(m, "transaction", transaction)
        m.client = SDKClient(HTTPFactory(lambda: httpx2.MockTransport(handler), public_ip))
        peer.client = SDKClient(HTTPFactory(lambda: httpx2.MockTransport(unauthorized), public_ip))
        task = asyncio.create_task(m.tools(who, row.id, row.generation))
        try:
            await asyncio.wait_for(reached.wait(), 3)
            if boundary == "before_send":
                assert not dispatches
            with pytest.raises(Failure) as failed:
                await peer.tools(who, row.id, row.generation)
            assert failed.value.code in {Code.AUTH_REQUIRED, Code.AUTH_FAILED}
            current = peer.status(who, row.id)
            assert current.state == State.REAUTH_DRAINING
            assert current.generation == row.generation and current.secret_ref == row.secret_ref
            assert current.operations_pending == 1
            before = len(dispatches)
            for attempt in (
                m.tools(who, row.id, row.generation),
                peer.connect(who, row.id, row.generation, SecretStr("replacement")),
            ):
                with pytest.raises(Failure) as rejected:
                    await attempt
                assert rejected.value.code in {Code.REAUTH_REQUIRED, Code.STALE}
            assert len(dispatches) == before
            assert "SUCCEEDED" not in audits
        finally:
            release.set()
        with pytest.raises(Failure) as late:
            await task
        assert late.value.code == Code.REAUTH_REQUIRED
        assert "tools/list" in dispatches  # Admitted G1 may physically send while draining.
        current = peer.status(who, row.id)
        assert current.state == State.REAUTH_REQUIRED and current.operations_pending == 0
        assert current.secret_ref is None and current.generation == row.generation + 1
        assert current.error == Code.REAUTH_REQUIRED
        with m.factory() as db:
            records = list(
                db.scalars(select(MCPOperation).where(MCPOperation.connection_id == row.id))
            )
            assert all(p.state == "COMPLETE" and p.outcome != "SUCCESS" for p in records)
            assert any(
                p.provider_outcome == "SUCCESS" and p.outcome == Code.REAUTH_REQUIRED
                for p in records
            )
        assert "SUCCEEDED" not in audits
        before = len(dispatches)
        with pytest.raises(Failure):
            await m.tools(who, row.id, row.generation)
        assert len(dispatches) == before

    asyncio.run(run())


@pytest.mark.parametrize("iteration", range(3))
@pytest.mark.parametrize("terminal", [Code.TIMEOUT, Code.CANCELLED])
@pytest.mark.parametrize("phase", ["prepare_commit", "decision_commit", "commit_delivery"])
def test_terminal_decision_survives_delayed_completion(
    fixture: Fixture, terminal: Code, phase: str, iteration: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    m, who, _, _ = fixture
    # Leave time for actual SDK work under suite load; this test must expire
    # at finalization, not during initialize. Separate pool tests exercise 80 ms.
    budget = 0.4
    api_key(m, budget if terminal == Code.TIMEOUT else 2)
    audits: list[str] = []
    monkeypatch.setattr(m, "audit", lambda *args: audits.append(args[-1]))

    async def run() -> None:
        row = await m.create(who, "fixture", f"finalize-{iteration}")
        row = await m.connect(who, row.id, 0, SecretStr("synthetic-key"))
        audits.clear()
        entered, release = asyncio.Event(), threading.Event()
        loop = asyncio.get_running_loop()
        original = m.transaction
        blocked = False

        def transaction(fn: Callable[[Session], Any]) -> Any:
            nonlocal blocked
            name = "finish" if phase == "prepare_commit" else "settle"
            if fn.__name__ != name or blocked:
                return original(fn)
            blocked = True

            def hold() -> None:
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(5)

            if phase == "commit_delivery":
                result = original(fn)
                hold()
                return result

            def before_commit(db: Session) -> Any:
                result = fn(db)
                hold()  # The real transaction has not committed yet.
                return result

            return original(before_commit)

        monkeypatch.setattr(m, "transaction", transaction)
        start = time.monotonic()
        task = asyncio.create_task(m.tools(who, row.id, row.generation))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            scope = next(iter(m.operations.tasks))
            if terminal == Code.CANCELLED:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                with pytest.raises(Failure) as timed_out:
                    await task
                assert timed_out.value.code == Code.TIMEOUT
                assert time.monotonic() - start < budget + 0.12
            assert "SUCCEEDED" not in audits
            assert m.operations.tasks  # DB completion/reconciliation remains owned.
        finally:
            release.set()
        assert await m.operations.drain(3)
        with m.factory() as db:
            p = db.get(MCPOperation, scope.id)
            assert p and p.state == "COMPLETE" and p.outcome == terminal
            assert p.provider_outcome == "SUCCESS"
        # A delayed completion using only the durable guard cannot restore success.
        scope.terminal, scope.outcome = None, "SUCCESS"
        scope.deadline = time.monotonic() + 2
        await m.completed(who, row.id, scope)
        with m.factory() as db:
            p = db.get(MCPOperation, scope.id)
            assert p and p.outcome == terminal
        assert "SUCCEEDED" not in audits

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["finish", "settle"])
@pytest.mark.parametrize("recovery_write_fails", [False, True])
def test_failed_completion_is_typed_and_recoverable(
    fixture: Fixture, phase: str, recovery_write_fails: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    m, who, _, _ = fixture
    api_key(m)
    audits: list[str] = []
    monkeypatch.setattr(m, "audit", lambda *args: audits.append(args[-1]))

    async def run() -> None:
        row = await m.create(who, "fixture", "persistence-failure")
        row = await m.connect(who, row.id, 0, SecretStr("synthetic-key"))
        audits.clear()
        original = m.transaction

        def transaction(fn: Callable[[Session], Any]) -> Any:
            if fn.__name__ == phase or (recovery_write_fails and fn.__name__ == "unresolved"):

                def fail_commit(db: Session) -> None:
                    fn(db)
                    raise OSError("private-db-credential-and-provider-payload")

                return original(fail_commit)
            return original(fn)

        monkeypatch.setattr(m, "transaction", transaction)
        with pytest.raises(Failure) as failure:
            await m.tools(who, row.id, row.generation)
        assert failure.value.code == Code.STORAGE
        assert "private" not in str(failure.value) and "SUCCEEDED" not in audits
        with m.factory() as db:
            p = db.scalar(select(MCPOperation).where(MCPOperation.connection_id == row.id))
            assert p and p.state in {"UNRESOLVED", "FINALIZING", "RUNNING"}
            assert p.outcome != "SUCCESS"
        restarted = ConnectionManager(
            m.factory, m.settings, tuple(m.providers.values()), http=m.http
        )
        state = await restarted.disconnect(who, row.id, row.generation)
        assert state.state == State.DISCONNECTING and state.operations_pending == 1
        assert state.secret_ref == row.secret_ref and state.generation == row.generation
        with pytest.raises(Failure):
            await restarted.tools(who, row.id, row.generation)

    asyncio.run(run())


def test_success_audit_observes_committed_success(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    m, who, _, _ = fixture
    api_key(m)

    async def run() -> None:
        row = await m.create(who, "fixture", "durable-success")
        row = await m.connect(who, row.id, 0, SecretStr("synthetic-key"))
        seen = []

        def audit(*args: Any) -> None:
            if args[-1] == "SUCCEEDED":
                with m.factory() as db:
                    p = db.scalar(select(MCPOperation).where(MCPOperation.connection_id == row.id))
                    assert p and p.state == "COMPLETE" and p.outcome == "SUCCESS"
                    assert p.provider_outcome == "SUCCESS"
                seen.append(args[-1])

        monkeypatch.setattr(m, "audit", audit)
        await m.tools(who, row.id, row.generation)
        assert await m.operations.drain(2)
        assert seen == ["SUCCEEDED"]

    asyncio.run(run())


def test_multi_operation_auth_drain_and_lost_worker(fixture: Fixture) -> None:
    m, who, server, _ = fixture
    api_key(m)

    async def run() -> None:
        row = await m.create(who, "fixture", "multi-drain")
        row = await m.connect(who, row.id, 0, SecretStr("synthetic-key"))
        entered = [asyncio.Event(), asyncio.Event()]
        release = [asyncio.Event(), asyncio.Event()]
        count = 0

        async def handler(req: httpx2.Request) -> httpx2.Response:
            nonlocal count
            if req.method == "POST" and json.loads(await req.aread())["method"] == "tools/list":
                index = count
                count += 1
                entered[index].set()
                await release[index].wait()
            return await server.handle(req)

        m.client = SDKClient(HTTPFactory(lambda: httpx2.MockTransport(handler), public_ip))
        tasks = []
        for i in range(2):
            tasks.append(asyncio.create_task(m.tools(who, row.id, row.generation)))
            await asyncio.wait_for(entered[i].wait(), 2)
        # Simulate a crashed worker whose deadline elapsed. Expiry cannot prove drain.
        lost_id = uuid4()
        with m.factory() as db:
            db.add(
                MCPOperation(
                    id=lost_id,
                    connection_id=row.id,
                    owner_id=who.owner_id,
                    generation=row.generation,
                    session_hash=who.session_hash,
                    worker_id=uuid4(),
                    state="RUNNING",
                    cleanup_state="RUNNING",
                    created_at=datetime.now(UTC),
                    deadline_at=datetime.now(UTC) - timedelta(seconds=1),
                )
            )
            db.commit()
        await m.fail(who, row.id, row.generation, Code.AUTH_REQUIRED, reauth=True)
        for i in range(2):
            release[i].set()
            with pytest.raises(Failure):
                await tasks[i]
            current = m.status(who, row.id)
            assert current.state == State.REAUTH_DRAINING
            assert current.operations_pending == 2 - i
            assert current.secret_ref == row.secret_ref and current.generation == row.generation
        assert current.recovery_required
        restarted = ConnectionManager(
            m.factory, m.settings, tuple(m.providers.values()), http=m.http
        )
        await restarted.cleanup(who, row.id)
        assert restarted.status(who, row.id).state == State.REAUTH_DRAINING
        with pytest.raises(Failure):
            await restarted.tools(who, row.id, row.generation)
        with pytest.raises(Failure):
            await restarted.connect(who, row.id, row.generation, SecretStr("replacement"))

    asyncio.run(run())
