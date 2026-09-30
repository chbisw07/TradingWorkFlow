"""Socket-free synthetic OAuth/MCP server exercising the actual official SDK."""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs
from uuid import uuid4

import httpx2
from cryptography.fernet import Fernet
from pydantic import JsonValue, SecretStr
from sqlalchemy import Engine

from twf.config.settings import Settings
from twf.infrastructure.database import Base, create_database_engine, create_session_factory
from twf.infrastructure.identity import AuthSession, User
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import AuthMode, Context, OAuthConfig, ProviderConfig
from twf.integrations.mcp.http import HTTPFactory


async def public_ip(host: str) -> tuple[str, ...]:
    return ("8.8.8.8",)


class SyntheticServer:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.challenge: str | None = None
        self.token_calls = 0
        self.auth_required = False
        self.status = 200
        self.bad_tools = False
        self.expiry = 3600
        self.revoked = 0
        self.closed = 0

    async def handle(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path == "/token":
            self.token_calls += 1
            data = parse_qs((await request.aread()).decode())
            if data["grant_type"] == ["authorization_code"]:
                assert data["resource"] == ["https://provider.example/mcp"]
                challenge = (
                    base64.urlsafe_b64encode(
                        hashlib.sha256(data["code_verifier"][0].encode()).digest()
                    )
                    .rstrip(b"=")
                    .decode()
                )
                assert self.challenge == challenge
            else:
                assert data["refresh_token"] == ["fixture-refresh-secret"]
            return httpx2.Response(
                self.status,
                json={
                    "access_token": "fixture-access-secret",
                    "refresh_token": "fixture-refresh-secret",
                    "token_type": "Bearer",
                    "expires_in": self.expiry,
                },
            )
        if path == "/revoke":
            self.revoked += 1
            return httpx2.Response(self.status)
        assert path == "/mcp"
        if self.status != 200:
            return httpx2.Response(self.status, headers={"Retry-After": "12"})
        if (
            self.auth_required
            and request.headers.get("authorization") != "Bearer fixture-access-secret"
        ):
            return httpx2.Response(401)
        if request.method == "DELETE":
            self.closed += 1
            return httpx2.Response(200)
        if request.method == "GET":
            return httpx2.Response(405)
        message = json.loads(await request.aread())
        method = message["method"]
        self.calls.append(method)
        if "id" not in message:
            return httpx2.Response(202)
        result: dict[str, JsonValue]
        if method == "initialize":
            result = {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "synthetic", "version": "1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": name,
                        "inputSchema": {
                            "type": "object",
                            "properties": {"value": {"type": "integer"}},
                            "required": ["value"],
                            "additionalProperties": False,
                        },
                    }
                    for name in ("read_demo", "write_demo")
                ]
            }
            if self.bad_tools:
                result = {"tools": [{"inputSchema": {}}]}
        elif method == "tools/call":
            assert message["params"]["name"] == "read_demo"
            result = {"content": [{"type": "text", "text": "synthetic result"}], "isError": False}
        else:
            raise AssertionError(method)
        return httpx2.Response(
            200,
            headers={"Mcp-Session-Id": "synthetic-session"},
            json={"jsonrpc": "2.0", "id": message["id"], "result": result},
        )


def setup(
    path: Path, mode: AuthMode = AuthMode.NONE
) -> tuple[ConnectionManager, Context, SyntheticServer, Engine]:
    settings = Settings(
        database_url=f"sqlite+pysqlite:///{path}",
        credential_master_key=SecretStr(Fernet.generate_key().decode()),
    )
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    now = datetime.now(UTC)
    owner = uuid4()
    context = Context(owner_id=owner, session_hash="a" * 64)
    with factory() as db:
        db.add(
            User(
                id=owner,
                username="test-mcp",
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
                token_hash=context.session_hash,
                user_id=owner,
                created_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        db.commit()
    oauth = (
        OAuthConfig(
            issuer="https://provider.example",
            authorization_endpoint="https://provider.example/authorize",
            token_endpoint="https://provider.example/token",
            revocation_endpoint="https://provider.example/revoke",
            client_id="fixture-client",
            redirect_uri="https://twf.example/mcp/callback",
        )
        if mode == AuthMode.OAUTH_2_1
        else None
    )
    provider = ProviderConfig(
        provider_id="fixture",
        display_name="Synthetic MCP",
        endpoint="https://provider.example/mcp",
        auth_mode=mode,
        oauth=oauth,
        timeout_seconds=1,
    )
    server = SyntheticServer()
    http = HTTPFactory(lambda: httpx2.MockTransport(server.handle), public_ip)
    manager = ConnectionManager(factory, settings, (provider,), http=http)
    return manager, context, server, engine
