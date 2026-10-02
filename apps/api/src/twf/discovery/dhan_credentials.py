"""Encrypted owner-scoped Dhan credentials and readiness lifecycle."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, cast
from uuid import UUID, uuid4

from pydantic import Field, SecretStr, ValidationError
from sqlalchemy import delete, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from twf.brokers.contracts import BrokerFailure
from twf.brokers.secrets import ALGORITHM, CredentialCipher
from twf.config.settings import Settings
from twf.discovery.market_data import (
    DhanMarketDataProvider,
    DhanMarketDataSettings,
    MarketDataErrorCode,
    MarketDataFailure,
    MarketDataProvider,
)
from twf.infrastructure.dhan import DhanMarketDataConnection, DhanMarketDataSecret
from twf.integrations.contracts import Contract


class DhanCredentialState(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    CONFIGURED = "CONFIGURED"
    READY = "READY"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    DISABLED = "DISABLED"


class DhanCredentialStatus(Contract):
    state: DhanCredentialState
    configured: bool
    enabled: bool
    generation: int = Field(ge=0)
    source: Literal["DATABASE", "ENVIRONMENT", "NONE"]
    checked_at: datetime | None = None
    last_error: str | None = None


class DhanCredentialFailure(Exception):
    def __init__(self, code: str, status: int) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


class _CredentialBundle(Contract):
    owner_id: UUID
    generation: int = Field(ge=1)
    client_id: SecretStr = Field(min_length=1, max_length=128, repr=False)
    access_token: SecretStr = Field(min_length=8, max_length=4096, repr=False)


@dataclass(frozen=True)
class DhanCredentialCapture:
    provider: MarketDataProvider | None
    status: DhanCredentialStatus


def _now() -> datetime:
    return datetime.now(UTC)


class DhanCredentialManager:
    """Owns DB authority; provider HTTP always runs after its DB session closes."""

    def __init__(
        self,
        factory: sessionmaker[Session],
        settings: Settings,
        provider_factory: Callable[[DhanMarketDataSettings], MarketDataProvider] | None = None,
    ) -> None:
        self.factory = factory
        self.settings = settings
        self.provider_factory = provider_factory or DhanMarketDataProvider
        self._providers: dict[tuple[UUID, int], MarketDataProvider] = {}

    def _fallback(self) -> DhanCredentialStatus:
        configured = self.settings.dhan_market_data.configured
        return DhanCredentialStatus(
            state=(DhanCredentialState.READY if configured else DhanCredentialState.NOT_CONFIGURED),
            configured=configured,
            enabled=configured,
            generation=0,
            source="ENVIRONMENT" if configured else "NONE",
        )

    @staticmethod
    def _view(row: DhanMarketDataConnection) -> DhanCredentialStatus:
        return DhanCredentialStatus(
            state=DhanCredentialState(row.state),
            configured=row.secret_id is not None,
            enabled=row.enabled,
            generation=row.generation,
            source="DATABASE" if row.secret_id is not None else "NONE",
            checked_at=row.checked_at,
            last_error=row.last_error,
        )

    def status(self, owner_id: UUID) -> DhanCredentialStatus:
        with self.factory() as db:
            row = db.get(DhanMarketDataConnection, owner_id)
            return self._view(row) if row is not None else self._fallback()

    def _seal(self, bundle: _CredentialBundle) -> str:
        plaintext = json.dumps(
            {
                "owner_id": str(bundle.owner_id),
                "generation": bundle.generation,
                "client_id": bundle.client_id.get_secret_value(),
                "access_token": bundle.access_token.get_secret_value(),
            }
        ).encode()
        try:
            return CredentialCipher(self.settings).encrypt(plaintext)
        except BrokerFailure as exc:
            raise DhanCredentialFailure(exc.code, exc.status) from None

    def _open(self, secret: DhanMarketDataSecret) -> _CredentialBundle:
        try:
            raw = CredentialCipher(self.settings).decrypt(secret.ciphertext, secret.algorithm)
            return _CredentialBundle.model_validate_json(raw)
        except BrokerFailure as exc:
            raise DhanCredentialFailure(exc.code, exc.status) from None
        except (ValidationError, ValueError):
            raise DhanCredentialFailure("SECRET_STORE_UNAVAILABLE", 503) from None

    def configure(
        self,
        owner_id: UUID,
        expected_generation: int,
        client_id: SecretStr,
        access_token: SecretStr,
    ) -> DhanCredentialStatus:
        now = _now()
        with self.factory() as db:
            current = db.get(DhanMarketDataConnection, owner_id)
            generation = 1 if current is None else current.generation + 1
            if (current is None and expected_generation != 0) or (
                current is not None and current.generation != expected_generation
            ):
                raise DhanCredentialFailure("STALE_GENERATION", 409)
            bundle = _CredentialBundle(
                owner_id=owner_id,
                generation=generation,
                client_id=client_id,
                access_token=access_token,
            )
            secret = DhanMarketDataSecret(
                id=uuid4(),
                owner_id=owner_id,
                generation=generation,
                ciphertext=self._seal(bundle),
                algorithm=ALGORITHM,
                created_at=now,
            )
            old_secret_id = current.secret_id if current is not None else None
            try:
                db.add(secret)
                db.flush()
                if current is None:
                    current = DhanMarketDataConnection(
                        owner_id=owner_id,
                        secret_id=secret.id,
                        generation=generation,
                        state=DhanCredentialState.CONFIGURED.value,
                        enabled=True,
                        last_error=None,
                        checked_at=None,
                        updated_at=now,
                    )
                    db.add(current)
                else:
                    result = cast(
                        CursorResult[tuple[object, ...]],
                        db.execute(
                            update(DhanMarketDataConnection)
                            .where(
                                DhanMarketDataConnection.owner_id == owner_id,
                                DhanMarketDataConnection.generation == expected_generation,
                            )
                            .values(
                                secret_id=secret.id,
                                generation=generation,
                                state=DhanCredentialState.CONFIGURED.value,
                                enabled=True,
                                last_error=None,
                                checked_at=None,
                                updated_at=now,
                            )
                        ),
                    )
                    if result.rowcount != 1:
                        raise DhanCredentialFailure("STALE_GENERATION", 409)
                    db.flush()
                    if old_secret_id is not None:
                        db.execute(
                            delete(DhanMarketDataSecret).where(
                                DhanMarketDataSecret.id == old_secret_id
                            )
                        )
                db.commit()
            except IntegrityError:
                db.rollback()
                raise DhanCredentialFailure("STALE_GENERATION", 409) from None
        self._drop_cached(owner_id)
        return self.status(owner_id)

    def _drop_cached(self, owner_id: UUID) -> None:
        self._providers = {
            key: value for key, value in self._providers.items() if key[0] != owner_id
        }

    def capture(self, owner_id: UUID, *, ready_only: bool) -> DhanCredentialCapture:
        with self.factory() as db:
            row = db.get(DhanMarketDataConnection, owner_id)
            if row is None:
                status = self._fallback()
                if not status.configured or (
                    ready_only and status.state != DhanCredentialState.READY
                ):
                    return DhanCredentialCapture(None, status)
                key = (owner_id, 0)
                provider = self._providers.get(key)
                if provider is None:
                    provider = self.provider_factory(self.settings.dhan_market_data)
                    self._providers[key] = provider
                return DhanCredentialCapture(provider, status)
            status = self._view(row)
            if (
                not row.enabled
                or row.secret_id is None
                or (ready_only and status.state != DhanCredentialState.READY)
            ):
                return DhanCredentialCapture(None, status)
            secret = db.get(DhanMarketDataSecret, row.secret_id)
            if secret is None or secret.owner_id != owner_id or secret.generation != row.generation:
                return DhanCredentialCapture(
                    None,
                    status.model_copy(
                        update={
                            "state": DhanCredentialState.PROVIDER_ERROR,
                            "last_error": "SECRET_STORE_UNAVAILABLE",
                        }
                    ),
                )
            try:
                bundle = self._open(secret)
            except DhanCredentialFailure as exc:
                return DhanCredentialCapture(
                    None,
                    status.model_copy(
                        update={
                            "state": DhanCredentialState.PROVIDER_ERROR,
                            "last_error": exc.code,
                        }
                    ),
                )
            if bundle.owner_id != owner_id or bundle.generation != row.generation:
                return DhanCredentialCapture(
                    None,
                    status.model_copy(
                        update={
                            "state": DhanCredentialState.PROVIDER_ERROR,
                            "last_error": "SECRET_STORE_UNAVAILABLE",
                        }
                    ),
                )
            key = (owner_id, row.generation)
            provider = self._providers.get(key)
            if provider is None:
                provider = self.provider_factory(
                    self.settings.dhan_market_data.model_copy(
                        update={
                            "enabled": True,
                            "client_id": bundle.client_id,
                            "access_token": bundle.access_token,
                        }
                    )
                )
                self._providers[key] = provider
            return DhanCredentialCapture(provider, status)

    def _record_test(
        self,
        owner_id: UUID,
        generation: int,
        state: DhanCredentialState,
        error: str | None,
    ) -> DhanCredentialStatus:
        now = _now()
        with self.factory() as db:
            row = db.get(DhanMarketDataConnection, owner_id)
            if row is None:
                fallback = self._fallback()
                if generation != 0:
                    raise DhanCredentialFailure("STALE_GENERATION", 409)
                return fallback.model_copy(
                    update={"state": state, "last_error": error, "checked_at": now}
                )
            result = cast(
                CursorResult[tuple[object, ...]],
                db.execute(
                    update(DhanMarketDataConnection)
                    .where(
                        DhanMarketDataConnection.owner_id == owner_id,
                        DhanMarketDataConnection.generation == generation,
                        DhanMarketDataConnection.enabled.is_(True),
                    )
                    .values(
                        state=state.value,
                        last_error=error,
                        checked_at=now,
                        updated_at=now,
                    )
                ),
            )
            if result.rowcount != 1:
                db.rollback()
                raise DhanCredentialFailure("STALE_GENERATION", 409)
            db.commit()
        return self.status(owner_id)

    async def test_connection(
        self, owner_id: UUID, expected_generation: int
    ) -> DhanCredentialStatus:
        capture = self.capture(owner_id, ready_only=False)
        if capture.status.generation != expected_generation:
            raise DhanCredentialFailure("STALE_GENERATION", 409)
        if capture.provider is None:
            raise DhanCredentialFailure("DHAN_NOT_CONFIGURED", 409)
        try:
            instrument = (await capture.provider.resolve_instruments(("RELIANCE",)))[0]
            quotes = await capture.provider.get_quotes((instrument,))
            if len(quotes) != 1:
                raise MarketDataFailure(MarketDataErrorCode.PARTIAL_RESPONSE)
        except MarketDataFailure as exc:
            state = {
                MarketDataErrorCode.AUTH_REQUIRED: DhanCredentialState.AUTH_FAILED,
                MarketDataErrorCode.RATE_LIMITED: DhanCredentialState.RATE_LIMITED,
            }.get(exc.code, DhanCredentialState.PROVIDER_ERROR)
            return self._record_test(owner_id, expected_generation, state, exc.code.value)
        return self._record_test(owner_id, expected_generation, DhanCredentialState.READY, None)

    def disconnect(self, owner_id: UUID, expected_generation: int) -> DhanCredentialStatus:
        now = _now()
        with self.factory() as db:
            current = db.get(DhanMarketDataConnection, owner_id)
            if current is None:
                if expected_generation != 0:
                    raise DhanCredentialFailure("STALE_GENERATION", 409)
                current = DhanMarketDataConnection(
                    owner_id=owner_id,
                    secret_id=None,
                    generation=1,
                    state=DhanCredentialState.DISABLED.value,
                    enabled=False,
                    last_error=None,
                    checked_at=now,
                    updated_at=now,
                )
                db.add(current)
            else:
                if current.generation != expected_generation:
                    raise DhanCredentialFailure("STALE_GENERATION", 409)
                old_secret_id = current.secret_id
                result = cast(
                    CursorResult[tuple[object, ...]],
                    db.execute(
                        update(DhanMarketDataConnection)
                        .where(
                            DhanMarketDataConnection.owner_id == owner_id,
                            DhanMarketDataConnection.generation == expected_generation,
                        )
                        .values(
                            secret_id=None,
                            generation=expected_generation + 1,
                            state=DhanCredentialState.DISABLED.value,
                            enabled=False,
                            last_error=None,
                            checked_at=now,
                            updated_at=now,
                        )
                    ),
                )
                if result.rowcount != 1:
                    raise DhanCredentialFailure("STALE_GENERATION", 409)
                db.flush()
                if old_secret_id is not None:
                    db.execute(
                        delete(DhanMarketDataSecret).where(DhanMarketDataSecret.id == old_secret_id)
                    )
            db.commit()
        self._drop_cached(owner_id)
        return self.status(owner_id)
