import io
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from twf.auth import create_user, token_digest
from twf.bootstrap import main as bootstrap
from twf.config.settings import Settings
from twf.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from twf.infrastructure.identity import AuthSession, User
from twf.main import create_app
from twf.observability import JsonFormatter

PASSWORD = "test-only-strong-password"
ORIGIN = "https://web.example"


@pytest.fixture
def client() -> Iterator[TestClient]:
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    engine = create_database_engine(Settings())
    with session_scope(create_session_factory(engine)) as session:
        create_user(session, "Alice", "Alice Trader", PASSWORD)
        inactive = create_user(session, "disabled", "Inactive", PASSWORD)
        inactive.is_active = False
        session.commit()
    with TestClient(
        create_app(Settings(cors_origins=(ORIGIN,)), engine_factory=lambda _: engine)
    ) as test:
        yield test


def login(client: TestClient, username: str = "ALICE", password: str = PASSWORD) -> object:
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": ORIGIN},
    )


def test_login_me_logout_and_replay(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401
    response = client.post(
        "/api/v1/auth/login",
        json={"username": " ALICE ", "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200
    assert set(response.json()) == {"id", "username", "display_name"}
    assert response.json()["username"] == "alice"
    assert client.get("/api/v1/auth/me").json() == response.json()
    cookie = client.cookies.get("twf_session")
    assert cookie and "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert "Secure" not in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    with session_scope(cast(FastAPI, client.app).state.session_factory) as session:
        stored = session.get(AuthSession, token_digest(cookie))
        assert stored and stored.token_hash != cookie
        user = session.scalar(select(User).where(User.username == "alice"))
        assert user and user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash
    assert client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN}).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set("twf_session", cookie)
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize(
    "username,password", [("unknown", PASSWORD), ("alice", "wrong"), ("disabled", PASSWORD)]
)
def test_failed_credentials_are_indistinguishable(
    client: TestClient, username: str, password: str
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Unauthorized"
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("origin", [None, "null", "https://evil.example"])
@pytest.mark.parametrize("action", ["login", "logout"])
def test_csrf_rejected(client: TestClient, origin: str | None, action: str) -> None:
    response = client.post(
        f"/api/v1/auth/{action}",
        json={"username": "alice", "password": PASSWORD},
        headers={"Origin": origin} if origin else {},
    )
    assert response.status_code == 403


def test_expiration_inactive_and_rotation(client: TestClient) -> None:
    login(client)
    original = client.cookies.get("twf_session")
    assert original is not None
    login(client)
    current = client.cookies.get("twf_session")
    assert current is not None
    assert original != current
    with session_scope(cast(FastAPI, client.app).state.session_factory) as session:
        old_session = session.get(AuthSession, token_digest(original))
        assert old_session and old_session.revoked_at is not None
        stored = session.get(AuthSession, token_digest(current))
        assert stored
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    assert client.get("/api/v1/auth/me").status_code == 401
    login(client)
    with session_scope(cast(FastAPI, client.app).state.session_factory) as session:
        user = session.scalar(select(User).where(User.username == "alice"))
        assert user
        user.is_active = False
        session.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_unique_user_and_password_policy(client: TestClient) -> None:
    with session_scope(cast(FastAPI, client.app).state.session_factory) as session:
        with pytest.raises(ValueError):
            create_user(session, "valid", "Valid", "short")
        with pytest.raises(IntegrityError):
            create_user(session, "ALICE", "Duplicate", PASSWORD)


def test_auth_logging_redacts_secrets(client: TestClient) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(Settings()))
    cast(FastAPI, client.app).state.logger.handlers = [handler]
    login(client)
    token = client.cookies.get("twf_session")
    assert token is not None
    login(client, "unknown")
    login(client, "disabled")
    client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN})
    output = stream.getvalue()
    assert PASSWORD not in output and token not in output and "$argon2" not in output
    for name in (
        "auth_login_succeeded",
        "auth_login_failed",
        "auth_inactive_rejected",
        "auth_logout",
    ):
        assert name in output


def test_production_cookie_and_bootstrap_guard(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    with TestClient(
        create_app(Settings(environment="production", cors_origins=(ORIGIN,)))
    ) as production:
        response = production.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": PASSWORD},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert cookie.startswith("__Host-twf_session=")
        assert "Secure" in cookie and "HttpOnly" in cookie and "Path=/" in cookie
        assert "Domain=" not in cookie
    monkeypatch.setenv("TWF_ENVIRONMENT", "production")
    with (
        patch("sys.argv", ["bootstrap", "--username", "test", "--display-name", "Test"]),
        patch("twf.bootstrap.getpass") as prompt,
    ):
        with pytest.raises(SystemExit) as error:
            bootstrap()
        assert error.value.code == 2
        prompt.assert_not_called()


def test_bootstrap_creates_once(client: TestClient) -> None:
    with (
        patch("sys.argv", ["bootstrap", "--username", "newuser", "--display-name", "New User"]),
        patch("twf.bootstrap.getpass", return_value=PASSWORD),
    ):
        bootstrap()
        with pytest.raises(SystemExit):
            bootstrap()
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "newuser", "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200


def test_hash_verification() -> None:
    encoded = PasswordHasher().hash(PASSWORD)
    assert PasswordHasher().verify(encoded, PASSWORD)
