from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from twf.config.settings import Settings
from twf.main import create_app
from twf.schemas import ErrorResponse


@pytest.mark.parametrize(
    "method,action,status",
    [
        ("post", "login", 401),
        ("post", "login", 403),
        ("post", "login", 429),
        ("post", "logout", 403),
        ("get", "me", 401),
    ],
)
def test_auth_errors_match_openapi(method: str, action: str, status: int) -> None:
    # The autouse fixture supplies an isolated database and clears deployment env.
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    app = create_app(Settings(cors_origins=("https://web.example",)))
    path = f"/api/v1/auth/{action}"
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
        contract = schema["paths"][path][method]["responses"][str(status)]
        assert contract["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }
        assert schema["components"]["schemas"]["ErrorResponse"]["properties"]["error"] == {
            "$ref": "#/components/schemas/ErrorDetail"
        }
        with patch.object(app.state.login_limit, "allow", return_value=status != 429):
            response = client.request(
                method,
                path,
                headers={
                    "Origin": "https://evil.example" if status == 403 else "https://web.example"
                },
                json={"username": "unknown", "password": "test-only-invalid-password"},
            )
        assert response.status_code == status
        body = response.json()
        assert ErrorResponse.model_validate(body).model_dump() == body
        assert body == {
            "error": {
                "code": f"HTTP_{status}",
                "message": HTTPStatus(status).phrase,
                "request_id": response.headers["X-Request-ID"],
                "details": None,
            }
        }
        assert "set-cookie" not in response.headers
        if status == 429:
            assert response.headers["Retry-After"] == "60"
