"""Approved durable admission/drain semantics, tested at actual transport boundaries."""

import asyncio
import json
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import anyio
import httpcore2
import httpx2
import pytest
from mcp_support import SyntheticServer, public_ip, setup
from pydantic import SecretStr
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_mcp_remediation import fixture as fixture

from twf.infrastructure.mcp import MCPConnection, MCPOperation
from twf.integrations.mcp.client import SDKClient
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import AuthMode, Code, Context, Failure, State
from twf.integrations.mcp.http import HTTPFactory


@pytest.mark.parametrize("round_number", range(5))
@pytest.mark.parametrize("boundary", ["admission", "final_fence"])
def test_worker_completion_gap_drains_across_workers(
    fixture: tuple[ConnectionManager, Context, SyntheticServer, Engine],
    round_number: int,
    boundary: str,
) -> None:
    m, who, server, _ = fixture
    m.providers["fixture"] = m.providers["fixture"].model_copy(
        update={"auth_mode": AuthMode.API_KEY, "oauth": None}
    )
    peer = ConnectionManager(m.factory, m.settings, tuple(m.providers.values()), http=m.http)

    async def run() -> None:
        row = await m.create(who, "fixture", f"gap-{round_number}")
        row = await m.connect(who, row.id, 0, SecretStr("synthetic-key"))
        committed, release = asyncio.Event(), threading.Event()
        loop = asyncio.get_running_loop()
        original = m.transaction
        paused = False
        checks = 0
        sends: list[tuple[str, bool, str, int, float]] = []

        def delayed(operation: Callable[[Session], Any]) -> Any:
            nonlocal paused, checks
            result = original(operation)
            # The real transaction has COMMITTED. Delay delivery to its awaiting worker.
            if operation.__name__ == "check":
                checks += 1
            target = (
                operation.__name__ == "capture"
                if boundary == "admission"
                else operation.__name__ == "check" and checks == 2
            )
            if target and not paused:
                paused = True
                loop.call_soon_threadsafe(committed.set)
                assert release.wait(3)
            return result

        m.transaction = delayed  # type: ignore[method-assign]

        async def handler(request: httpx2.Request) -> httpx2.Response:
            sends.append(
                (
                    request.method,
                    bool(request.headers.get("authorization")),
                    str(row.id),
                    row.generation,
                    time.monotonic(),
                )
            )
            # Acquire the SAME authority locks from another manager while provider I/O
            # is executing. A DB guard spanning I/O would deadlock/time out here.
            await asyncio.wait_for(peer.write(lambda db: peer.owned(db, who, row.id).id), 0.5)
            assert peer.status(who, row.id).state == State.DISCONNECTING
            return await server.handle(request)

        m.client = SDKClient(HTTPFactory(lambda: httpx2.MockTransport(handler), public_ip))
        task = asyncio.create_task(m.tools(who, row.id, row.generation))
        try:
            await asyncio.wait_for(committed.wait(), 2)
            draining = await peer.disconnect(who, row.id, row.generation)
            assert draining.state == State.DISCONNECTING
            assert draining.operations_pending == 1 and draining.generation == row.generation
            assert not sends
            # Another worker cannot admit, reconnect or advance this generation.
            for attempt in (
                peer.tools(who, row.id, row.generation),
                peer.connect(who, row.id, row.generation, SecretStr("replacement")),
                peer.refresh(who, row.id, row.generation),
            ):
                with pytest.raises(Failure) as blocked:
                    await attempt
                assert blocked.value.code == Code.STALE
            assert not sends
        finally:
            release.set()
        with pytest.raises(Failure) as late:
            await task
        assert late.value.code == Code.STALE  # Result quarantined during disconnect.
        done_at = time.monotonic()
        current = peer.status(who, row.id)
        assert current.state == State.DISCONNECTED and current.operations_pending == 0
        assert current.generation == row.generation + 1 and current.secret_ref is None
        assert sends and any(method == "POST" and auth for method, auth, *_ in sends)
        assert all(at < done_at for *_, at in sends)
        count = len(sends)
        with pytest.raises(Failure):
            await m.tools(who, row.id, row.generation)
        assert len(sends) == count  # No actual authenticated send after completion.
        replacement = await peer.connect(who, row.id, current.generation, SecretStr("new-key"))
        assert replacement.generation > current.generation
        with pytest.raises(Failure):
            await m.tools(who, row.id, row.generation)
        assert len(sends) == count

    asyncio.run(run())


