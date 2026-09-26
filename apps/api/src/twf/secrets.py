"""Provider-neutral secret storage boundary with a non-production memory implementation."""

from collections.abc import Callable
from dataclasses import dataclass
from secrets import token_urlsafe
from typing import Literal, Protocol
from uuid import UUID

from twf.config.settings import Settings


class SecretStoreUnavailable(RuntimeError):
    """Raised when a deployment has no authorized secret-store implementation."""


class SecretAccessDenied(LookupError):
    """Do not reveal whether a reference exists outside the caller's scope."""


@dataclass(frozen=True, repr=False)
class SecretValue:
    """A value that never exposes its contents through repr or str."""

    _value: str

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "SecretValue([REDACTED])"

    __str__ = __repr__


@dataclass(frozen=True)
class SecretScope:
    owner_user_id: UUID
    provider_id: str
    broker_account_id: UUID
    environment: str
    connection_generation: int
    purpose: Literal["access", "configuration", "pending"] = "access"
    context: str = ""

    def __post_init__(self) -> None:
        if self.connection_generation < (0 if self.purpose == "configuration" else 1):
            raise ValueError("Secret scope requires a positive target generation")


@dataclass(frozen=True)
class StoredSecret:
    reference: str
    scope: SecretScope


class SecretStore(Protocol):
    @property
    def production_safe(self) -> bool: ...

    def put(self, scope: SecretScope, value: SecretValue) -> StoredSecret: ...

    def get(self, scope: SecretScope, reference: str) -> SecretValue: ...

    def delete(self, scope: SecretScope, reference: str) -> bool: ...

    def exists(self, scope: SecretScope, reference: str) -> bool: ...


class MemorySecretStore:
    """Process-local DEVELOPMENT/TEST store; never a production fallback."""

    production_safe = False

    def __init__(self, reference_factory: Callable[[], str] = lambda: token_urlsafe(32)) -> None:
        self._reference_factory = reference_factory
        self._values: dict[str, tuple[SecretScope, SecretValue]] = {}

    def put(self, scope: SecretScope, value: SecretValue) -> StoredSecret:
        reference = self._reference_factory()
        if not reference or reference in self._values:
            raise ValueError("Secret reference factory must return a unique opaque value")
        self._values[reference] = (scope, value)
        return StoredSecret(reference=reference, scope=scope)

    def _owned(self, scope: SecretScope, reference: str) -> tuple[SecretScope, SecretValue]:
        saved = self._values.get(reference)
        if saved is None or saved[0] != scope:
            raise SecretAccessDenied("Secret reference is unavailable")
        return saved

    def get(self, scope: SecretScope, reference: str) -> SecretValue:
        return self._owned(scope, reference)[1]

    def delete(self, scope: SecretScope, reference: str) -> bool:
        self._owned(scope, reference)
        del self._values[reference]
        return True

    def exists(self, scope: SecretScope, reference: str) -> bool:
        saved = self._values.get(reference)
        return saved is not None and saved[0] == scope


class UnavailableSecretStore:
    """Fail-closed placeholder for deployments without an approved store."""

    production_safe = True  # No storage or credential fallback.

    @staticmethod
    def _unavailable() -> SecretStoreUnavailable:
        return SecretStoreUnavailable("No production secret store is configured")

    def put(self, scope: SecretScope, value: SecretValue) -> StoredSecret:
        raise self._unavailable()

    def get(self, scope: SecretScope, reference: str) -> SecretValue:
        raise self._unavailable()

    def delete(self, scope: SecretScope, reference: str) -> bool:
        raise self._unavailable()

    def exists(self, scope: SecretScope, reference: str) -> bool:
        return False


def default_secret_store(settings: Settings) -> SecretStore:
    """Development/test is explicit; production never falls back to process memory."""
    if settings.environment in {"development", "test"}:
        return MemorySecretStore()
    return UnavailableSecretStore()


def select_secret_store(settings: Settings, injected: SecretStore | None) -> SecretStore:
    """Reject development stores at composition, including explicitly injected ones."""
    store = injected if injected is not None else default_secret_store(settings)
    if settings.environment == "production" and (
        isinstance(store, MemorySecretStore) or getattr(store, "production_safe", False) is not True
    ):
        raise SecretStoreUnavailable("Secret store is not approved for production")
    return store
