import asyncio
import io
import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

import httpx
import pytest
from fastapi import Depends, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from twf.api.dependencies import get_request_id, get_settings
from twf.config.settings import Settings
from twf.main import create_app
from twf.observability import JsonFormatter, request_id_context


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # No developer .env or inherited deployment settings control this fixture.
    monkeypatch.chdir(tmp_path)
    for key in (
        "ENVIRONMENT",
        "SERVICE_NAME",
        "SERVICE_VERSION",
        "API_PREFIX",
        "API_VERSION",
        "LOG_LEVEL",
        "CORS_ORIGINS",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(f"TWF_{key}", raising=False)
    monkeypatch.setenv("TWF_DATABASE_URL", "sqlite+pysqlite:///:memory:")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        service_name="test-api",
        service_version="1.2.3",
        cors_origins=("https://web.example",),
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)

    class Input(BaseModel):
        count: int

    @app.post("/test/validate")
    def validate(payload: Input) -> Input:
        return payload

    @app.get("/test/http-error")
    def http_error() -> None:
        raise HTTPException(429, detail="secret-http-detail", headers={"Retry-After": "7"})

    @app.get("/test/crash")
    def crash() -> None:
        raise RuntimeError("secret-exception-content")

    with TestClient(app) as test_client:
        yield test_client


def test_lifecycle_and_contracts(settings: Settings) -> None:
    app = create_app(settings)
    assert app.state.initialized is False
    # Missing lifespan startup must not claim readiness.
    assert TestClient(app).get("/ready").status_code == 503
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ready",
            "checks": "application_initialization_only",
            "satellite_dependencies_checked": False,
            "database_checked": False,
        }
        assert client.get("/api/v1/status").json() == {
            "service": "test-api",
            "version": "1.2.3",
            "api_version": "v1",
            "environment": "test",
            "status": "ok",
        }
        assert client.get("/api/v1/meta").json() == {
            "service_name": "test-api",
            "service_version": "1.2.3",
            "api_version": "v1",
            "environment": "test",
        }
        schema = client.get("/openapi.json").json()
        assert set(schema["paths"]) == {
            "/health",
            "/ready",
            "/api/v1/status",
            "/api/v1/services",
            "/api/v1/meta",
            "/api/v1/auth/login",
            "/api/v1/auth/logout",
            "/api/v1/auth/me",
            "/api/v1/settings/definitions",
            "/api/v1/settings/values",
            "/api/v1/settings/reset",
            "/api/v1/settings/deactivate",
            "/api/v1/settings/profiles",
            "/api/v1/settings/profiles/{profile_id}",
            "/api/v1/settings/profiles/{profile_id}/apply",
        }
        assert schema["info"]["version"] == "1.2.3"
        for route in schema["paths"].values():
            for operation in route.values():
                assert operation["responses"]["500"]["content"]["application/json"]["schema"][
                    "$ref"
                ].endswith("/ErrorResponse")
        assert client.get("/docs").status_code == 200
    assert app.state.initialized is False


@pytest.mark.parametrize("supplied", [None, "", "bad id", "x" * 65, "bad/segment", "line\nbreak"])
def test_invalid_ids_are_replaced(client: TestClient, supplied: str | None) -> None:
    headers = {} if supplied is None else {"X-Request-ID": supplied}
    response = client.get("/health", headers=headers)
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_supplied_normalized_and_duplicate_ids(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "  request-123_abc.xyz  "})
    assert response.headers["X-Request-ID"] == "request-123_abc.xyz"
    response = client.get("/health", headers=[("X-Request-ID", "one"), ("X-Request-ID", "two")])
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


@pytest.mark.parametrize(
    "path,status,code",
    [
        ("/missing", 404, "HTTP_404"),
        ("/test/http-error", 429, "HTTP_429"),
        ("/test/crash", 500, "INTERNAL_ERROR"),
    ],
)
def test_error_envelopes_and_cors(client: TestClient, path: str, status: int, code: str) -> None:
    response = client.get(
        path, headers={"X-Request-ID": "error-123", "Origin": "https://web.example"}
    )
    assert response.status_code == status
    assert response.headers["X-Request-ID"] == "error-123"
    assert response.headers["Access-Control-Allow-Origin"] == "https://web.example"
    error = response.json()["error"]
    assert set(error) == {"code", "message", "request_id", "details"}
    assert error["code"] == code and error["request_id"] == "error-123"
    assert error["details"] is None
    assert "secret" not in response.text and "Traceback" not in response.text
    if status == 429:
        assert response.headers["Retry-After"] == "7"