@pytest.mark.parametrize("body_timeout", [False, True])
@pytest.mark.parametrize("close_error", [False, True])
def test_real_pool_shield_does_not_extend_public_deadline(
    tmp_path: Path,
    body_timeout: bool,
    close_error: bool,
) -> None:
    m, who, server, engine = setup(tmp_path / "shield.db")
    m.providers["fixture"] = m.providers["fixture"].model_copy(update={"timeout_seconds": 0.08})

    async def run() -> None:
        closed, entered, finish_close = asyncio.Event(), asyncio.Event(), asyncio.Event()
        pool = httpcore2.AsyncConnectionPool()
        sends: list[float] = []

        class SlowConnection:
            async def aclose(self) -> None:
                entered.set()
                release = asyncio.Event()
                asyncio.get_running_loop().call_later(0.32, release.set)
                await release.wait()
                await finish_close.wait()
                closed.set()
                if close_error:
                    raise OSError("synthetic private teardown error")

        pool._connections.append(cast(Any, SlowConnection()))

        async def handler(request: httpx2.Request) -> httpx2.Response:
            sends.append(time.monotonic())
            if body_timeout and request.method == "POST":
                if json.loads(await request.aread())["method"] == "tools/list":
                    await asyncio.Event().wait()
            return await server.handle(request)

        class Transport(httpx2.MockTransport):
            async def aclose(self) -> None:
                # REAL HTTPcore shielding, not a stand-in timeout implementation.
                await pool.aclose()

        m.client = SDKClient(HTTPFactory(lambda: Transport(handler), public_ip))
        row = await m.create(who, "fixture", "shield")
        row = await m.connect(who, row.id, 0)
        start = time.monotonic()
        with pytest.raises(Failure) as result:
            await m.tools(who, row.id, row.generation)
        elapsed = time.monotonic() - start
        assert result.value.code == Code.TIMEOUT and elapsed < 0.15
        assert not closed.is_set() and m.operations.tasks  # Owned, still unwinding.
        try:
            draining = await m.disconnect(who, row.id, row.generation)
            assert draining.state == State.DISCONNECTING and draining.operations_pending == 1
            assert draining.generation == row.generation
        finally:
            finish_close.set()
        count = len(sends)
        assert await m.operations.drain()
        assert entered.is_set() and closed.is_set() and len(sends) == count
        with m.factory() as db:
            permit = db.scalar(select(MCPOperation))
            assert permit and permit.outcome == Code.TIMEOUT
            assert permit.cleanup_state == ("FAILED_RETRYABLE" if close_error else "COMPLETE")
        current = m.status(who, row.id)
        assert current.state == (State.DISCONNECTING if close_error else State.DISCONNECTED)
        assert not current.tools  # A late completed list never promotes to success.
        if close_error:
            assert current.recovery_required and current.operations_pending == 1
        assert result.value.code == Code.TIMEOUT

    try:
        asyncio.run(run())
    finally:
        engine.dispose()


def test_expired_foreign_worker_permit_is_not_assumed_drained(tmp_path: Path) -> None:
    m, who, _, engine = setup(tmp_path / "restart.db", AuthMode.API_KEY)

    async def run() -> None:
        row = await m.create(who, "fixture", "lost-worker")
        row = await m.connect(who, row.id, 0, SecretStr("synthetic-key"))
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
                    created_at=datetime.now(UTC),
                    deadline_at=datetime.now(UTC) - timedelta(seconds=10),
                )
            )
            db.commit()
        restarted = ConnectionManager(m.factory, m.settings, tuple(m.providers.values()))
        with pytest.raises(Failure):
            await restarted.tools(who, row.id, row.generation)
        current = await restarted.disconnect(who, row.id, row.generation)
        assert current.state == State.DISCONNECTING and current.recovery_required
        assert current.generation == row.generation and current.secret_ref is not None
        for attempt in (
            restarted.tools(who, row.id, row.generation),
            restarted.connect(who, row.id, row.generation, SecretStr("new-key")),
        ):
            with pytest.raises(Failure):
                await attempt
        await restarted.cleanup(who, row.id)
        assert restarted.status(who, row.id).state == State.DISCONNECTING

    try:
        asyncio.run(run())
    finally:
        engine.dispose()


