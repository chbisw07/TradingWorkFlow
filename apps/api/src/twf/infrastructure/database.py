import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

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
    return create_engine(url, pool_pre_ping=True, hide_parameters=True, echo=False)


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
