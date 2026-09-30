import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from mcp_support import public_ip, setup
from pydantic import SecretStr, ValidationError
from sqlalchemy import select

from twf.infrastructure.mcp import MCPConnection, MCPSecret
from twf.integrations.mcp.client import validate_schema
from twf.integrations.mcp.contracts import AuthMode, Code, Failure, ProviderConfig, State
from twf.integrations.mcp.http import HTTPFactory, SafeTransport


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/mcp",
        "https://user:secret@site/mcp",
        "https://site/mcp?token=secret",
        "https://site/mcp#fragment",
        "https://site:22/mcp",
        "file:///etc/passwd",
        "https://site/\\evil",
        "https://site/%2fpath",
    ],
)
def test_configuration_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(provider_id="fixture", display_name="test", endpoint=url)


@pytest.mark.parametrize("address", ["127.0.0.1", "::1", "169.254.169.254", "10.0.0.1", "0.0.0.0"])
def test_transport_blocks_internal_dns(address: str) -> None:
    calls = 0

    async def resolver(host: str) -> tuple[str, ...]:
        return (address,)

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(200)

    async def exercise() -> None:
        async with httpx2.AsyncClient(
            transport=SafeTransport(
                frozenset({"https://provider.example/mcp"}),
                1024,
                inner=httpx2.MockTransport(handler),
                resolver=resolver,
            )
        ) as client:
            with pytest.raises(Failure) as caught:
                await client.get("https://provider.example/mcp")
            assert caught.value.code == Code.DENIED

    asyncio.run(exercise())
    assert calls == 0


def test_transport_pins_public_ip_and_rejects_redirect() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.host == "8.8.8.8"
        assert request.headers["Host"] == "provider.example"
        assert request.extensions["sni_hostname"] == "provider.example"
        return httpx2.Response(302, headers={"Location": "https://evil.example"})

    async def exercise() -> None:
        async with httpx2.AsyncClient(
            transport=SafeTransport(
                frozenset({"https://provider.example/mcp"}),
                1024,
                inner=httpx2.MockTransport(handler),
                resolver=public_ip,
            )
        ) as client:
            with pytest.raises(Failure):
                await client.get("https://provider.example/mcp")
            with pytest.raises(Failure):
                await client.get("https://evil.example")

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "$ref": "https://evil.example"},
        {"type": "object", "properties": {"x": {"pattern": "(a+)+"}}},
        {"type": "nonsense"},
    ],
)
def test_schema_never_resolves_remote_refs_or_unbounded_regex(schema: dict[str, object]) -> None:
    with pytest.raises(Failure) as caught:
        validate_schema(schema)  # type: ignore[arg-type]
    assert caught.value.code == Code.SCHEMA_MISMATCH


@pytest.mark.parametrize("round_number", range(5))
def test_only_one_concurrent_callback_exchanges(tmp_path: Path, round_number: int) -> None:
    manager, who, server, engine = setup(tmp_path / f"race-{round_number}.db", AuthMode.OAUTH_2_1)

    async def exercise() -> None:
        row = await manager.create(who, "fixture", "test")
        url = await manager.begin(who, row.id, row.generation)
        params = parse_qs(urlsplit(url.authorization_url).query)
        server.challenge = params["code_challenge"][0]
        results = await asyncio.gather(
            *(manager.callback(who, row.id, params["state"][0], "code") for _ in range(4)),
            return_exceptions=True,
        )
        failures = [r for r in results if isinstance(r, Failure)]
        assert len(failures) == 3 and all(f.code == Code.STALE for f in failures)
        assert server.token_calls == 1
        assert manager.status(who, row.id).state == State.CONNECTED

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