def test_late_provider_result_is_quarantined(tmp_path: Path) -> None:
    m, who, server, engine = setup(tmp_path / "late.db")
    m.providers["fixture"] = m.providers["fixture"].model_copy(update={"timeout_seconds": 0.08})

    async def run() -> None:
        entered, release = asyncio.Event(), asyncio.Event()
        sends: list[float] = []

        async def handler(request: httpx2.Request) -> httpx2.Response:
            sends.append(time.monotonic())
            if (
                request.method == "POST"
                and json.loads(await request.aread())["method"] == "tools/list"
            ):
                entered.set()
                with anyio.CancelScope(shield=True):
                    await release.wait()
            return await server.handle(request)

        m.client = SDKClient(HTTPFactory(lambda: httpx2.MockTransport(handler), public_ip))
        row = await m.create(who, "fixture", "late")
        row = await m.connect(who, row.id, 0)
        task = asyncio.create_task(m.tools(who, row.id, row.generation))
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(Failure) as result:
            await task
        assert result.value.code == Code.TIMEOUT
        count = len(sends)
        release.set()
        assert await m.operations.drain()
        assert len(sends) == count
        with m.factory() as db:
            stored = db.get(MCPConnection, row.id)
            assert stored and stored.last_success_at is None and stored.tools_json == "[]"
        assert m.status(who, row.id).error == Code.TIMEOUT

    try:
        asyncio.run(run())
    finally:
        engine.dispose()


def test_timeout_owns_delayed_admission_worker_until_it_stops(tmp_path: Path) -> None:
    m, who, server, engine = setup(tmp_path / "admission-timeout.db", AuthMode.API_KEY)
    m.providers["fixture"] = m.providers["fixture"].model_copy(update={"timeout_seconds": 0.08})

    async def run() -> None:
        row = await m.create(who, "fixture", "admission-timeout")
        row = await m.connect(who, row.id, 0, SecretStr("synthetic-key"))
        committed, release = asyncio.Event(), threading.Event()
        original = m.transaction
        loop = asyncio.get_running_loop()

        def delayed(operation: Callable[[Session], Any]) -> Any:
            result = original(operation)
            if operation.__name__ == "capture":
                loop.call_soon_threadsafe(committed.set)
                assert release.wait(3)
            return result

        m.transaction = delayed  # type: ignore[method-assign]
        started = time.monotonic()
        task = asyncio.create_task(m.tools(who, row.id, row.generation))
        try:
            await asyncio.wait_for(committed.wait(), 1)
            with pytest.raises(Failure) as outcome:
                await task
            assert outcome.value.code == Code.TIMEOUT
            assert time.monotonic() - started < 0.15
            assert not server.calls and m.operations.tasks
            pending = m.status(who, row.id)
            assert pending.operations_pending == 1 and pending.recovery_required
            draining = await m.disconnect(who, row.id, row.generation)
            assert draining.state == State.DISCONNECTING
        finally:
            release.set()
        assert await m.operations.drain()
        assert not server.calls
        assert m.status(who, row.id).state == State.DISCONNECTED

    try:
        asyncio.run(run())
    finally:
        engine.dispose()


def test_revocation_permit_protects_group_after_cleanup_lease_expiry(
    fixture: tuple[ConnectionManager, Context, SyntheticServer, Engine],
) -> None:
    m, who, _, _ = fixture
    m.providers["fixture"] = m.providers["fixture"].model_copy(
        update={"auth_mode": AuthMode.API_KEY, "oauth": None}
    )

    async def run() -> None:
        row = await m.create(who, "fixture", "retired")
        row = await m.connect(who, row.id, 0, SecretStr("synthetic-key"))
        row = await m.disconnect(who, row.id, row.generation)
        identity = uuid4()
        with m.factory() as db:
            db.add(
                MCPOperation(
                    id=identity,
                    connection_id=row.id,
                    owner_id=who.owner_id,
                    generation=row.generation,
                    session_hash=who.session_hash,
                    worker_id=uuid4(),
                    kind="REVOCATION",
                    state="RUNNING",
                    cleanup_state="RUNNING",
                    created_at=datetime.now(UTC) - timedelta(seconds=2),
                    deadline_at=datetime.now(UTC) - timedelta(seconds=1),
                )
            )
            db.commit()
        try:
            other = await m.create(who, "fixture", "new-connection")
            with pytest.raises(Failure) as denied:
                await m.connect(who, other.id, 0, SecretStr("synthetic-new-key"))
            assert denied.value.code == Code.STALE
            assert m.status(who, row.id).recovery_required
        finally:
            # Receipt bookkeeping is owned after the public result; finish it before
            # this test manually removes its fabricated lost-worker permit.
            assert await m.operations.drain(2)
            # Fixture-only cleanup: never infer that a production worker stopped from expiry.
            with m.factory() as db:
                permit = db.get(MCPOperation, identity)
                assert permit
                db.delete(permit)
                db.commit()

    asyncio.run(run())


