import asyncio
import io
import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from twf.api.dependencies import get_db_session
from twf.auth import create_user
from twf.config.settings import Settings
from twf.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from twf.integrations.adapters import (
    LocalAdapter,
    RemoteAdapter,
    SyntheticLLMService,
    SyntheticScannerService,
    SyntheticTIService,
    SyntheticTMService,
)
from twf.integrations.config import ServiceDescriptor
from twf.integrations.contracts import (
    CONTRACT_VERSION,
    DeploymentMode,
    ErrorCode,
    Health,
    HealthResult,
    RequestContext,
    ServiceClient,
    ServiceFailure,
)
from twf.integrations.registry import ServiceRegistry
from twf.main import create_app
from twf.observability import JsonFormatter

ORIGIN = "https://satellite.test"
IDENTITY = SyntheticTIService().identity
CONTEXT = RequestContext(request_id="service-test-1")


def descriptor(mode: DeploymentMode = DeploymentMode.REMOTE, **kwargs: Any) -> ServiceDescriptor:
    return ServiceDescriptor(
        identity=IDENTITY,
        mode=mode,
        enabled=True,
        endpoint=ORIGIN if mode == DeploymentMode.REMOTE else None,
        **kwargs,
    )


def payload() -> dict[str, Any]:
    return HealthResult(
        identity=IDENTITY,
        request_id=CONTEXT.request_id,
        health=Health.AVAILABLE,
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
        synthetic=True,
    ).model_dump(mode="json")


def remote(handler: Any, **kwargs: Any) -> RemoteAdapter:
    return RemoteAdapter(
        descriptor(**kwargs), allowed_origins=(ORIGIN,), transport=httpx.MockTransport(handler)
    )


@pytest.mark.parametrize("mode", list(DeploymentMode))
def test_equivalent_contract_and_registry(mode: DeploymentMode) -> None:
    fixture = SyntheticTIService()
    client: ServiceClient
    if mode == DeploymentMode.LOCAL:
        client = LocalAdapter(IDENTITY, fixture.health)
    elif mode == DeploymentMode.SYNTHETIC:
        client = fixture
    else:
        client = remote(lambda _: httpx.Response(200, json=payload()))
    registry = ServiceRegistry((descriptor(mode),), allowed_origins=(ORIGIN,), clients=(client,))
    result = asyncio.run(registry.statuses(uuid4(), CONTEXT, logging.getLogger("test")))[0]
    assert result.health == Health.AVAILABLE
    assert result.configured and result.enabled and result.active
    assert result.observation is not None
    assert result.observation.request_id == CONTEXT.request_id
    assert result.observation.identity == IDENTITY
    assert result.observation.synthetic  # Provenance survives even a local/remote test fixture.
    assert result.observation.as_of == datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "factory",
    [SyntheticScannerService, SyntheticTIService, SyntheticTMService, SyntheticLLMService],
)
def test_synthetic_families_are_deterministic(factory: Any) -> None:
    client = factory()
    assert asyncio.run(client.health(CONTEXT)) == asyncio.run(client.health(CONTEXT))
    assert asyncio.run(client.health(CONTEXT)).synthetic


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, ErrorCode.AUTHENTICATION_FAILED),
        (403, ErrorCode.AUTHORIZATION_FAILED),
        (503, ErrorCode.SERVICE_UNAVAILABLE),
        (500, ErrorCode.REMOTE_ERROR),
        (302, ErrorCode.REMOTE_ERROR),
        (404, ErrorCode.REMOTE_ERROR),
    ],
)
def test_http_failures_are_safe(status: int, code: ErrorCode) -> None:
    client = remote(
        lambda _: httpx.Response(status, text="private-secret", headers={"Location": ORIGIN})
    )
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(client.health(CONTEXT))
    assert failure.value.code == code
    assert "private-secret" not in str(failure.value)


@pytest.mark.parametrize("failure", ["timeout", "connection", "deadline"])
def test_transport_failures_and_total_deadline(failure: str) -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("private-secret")
        if failure == "connection":
            raise httpx.ConnectError("private-secret")
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    with pytest.raises(ServiceFailure) as caught:
        asyncio.run(remote(respond, timeout_seconds=0.1).health(CONTEXT))
    assert caught.value.code == (
        ErrorCode.SERVICE_UNAVAILABLE if failure == "connection" else ErrorCode.TIMEOUT
    )
    assert "private-secret" not in str(caught.value)


