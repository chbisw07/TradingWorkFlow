"""Authenticated owner/actor scope for OE-1 order operations.

The application auth boundary supplies a User and AuthSession. OrderService
rechecks the persisted session on every operation; an owner UUID in a request
is never authority. Future subsystem actors need a separate trusted boundary.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID
from weakref import WeakValueDictionary

from twf.infrastructure.identity import AuthSession, User
from twf.orders.contracts import Source
from twf.orders.errors import OrderError, OrderErrorCode


class OrderActor(StrEnum):
    USER = "USER"
    SYSTEM = "SYSTEM"
    WATCHLIST = "WATCHLIST"
    SCANNER = "SCANNER"
    DISCOVERY = "DISCOVERY"
    STRATEGY = "STRATEGY"
    AGENT = "AGENT"
    WEBHOOK = "WEBHOOK"
    QUEUE = "QUEUE"
    BROKER_RECONCILIATION = "BROKER_RECONCILIATION"


@dataclass(frozen=True, init=False)
class OrderContext:
    owner_id: UUID
    session_hash: str
    source: Source
    source_ref: str | None
    correlation_id: str | None

    @classmethod
    def from_authenticated_session(
        cls,
        user: User,
        login: AuthSession,
        *,
        correlation_id: str | None = None,
    ) -> "OrderContext":
        if not user.is_active or login.user_id != user.id or login.revoked_at is not None:
            raise OrderError(OrderErrorCode.UNAUTHORIZED, "Authenticated order context required")
        expires = login.expires_at
        expires = expires.replace(tzinfo=UTC) if expires.tzinfo is None else expires
        if expires <= datetime.now(UTC):
            raise OrderError(OrderErrorCode.UNAUTHORIZED, "Authenticated order context expired")
        if correlation_id is not None and (not correlation_id or len(correlation_id) > 128):
            raise OrderError(OrderErrorCode.INVALID_ORDER, "Invalid correlation id")
        context = object.__new__(cls)
        object.__setattr__(context, "owner_id", user.id)
        object.__setattr__(context, "session_hash", login.token_hash)
        object.__setattr__(context, "source", Source.MANUAL)
        object.__setattr__(context, "source_ref", None)
        object.__setattr__(context, "correlation_id", correlation_id)
        return context

    @property
    def actor(self) -> str:
        return f"{OrderActor.USER.value}:{self.owner_id}"

    @classmethod
    def from_trusted_subsystem(
        cls,
        user: User,
        login: AuthSession,
        origin: "_TrustedSubsystemOrigin",
        *,
        correlation_id: str | None = None,
    ) -> "OrderContext":
        """Bind delegated user action to an internally verified subsystem event."""
        if (
            type(origin) is not _TrustedSubsystemOrigin
            or _ISSUED_ORIGINS.get(id(origin)) is not origin
        ):
            raise OrderError(OrderErrorCode.UNAUTHORIZED, "Verified subsystem origin required")
        context = cls.from_authenticated_session(user, login, correlation_id=correlation_id)
        if origin.owner_id != context.owner_id:
            raise OrderError(
                OrderErrorCode.UNAUTHORIZED, "Subsystem origin belongs to another owner"
            )
        object.__setattr__(context, "source", origin.source)
        object.__setattr__(context, "source_ref", origin.reference)
        return context


@dataclass(frozen=True, init=False, slots=True, weakref_slot=True)
class _TrustedSubsystemOrigin:
    owner_id: UUID
    source: Source
    reference: str


_ISSUED_ORIGINS: WeakValueDictionary[int, _TrustedSubsystemOrigin] = WeakValueDictionary()


class _SubsystemOriginIssuer:
    """Internal composition capability; validator checks source event existence/ownership.

    An intake/Scanner/Watchlist adapter must own this issuer and pass a validator
    backed by its trusted event/run reference, never by request fields alone.
    """

    def __init__(self, source: Source, validate_reference: Callable[[UUID, str], bool]) -> None:
        if type(source) is not Source or source == Source.MANUAL:
            raise ValueError("Subsystem origin must be a non-manual Source")
        self.source = source
        self.validate_reference = validate_reference

    def issue(self, owner_id: UUID, reference: str) -> _TrustedSubsystemOrigin:
        if not isinstance(reference, str) or not reference.strip() or len(reference) > 256:
            raise OrderError(OrderErrorCode.INVALID_ORDER, "Invalid subsystem reference")
        if type(owner_id) is not UUID or self.validate_reference(owner_id, reference) is not True:
            raise OrderError(OrderErrorCode.UNAUTHORIZED, "Unverified subsystem reference")
        origin = object.__new__(_TrustedSubsystemOrigin)
        object.__setattr__(origin, "owner_id", owner_id)
        object.__setattr__(origin, "source", self.source)
        object.__setattr__(origin, "reference", reference)
        _ISSUED_ORIGINS[id(origin)] = origin
        return origin