def test_public_test_status_lookup_shares_invocation_deadline(tmp_path: Path) -> None:
    m, who, _, engine = setup(tmp_path / "status-deadline.db")
    m.providers["fixture"] = m.providers["fixture"].model_copy(update={"timeout_seconds": 0.08})

    async def run() -> None:
        row = await m.create(who, "fixture", "status-deadline")
        row = await m.connect(who, row.id, 0)
        entered, release = asyncio.Event(), threading.Event()
        original = m.view
        loop = asyncio.get_running_loop()

        def delayed(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(3)
            return result

        m.view = delayed  # type: ignore[method-assign]
        started = time.monotonic()
        task = asyncio.create_task(m.test_connection(who, row.id, row.generation))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            with pytest.raises(Failure) as outcome:
                await task
            assert outcome.value.code == Code.TIMEOUT
            assert time.monotonic() - started < 0.15
            assert m.operations.tasks
        finally:
            release.set()
        assert await m.operations.drain()

    try:
        asyncio.run(run())
    finally:
        engine.dispose()


def test_separate_process_observes_durable_drain(
    fixture: tuple[ConnectionManager, Context, SyntheticServer, Engine],
) -> None:
    import sys

    m, who, server, _ = fixture
    m.providers["fixture"] = m.providers["fixture"].model_copy(
        update={"auth_mode": AuthMode.API_KEY, "oauth": None, "timeout_seconds": 5.0}
    )
    child_code = """
import asyncio, json, sys
from uuid import UUID
from twf.config.settings import Settings
from twf.infrastructure.database import create_database_engine, create_session_factory
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import Context, ProviderConfig, Failure
class NoIO:
    async def execute(self, *args, **kwargs):
        raise AssertionError("new worker must not reach provider I/O")
p = json.load(sys.stdin)
settings = Settings(database_url=p["database_url"])
engine = create_database_engine(settings)
m = ConnectionManager(create_session_factory(engine), settings,
                      (ProviderConfig.model_validate(p["provider"]),), client=NoIO())
who = Context.model_validate(p["who"])
async def run():
    row = await m.disconnect(who, UUID(p["connection"]), p["generation"])
    try:
        await m.tools(who, row.id, row.generation)
    except Failure as error:
        print(json.dumps({"state": row.state, "pending": row.operations_pending,
                          "generation": row.generation, "admission_error": error.code}))
    else:
        raise AssertionError("new operation was admitted")
try:
    asyncio.run(run())
finally:
    engine.dispose()
"""

    async def run() -> None:
        row = await m.create(who, "fixture", "process-race")
        row = await m.connect(who, row.id, 0, SecretStr("synthetic-key"))
        committed, release = asyncio.Event(), threading.Event()
        original = m.transaction
        loop = asyncio.get_running_loop()

        def delayed(operation: Callable[[Session], Any]) -> Any:
            result = original(operation)
            if operation.__name__ == "capture":
                loop.call_soon_threadsafe(committed.set)
                assert release.wait(10)
            return result

        m.transaction = delayed  # type: ignore[method-assign]
        task = asyncio.create_task(m.tools(who, row.id, row.generation))
        try:
            await asyncio.wait_for(committed.wait(), 2)
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                child_code,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            payload = {
                "database_url": m.settings.database_url,
                "provider": m.providers["fixture"].model_dump(mode="json"),
                "who": {"owner_id": str(who.owner_id), "session_hash": who.session_hash},
                "connection": str(row.id),
                "generation": row.generation,
            }
            stdout, stderr = await asyncio.wait_for(
                process.communicate(json.dumps(payload).encode()), 4
            )
            assert process.returncode == 0, stderr.decode()
            result = json.loads(stdout)
            assert result == {
                "state": "DISCONNECTING",
                "pending": 1,
                "generation": row.generation,
                "admission_error": "STALE_GENERATION",
            }
            assert not server.calls
        finally:
            release.set()
        with pytest.raises(Failure) as late:
            await task
        assert late.value.code == Code.STALE
        assert m.status(who, row.id).state == State.DISCONNECTED

    asyncio.run(run())
