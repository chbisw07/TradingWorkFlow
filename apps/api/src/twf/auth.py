"""Replaceable first-party identity seam. Callers own database transactions."""

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from twf.infrastructure.identity import AuthSession, User


def normalize_username(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", value):
        raise ValueError(
            "Username must contain 3–64 ASCII letters, numbers, dots, underscores or hyphens"
        )
    return value


def create_user(session: Session, username: str, display_name: str, password: str) -> User:
    if not 12 <= len(password) <= 128:
        raise ValueError("Password must contain 12–128 characters")
    if not display_name.strip() or len(display_name.strip()) > 80:
        raise ValueError("Display name must contain 1–80 characters")
    now = datetime.now(UTC)
    user = User(
        username=normalize_username(username),
        display_name=display_name.strip(),
        password_hash=PasswordHasher().hash(password),
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.flush()
    return user


def verify_password(encoded: str, password: str) -> bool:
    try:
        return PasswordHasher().verify(encoded, password)
    except VerificationError:
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def resolve_session(session: Session, token: str | None) -> AuthSession | None:
    if token is None or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return None
    stored = session.get(AuthSession, token_digest(token))
    if stored is None or stored.revoked_at is not None:
        return None
    # SQLite returns naive timestamps; persisted values always have UTC semantics.
    expires = (
        stored.expires_at.replace(tzinfo=UTC)
        if stored.expires_at.tzinfo is None
        else stored.expires_at
    )
    return stored if expires > datetime.now(UTC) else None


def current_user(session: Session, token: str | None) -> User | None:
    stored = resolve_session(session, token)
    user = session.get(User, stored.user_id) if stored else None
    return user if user and user.is_active else None


def authenticate(session: Session, username: str, password: str, dummy_hash: str) -> User | None:
    user = session.scalar(select(User).where(User.username == username))
    if user is not None:
        session.expunge(user)
    session.rollback()  # End the read transaction before hashing and session writes.
    valid = verify_password(user.password_hash if user else dummy_hash, password)
    return user if user and valid else None


def establish_session(session: Session, user: User, ttl: int, old_token: str | None) -> str:
    revoke_session(session, old_token)
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    session.add(
        AuthSession(
            token_hash=token_digest(token),
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
        )
    )
    return token


def revoke_session(session: Session, token: str | None) -> None:
    if token is not None and re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        session.execute(
            update(AuthSession)
            .where(AuthSession.token_hash == token_digest(token), AuthSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
