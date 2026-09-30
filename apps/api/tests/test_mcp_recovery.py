"""Boundary, expiry, cancellation and stale-session regressions."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp_support import public_ip, setup
from sqlalchemy import select

from twf.auth import token_digest
from twf.infrastructure.identity import AuthSession
from twf.infrastructure.mcp import MCPConnection, MCPSecret
from twf.integrations.mcp.client import SDKClient
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import AuthMode, Code, Failure, State
from twf.integrations.mcp.http import HTTPFactory
from twf.main import create_app


def test_authenticated_settings_api_origin_generation_and_no_tool_route(tmp_path: Path) -> None:
    manager, who, server, engine = setup(tmp_path / "api.db")
    cookie = "b" * 43
    with manager.factory() as db:
        login = db.get(AuthSession, who.session_hash)
        assert login
        login.token_hash = token_digest(cookie)
        db.commit()
    app = create_app(manager.settings, engine_factory=lambda _: engine)
    with TestClient(app) as client:
        cast(FastAPI, client.app).state.mcp_manager = manager
        base = "/api/v1/settings/mcp/connections"
        assert client.get(base + "/00000000-0000-0000-0000-000000000000").status_code == 403
        client.cookies.set(manager.settings.session_cookie_name, cookie)
        payload = {"provider_id": "fixture", "display_name": "A"}
        assert client.post(base, json=payload).status_code == 403
        headers = {"Origin": manager.settings.allowed_origins[0], "X-Request-ID": "mcp-test"}
        response = client.post(base, json=payload, headers=headers)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        target = base + "/" + response.json()["id"]
        response = client.post(target + "/connect", json={"generation": 0}, headers=headers)
        assert response.status_code == 200 and response.json()["generation"] == 1
        response = client.post(target + "/connect", json={"generation": 0}, headers=headers)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "STALE_GENERATION"
        assert response.json()["error"]["request_id"] == "mcp-test"
        response = client.post(target + "/test", json={"generation": 1}, headers=headers)
        assert response.status_code == 200 and len(response.json()["tools"]) == 2
        assert client.post(target + "/call", json={}, headers=headers).status_code == 404
        assert (
            client.post(target + "/disconnect", json={"generation": 1}, headers=headers).json()[
                "state"
            ]
            == "DISCONNECTED"
        )


def test_expired_token_refresh_restart_and_stale_refresh(tmp_path: Path) -> None:
    manager, who, server, engine = setup(tmp_path / "expiry.db", AuthMode.OAUTH_2_1)

    async def exercise() -> None:
        row = await manager.create(who, "fixture", "test")
        auth = await manager.begin(who, row.id, 0)
        params = parse_qs(urlsplit(auth.authorization_url).query)
        server.challenge = params["code_challenge"][0]
        row = await manager.callback(who, row.id, params["state"][0], "code")
        with manager.factory() as db:
            stored = db.get(MCPConnection, row.id)
            assert stored
            stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
        restarted = ConnectionManager(
            manager.factory, manager.settings, tuple(manager.providers.values()), http=manager.http
        )
        assert restarted.status(who, row.id).state == State.REAUTH_REQUIRED
        with pytest.raises(Failure) as caught:
            await restarted.tools(who, row.id, row.generation)
        assert caught.value.code == Code.REAUTH_REQUIRED
        refreshed = await restarted.refresh(who, row.id, row.generation)
        assert refreshed.state == State.CONNECTED and refreshed.generation > row.generation
        with pytest.raises(Failure) as caught:
            await restarted.refresh(who, row.id, row.generation)
        assert caught.value.code == Code.STALE
        assert server.token_calls == 2
        await restarted.cleanup(who, row.id)
        assert server.revoked == 0  # Refresh may have retained the same token.

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


def test_cancelled_exchange_leaves_no_active_binding(tmp_path: Path) -> None:
    manager, who, server, engine = setup(tmp_path / "cancel.db", AuthMode.OAUTH_2_1)

    async def exercise() -> None:
        entered = asyncio.Event()

        async def handler(request: httpx2.Request) -> httpx2.Response:
            entered.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        manager.oauth.http = HTTPFactory(lambda: httpx2.MockTransport(handler), public_ip)
        row = await manager.create(who, "fixture", "test")
        auth = await manager.begin(who, row.id, 0)
        state = parse_qs(urlsplit(auth.authorization_url).query)["state"][0]
        work = asyncio.create_task(manager.callback(who, row.id, state, "code"))
        await entered.wait()
        work.cancel()
        with pytest.raises(asyncio.CancelledError):
            await work
        assert await manager.operations.drain()
        current = manager.status(who, row.id)
        assert current.state == State.REAUTH_REQUIRED and current.secret_ref is None
        with manager.factory() as db:
            assert db.scalar(select(MCPSecret)) is None

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


@pytest.mark.parametrize("case", ["stale", "oversize", "protocol", "timeout", "pages"])
def test_sdk_session_bounds_and_generation(tmp_path: Path, case: str) -> None:
    manager, who, server, engine = setup(tmp_path / "session.db")
    manager.providers["fixture"] = manager.providers["fixture"].model_copy(
        update={"timeout_seconds": 0.3, "max_response_bytes": 4096}
    )

    async def exercise() -> None:
        entered, release = asyncio.Event(), asyncio.Event()

        async def handler(request: httpx2.Request) -> httpx2.Response:
            if request.method == "POST":
                message = json.loads(await request.aread())
                if case == "protocol" and message["method"] == "initialize":
                    return httpx2.Response(
                        200,
                        json={
                            "jsonrpc": "2.0",
                            "id": message["id"],
                            "result": {
                                "protocolVersion": "invalid",
                                "capabilities": {},
                                "serverInfo": {"name": "test", "version": "1"},
                            },
                        },
                    )
                if message["method"] == "tools/list":
                    if case == "stale":
                        entered.set()
                        await release.wait()
                    if case == "timeout":
                        await asyncio.sleep(1)
                    if case == "oversize":
                        return httpx2.Response(200, content=b"x" * 8192)
                    if case == "pages":
                        return httpx2.Response(
                            200,
                            json={
                                "jsonrpc": "2.0",
                                "id": message["id"],
                                "result": {"tools": [], "nextCursor": "again"},
                            },
                        )
            return await server.handle(request)

        manager.client = SDKClient(HTTPFactory(lambda: httpx2.MockTransport(handler), public_ip))
        row = await manager.create(who, "fixture", "test")
        row = await manager.connect(who, row.id, 0)
        work = asyncio.create_task(manager.tools(who, row.id, row.generation))
        if case == "stale":
            await entered.wait()
            await manager.disconnect(who, row.id, row.generation)
            release.set()
        with pytest.raises(Failure) as caught:
            await work
        assert (
            caught.value.code
            == {
                "stale": Code.STALE,
                "oversize": Code.SCHEMA_MISMATCH,
                "protocol": Code.CONTRACT_MISMATCH,
                "timeout": Code.TIMEOUT,
                "pages": Code.SCHEMA_MISMATCH,
            }[case]
        )
        assert not manager.status(who, row.id).tools

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


def test_real_second_owner_cannot_read_use_or_disconnect(tmp_path: Path) -> None:
    from uuid import uuid4

    from twf.infrastructure.identity import User
    from twf.integrations.mcp.contracts import Context

    manager, who, server, engine = setup(tmp_path / "owners.db")
    other = Context(owner_id=uuid4(), session_hash="d" * 64)
    now = datetime.now(UTC)
    with manager.factory() as db:
        db.add(
            User(
                id=other.owner_id,
                username="second-mcp",
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
                token_hash=other.session_hash,
                user_id=other.owner_id,
                created_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        db.commit()

    async def exercise() -> None:
        row = await manager.create(who, "fixture", "first")
        row = await manager.connect(who, row.id, 0)
        second = await manager.create(other, "fixture", "second")
        assert second.owner_id == other.owner_id and second.id != row.id
        with pytest.raises(Failure) as caught:
            manager.status(other, row.id)
        assert caught.value.code == Code.DENIED
        for operation in [
            manager.tools(other, row.id, row.generation),
            manager.disconnect(other, row.id, row.generation),
        ]:
            with pytest.raises(Failure) as caught:
                await operation
            assert caught.value.code == Code.DENIED
        assert manager.status(who, row.id).state == State.CONNECTED and not server.calls

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


def test_config_drift_invalidates_health_and_cannot_reuse_credentials(tmp_path: Path) -> None:
    manager, who, server, engine = setup(tmp_path / "config.db")

    async def exercise() -> None:
        with pytest.raises(Failure) as caught:
            await manager.create(who, "unknown", "test")
        assert caught.value.code == Code.NOT_CONFIGURED
        row = await manager.create(who, "fixture", "test")
        row = await manager.connect(who, row.id, 0)
        await manager.tools(who, row.id, row.generation)
        manager.providers["fixture"] = manager.providers["fixture"].model_copy(
            update={"endpoint": "https://changed.example/mcp"}
        )
        assert await manager.operations.drain()
        current = manager.status(who, row.id)
        assert current.state == State.REAUTH_REQUIRED and current.error == Code.STALE
        before = len(server.calls)
        with pytest.raises(Failure) as caught:
            await manager.tools(who, row.id, row.generation)
        assert caught.value.code == Code.STALE and len(server.calls) == before
        assert (await manager.disconnect(who, row.id, row.generation)).state == State.DISCONNECTED

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()
