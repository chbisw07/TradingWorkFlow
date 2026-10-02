import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from mcp_support import setup
from pydantic import JsonValue, SecretStr, ValidationError
from sqlalchemy import select

from twf.infrastructure.identity import AuthSession
from twf.infrastructure.mcp import MCPConnection, MCPOAuthAttempt, MCPSecret
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import AuthMode, Code, Context, Failure, State, ToolPolicy


def test_no_auth_sdk_lifecycle_allowlist_and_restart(tmp_path: Path) -> None:
    manager, who, server, engine = setup(tmp_path / "mcp.db")

    async def exercise() -> None:
        row = await manager.create(who, "fixture", "My provider")
        assert [item.id for item in manager.connections(who)] == [row.id]
        assert [item.id for item in manager.connections(who, "fixture")] == [row.id]
        with pytest.raises(Failure) as caught:
            await manager.tools(who, row.id, 0)
        assert caught.value.code == Code.CLOSED and not server.calls
        row = await manager.connect(who, row.id, 0)
        tools, result = await manager.tools(
            who,
            row.id,
            row.generation,
            policy=ToolPolicy(allowed=frozenset({"read_demo"})),
            name="read_demo",
            arguments={"value": 42},
        )
        assert [t.name for t in tools] == ["read_demo", "write_demo"]
        assert result and result["content"]
        assert server.closed == 1
        cases: list[tuple[str, dict[str, JsonValue], Code]] = [
            ("write_demo", {"value": 1}, Code.TOOL_NOT_ALLOWED),
            ("read_demo", {"value": "bad"}, Code.INVALID_ARGUMENTS),
            ("absent", {}, Code.TOOL_NOT_FOUND),
        ]
        for name, args, code in cases:
            before = server.calls.count("tools/call")
            with pytest.raises(Failure) as caught:
                await manager.tools(
                    who,
                    row.id,
                    row.generation,
                    policy=ToolPolicy(allowed=frozenset({"read_demo", "absent"})),
                    name=name,
                    arguments=args,
                )
            assert caught.value.code == code
            assert server.calls.count("tools/call") == before
        restarted = ConnectionManager(
            manager.factory, manager.settings, tuple(manager.providers.values()), http=manager.http
        )
        assert restarted.status(who, row.id).generation == row.generation
        disconnected = await restarted.disconnect(who, row.id, row.generation)
        assert not disconnected.enabled and disconnected.state == State.DISCONNECTED
        with pytest.raises(Failure):
            await manager.tools(who, row.id, row.generation)

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


def test_disconnected_connection_exposes_stale_provider_registration(tmp_path: Path) -> None:
    manager, who, _, engine = setup(tmp_path / "mcp.db", AuthMode.OAUTH_2_1)

    async def exercise() -> None:
        row = await manager.create(who, "fixture", "Old registration")
        changed = manager.providers["fixture"].model_copy(
            update={"display_name": "Replacement registration"}
        )
        restarted = ConnectionManager(
            manager.factory, manager.settings, (changed,), http=manager.http
        )

        current = restarted.status(who, row.id)

        assert current.state == State.DISCONNECTED
        assert current.error == Code.STALE
        assert current.health.value == "UNAVAILABLE"
        assert not current.enabled

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