@pytest.mark.parametrize(
    "case", ["json", "shape", "version", "correlation", "identity", "large", "type"]
)
def test_invalid_wire_responses(case: str) -> None:
    data = payload()
    if case == "version":
        data["identity"]["contract_version"] = "foundation.health.v2"
    elif case == "correlation":
        data["request_id"] = "other"
    elif case == "identity":
        data["identity"]["service_id"] = "other"
    elif case == "shape":
        data = {"secret": "private-secret"}
    elif case == "type":
        data["synthetic"] = "yes"
    response = httpx.Response(200, json=data)
    if case == "json":
        response = httpx.Response(200, content=b"{", headers={"content-type": "application/json"})
    elif case == "large":
        response = httpx.Response(200, json={"oversize": "x" * 17000})
    with pytest.raises(ServiceFailure) as caught:
        asyncio.run(remote(lambda _: response).health(CONTEXT))
    assert caught.value.code == (
        ErrorCode.CONTRACT_MISMATCH if case == "version" else ErrorCode.INVALID_RESPONSE
    )


def test_header_allowlist_cookie_isolation_and_no_redirect() -> None:
    seen: list[httpx.Request] = []
    data = payload()

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=data, headers={"Set-Cookie": "satellite=secret"})

    client = remote(respond)
    asyncio.run(client.health(CONTEXT))
    asyncio.run(client.health(CONTEXT))
    assert len(seen) == 2
    for request in seen:
        assert str(request.url) == ORIGIN + "/health"
        assert request.headers["x-request-id"] == CONTEXT.request_id
        assert request.headers["x-twf-contract-version"] == CONTRACT_VERSION
        assert not {"cookie", "authorization", "origin", "x-user-id", "x-tenant-id"} & set(
            request.headers
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        "file:///etc/passwd",
        "https://u:secret@host.test",
        "https://host.test/path",
        "https://host.test?q=secret",
        "https://host.test#secret",
        "https://host.test\n",
        "https://host.test:bad",
        "http://169.254.169.254",
        "https://host\\evil.test",
        "https://host.test%2fother",
        "https://[::]",
        "https://bad_host",
        "https://host.test:0",
        "https://host..test",
    ],
)
def test_rejects_unsafe_endpoints_without_rendering_input(endpoint: str) -> None:
    with pytest.raises((ValueError, ValidationError)) as caught:
        ServiceDescriptor(identity=IDENTITY, mode=DeploymentMode.REMOTE, endpoint=endpoint)
    assert "secret" not in str(caught.value)


def test_operator_policy_and_production_guards() -> None:
    with pytest.raises(ValueError):
        Settings(service_clients=(descriptor(),))
    Settings(service_clients=(descriptor(),), service_allowed_origins=(ORIGIN,))
    with pytest.raises(ValueError):
        Settings(environment="production", service_clients=(descriptor(DeploymentMode.SYNTHETIC),))
    http_descriptor = descriptor().model_copy(update={"endpoint": "http://satellite.test"})
    with pytest.raises(ValueError):
        Settings(
            environment="production",
            service_clients=(http_descriptor,),
            service_allowed_origins=("http://satellite.test",),
        )
    with pytest.raises(ValueError):
        Settings(service_clients=(descriptor(), descriptor()), service_allowed_origins=(ORIGIN,))
    for timeout in [0, 11, float("nan"), float("inf")]:
        with pytest.raises(ValidationError):
            descriptor(timeout_seconds=timeout)


def test_disabled_inactive_and_denied_are_not_healthy() -> None:
    for desc in [
        descriptor(DeploymentMode.LOCAL),
        descriptor(DeploymentMode.SYNTHETIC).model_copy(update={"enabled": False}),
    ]:
        registry = ServiceRegistry((desc,))
        status = asyncio.run(registry.statuses(uuid4(), CONTEXT, logging.getLogger("test")))[0]
        assert status.configured and not status.active and status.health == Health.UNKNOWN
        assert status.observation is None
        for service_id, capability in [
            ("unknown", "foundation.health"),
            (IDENTITY.service_id, "trade"),
        ]:
            with pytest.raises(ServiceFailure) as caught:
                registry.require(uuid4(), service_id, capability)
            assert caught.value.code == ErrorCode.UNSUPPORTED_CAPABILITY

    class Deny:
        def allows(self, user_id: UUID, service_id: str, capability: str) -> bool:
            return False

    registry = ServiceRegistry((descriptor(DeploymentMode.SYNTHETIC),), policy=Deny())
    denied = asyncio.run(registry.statuses(uuid4(), CONTEXT, logging.getLogger("test")))[0]
    assert denied.error == ErrorCode.AUTHORIZATION_FAILED and denied.observation is None