def test_disconnect_fences_inflight_token_and_retains_cleanup(tmp_path: Path) -> None:
    manager, who, server, engine = setup(tmp_path / "late.db", AuthMode.OAUTH_2_1)

    async def exercise() -> None:
        entered, release = asyncio.Event(), asyncio.Event()

        async def handler(request: httpx2.Request) -> httpx2.Response:
            if request.url.path == "/token":
                entered.set()
                await release.wait()
            if request.url.path == "/revoke":
                return httpx2.Response(503)
            return await server.handle(request)

        manager.oauth.http = HTTPFactory(lambda: httpx2.MockTransport(handler), public_ip)
        row = await manager.create(who, "fixture", "test")
        url = await manager.begin(who, row.id, 0)
        params = parse_qs(urlsplit(url.authorization_url).query)
        server.challenge = params["code_challenge"][0]
        work = asyncio.create_task(manager.callback(who, row.id, params["state"][0], "code"))
        await entered.wait()
        await manager.disconnect(who, row.id, url.generation)
        release.set()
        with pytest.raises(Failure) as caught:
            await work
        assert caught.value.code == Code.STALE
        status = manager.status(who, row.id)
        assert (
            status.state == State.DISCONNECTED and not status.secret_ref and status.cleanup_pending
        )
        with manager.factory() as db:
            secret = db.scalar(select(MCPSecret))
            assert secret and secret.revoked
        manager.oauth.http = manager.http
        await manager.cleanup(who, row.id)
        assert not manager.status(who, row.id).cleanup_pending

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


class SlowBody(httpx2.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        for _ in range(20):
            await asyncio.sleep(0.02)
            yield b" "


def test_token_total_deadline_streaming_leaves_no_binding(tmp_path: Path) -> None:
    manager, who, server, engine = setup(tmp_path / "slow.db", AuthMode.OAUTH_2_1)
    provider = manager.providers["fixture"].model_copy(update={"timeout_seconds": 0.08})
    manager.providers["fixture"] = provider

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, stream=SlowBody())

    manager.oauth.http = HTTPFactory(lambda: httpx2.MockTransport(handler), public_ip)

    async def exercise() -> None:
        row = await manager.create(who, "fixture", "test")
        auth = await manager.begin(who, row.id, 0)
        state = parse_qs(urlsplit(auth.authorization_url).query)["state"][0]
        with pytest.raises(Failure) as caught:
            await manager.callback(who, row.id, state, "code")
        assert caught.value.code == Code.TIMEOUT
        assert await manager.operations.drain()
        current = manager.status(who, row.id)
        assert current.state == State.REAUTH_REQUIRED and not current.secret_ref
        assert current.generation > auth.generation

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


def test_swapped_secret_reference_rejected(tmp_path: Path) -> None:
    manager, who, server, engine = setup(tmp_path / "swap.db", AuthMode.API_KEY)

    async def exercise() -> None:
        a = await manager.create(who, "fixture", "a")
        b = await manager.create(who, "fixture", "b")
        a = await manager.connect(who, a.id, 0, SecretStr("one"))
        b = await manager.connect(who, b.id, 0, SecretStr("two"))
        assert b.secret_ref
        with manager.factory() as db:
            row = db.get(MCPConnection, a.id)
            assert row
            row.secret_id = b.secret_ref.reference_id
            db.commit()
        with pytest.raises(Failure) as caught:
            await manager.tools(who, a.id, a.generation)
        assert caught.value.code == Code.REVOKED and not server.calls

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "status,code",
    [
        (401, Code.AUTH_REQUIRED),
        (403, Code.AUTH_REQUIRED),
        (429, Code.RATE_LIMITED),
        (503, Code.UNAVAILABLE),
    ],
)
def test_sdk_transport_error_mapping(tmp_path: Path, status: int, code: Code) -> None:
    manager, who, server, engine = setup(tmp_path / "errors.db")

    async def exercise() -> None:
        row = await manager.create(who, "fixture", "test")
        row = await manager.connect(who, row.id, 0)
        server.status = status
        with pytest.raises(Failure) as caught:
            await manager.tools(who, row.id, row.generation)
        assert caught.value.code == code
        if status == 429:
            assert caught.value.retry_after == 12

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


def test_sdk_malformed_tool_discovery(tmp_path: Path) -> None:
    manager, who, server, engine = setup(tmp_path / "bad.db")

    async def exercise() -> None:
        row = await manager.create(who, "fixture", "test")
        row = await manager.connect(who, row.id, 0)
        server.bad_tools = True
        with pytest.raises(Failure) as caught:
            await manager.tools(who, row.id, row.generation)
        assert caught.value.code == Code.SCHEMA_MISMATCH

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()
