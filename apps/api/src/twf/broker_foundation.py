"""BW-2.1 use cases for durable, disabled-by-default personal broker accounts."""

from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from twf.brokers.foundation_contracts import (
    PROVIDERS,
    BrokerAccountConfiguration,
    BrokerAccountCreate,
    BrokerAccountView,
    BrokerPermission,
    BrokerPermissionPolicy,
    ProviderStatus,
)
from twf.infrastructure.broker_foundation import (
    BrokerAccountRecord,
    BrokerAuditEvent,
    BrokerConnectionRecord,
    BrokerProviderConfiguration,
)
from twf.secrets import SecretAccessDenied, SecretScope, SecretStore


class BrokerFoundationFailure(Exception):
    def __init__(self, status: int) -> None:
        self.status = status


class BrokerFoundation:
    def __init__(
        self,
        session: Session,
        actor_user_id: UUID,
        policy: BrokerPermissionPolicy,
        secret_store: SecretStore,
        environment: str,
        request_id: str | None = None,
        *,
        logger: Logger | None = None,
    ) -> None:
        self.session = session
        self.actor_user_id = actor_user_id
        self.policy = policy
        self.secret_store = secret_store
        self.environment = environment
        self.request_id = request_id
        self.logger = logger if logger is not None else getLogger(__name__)

    def _authorized(self, permission: BrokerPermission, owner_user_id: UUID) -> None:
        if not self.policy.allows(self.actor_user_id, permission, owner_user_id):
            raise BrokerFoundationFailure(404 if owner_user_id != self.actor_user_id else 403)

    def _account(self, account_id: UUID, permission: BrokerPermission) -> BrokerAccountRecord:
        account = self.session.get(BrokerAccountRecord, account_id)
        if account is None:
            raise BrokerFoundationFailure(404)
        self._authorized(permission, account.owner_user_id)
        return account

    def _audit(self, account: BrokerAccountRecord, event_type: str) -> None:
        self.session.add(
            BrokerAuditEvent(
                owner_user_id=account.owner_user_id,
                broker_account_id=account.id,
                provider_id=account.provider_id,
                event_type=event_type,
                configuration_revision=account.configuration_revision,
                connection_generation=account.connection_generation,
                request_id=self.request_id,
                outcome="SUCCEEDED",
                created_at=datetime.now(UTC),
            )
        )

    def _flush(self) -> None:
        try:
            self.session.flush()
        except IntegrityError as error:
            self.session.rollback()
            raise BrokerFoundationFailure(409) from error

    def _commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise BrokerFoundationFailure(409) from error

    def providers(self) -> tuple[ProviderStatus, ...]:
        rows = {
            row.provider_id: row
            for row in self.session.scalars(select(BrokerProviderConfiguration))
        }
        return tuple(
            ProviderStatus(
                **provider.model_dump(),
                configured=bool(
                    rows.get(provider.provider_id) and rows[provider.provider_id].configured
                ),
            )
            for provider in PROVIDERS.values()
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _view(
        account: BrokerAccountRecord, connection: BrokerConnectionRecord
    ) -> BrokerAccountView:
        return BrokerAccountView(
            broker_account_id=account.id,
            owner_user_id=account.owner_user_id,
            provider_id=account.provider_id,
            provider_account_id=account.provider_account_id,
            label=account.label,
            enabled=account.enabled,
            configured=account.configured,
            configuration_revision=account.configuration_revision,
            connection_generation=account.connection_generation,
            authentication_state=cast(
                Literal[
                    "NOT_CONFIGURED",
                    "DISCONNECTED",
                    "AUTHENTICATING",
                    "AUTH_REQUIRED",
                    "AUTH_IN_PROGRESS",
                    "CONNECTED",
                    "REAUTH_REQUIRED",
                    "ERROR",
                ],
                connection.authentication_state,
            ),
            read_health=cast(
                Literal["UNKNOWN", "AVAILABLE", "DEGRADED", "UNAVAILABLE"],
                connection.read_health,
            ),
            last_successful_read_at=connection.last_successful_read_at,
            last_failure_at=connection.last_failure_at,
            created_at=BrokerFoundation._aware(account.created_at),
            updated_at=BrokerFoundation._aware(account.updated_at),
        )

    def list_accounts(self) -> tuple[BrokerAccountView, ...]:
        self._authorized(BrokerPermission.READ, self.actor_user_id)
        pairs = self.session.execute(
            select(BrokerAccountRecord, BrokerConnectionRecord)
            .join(
                BrokerConnectionRecord,
                BrokerConnectionRecord.broker_account_id == BrokerAccountRecord.id,
            )
            .where(BrokerAccountRecord.owner_user_id == self.actor_user_id)
            .order_by(BrokerAccountRecord.created_at, BrokerAccountRecord.id)
        )
        return tuple(self._view(account, connection) for account, connection in pairs)

    def create_account(self, payload: BrokerAccountCreate) -> BrokerAccountView:
        self._authorized(BrokerPermission.CONFIGURE, self.actor_user_id)
        provider = PROVIDERS.get(payload.provider_id)
        if provider is None:
            raise BrokerFoundationFailure(422)
        now = datetime.now(UTC)
        if self.session.get(BrokerProviderConfiguration, provider.provider_id) is None:
            self.session.add(
                BrokerProviderConfiguration(
                    provider_id=provider.provider_id,
                    enabled=False,
                    configured=False,
                    configuration_revision=1,
                    secret_reference=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            self._flush()
        account = BrokerAccountRecord(
            owner_user_id=self.actor_user_id,
            provider_id=provider.provider_id,
            environment=self.environment,
            provider_account_id=None,
            mode="LIVE",
            label=payload.label,
            enabled=False,
            configured=False,
            configuration_revision=1,
            connection_generation=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(account)
        self._flush()
        connection = BrokerConnectionRecord(
            broker_account_id=account.id,
            authentication_state="NOT_CONFIGURED",
            read_health="UNKNOWN",
            applied_configuration_revision=0,
            secret_reference=None,
            secret_version=None,
            expires_at=None,
            last_successful_read_at=None,
            last_failure_at=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(connection)
        self._audit(account, "BROKER_ACCOUNT_CREATED")
        self._commit()
        return self._view(account, connection)

    def configure_account(
        self, account_id: UUID, payload: BrokerAccountConfiguration
    ) -> BrokerAccountView:
        self._account(account_id, BrokerPermission.CONFIGURE)
        self.session.rollback()
        now = datetime.now(UTC)
        try:
            result = self.session.execute(
                update(BrokerAccountRecord)
                .where(
                    BrokerAccountRecord.id == account_id,
                    BrokerAccountRecord.owner_user_id == self.actor_user_id,
                    BrokerAccountRecord.configuration_revision == payload.expected_revision,
                )
                .values(
                    label=payload.label,
                    enabled=payload.enabled,
                    configuration_revision=payload.expected_revision + 1,
                    updated_at=now,
                )
            )
        except IntegrityError:
            self.session.rollback()
            raise BrokerFoundationFailure(409) from None
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            self.session.rollback()
            raise BrokerFoundationFailure(409)
        updated_account = self.session.get(BrokerAccountRecord, account_id)
        connection = self.session.get(BrokerConnectionRecord, account_id)
        if updated_account is None or connection is None:
            self.session.rollback()
            raise BrokerFoundationFailure(404)
        self._audit(updated_account, "BROKER_ACCOUNT_CONFIGURATION_CHANGED")
        self._commit()
        return self._view(updated_account, connection)

    def _advance_generation(
        self, account_id: UUID, permission: BrokerPermission, expected_generation: int
    ) -> tuple[BrokerAccountRecord, BrokerConnectionRecord]:
        """Acquire the account write lock with an owner-scoped compare-and-swap."""
        self._account(account_id, permission)
        # End the authorization read transaction before attempting the CAS (also SQLite-safe).
        self.session.rollback()
        if type(expected_generation) is not int or expected_generation < 0:
            raise BrokerFoundationFailure(422)
        result = self.session.execute(
            update(BrokerAccountRecord)
            .where(
                BrokerAccountRecord.id == account_id,
                BrokerAccountRecord.owner_user_id == self.actor_user_id,
                BrokerAccountRecord.environment == self.environment,
                BrokerAccountRecord.connection_generation == expected_generation,
            )
            .values(
                connection_generation=BrokerAccountRecord.connection_generation + 1,
                updated_at=datetime.now(UTC),
            )
            .execution_options(synchronize_session=False)
        )
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            self.session.rollback()
            raise BrokerFoundationFailure(409)
        account = self.session.get(BrokerAccountRecord, account_id, populate_existing=True)
        connection = self.session.get(BrokerConnectionRecord, account_id, populate_existing=True)
        if account is None or connection is None:
            self.session.rollback()
            raise BrokerFoundationFailure(404)
        return account, connection

    @staticmethod
    def _secret_scope(account: BrokerAccountRecord, generation: int) -> SecretScope:
        return SecretScope(
            account.owner_user_id, account.provider_id, account.id, account.environment, generation
        )

    def _delete_superseded(self, scope: SecretScope, reference: str | None) -> None:
        """Cleanup follows durable fencing. A vault outage cannot resurrect an old generation."""
        if reference is None:
            return
        try:
            self.secret_store.delete(scope, reference)
        except SecretAccessDenied:
            pass  # Already absent: deletion is complete.
        except Exception:
            # Never render the reference, store exception, or arbitrary provider payload.
            self.logger.warning(
                "broker_secret_cleanup_failed",
                extra={"operation": "secret_delete", "outcome": "generation_revoked"},
            )

    def replace_secret_reference(
        self, account_id: UUID, reference: str, *, expected_generation: int
    ) -> int:
        """Attach only a reference scoped to the next generation; no provider authentication."""
        try:
            account, connection = self._advance_generation(
                account_id, BrokerPermission.CONNECT, expected_generation
            )
            target_scope = self._secret_scope(account, account.connection_generation)
            try:
                exists = self.secret_store.exists(target_scope, reference)
            except Exception:
                raise BrokerFoundationFailure(503) from None
            if not exists:
                raise BrokerFoundationFailure(404)
            old_reference = connection.secret_reference
            old_scope = self._secret_scope(account, expected_generation) if old_reference else None
            generation = account.connection_generation
            connection.secret_reference = reference
            connection.authentication_state = "DISCONNECTED"
            connection.read_health = "UNKNOWN"
            connection.secret_version = None
            connection.expires_at = None
            connection.updated_at = account.updated_at
            self._audit(account, "SECRET_REFERENCE_REPLACED")
            self._commit()
        except Exception:
            self.session.rollback()
            raise
        if old_scope is not None:
            self._delete_superseded(old_scope, old_reference)
        return generation

    def invalidate_connection(self, account_id: UUID, *, expected_generation: int) -> int:
        """Commit local invalidation before physical cleanup; no provider logout."""
        try:
            account, connection = self._advance_generation(
                account_id, BrokerPermission.DISCONNECT, expected_generation
            )
            old_reference = connection.secret_reference
            old_scope = self._secret_scope(account, expected_generation) if old_reference else None
            generation = account.connection_generation
            connection.secret_reference = None
            connection.secret_version = None
            connection.expires_at = None
            connection.authentication_state = "DISCONNECTED"
            connection.read_health = "UNKNOWN"
            connection.updated_at = account.updated_at
            self._audit(account, "CONNECTION_INVALIDATED")
            self._commit()
        except Exception:
            self.session.rollback()
            raise
        if old_scope is not None:
            self._delete_superseded(old_scope, old_reference)
        return generation