def test_correlation_bounds() -> None:
    assert len(RequestContext().request_id) == 32
    for value in ["x" * 65, "unsafe\nheader", "", " spaces "]:
        with pytest.raises(ValidationError):
            RequestContext(request_id=value)


def test_authenticated_api_releases_transaction_and_isolates_downstream_failure() -> None:
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    engine = create_database_engine(Settings())
    factory = create_session_factory(engine)
    with session_scope(factory) as session:
        create_user(session, "serviceuser", "Service user", "test-only-service-password")
        session.commit()
    sessions: list[Session] = []
    transaction_states: list[bool] = []

    def dependency() -> Iterator[Session]:
        with session_scope(factory) as session:
            sessions.append(session)
            yield session

    async def fail(context: RequestContext) -> HealthResult:
        transaction_states.extend(session.in_transaction() for session in sessions)
        raise RuntimeError("private-secret")

    registry = ServiceRegistry(
        (descriptor(DeploymentMode.LOCAL),), clients=(LocalAdapter(IDENTITY, fail),)
    )
    app = create_app(
        Settings(cors_origins=("https://web.test",)),
        engine_factory=lambda _: engine,
        service_registry=registry,
    )
    app.dependency_overrides[get_db_session] = dependency
    with TestClient(app) as client:
        denied = client.get("/api/v1/services")
        assert denied.status_code == 401 and denied.json()["error"]["request_id"]
        assert client.get("/ready").status_code == 200
        login = client.post(
            "/api/v1/auth/login",
            headers={"origin": "https://web.test"},
            json={"username": "serviceuser", "password": "test-only-service-password"},
        )
        assert login.status_code == 200
        response = client.get("/api/v1/services", headers={"X-Request-ID": CONTEXT.request_id})
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        status = response.json()["services"][0]
        assert status["health"] == "UNAVAILABLE" and status["error"] == "SERVICE_UNAVAILABLE"
        assert transaction_states and not any(transaction_states)
        assert "private-secret" not in response.text
        assert client.get("/ready").status_code == 200


def test_safe_observability_and_unknown_exception_mapping() -> None:
    output = io.StringIO()
    logger = logging.Logger("service-test")
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonFormatter(Settings()))
    logger.addHandler(handler)

    async def fail(context: RequestContext) -> HealthResult:
        raise RuntimeError("private-secret")

    registry = ServiceRegistry(
        (descriptor(DeploymentMode.LOCAL),), clients=(LocalAdapter(IDENTITY, fail),)
    )
    asyncio.run(registry.statuses(uuid4(), CONTEXT, logger))
    record = json.loads(output.getvalue())
    assert record["operation_request_id"] == CONTEXT.request_id
    assert record["service_id"] == IDENTITY.service_id
    assert record["operation"] == "foundation.health"
    assert record["outcome"] == "SERVICE_UNAVAILABLE" and record["duration_ms"] >= 0
    assert "private-secret" not in output.getvalue() and ORIGIN not in output.getvalue()


def test_real_loopback_http_and_socket_timeout() -> None:
    async def scenario() -> None:
        seen: list[str] = []

        async def respond(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                request = await reader.readuntil(b"\r\n\r\n")
                seen.append(request.decode("ascii"))
                body = json.dumps(payload()).encode()
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                    + str(len(body)).encode()
                    + b"\r\nConnection: close\r\n\r\n"
                    + body
                )
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(respond, "127.0.0.1", 0)
        async with server:
            port = server.sockets[0].getsockname()[1]
            origin = f"http://127.0.0.1:{port}"
            desc = ServiceDescriptor(
                identity=IDENTITY, mode=DeploymentMode.REMOTE, endpoint=origin, enabled=True
            )
            result = await RemoteAdapter(desc, allowed_origins=(origin,)).health(CONTEXT)
            assert result.health == Health.AVAILABLE
        assert len(seen) == 1 and "X-Request-ID: service-test-1" in seen[0]
        assert "Cookie:" not in seen[0] and "Authorization:" not in seen[0]

        async def stall(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                await reader.read()  # Ends when the timed-out client closes its socket.
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(stall, "127.0.0.1", 0)
        async with server:
            origin = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
            desc = ServiceDescriptor(
                identity=IDENTITY, mode=DeploymentMode.REMOTE, endpoint=origin, timeout_seconds=0.1
            )
            with pytest.raises(ServiceFailure) as caught:
                await RemoteAdapter(desc, allowed_origins=(origin,)).health(CONTEXT)
            assert caught.value.code == ErrorCode.TIMEOUT

    asyncio.run(scenario())
