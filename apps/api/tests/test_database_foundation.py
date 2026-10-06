import io
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, ForeignKey, Integer, String, event, inspect, select, text
from sqlalchemy.exc import IntegrityError, InvalidRequestError, OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from twf.api.dependencies import get_db_session
from twf.config.settings import Settings
from twf.infrastructure.database import (
    Base,
    create_database_engine,
    create_session_factory,
    probe_database,
    session_scope,
)
from twf.main import create_app


# Proof objects never register with production metadata.
class ProofBase(DeclarativeBase):
    pass


class Proof(ProofBase):
    __tablename__ = "persistence_proof"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    value: Mapped[str] = mapped_column(String(40), unique=True)


class Child(ProofBase):
    __tablename__ = "persistence_child"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    parent_id: Mapped[int] = mapped_column(ForeignKey("persistence_proof.id"))


@pytest.fixture
def engine() -> Iterator[Engine]:
    instance = create_database_engine(Settings())
    ProofBase.metadata.create_all(instance)  # Test-only schema, never application startup.
    try:
        yield instance
    finally:
        instance.dispose()


def test_settings_default_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TWF_DATABASE_URL")
    assert Settings().database_url == "sqlite+pysqlite:///./twf.db"
    monkeypatch.setenv("TWF_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    assert Settings(environment="test").database_url.endswith(":memory:")
    value = "postgresql://placeholder:credential_marker_123@db.invalid:5432/twf"
    monkeypatch.setenv("TWF_DATABASE_URL", value)
    settings = Settings(environment="production")
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "secret" not in repr(settings)
    pg = create_database_engine(settings)
    try:
        assert pg.dialect.name == "postgresql" and pg.dialect.driver == "psycopg"
        assert pg.echo is False and pg.hide_parameters is True
        # No connection to db.invalid is attempted by construction.
    finally:
        pg.dispose()


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url-secret",
        "mysql://user:secret@host/db",
        "postgresql+asyncpg://user:secret@host/db",
        "postgresql://user:secret@host",
        "sqlite://user:secret@host/db",
        "sqlite:///db?uri=true",
        "postgresql://user:secret@host:bad/db",
    ],
)
def test_invalid_production_configuration_is_safe(url: str) -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(environment="production", database_url=url)
    assert "secret" not in str(caught.value)


def test_lazy_engine_and_app_lifecycle(tmp_path: Path) -> None:
    path = tmp_path / "lazy.db"
    settings = Settings(database_url=f"sqlite+pysqlite:///{path}")
    created: list[Engine] = []
    disposed = Mock()

    def factory(config: Settings) -> Engine:
        db = create_database_engine(config)
        event.listen(db, "engine_disposed", disposed)
        created.append(db)
        return db

    app = create_app(settings, engine_factory=factory)
    assert not created and not path.exists()
    with TestClient(app) as client:
        assert len(created) == 1 and not path.exists()
        assert client.get("/ready").json()["database_checked"] is False
        assert not path.exists()  # Neither startup nor readiness connects/migrates.
        assert probe_database(created[0])
        assert inspect(created[0]).get_table_names() == []
    disposed.assert_called_once()
    assert app.state.session_factory is None and app.state.database_engine is None


def test_memory_connection_is_shared_across_threads() -> None:
    from concurrent.futures import ThreadPoolExecutor

    db = create_database_engine(Settings(database_url="sqlite+pysqlite:///:memory:"))
    try:
        assert isinstance(db.pool, StaticPool)
        ProofBase.metadata.create_all(db)
        with session_scope(create_session_factory(db)) as session:
            session.add(Proof(id=1, value="shared"))
            session.commit()

        def read() -> str | None:
            with session_scope(create_session_factory(db)) as session:
                return session.scalar(select(Proof.value))

        with ThreadPoolExecutor(max_workers=1) as executor:
            assert executor.submit(read).result() == "shared"
    finally:
        db.dispose()


def test_session_commit_rollback_and_close(engine: Engine) -> None:
    factory = create_session_factory(engine)
    with session_scope(factory) as first, session_scope(factory) as second:
        assert first is not second
        row = Proof(id=1, value="committed")
        first.add(row)
        assert first.autoflush is False and first.expire_on_commit is False
        first.commit()
        assert row.value == "committed"
    with pytest.raises(InvalidRequestError):
        first.execute(select(Proof))
    with session_scope(factory) as session:
        assert session.scalar(select(Proof.value)) == "committed"
        session.add(Proof(id=2, value="uncommitted"))
        session.flush()  # Normal dependency exit must roll this back too.
    with pytest.raises(RuntimeError), session_scope(factory) as session:
        session.add(Proof(id=3, value="failed"))
        session.flush()
        raise RuntimeError("test failure")
    with session_scope(factory) as session:
        assert list(session.scalars(select(Proof.id))) == [1]


