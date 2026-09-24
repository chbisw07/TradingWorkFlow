from collections.abc import Iterator
from typing import cast

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from twf.config.settings import Settings
from twf.infrastructure.database import session_scope


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_request_id(request: Request) -> str | None:
    return cast(str | None, getattr(request.state, "request_id", None))


def get_db_session(request: Request) -> Iterator[Session]:
    """One session per request; write use-cases explicitly own commit/rollback."""
    factory = cast(
        sessionmaker[Session] | None, getattr(request.app.state, "session_factory", None)
    )
    if factory is None:
        raise RuntimeError("Database lifecycle is not initialized")
    with session_scope(factory) as session:
        yield session