def test_validation_redacts_input_and_method_error(client: TestClient) -> None:
    response = client.post("/test/validate", json={"count": "secret-body"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
    assert "secret-body" not in response.text
    response = client.post("/health")
    assert response.status_code == 405
    assert "GET" in response.headers["Allow"]


def test_cors_preflight_and_rejection(client: TestClient) -> None:
    headers = {
        "Origin": "https://web.example",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "X-Request-ID",
    }
    response = client.options("/api/v1/status", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert response.headers["Access-Control-Allow-Origin"] == "https://web.example"
    assert "access-control-allow-credentials" not in response.headers
    headers["Origin"] = "https://untrusted.example"
    response = client.options("/health", headers=headers)
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    assert response.headers["X-Request-ID"]


def test_settings_environment_and_seams(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert Settings().allowed_origins == ("http://localhost:3000",)
    assert Settings(environment="production").allowed_origins == ()
    assert Settings(cors_origins=()).allowed_origins == ()
    monkeypatch.setenv("TWF_ENVIRONMENT", "production")
    monkeypatch.setenv("TWF_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("TWF_CORS_ORIGINS", '["https://cloud.example"]')
    loaded = Settings()
    assert loaded.allowed_origins == ("https://cloud.example",)
    assert loaded.effective_log_level == "WARNING"
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: loaded
    with TestClient(app) as client:
        assert client.get("/api/v1/status").json()["environment"] == "production"


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "null",
        "https://user:secret@example.com",
        "https://x/path",
        "https://x?token=secret",
        "https://x#fragment",
        "https://x:bad",
        "ftp://x",
    ],
)
def test_bad_cors_config_rejected(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(cors_origins=(origin,))


def test_concurrent_context_isolation_and_reset(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/test/context")
    async def context(
        request_id: Annotated[str | None, Depends(get_request_id)],
    ) -> dict[str, str | None]:
        await asyncio.sleep(0.001)
        return {"dependency": request_id, "context": request_id_context.get()}

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            responses = await asyncio.gather(
                *[
                    client.get("/test/context", headers={"X-Request-ID": f"request-{i}"})
                    for i in range(20)
                ]
            )
        for i, response in enumerate(responses):
            assert response.json() == {"dependency": f"request-{i}", "context": f"request-{i}"}
            assert response.headers["X-Request-ID"] == f"request-{i}"
        assert request_id_context.get() is None

    asyncio.run(exercise())


def test_structured_lifecycle_request_and_error_logs(settings: Settings) -> None:
    app = create_app(settings)
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonFormatter(settings))
    app.state.logger.handlers = [handler]

    @app.post("/test/failure/{value}")
    def failure(value: str) -> None:
        raise RuntimeError("secret-exception")

    with TestClient(app) as client:
        response = client.post(
            "/test/failure/secret-path?token=secret-query",
            headers={"X-Request-ID": "log-123", "Authorization": "secret-header"},
            content="secret-body",
        )
        assert response.status_code == 500
    raw = output.getvalue()
    assert "secret" not in raw
    records = [json.loads(line) for line in raw.splitlines()]
    assert [r["event"] for r in records] == [
        "application_started",
        "request_failed",
        "request_completed",
        "application_stopped",
    ]
    assert records[1]["request_id"] == records[2]["request_id"] == "log-123"
    assert records[2]["route"] == "/test/failure/{value}"
    assert records[2]["status_code"] == 500 and records[2]["duration_ms"] >= 0
    assert records[0]["request_id"] is None and records[3]["request_id"] is None
    assert create_app(Settings(log_level="ERROR")).state.logger.level == logging.ERROR