def test_sqlite_foreign_keys_and_failed_transaction(engine: Engine) -> None:
    factory = create_session_factory(engine)
    with pytest.raises(IntegrityError), session_scope(factory) as session:
        session.add(Child(id=1, parent_id=999))
        session.flush()
    with session_scope(factory) as session:
        assert list(session.scalars(select(Child))) == []
        session.add(Proof(id=1, value="valid"))
        session.commit()
    with pytest.raises(IntegrityError), session_scope(factory) as session:
        session.add(Proof(id=2, value="valid"))
        session.commit()
    with session_scope(factory) as session:
        assert list(session.scalars(select(Proof.id))) == [1]


def test_dependency_request_cleanup_and_error_redaction(engine: Engine) -> None:
    app = create_app(Settings(), engine_factory=lambda _: engine)
    captured: list[Session] = []

    @app.post("/test/write/{mode}")
    def write(mode: str, session: Annotated[Session, Depends(get_db_session)]) -> dict[str, bool]:
        captured.append(session)
        session.add(Proof(id=len(captured), value=mode))
        session.flush()
        if mode == "fail":
            raise OperationalError("secret-sql", {}, Exception("secret-credentials"))
        if mode == "commit":
            session.commit()
        return {"ok": True}

    with TestClient(app) as client:
        assert client.post("/test/write/commit").status_code == 200
        assert client.post("/test/write/uncommitted").status_code == 200
        response = client.post("/test/write/fail", headers={"X-Request-ID": "db-error"})
        assert response.status_code == 500 and "secret" not in response.text
        assert response.json()["error"]["request_id"] == "db-error"
        with session_scope(create_session_factory(engine)) as session:
            assert list(session.scalars(select(Proof.value))) == ["commit"]
        for session in captured:
            with pytest.raises(InvalidRequestError):
                session.execute(text("SELECT 1"))


def test_probe_failure_safe_and_ready_unchanged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    settings = Settings(database_url=f"sqlite+pysqlite:///{tmp_path / 'missing' / 'secret.db'}")
    engine = create_database_engine(settings)
    try:
        assert probe_database(engine) is False
        assert "secret" not in caplog.text
    finally:
        engine.dispose()
    with TestClient(create_app(settings)) as client:
        assert client.get("/ready").status_code == 200
        assert client.get("/ready").json()["database_checked"] is False


def test_migration_history_and_metadata() -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    assert set(Base.metadata.tables) == {
        "users",
        "auth_sessions",
        "user_preferences",
        "preference_profiles",
        "preference_changes",
        "broker_accounts",
        "broker_attempts",
        "broker_order_intents",
        "broker_secrets",
        "mcp_connections",
        "mcp_oauth_attempts",
        "mcp_operations",
        "mcp_secrets",
        "dhan_market_data_connections",
        "dhan_market_data_secrets",
        "discovery_settings",
        "discovery_comparison_scopes",
        "discovery_temporal_lanes",
        "discovery_scan_admissions",
        "discovery_active_slots",
        "discovery_observations",
        "discovery_projection_checkpoints",
        "discovery_scan_runs",
        "discovery_scan_matches",
        "discovery_scan_evidence_series",
        "discovery_market_context",
        "discovery_episodes",
        "discovery_snapshots",
        "discovery_transitions",
        "discovery_llm_explanations",
        "watchlists",
        "watchlist_items",
        "watchlist_notes",
        "watchlist_activity",
    }
    assert set(Base.metadata.naming_convention) == {"pk", "fk", "ix", "uq", "ck"}
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    command.check(config)
    db = create_database_engine(Settings())
    try:
        with db.connect() as connection:
            assert (
                MigrationContext.configure(connection).get_current_revision() == "0017_watchlists"
            )
            assert inspect(connection).get_table_names() == [
                "alembic_version",
                "auth_sessions",
                "broker_accounts",
                "broker_attempts",
                "broker_order_intents",
                "broker_secrets",
                "dhan_market_data_connections",
                "dhan_market_data_secrets",
                "discovery_active_slots",
                "discovery_comparison_scopes",
                "discovery_episodes",
                "discovery_llm_explanations",
                "discovery_market_context",
                "discovery_observations",
                "discovery_projection_checkpoints",
                "discovery_scan_admissions",
                "discovery_scan_evidence_series",
                "discovery_scan_matches",
                "discovery_scan_runs",
                "discovery_settings",
                "discovery_snapshots",
                "discovery_temporal_lanes",
                "discovery_transitions",
                "mcp_connections",
                "mcp_oauth_attempts",
                "mcp_operations",
                "mcp_secrets",
                "preference_changes",
                "preference_profiles",
                "user_preferences",
                "users",
                "watchlist_activity",
                "watchlist_items",
                "watchlist_notes",
                "watchlists",
            ]
        command.downgrade(config, "base")
        with db.connect() as connection:
            assert MigrationContext.configure(connection).get_current_revision() is None
        command.upgrade(config, "head")
        with db.connect() as connection:
            assert (
                MigrationContext.configure(connection).get_current_revision() == "0017_watchlists"
            )
    finally:
        db.dispose()


