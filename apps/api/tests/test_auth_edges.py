from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError

from twf.auth import create_user
from twf.config.settings import Settings
from twf.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from twf.login_limit import LoginLimit
from twf.main import create_app


def test_concurrent_sqlite_logins_and_logout() -> None:
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    engine = create_database_engine(Settings())
    with session_scope(create_session_factory(engine)) as session:
        create_user(session, "parallel", "Parallel User", "test-only-parallel-password")
        session.commit()
    app = create_app(
        Settings(cors_origins=("https://web.example",)), engine_factory=lambda _: engine
    )
    with TestClient(app):

        def exercise(_: int) -> None:
            # Separate clients/cookie jars share the same app and file database.
            client = TestClient(app)
            response = client.post(
                "/api/v1/auth/login",
                headers={"Origin": "https://web.example"},
                json={"username": "parallel", "password": "test-only-parallel-password"},
            )
            assert response.status_code == 200
            assert client.get("/api/v1/auth/me").status_code == 200
            assert (
                client.post(
                    "/api/v1/auth/logout", headers={"Origin": "https://web.example"}
                ).status_code
                == 200
            )
            assert client.get("/api/v1/auth/me").status_code == 401
            client.close()

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(exercise, range(8)))


def test_login_budget_rejects_and_resets() -> None:
    limit = LoginLimit()
    with patch("twf.login_limit.monotonic", return_value=0):
        assert all(limit.allow("peer") for _ in range(60))
        assert not limit.allow("peer")
        assert limit.allow("another-peer")
    with patch("twf.login_limit.monotonic", return_value=61):
        assert limit.allow("peer")


def test_production_origins_and_session_duration_validation() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", cors_origins=("http://web.example",))
    for ttl in (0, 59, 604801):
        with pytest.raises(ValidationError):
            Settings(session_ttl_seconds=ttl)
    assert Settings(environment="production").allowed_origins == ()
