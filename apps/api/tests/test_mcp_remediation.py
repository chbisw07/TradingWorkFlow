"""Event-driven dispatch, refresh, revocation and deadline acceptance regressions."""

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx2
import pytest
from mcp_support import SyntheticServer, public_ip, setup
from pydantic import SecretStr
from sqlalchemy import Engine, select

from twf.infrastructure.database import create_database_engine, create_session_factory
from twf.infrastructure.identity import AuthSession, User
from twf.infrastructure.mcp import MCPSecret
from twf.integrations.mcp.client import SDKClient
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import AuthMode, Code, Context, Failure, State, ToolPolicy
from twf.integrations.mcp.http import HTTPFactory, SafeTransport
from twf.integrations.mcp.lifecycle import operation as active_operation

POSTGRES_TEST_URL = os.getenv("TWF_MCP_TEST_POSTGRES_URL")


@pytest.fixture(params=["sqlite"] + (["postgres"] if POSTGRES_TEST_URL else []))
def fixture(
    request: pytest.FixtureRequest, tmp_path: Path
) -> Iterator[tuple[ConnectionManager, Context, SyntheticServer, Engine]]:
    m, w, s, e = setup(tmp_path / "review.db", AuthMode.OAUTH_2_1)
    if request.param == "postgres":
        url = POSTGRES_TEST_URL
        assert url is not None
        # Explicit opt-in, disposable local database only; never application settings.
        parsed = urlsplit(url)
        assert parsed.hostname in {"127.0.0.1", "localhost"}
        assert parsed.path.startswith("/twf_mcp_test_")
        settings = m.settings.model_copy(update={"database_url": url})
        e.dispose()
        e = create_database_engine(settings)
        factory = create_session_factory(e)
        w = w.model_copy(update={"session_hash": uuid4().hex + uuid4().hex})
        now = datetime.now(UTC)
        with factory() as db:
            db.add(
                User(
                    id=w.owner_id,
                    username=uuid4().hex,
                    display_name="test",
                    password_hash="unused",
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.flush()
            db.add(
                AuthSession(
                    token_hash=w.session_hash,
                    user_id=w.owner_id,
                    created_at=now,
                    expires_at=now + timedelta(hours=1),
                )
            )
            db.commit()
        m = ConnectionManager(factory, settings, tuple(m.providers.values()), http=m.http)
    try:
        yield m, w, s, e
    finally:
        e.dispose()


async def connected(m: ConnectionManager, w: Context, s: SyntheticServer) -> Any:
    row = await m.create(w, "fixture", "test")
    auth = await m.begin(w, row.id, 0)
    params = parse_qs(urlsplit(auth.authorization_url).query)
    s.challenge = params["code_challenge"][0]
    return await m.callback(w, row.id, params["state"][0], "code")


@pytest.mark.parametrize("transition", ["disconnect", "supersede", "logout"])
def test_final_dispatch_fence_after_dns(
    fixture: tuple[ConnectionManager, Context, SyntheticServer, Engine], transition: str
) -> None:
    m, w, s, _ = fixture

    async def run() -> None:
        row = await connected(m, w, s)
        entered, release = asyncio.Event(), asyncio.Event()
        dispatches = 0

        async def resolver(host: str) -> tuple[str, ...]:
            entered.set()
            await release.wait()
            return await public_ip(host)

        async def handler(req: httpx2.Request) -> httpx2.Response:
            nonlocal dispatches
            if req.headers.get("authorization"):
                dispatches += 1
            return await s.handle(req)

        m.client = SDKClient(HTTPFactory(lambda: httpx2.MockTransport(handler), resolver))
        task = asyncio.create_task(m.tools(w, row.id, row.generation))
        await entered.wait()
        if transition == "disconnect":
            draining = await m.disconnect(w, row.id, row.generation)
            assert draining.state == State.DISCONNECTING
            assert draining.generation == row.generation
            with pytest.raises(Failure):
                await m.tools(w, row.id, row.generation)
        elif transition == "supersede":
            with pytest.raises(Failure) as blocked:
                await m.begin(w, row.id, row.generation)
            assert blocked.value.code == Code.STALE
        else:
            with m.factory() as db:
                login = db.get(AuthSession, w.session_hash)
                assert login
                login.revoked_at = datetime.now(UTC)
                db.commit()
        release.set()
        if transition == "supersede":
            await task
            await m.begin(w, row.id, row.generation)
        else:
            with pytest.raises(Failure) as error:
                await task
            assert error.value.code == (Code.DENIED if transition == "logout" else Code.STALE)
        if transition == "logout":
            assert dispatches == 0
        if transition == "disconnect":
            assert m.status(w, row.id).state == State.DISCONNECTED
            before = dispatches
            with pytest.raises(Failure):
                await m.tools(w, row.id, row.generation)
            assert dispatches == before

    asyncio.run(run())


@pytest.mark.parametrize(
    "phase",
    [
        "BEFORE_PROVIDER_CALL",
        "PROVIDER_CALL_IN_FLIGHT",
        "TOKEN_RETURNED",
        "PENDING_STORED",
        "PROMOTION_PENDING",
        "PROMOTED",
        "OLD_CLEANUP_PENDING",
    ],
)
def test_disconnect_refresh_matrix(
    fixture: tuple[ConnectionManager, Context, SyntheticServer, Engine],
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    m, w, s, _ = fixture

    async def run() -> None:
        row = await connected(m, w, s)
        entered, release = asyncio.Event(), asyncio.Event()
        queued = False
        original_queue, original_write = m.queue_token, m.write
        original_refresh = m.oauth.refresh
        revocations: set[str] = set()
        reject_revoke = True

        async def barrier() -> None:
            entered.set()
            await release.wait()

        async def handler(req: httpx2.Request) -> httpx2.Response:
            if req.url.path == "/revoke":
                if reject_revoke:
                    return httpx2.Response(503)
                revocations.add(parse_qs((await req.aread()).decode())["token"][0])
                return httpx2.Response(200)
            if req.url.path == "/token":
                if phase == "PROVIDER_CALL_IN_FLIGHT":
                    await barrier()
                return httpx2.Response(
                    200,
                    json={
                        "access_token": "rotated-access",
                        "refresh_token": "rotated-refresh",
                        "token_type": "Bearer",
                    },
                )
            return await s.handle(req)

        async def refresh(*args: Any, **kwargs: Any) -> Any:
            if phase == "BEFORE_PROVIDER_CALL":
                await barrier()
            return await original_refresh(*args, **kwargs)

        async def queue(*args: Any, **kwargs: Any) -> Any:
            nonlocal queued
            if phase == "TOKEN_RETURNED":
                await barrier()
            result = await original_queue(*args, **kwargs)
            queued = True
            if phase == "PENDING_STORED":
                await barrier()
            return result

        async def write(operation: Callable[..., Any]) -> Any:
            is_promotion = (
                queued and operation.__name__ == "save" and active_operation.get() is not None
            )
            if is_promotion and phase == "PROMOTION_PENDING":
                await barrier()
            result = await original_write(operation)
            if is_promotion and phase == "PROMOTED":
                await barrier()
            return result

        m.oauth.http = HTTPFactory(lambda: httpx2.MockTransport(handler), public_ip)
        monkeypatch.setattr(m.oauth, "refresh", refresh)
        monkeypatch.setattr(m, "queue_token", queue)
        monkeypatch.setattr(m, "write", write)
        task = asyncio.create_task(m.refresh(w, row.id, row.generation))
        if phase == "OLD_CLEANUP_PENDING":
            await task
        else:
            await entered.wait()
        current = m.status(w, row.id)
        await m.disconnect(w, row.id, current.generation)
        release.set()
        result = (await asyncio.gather(task, return_exceptions=True))[0]
        if phase not in {"PROMOTED", "OLD_CLEANUP_PENDING"}:
            assert isinstance(result, Failure) and result.code == Code.STALE
        current = m.status(w, row.id)
        assert current.state == State.DISCONNECTED and not current.secret_ref
        assert current.cleanup_pending
        with m.factory() as db:
            records = list(db.scalars(select(MCPSecret).where(MCPSecret.connection_id == row.id)))
            assert records and all(record.revoked for record in records)
        assert await m.operations.drain(2)  # Complete local receipts before worker handoff.
        # New manager uses durable obligations; no original in-memory transition state.
        restarted = ConnectionManager(
            m.factory, m.settings, tuple(m.providers.values()), http=m.oauth.http
        )
        reject_revoke = False
        await restarted.cleanup(w, row.id)
        assert await restarted.operations.drain(2)
        assert not restarted.status(w, row.id).cleanup_pending
        assert {"fixture-access-secret", "fixture-refresh-secret"} <= revocations
        if phase != "BEFORE_PROVIDER_CALL":
            assert {"rotated-access", "rotated-refresh"} <= revocations
        with pytest.raises(Failure):
            await m.tools(w, row.id, row.generation)

    asyncio.run(run())


def test_reused_tokens_protected_until_disconnect(
    fixture: tuple[ConnectionManager, Context, SyntheticServer, Engine],
) -> None:
    m, w, s, _ = fixture

    async def run() -> None:
        row = await connected(m, w, s)
        assert await m.operations.drain(2)  # Settle the post-return delivery receipt.
        auth = await m.begin(w, row.id, row.generation)
        p = parse_qs(urlsplit(auth.authorization_url).query)
        s.challenge = p["code_challenge"][0]
        await m.cleanup(w, row.id)  # Pending authority also protects the old material.
        assert s.revoked == 0
        row = await m.callback(w, row.id, p["state"][0], "code")

        async def handler(req: httpx2.Request) -> httpx2.Response:
            if req.url.path == "/mcp" and s.revoked:
                return httpx2.Response(401)
            return await s.handle(req)

        m.client = SDKClient(HTTPFactory(lambda: httpx2.MockTransport(handler), public_ip))
        await m.cleanup(w, row.id)
        assert s.revoked == 0 and m.status(w, row.id).cleanup_pending
        await m.tools(w, row.id, row.generation)
        assert await m.operations.drain(2)
        row = await m.disconnect(w, row.id, row.generation)
        assert s.revoked == 2 and not row.cleanup_pending

    asyncio.run(run())


def test_cleanup_claim_blocks_new_authority(
    fixture: tuple[ConnectionManager, Context, SyntheticServer, Engine],
) -> None:
    m, w, s, _ = fixture

    async def run() -> None:
        row = await connected(m, w, s)
        entered, release = asyncio.Event(), asyncio.Event()

        async def handler(req: httpx2.Request) -> httpx2.Response:
            if req.url.path == "/revoke":
                entered.set()
                await release.wait()
            return await s.handle(req)

        m.oauth.http = HTTPFactory(lambda: httpx2.MockTransport(handler), public_ip)
        task = asyncio.create_task(m.disconnect(w, row.id, row.generation))
        await entered.wait()
        current = m.status(w, row.id)
        with pytest.raises(Failure) as error:
            await m.begin(w, row.id, current.generation)
        assert error.value.code == Code.STALE
        release.set()
        await task
        # Completed cleanup releases the claim; ordinary reconnect can proceed.
        await m.begin(w, row.id, current.generation)

    asyncio.run(run())


class BlockedClose(httpx2.AsyncByteStream):
    def __init__(self, entered: asyncio.Event, cancelled: asyncio.Event) -> None:
        self.entered, self.cancelled = entered, cancelled

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.entered.set()
        try:
            await asyncio.Event().wait()
            yield b"unreachable"
        finally:
            self.cancelled.set()


@pytest.mark.parametrize("close", ["blocked", "failure", "normal"])
def test_teardown_inside_caller_deadline(tmp_path: Path, close: str) -> None:
    m, w, s, e = setup(tmp_path / "deadline.db")
    m.providers["fixture"] = m.providers["fixture"].model_copy(update={"timeout_seconds": 0.08})

    async def run() -> None:
        entered, cancelled = asyncio.Event(), asyncio.Event()

        async def handler(req: httpx2.Request) -> httpx2.Response:
            if req.method == "DELETE" and close == "blocked":
                return httpx2.Response(200, stream=BlockedClose(entered, cancelled))
            if req.method == "DELETE" and close == "failure":
                # Deadline expires while operation is still waiting; no unbudgeted DELETE.
                raise httpx2.ConnectError("private remote failure")
            if req.method == "POST" and close == "failure":
                data = json.loads(await req.aread())
                if data["method"] == "tools/list":
                    entered.set()
                    await asyncio.Event().wait()
            return await s.handle(req)

        m.client = SDKClient(HTTPFactory(lambda: httpx2.MockTransport(handler), public_ip))

        async def fence() -> None:
            pass

        async def execute() -> None:
            await m.client.execute(m.providers["fixture"], {}, fence, ToolPolicy())

        start = time.monotonic()
        if close == "normal":
            await execute()
            assert s.closed == 1
        else:
            with pytest.raises(Failure) as error:
                await execute()
            assert error.value.code == Code.TIMEOUT
            assert time.monotonic() - start < 0.25  # Far below the original 310+ ms escape.
            assert entered.is_set()
            if close == "blocked":
                assert await m.client.operations.drain()
                assert cancelled.is_set()

    try:
        asyncio.run(run())
    finally:
        e.dispose()


def test_transport_retirement_is_idempotent() -> None:
    async def run() -> None:
        sends = 0

        async def handler(req: httpx2.Request) -> httpx2.Response:
            nonlocal sends
            sends += 1
            return httpx2.Response(200)

        transport = SafeTransport(
            frozenset({"https://provider.example/mcp"}),
            1024,
            inner=httpx2.MockTransport(handler),
            resolver=public_ip,
        )
        await transport.aclose()
        await transport.aclose()
        with pytest.raises(Failure) as error:
            await transport.handle_async_request(
                httpx2.Request(
                    "GET", "https://provider.example/mcp", headers={"Authorization": "Bearer test"}
                )
            )
        assert error.value.code == Code.STALE and sends == 0

    asyncio.run(run())


def test_timeout_wins_over_local_close_error(tmp_path: Path) -> None:
    m, w, s, e = setup(tmp_path / "close-error.db")
    m.providers["fixture"] = m.providers["fixture"].model_copy(update={"timeout_seconds": 0.08})

    async def run() -> None:
        closed = asyncio.Event()

        async def handler(req: httpx2.Request) -> httpx2.Response:
            if req.method == "POST" and json.loads(await req.aread())["method"] == "tools/list":
                await asyncio.Event().wait()
            return await s.handle(req)

        class BrokenClose(httpx2.MockTransport):
            async def aclose(self) -> None:
                closed.set()
                raise OSError("private close failure")

        m.client = SDKClient(HTTPFactory(lambda: BrokenClose(handler), public_ip))
        row = await m.create(w, "fixture", "test")
        row = await m.connect(w, row.id, 0)
        start = time.monotonic()
        with pytest.raises(Failure) as error:
            await m.tools(w, row.id, row.generation)
        assert error.value.code == Code.TIMEOUT and time.monotonic() - start < 0.25
        assert await m.operations.drain()
        assert closed.is_set() and m.status(w, row.id).error == Code.TIMEOUT

    try:
        asyncio.run(run())
    finally:
        e.dispose()


def test_sdk_reconnect_is_fenced_without_sleeps(tmp_path: Path) -> None:
    m, w, s, e = setup(tmp_path / "reconnect.db", AuthMode.API_KEY)

    async def run() -> None:
        initial_get, next_get, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        gets = 0
        stale = False
        authenticated_after_stale = 0

        class SSE(httpx2.AsyncByteStream):
            async def __aiter__(self) -> AsyncIterator[bytes]:
                initial_get.set()
                yield b"id: one\nretry: 0\n\n"
                await release.wait()

        async def resolver(host: str) -> tuple[str, ...]:
            if stale:
                next_get.set()
            return await public_ip(host)

        async def handler(req: httpx2.Request) -> httpx2.Response:
            nonlocal gets, authenticated_after_stale
            if stale and req.headers.get("authorization"):
                authenticated_after_stale += 1
            if req.method == "GET":
                gets += 1
                return httpx2.Response(
                    200, headers={"content-type": "text/event-stream"}, stream=SSE()
                )
            if req.method == "POST" and json.loads(await req.aread())["method"] == "tools/list":
                await next_get.wait()
            return await s.handle(req)

        m.client = SDKClient(HTTPFactory(lambda: httpx2.MockTransport(handler), resolver))
        row = await m.create(w, "fixture", "test")
        row = await m.connect(w, row.id, 0, SecretStr("fixture-access-secret"))
        task = asyncio.create_task(m.tools(w, row.id, row.generation))
        await initial_get.wait()
        draining = await m.disconnect(w, row.id, row.generation)
        assert draining.state == State.DISCONNECTING
        # Admitted SDK work can finish while draining, but cannot outlive its deadline.
        for scope in m.operations.tasks:
            scope.expire()
        assert await m.operations.drain()
        assert m.status(w, row.id).state == State.DISCONNECTED
        stale = True
        release.set()
        with pytest.raises(Failure) as error:
            await asyncio.wait_for(task, 2)
        assert error.value.code == Code.TIMEOUT
        assert gets == 1 and authenticated_after_stale == 0

    try:
        asyncio.run(run())
    finally:
        e.dispose()