def test_offline_postgresql_migration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TWF_DATABASE_URL", "postgresql+psycopg://placeholder:credential_marker_123@db.invalid/twf"
    )
    output = io.StringIO()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "0001_empty_baseline" in sql and "alembic_version" in sql
    assert "credential_marker_123" not in sql and "db.invalid" not in sql
    assert "version_num VARCHAR(128)" in sql
    assert sql.count("CREATE TABLE alembic_version") == 1


def test_temporal_migration_preserves_legacy_episode_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "temporal-legacy.db"
    monkeypatch.setenv("TWF_DATABASE_URL", f"sqlite+pysqlite:///{database}")
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "0013_discovery_scan_archive")
    db = create_database_engine(Settings())
    owner_id = "11111111111111111111111111111111"
    episode_id = "22222222222222222222222222222222"
    candidate_id = "33333333333333333333333333333333"
    instrument_id = "44444444444444444444444444444444"
    timestamp = "2026-10-01 09:15:00+00:00"
    try:
        with db.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, username, display_name, password_hash, is_active, created_at, "
                    "updated_at) VALUES (:id, :username, :display_name, :password_hash, 1, "
                    ":created_at, :updated_at)"
                ),
                {
                    "id": owner_id,
                    "username": "legacy-temporal-owner",
                    "display_name": "Legacy Temporal Owner",
                    "password_hash": "test-only-hash",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO discovery_episodes "
                    "(id, candidate_id, user_id, instrument_id, intent_key, horizon_key, state, "
                    "revision, snapshot_count, previous_episode_id, opened_at, updated_at, "
                    "payload) "
                    "VALUES (:id, :candidate_id, :user_id, :instrument_id, :intent_key, "
                    ":horizon_key, :state, 7, 0, NULL, :opened_at, :updated_at, :payload)"
                ),
                {
                    "id": episode_id,
                    "candidate_id": candidate_id,
                    "user_id": owner_id,
                    "instrument_id": instrument_id,
                    "intent_key": "MOMENTUM",
                    "horizon_key": "5d",
                    "state": "CURRENT",
                    "opened_at": timestamp,
                    "updated_at": timestamp,
                    "payload": '{"legacy_marker":"preserve-verbatim","relevance_model":"v1"}',
                },
            )
        command.upgrade(config, "head")
        with db.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT revision, payload, comparison_scope_id FROM discovery_episodes "
                    "WHERE id = :id"
                ),
                {"id": episode_id},
            ).one()
            assert row.revision == 7
            assert "preserve-verbatim" in row.payload
            assert row.comparison_scope_id is None
            assert (
                connection.execute(text("SELECT count(*) FROM discovery_observations")).scalar_one()
                == 0
            )
        command.downgrade(config, "0013_discovery_scan_archive")
        with db.connect() as connection:
            row = connection.execute(
                text("SELECT revision, payload FROM discovery_episodes WHERE id = :id"),
                {"id": episode_id},
            ).one()
            assert row.revision == 7 and "preserve-verbatim" in row.payload
            assert "comparison_scope_id" not in {
                column["name"] for column in inspect(connection).get_columns("discovery_episodes")
            }
        command.upgrade(config, "head")
        with db.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM discovery_episodes WHERE id = :id"),
                    {"id": episode_id},
                ).scalar_one()
                == 1
            )
    finally:
        db.dispose()
