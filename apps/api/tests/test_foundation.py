from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, text

from twf import __version__
from twf.config.settings import Settings
from twf.infrastructure.database import Base, create_database_engine, create_session_factory
from twf.main import create_app


@pytest.fixture(autouse=True)
def test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWF_ENVIRONMENT", "test")
    monkeypatch.setenv("TWF_DATABASE_URL", "sqlite+pysqlite:///:memory:")


def test_health_and_status() -> None:
    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        status = client.get("/api/v1/status")
        assert status.status_code == 200
        assert status.json() == {
            "service": "twf-api",
            "version": __version__,
            "environment": "test",
            "api_version": "v1",
            "status": "ok",
        }


@pytest.mark.parametrize("environment", ["development", "test", "production"])
def test_environment_configuration(environment: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWF_ENVIRONMENT", environment)
    assert Settings().environment == environment


def test_invalid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWF_ENVIRONMENT", "invalid")
    with pytest.raises(ValidationError):
        Settings()


def test_application_settings_are_isolated() -> None:
    with (
        TestClient(create_app(Settings(environment="production"))) as production,
        TestClient(create_app(Settings(environment="test"))) as testing,
    ):
        assert production.get("/api/v1/status").json()["environment"] == "production"
        assert testing.get("/api/v1/status").json()["environment"] == "test"


def test_database_boundary() -> None:
    engine = create_database_engine(Settings())
    try:
        with create_session_factory(engine)() as session:
            assert session.scalar(text("SELECT 1")) == 1
        assert set(Base.metadata.tables) == {
            "users",
            "auth_sessions",
            "user_preferences",
            "preference_profiles",
            "preference_changes",
            "broker_provider_configurations",
            "broker_accounts",
            "broker_connections",
            "broker_audit_events",
        }
        assert not inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_empty_migration_foundation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWF_DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'migration.db'}")
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, "base")
    engine = create_database_engine(Settings())
    try:
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    finally:
        engine.dispose()