def test_oauth_pkce_storage_refresh_disconnect(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    manager, who, server, engine = setup(tmp_path / "mcp.db", AuthMode.OAUTH_2_1)

    async def exercise() -> None:
        row = await manager.create(who, "fixture", "OAuth provider")
        auth = await manager.begin(who, row.id, 0)
        params = parse_qs(urlsplit(auth.authorization_url).query)
        assert params["code_challenge_method"] == ["S256"]
        server.challenge = params["code_challenge"][0]
        state = params["state"][0]
        row = await manager.callback(who, row.id, state, "fixture-code")
        assert row.secret_ref and row.generation == 1
        assert "fixture-access-secret" not in row.model_dump_json()
        with manager.factory() as db:
            secret = db.get(MCPSecret, row.secret_ref.reference_id)
            assert secret and "fixture-access-secret" not in secret.ciphertext
            attempt = db.scalar(select(MCPOAuthAttempt))
            assert attempt and attempt.consumed and not attempt.verifier_ciphertext
        with pytest.raises(Failure) as caught:
            await manager.callback(who, row.id, state, "fixture-code")
        assert caught.value.code == Code.STALE and server.token_calls == 1
        server.auth_required = True
        await manager.tools(who, row.id, row.generation)
        first_ref = row.secret_ref.reference_id
        row = await manager.refresh(who, row.id, row.generation)
        assert row.generation == 2 and row.secret_ref and row.secret_ref.reference_id != first_ref
        with manager.factory() as db:
            old = db.get(MCPSecret, first_ref)
            assert old and old.revoked
        row = await manager.disconnect(who, row.id, row.generation)
        assert not row.secret_ref and not row.cleanup_pending
        assert server.revoked == 2
        assert "fixture-access-secret" not in caplog.text
        assert "fixture-refresh-secret" not in caplog.text
        assert state not in caplog.text

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "case", ["owner", "session", "expired", "state", "missing", "stale", "logout"]
)
def test_oauth_callback_binding(tmp_path: Path, case: str) -> None:
    manager, who, server, engine = setup(tmp_path / "mcp.db", AuthMode.OAUTH_2_1)

    async def exercise() -> None:
        row = await manager.create(who, "fixture", "OAuth")
        result = await manager.begin(who, row.id, 0)
        params = parse_qs(urlsplit(result.authorization_url).query)
        state = params["state"][0]
        caller = who
        if case == "owner":
            caller = who.model_copy(update={"owner_id": uuid4()})
        if case == "session":
            with manager.factory() as db:
                db.add(
                    AuthSession(
                        token_hash="b" * 64,
                        user_id=who.owner_id,
                        created_at=datetime.now(UTC),
                        expires_at=datetime.now(UTC) + timedelta(hours=1),
                    )
                )
                db.commit()
            caller = who.model_copy(update={"session_hash": "b" * 64})
        if case == "expired":
            with manager.factory() as db:
                attempt = db.scalar(select(MCPOAuthAttempt))
                assert attempt
                attempt.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                db.commit()
        if case == "state":
            state = "incorrect"
        if case == "missing":
            state = ""
        if case == "stale":
            await manager.begin(who, row.id, result.generation)
        if case == "logout":
            with manager.factory() as db:
                login = db.get(AuthSession, who.session_hash)
                assert login
                login.revoked_at = datetime.now(UTC)
                db.commit()
        with pytest.raises(Failure):
            await manager.callback(caller, row.id, state, "fixture-code")
        assert server.token_calls == 0
        with manager.factory() as db:
            current = db.get(MCPConnection, row.id)
            assert current
            assert current.secret_id is None

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


@pytest.mark.parametrize("mode", [AuthMode.NONE, AuthMode.API_KEY, AuthMode.OAUTH_2_1])
def test_isolation_and_unsupported_scope(tmp_path: Path, mode: AuthMode) -> None:
    manager, who, server, engine = setup(tmp_path / "mcp.db", mode)
    try:
        row = asyncio.run(manager.create(who, "fixture", "One"))
        other = who.model_copy(update={"owner_id": uuid4()})
        with pytest.raises(Failure):
            manager.status(other, row.id)
        with pytest.raises(ValidationError):
            Context(owner_id=who.owner_id, session_hash=who.session_hash, scope="WORKSPACE")  # type: ignore[arg-type]
        assert not server.calls
    finally:
        engine.dispose()


def test_api_key_and_cleanup_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager, who, server, engine = setup(tmp_path / "mcp.db", AuthMode.API_KEY)

    async def exercise() -> None:
        row = await manager.create(who, "fixture", "Key")
        row = await manager.connect(who, row.id, 0, SecretStr("fixture-access-secret"))
        server.auth_required = True
        await manager.tools(who, row.id, row.generation)
        original = manager.delete_secret

        def broken(*args: object) -> None:
            raise OSError("sensitive storage error")

        monkeypatch.setattr(manager, "delete_secret", broken)
        row = await manager.disconnect(who, row.id, row.generation)
        assert row.cleanup_pending and not row.secret_ref
        with pytest.raises(Failure):
            await manager.tools(who, row.id, row.generation)
        monkeypatch.setattr(manager, "delete_secret", original)
        await manager.cleanup(who, row.id)
        assert not manager.status(who, row.id).cleanup_pending

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()
