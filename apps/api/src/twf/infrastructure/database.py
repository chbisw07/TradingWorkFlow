import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from alembic.runtime.migration import MigrationContext
from psycopg import Connection as PGConnection
from sqlalchemy import Engine, MetaData, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool

from twf.config.settings import Settings


class Base(DeclarativeBase):
    """Canonical metadata. Future model modules must register here for Alembic."""

    metadata = MetaData(
        naming_convention={
            "pk": "pk_%(table_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
        }
    )


def _configure_sqlite(connection: sqlite3.Connection, _: ConnectionPoolEntry) -> None:
    # PRAGMA must run outside a transaction (Python 3.12+ sqlite3).
    previous = connection.autocommit
    connection.autocommit = True
    try:
        connection.execute("PRAGMA foreign_keys=ON").close()
    finally:
        connection.autocommit = previous


def _configure_postgresql(
    connection: PGConnection[tuple[object, ...]], _: ConnectionPoolEntry
) -> None:
    # TWF persists UTC instants. Do not inherit the host/cluster's local TimeZone.
    previous = connection.autocommit
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")
    finally:
        connection.autocommit = previous


def create_database_engine(settings: Settings) -> Engine:
    """Caller owns disposal; construction does not connect or create schema."""
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite":
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "autocommit": False},
            poolclass=StaticPool if url.database in (None, "", ":memory:") else None,
            pool_pre_ping=True,
            hide_parameters=True,
            echo=False,
        )
        event.listen(engine, "connect", _configure_sqlite)
        return engine
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=10,
        connect_args={"connect_timeout": settings.database_connect_timeout},
        isolation_level="READ COMMITTED",
        hide_parameters=True,
        echo=False,
    )
    event.listen(engine, "connect", _configure_postgresql)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Explicit flush/commit; loaded values survive commit; closed sessions cannot reopen."""
    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
        close_resets_only=False,
    )


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Never commit implicitly; roll back failures and close on every exit."""
    with factory() as session:
        try:
            yield session
        except BaseException:
            session.rollback()
            raise


def probe_database(engine: Engine) -> bool:
    """Internal connectivity only; never expose driver errors or mutate schema."""
    try:
        with engine.connect() as connection:
            return bool(connection.scalar(text("SELECT 1")) == 1)
    except SQLAlchemyError:
        return False


# Deployment compatibility, checked against the Alembic graph in the platform gate.
DATABASE_SCHEMA_HEAD = "0026_oe3_queue_hardening"


def database_status(engine: Engine) -> dict[str, str]:
    """Credential-free readiness. No schema creation, fallback, or provider calls."""
    backend = "PostgreSQL" if engine.dialect.name == "postgresql" else "SQLite fallback"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            heads = MigrationContext.configure(connection).get_current_heads()
        if heads != (DATABASE_SCHEMA_HEAD,):
            return {"backend": backend, "status": "schema_mismatch"}
        return {"backend": backend, "status": "ready"}
    except SQLAlchemyError:
        return {"backend": backend, "status": "unavailable"}


def require_database_ready(engine: Engine) -> None:
    status = database_status(engine)
    if status["status"] != "ready":
        remedy = (
            "Run alembic upgrade head before starting TWF."
            if status["status"] == "schema_mismatch"
            else "Check TWF_DATABASE_URL and database availability; no fallback was attempted."
        )
        raise RuntimeError(f"Database {status['backend']}: {status['status']}. {remedy}")
