from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from twf.config.settings import Settings


class Base(DeclarativeBase):
    """Shared metadata for future TWF-owned models. Currently empty."""


def create_database_engine(settings: Settings) -> Engine:
    """Caller owns engine disposal; construction does not connect to the database."""
    return create_engine(settings.database_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Callers use a context manager and explicitly own transaction boundaries."""
    return sessionmaker(bind=engine, expire_on_commit=False)
