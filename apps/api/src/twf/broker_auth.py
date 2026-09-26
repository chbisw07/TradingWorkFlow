"""Fenced, two-stage broker authentication. Provider I/O never owns a DB transaction."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import Literal, cast
from urllib.parse import urlencode
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import insert, literal, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import OperationalError

from twf.auth import token_digest
from twf.broker_foundation import BrokerFoundation, BrokerFoundationFailure
from twf.brokers.foundation_contracts import BrokerPermission, ProviderStatus
from twf.brokers.zerodha_auth import AuthProvider, ProviderAuthFailure
from twf.config.settings import Settings
from twf.infrastructure.broker_auth import (
    BrokerAuthAttempt,
    BrokerAuthConfiguration,
    BrokerSecretLifecycle,
)
from twf.infrastructure.broker_foundation import (
    BrokerAccountRecord,
    BrokerAuditEvent,
    BrokerConnectionRecord,
)
from twf.infrastructure.identity import AuthSession, User
from twf.secrets import (
    MemorySecretStore,
    SecretScope,
    SecretValue,
    UnavailableSecretStore,
)


@dataclass(frozen=True)
class Lease:
    account_id: UUID
    owner: UUID
    generation: int
    revision: int
    enabled: bool
    configured: bool
    subject: str | None
    api_key: str | None
    config_ref: str | None
    config_generation: int | None
    credential_revision: int | None
    active_ref: str | None
    auth_state: str


class BrokerAuth(BrokerFoundation):
    settings: Settings
    provider: AuthProvider

    def setup(self, settings: Settings, provider: AuthProvider) -> "BrokerAuth":
        self.settings, self.provider = settings, provider
        return self

    def _audit(self, account: BrokerAccountRecord, event_type: str) -> None:
        outcome = (
            "REJECTED"
            if event_type.endswith("REJECTED")
            else "FAILED"
            if event_type.endswith("FAILED")
            else "SUCCEEDED"
        )
        self.session.add(
            BrokerAuditEvent(
                owner_user_id=account.owner_user_id,
                broker_account_id=account.id,
                provider_id=account.provider_id,
                event_type=event_type,
                configuration_revision=account.configuration_revision,
                connection_generation=account.connection_generation,
                request_id=self.request_id,
                outcome=outcome,
                created_at=datetime.now(UTC),
            )
        )

    def available(self) -> bool:
        return (
            self.settings.zerodha_auth_enabled
            and self.secret_store.production_safe is True
            and not isinstance(self.secret_store, (MemorySecretStore, UnavailableSecretStore))
        )

    def providers(self) -> tuple[ProviderStatus, ...]:
        return tuple(
            value.model_copy(update={"connectable": self.available()})
            for value in super().providers()
        )

    def _lease(self, account_id: UUID, permission: BrokerPermission) -> Lease:
        self.session.rollback()
        account = self._account(account_id, permission)
        if account.environment != self.environment or account.provider_id != "zerodha":
            raise BrokerFoundationFailure(404)
        connection = self.session.get(BrokerConnectionRecord, account_id)
        config = self.session.get(BrokerAuthConfiguration, account_id)
        if connection is None:
            raise BrokerFoundationFailure(404)
        lease = Lease(
            account.id,
            account.owner_user_id,
            account.connection_generation,
            account.configuration_revision,
            account.enabled,
            account.configured,
            account.provider_account_id,
            config.api_key if config else None,
            config.secret_reference if config else None,
            config.secret_generation if config else None,
            config.credential_revision if config else None,
            connection.secret_reference,
            connection.authentication_state,
        )
        self.session.rollback()
        return lease

    def _check(self, lease: Lease, permission: BrokerPermission = BrokerPermission.CONNECT) -> None:
        if self._lease(lease.account_id, permission) != lease:
            raise BrokerFoundationFailure(409)

    @staticmethod
    def _sqlite_contention(error: OperationalError) -> bool:
        return isinstance(error.orig, sqlite3.OperationalError) and (
            getattr(error.orig, "sqlite_errorcode", 0) & 0xFF
        ) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}

    def _audit_rejection(self, state_hash: str) -> None:
        # One write statement, with no prior read snapshot to upgrade on SQLite.
        # SQLite's existing finite busy timeout is the only wait; never replay auth I/O.
        self.session.rollback()
        try:
            self.session.execute(
                insert(BrokerAuditEvent).from_select(
                    [
                        "id",
                        "owner_user_id",
                        "broker_account_id",
                        "provider_id",
                        "event_type",
                        "configuration_revision",
                        "connection_generation",
                        "request_id",
                        "outcome",
                        "created_at",
                    ],
                    select(
                        literal(uuid4()),
                        BrokerAccountRecord.owner_user_id,
                        BrokerAccountRecord.id,
                        BrokerAccountRecord.provider_id,
                        literal("CALLBACK_REJECTED"),
                        BrokerAccountRecord.configuration_revision,
                        BrokerAccountRecord.connection_generation,
                        literal(self.request_id),
                        literal("REJECTED"),
                        literal(datetime.now(UTC)),
                    )
                    .join(
                        BrokerAuthAttempt,
                        BrokerAuthAttempt.broker_account_id == BrokerAccountRecord.id,
                    )
                    .where(
                        BrokerAuthAttempt.state_hash == state_hash,
                        BrokerAuthAttempt.owner_user_id == self.actor_user_id,
                        BrokerAccountRecord.owner_user_id == self.actor_user_id,
                    ),
                )
            )
            self._commit()
        except OperationalError as error:
            self.session.rollback()
            if not self._sqlite_contention(error):
                raise
            self.logger.warning("broker_callback_rejection_audit_contended")

    def _lock(self, lease: Lease, permission: BrokerPermission) -> BrokerAccountRecord:
        self._authorized(permission, lease.owner)
        try:
            result = self.session.execute(
                update(BrokerAccountRecord)
                .where(
                    BrokerAccountRecord.id == lease.account_id,
                    BrokerAccountRecord.owner_user_id == lease.owner,
                    BrokerAccountRecord.environment == self.environment,
                    BrokerAccountRecord.connection_generation == lease.generation,
                    BrokerAccountRecord.configuration_revision == lease.revision,
                    BrokerAccountRecord.enabled == lease.enabled,
                )
                .values(updated_at=datetime.now(UTC))
                .execution_options(synchronize_session=False)
            )
        except OperationalError as error:
            self.session.rollback()
            if not self._sqlite_contention(error):
                raise
            raise BrokerFoundationFailure(409) from None
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            self.session.rollback()
            raise BrokerFoundationFailure(409)
        account = self.session.get(BrokerAccountRecord, lease.account_id, populate_existing=True)
        if account is None:
            raise BrokerFoundationFailure(404)
        return account

    def _connection(self, account_id: UUID) -> BrokerConnectionRecord:
        connection = self.session.get(BrokerConnectionRecord, account_id, populate_existing=True)
        if connection is None:
            raise BrokerFoundationFailure(404)
        return connection

    def _session_valid(self, session_hash: str, owner: UUID) -> bool:
        session = self.session.get(AuthSession, session_hash, populate_existing=True)
        user = self.session.get(User, owner, populate_existing=True)
        return bool(
            session
            and session.user_id == owner
            and session.revoked_at is None
            and self._aware(session.expires_at) > datetime.now(UTC)
            and user
            and user.is_active
        )

    def _scope(self, row: BrokerSecretLifecycle) -> SecretScope:
        return SecretScope(
            row.owner_user_id,
            row.provider_id,
            row.broker_account_id,
            row.environment,
            row.generation,
            cast(Literal["access", "configuration", "pending"], row.purpose),
            row.context,
        )

    def _put(
        self,
        lease: Lease,
        value: SecretValue,
        purpose: Literal["access", "configuration", "pending"],
        generation: int,
        context: str,
        permission: BrokerPermission,
    ) -> str:
        self._check(lease, permission)
        scope = SecretScope(
            lease.owner, "zerodha", lease.account_id, self.environment, generation, purpose, context
        )
        try:
            saved = self.secret_store.put(scope, value)
        except Exception:
            raise BrokerFoundationFailure(503) from None
        row = BrokerSecretLifecycle(
            reference=saved.reference,
            broker_account_id=lease.account_id,
            owner_user_id=lease.owner,
            provider_id="zerodha",
            environment=self.environment,
            generation=generation,
            purpose=purpose,
            context=context,
            state="CANDIDATE",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
            cleanup_attempts=0,
        )
        self.session.add(row)
        try:
            self._commit()
        except Exception:
            self.session.rollback()
            try:
                self.secret_store.delete(scope, saved.reference)
            except Exception:
                self.logger.warning("broker_secret_storage_compensation_failed")
            raise BrokerFoundationFailure(503) from None
        return saved.reference

    def resolve(
        self,
        lease: Lease,
        reference: str,
        purpose: str,
        *,
        attempt: str | None = None,
        permission: BrokerPermission = BrokerPermission.CONNECT,
    ) -> SecretValue:
        """Re-read durable authority before/after vault access; never trust a reference alone."""
        self._check(lease, permission)
        row = self.session.get(BrokerSecretLifecycle, reference, populate_existing=True)
        valid = bool(
            row
            and row.owner_user_id == lease.owner
            and row.broker_account_id == lease.account_id
            and row.provider_id == "zerodha"
            and row.environment == self.environment
            and row.purpose == purpose
        )
        if row and purpose == "configuration":
            valid = (
                valid
                and row.state == "ACTIVE"
                and reference == lease.config_ref
                and row.generation == lease.generation == lease.config_generation
                and row.context == str(lease.credential_revision)
            )
        elif row and purpose == "access":
            connection = self._connection(lease.account_id)
            if connection.expires_at and self._aware(connection.expires_at) <= datetime.now(UTC):
                self.session.rollback()
                raise BrokerFoundationFailure(409)
            valid = (
                valid
                and row.state == "ACTIVE"
                and reference == lease.active_ref
                and row.generation == lease.generation
                and lease.auth_state == "CONNECTED"
                and lease.enabled
            )
        elif row and purpose == "pending":
            auth = self.session.get(BrokerAuthAttempt, attempt)
            valid = (
                valid
                and row.state == "CANDIDATE"
                and row.context == attempt
                and row.generation == lease.generation + 1
                and bool(
                    auth
                    and auth.status == "FINALIZING"
                    and auth.pending_reference == reference
                    and self._aware(auth.expires_at) > datetime.now(UTC)
                )
            )
        else:
            valid = False
        if not valid or row is None:
            self.session.rollback()
            raise BrokerFoundationFailure(409)
        scope, state = self._scope(row), row.state
        self.session.rollback()
        try:
            value = self.secret_store.get(scope, reference)
        except Exception:
            raise BrokerFoundationFailure(503) from None
        self._check(lease, permission)
        current = self.session.get(BrokerSecretLifecycle, reference, populate_existing=True)
        valid_after = current is not None and current.state == state
        self.session.rollback()
        if not valid_after:
            raise BrokerFoundationFailure(409)
        return value

    def _revoke(self, account: BrokerAccountRecord, keep: tuple[str, ...] = ()) -> None:
        rows = self.session.scalars(
            select(BrokerSecretLifecycle).where(
                BrokerSecretLifecycle.broker_account_id == account.id,
                BrokerSecretLifecycle.state.in_(("ACTIVE", "CANDIDATE")),
            )
        )
        for row in rows:
            if row.reference not in keep:
                row.state = "REVOKED"
                self._audit(account, "SECRET_CLEANUP_PENDING")
        for attempt in self.session.scalars(
            select(BrokerAuthAttempt).where(
                BrokerAuthAttempt.broker_account_id == account.id,
                BrokerAuthAttempt.status.in_(("CREATED", "EXCHANGING", "PENDING", "FINALIZING")),
            )
        ):
            attempt.status = "REJECTED"

    def _activate(self, reference: str) -> None:
        row = self.session.get(BrokerSecretLifecycle, reference, populate_existing=True)
        if (
            row is None
            or row.state != "CANDIDATE"
            or row.expires_at is None
            or self._aware(row.expires_at) <= datetime.now(UTC)
        ):
            raise BrokerFoundationFailure(409)
        row.state, row.expires_at = "ACTIVE", None

    def cleanup(
        self, account_id: UUID, permission: BrokerPermission = BrokerPermission.DISCONNECT
    ) -> int:
        """Bounded explicit/on-action recovery. Revocation is durable before vault deletion."""
        lease = self._lease(account_id, permission)
        account = self._lock(lease, permission)
        now = datetime.now(UTC)
        for attempt in self.session.scalars(
            select(BrokerAuthAttempt).where(
                BrokerAuthAttempt.broker_account_id == account_id,
                BrokerAuthAttempt.expires_at <= now,
                BrokerAuthAttempt.status.in_(("CREATED", "EXCHANGING", "PENDING", "FINALIZING")),
            )
        ):
            attempt.status = "REJECTED"
            if attempt.pending_reference:
                row = self.session.get(BrokerSecretLifecycle, attempt.pending_reference)
                if row and row.state == "CANDIDATE":
                    row.state = "REVOKED"
                    self._audit(account, "SECRET_CLEANUP_PENDING")
        for row in self.session.scalars(
            select(BrokerSecretLifecycle).where(
                BrokerSecretLifecycle.broker_account_id == account_id,
                BrokerSecretLifecycle.state == "CANDIDATE",
                BrokerSecretLifecycle.expires_at <= now,
            )
        ):
            row.state = "REVOKED"
            self._audit(account, "SECRET_CLEANUP_PENDING")
        self._commit()
        rows = list(
            self.session.scalars(
                select(BrokerSecretLifecycle)
                .where(
                    BrokerSecretLifecycle.broker_account_id == account_id,
                    BrokerSecretLifecycle.state == "REVOKED",
                )
                .limit(10)
            )
        )
        candidates = [(row.reference, self._scope(row)) for row in rows]
        self.session.rollback()
        for reference, scope in candidates:
            deleted = False
            try:
                deleted = self.secret_store.delete(scope, reference)
            except Exception:
                self.logger.warning("broker_secret_cleanup_failed")
            row = self.session.get(BrokerSecretLifecycle, reference, populate_existing=True)
            if row and row.state == "REVOKED":
                row.cleanup_attempts += 1
                if deleted:
                    row.state = "DELETED"
                    cleanup_account = self.session.get(BrokerAccountRecord, account_id)
                    if cleanup_account:
                        self._audit(cleanup_account, "SECRET_CLEANUP_COMPLETED")
                self._commit()
        pending = len(
            list(
                self.session.scalars(
                    select(BrokerSecretLifecycle.reference).where(
                        BrokerSecretLifecycle.broker_account_id == account_id,
                        BrokerSecretLifecycle.state == "REVOKED",
                    )
                )
            )
        )
        self.session.rollback()
        return pending

    def _discard(self, references: list[str]) -> None:
        self.session.rollback()
        for ref in references:
            row = self.session.get(BrokerSecretLifecycle, ref)
            if row and row.state == "CANDIDATE":
                row.state = "REVOKED"
                discarded_account = self.session.get(BrokerAccountRecord, row.broker_account_id)
                if discarded_account:
                    self._audit(discarded_account, "SECRET_CLEANUP_PENDING")
        self._commit()

    def configure(
        self,
        account_id: UUID,
        api_key: str,
        secret: SecretValue,
        expected_revision: int,
        expected_generation: int,
    ) -> None:
        lease = self._lease(account_id, BrokerPermission.CONFIGURE)
        if (lease.revision, lease.generation) != (expected_revision, expected_generation):
            raise BrokerFoundationFailure(409)
        ref = self._put(
            lease,
            secret,
            "configuration",
            lease.generation,
            str(lease.revision + 1),
            BrokerPermission.CONFIGURE,
        )
        try:
            account = self._lock(lease, BrokerPermission.CONFIGURE)
            account.configuration_revision += 1
            account.enabled, account.configured = True, True
            self._revoke(account, (ref,))
            self._activate(ref)
            config = self.session.get(BrokerAuthConfiguration, account_id)
            if config is None:
                config = BrokerAuthConfiguration(broker_account_id=account_id)
                self.session.add(config)
            config.api_key, config.secret_reference = api_key, ref
            config.secret_generation, config.credential_revision = (
                lease.generation,
                account.configuration_revision,
            )
            connection = self._connection(account_id)
            connection.secret_reference = None
            connection.authentication_state, connection.read_health = "AUTH_REQUIRED", "UNKNOWN"
            connection.expires_at = None
            self._audit(account, "PROVIDER_CONFIGURED")
            self._commit()
        except Exception:
            self._discard([ref])
            raise
        self.cleanup(account_id, BrokerPermission.CONFIGURE)

    def expire(self, account_id: UUID) -> None:
        lease = self._lease(account_id, BrokerPermission.CONNECT)
        connection = self._connection(account_id)
        expired = connection.expires_at and self._aware(connection.expires_at) <= datetime.now(UTC)
        self.session.rollback()
        if lease.auth_state != "CONNECTED" or not expired:
            return
        account = self._lock(lease, BrokerPermission.CONNECT)
        connection = self._connection(account_id)
        if connection.secret_reference:
            row = self.session.get(BrokerSecretLifecycle, connection.secret_reference)
            if row:
                row.state = "REVOKED"
                self._audit(account, "SECRET_CLEANUP_PENDING")
        connection.secret_reference = None
        connection.authentication_state = "REAUTH_REQUIRED"
        self._audit(account, "REAUTH_REQUIRED")
        self._commit()

    def initiate(self, account_id: UUID, session_hash: str) -> str:
        self.cleanup(account_id, BrokerPermission.CONNECT)
        self.expire(account_id)
        lease = self._lease(account_id, BrokerPermission.CONNECT)
        if not self.available():
            raise BrokerFoundationFailure(503)
        if not lease.enabled or not lease.configured or not lease.config_ref or not lease.api_key:
            raise BrokerFoundationFailure(409)
        if lease.auth_state == "CONNECTED":
            raise BrokerFoundationFailure(409)
        self.resolve(lease, lease.config_ref, "configuration")
        account = self._lock(lease, BrokerPermission.CONNECT)
        if not self._session_valid(session_hash, lease.owner):
            self.session.rollback()
            raise BrokerFoundationFailure(401)
        existing = self.session.scalar(
            select(BrokerAuthAttempt.state_hash).where(
                BrokerAuthAttempt.broker_account_id == account_id,
                BrokerAuthAttempt.status.in_(("CREATED", "EXCHANGING", "PENDING", "FINALIZING")),
                BrokerAuthAttempt.expires_at > datetime.now(UTC),
            )
        )
        if existing:
            self.session.rollback()
            raise BrokerFoundationFailure(409)
        state = token_urlsafe(32)
        self.session.add(
            BrokerAuthAttempt(
                state_hash=token_digest(state),
                broker_account_id=account_id,
                owner_user_id=lease.owner,
                session_hash=session_hash,
                provider_id="zerodha",
                environment=self.environment,
                generation=lease.generation,
                revision=lease.revision,
                status="CREATED",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
        self._connection(account_id).authentication_state = "AUTH_IN_PROGRESS"
        self._audit(account, "CONNECT_INITIATED")
        self._commit()
        return "https://kite.zerodha.com/connect/login?" + urlencode(
            {"v": "3", "api_key": lease.api_key, "redirect_params": urlencode({"state": state})}
        )

    def _attempt(self, state_hash: str, status: str) -> tuple[BrokerAuthAttempt, Lease]:
        self.session.rollback()
        attempt = self.session.get(BrokerAuthAttempt, state_hash)
        if (
            not attempt
            or attempt.status != status
            or self._aware(attempt.expires_at) <= datetime.now(UTC)
        ):
            raise BrokerFoundationFailure(409)
        if (
            attempt.owner_user_id != self.actor_user_id
            or attempt.provider_id != "zerodha"
            or attempt.environment != self.environment
            or not self._session_valid(attempt.session_hash, attempt.owner_user_id)
        ):
            raise BrokerFoundationFailure(404)
        # Detached metadata survives rollback; it contains no provider secret.
        self.session.expunge(attempt)
        lease = self._lease(attempt.broker_account_id, BrokerPermission.CONNECT)
        if (
            not lease.enabled
            or not lease.configured
            or (lease.generation, lease.revision) != (attempt.generation, attempt.revision)
        ):
            raise BrokerFoundationFailure(409)
        return attempt, lease

    def _claim(
        self, lease: Lease, state_hash: str, previous: str, target: str
    ) -> BrokerAccountRecord:
        account = self._lock(lease, BrokerPermission.CONNECT)
        result = self.session.execute(
            update(BrokerAuthAttempt)
            .where(
                BrokerAuthAttempt.state_hash == state_hash,
                BrokerAuthAttempt.status == previous,
                BrokerAuthAttempt.expires_at > datetime.now(UTC),
            )
            .values(status=target)
        )
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            self.session.rollback()
            raise BrokerFoundationFailure(409)
        return account

    def reject(self, state_hash: str, code: str = "ERROR") -> None:
        self.session.rollback()
        original = self.session.get(BrokerAuthAttempt, state_hash)
        if not original or original.owner_user_id != self.actor_user_id:
            self.session.rollback()
            return
        account_id = original.broker_account_id
        self.session.rollback()
        lease = self._lease(account_id, BrokerPermission.CONNECT)
        account = self._lock(lease, BrokerPermission.CONNECT)
        attempt = self.session.get(BrokerAuthAttempt, state_hash, populate_existing=True)
        if not attempt or attempt.status in {"FINISHED", "REJECTED"}:
            self.session.rollback()
            return
        previous = attempt.status
        attempt.status = "REJECTED"
        if attempt.pending_reference:
            row = self.session.get(BrokerSecretLifecycle, attempt.pending_reference)
            if row and row.state == "CANDIDATE":
                row.state = "REVOKED"
                self._audit(account, "SECRET_CLEANUP_PENDING")
        self._audit(account, "CALLBACK_REJECTED")
        if previous == "EXCHANGING":
            self._audit(account, "TOKEN_EXCHANGE_FAILED")
        if (account.connection_generation, account.configuration_revision) == (
            attempt.generation,
            attempt.revision,
        ):
            self._connection(account.id).authentication_state = (
                "REAUTH_REQUIRED" if code == "REAUTH_REQUIRED" else "ERROR"
            )
            if code == "REAUTH_REQUIRED":
                self._audit(account, "REAUTH_REQUIRED")
        self._commit()

    def receive(self, state: str, request_token: SecretValue) -> str:
        state_hash = token_digest(state)
        refs: list[str] = []
        claimed = False
        try:
            attempt, lease = self._attempt(state_hash, "CREATED")
            if not self.available() or not lease.config_ref or not lease.api_key:
                raise BrokerFoundationFailure(503)
            account = self._claim(lease, state_hash, "CREATED", "EXCHANGING")
            self._audit(account, "CALLBACK_ACCEPTED")
            self._commit()
            claimed = True
            secret = self.resolve(lease, lease.config_ref, "configuration")
            grant = self.provider.exchange(lease.api_key, secret, request_token)
            self._check(lease)
            ref = self._put(
                lease,
                grant.token,
                "pending",
                lease.generation + 1,
                state_hash,
                BrokerPermission.CONNECT,
            )
            refs.append(ref)
            account = self._claim(lease, state_hash, "EXCHANGING", "PENDING")
            if not self._session_valid(attempt.session_hash, lease.owner):
                raise BrokerFoundationFailure(401)
            pending = self.session.get(BrokerAuthAttempt, state_hash, populate_existing=True)
            assert pending is not None
            nonce = token_urlsafe(32)
            pending.finalize_hash, pending.pending_reference = token_digest(nonce), ref
            pending.verified_subject = grant.subject
            self._audit(account, "TOKEN_EXCHANGE_SUCCEEDED")
            self._commit()
            return nonce
        except (ProviderAuthFailure, BrokerFoundationFailure) as error:
            self._discard(refs)
            if not claimed:
                self._audit_rejection(state_hash)
            if claimed:
                self.reject(
                    state_hash, error.code if isinstance(error, ProviderAuthFailure) else "ERROR"
                )
            raise BrokerFoundationFailure(400 if claimed else 409) from None

    def finalize(self, nonce: str, session_hash: str) -> UUID:
        self.session.rollback()
        state_hash = self.session.scalar(
            select(BrokerAuthAttempt.state_hash).where(
                BrokerAuthAttempt.finalize_hash == token_digest(nonce),
                BrokerAuthAttempt.owner_user_id == self.actor_user_id,
            )
        )
        if not state_hash:
            raise BrokerFoundationFailure(404)
        refs: list[str] = []
        claimed = False
        try:
            attempt, lease = self._attempt(state_hash, "PENDING")
            if attempt.session_hash != session_hash:
                raise BrokerFoundationFailure(404)
            if (
                not self.available()
                or not attempt.pending_reference
                or not lease.api_key
                or not lease.config_ref
            ):
                raise BrokerFoundationFailure(503)
            self._claim(lease, state_hash, "PENDING", "FINALIZING")
            self._commit()
            claimed = True
            token = self.resolve(lease, attempt.pending_reference, "pending", attempt=state_hash)
            subject = self.provider.profile(lease.api_key, token)
            self._check(lease)
            if subject != attempt.verified_subject or (lease.subject and subject != lease.subject):
                raise ProviderAuthFailure("IDENTITY_MISMATCH")
            config_secret = self.resolve(lease, lease.config_ref, "configuration")
            active = self._put(
                lease, token, "access", lease.generation + 1, "", BrokerPermission.CONNECT
            )
            refs.append(active)
            config_ref = self._put(
                lease,
                config_secret,
                "configuration",
                lease.generation + 1,
                str(lease.credential_revision),
                BrokerPermission.CONNECT,
            )
            refs.append(config_ref)
            account = self._claim(lease, state_hash, "FINALIZING", "FINISHED")
            if not self._session_valid(session_hash, lease.owner):
                raise BrokerFoundationFailure(401)
            account.connection_generation += 1
            account.provider_account_id = subject
            self._revoke(account, (active, config_ref))
            self._activate(active)
            self._activate(config_ref)
            config = self.session.get(BrokerAuthConfiguration, account.id)
            assert config is not None
            config.secret_reference, config.secret_generation = (
                config_ref,
                account.connection_generation,
            )
            now = datetime.now(UTC)
            config.bound_at = config.bound_at or now
            config.last_auth_success_at = now
            connection = self._connection(account.id)
            connection.secret_reference = active
            connection.authentication_state, connection.read_health = "CONNECTED", "UNKNOWN"
            connection.applied_configuration_revision = account.configuration_revision
            local = now.astimezone(ZoneInfo("Asia/Kolkata"))
            connection.expires_at = (
                (local + timedelta(days=1))
                .replace(hour=6, minute=0, second=0, microsecond=0)
                .astimezone(UTC)
            )
            connection.updated_at = now
            self._audit(account, "ACCOUNT_BOUND")
            self._commit()
        except (ProviderAuthFailure, BrokerFoundationFailure) as error:
            self._discard(refs)
            if not claimed:
                self._audit_rejection(state_hash)
            if claimed:
                self.reject(
                    state_hash, error.code if isinstance(error, ProviderAuthFailure) else "ERROR"
                )
            raise BrokerFoundationFailure(409) from None
        self.cleanup(lease.account_id, BrokerPermission.CONNECT)
        return lease.account_id

    def disconnect(self, account_id: UUID, expected_generation: int) -> None:
        lease = self._lease(account_id, BrokerPermission.DISCONNECT)
        if lease.generation != expected_generation:
            raise BrokerFoundationFailure(409)
        refs: list[str] = []
        try:
            if lease.config_ref:
                try:
                    secret = self.resolve(
                        lease,
                        lease.config_ref,
                        "configuration",
                        permission=BrokerPermission.DISCONNECT,
                    )
                    refs.append(
                        self._put(
                            lease,
                            secret,
                            "configuration",
                            lease.generation + 1,
                            str(lease.credential_revision),
                            BrokerPermission.DISCONNECT,
                        )
                    )
                except BrokerFoundationFailure as error:
                    if error.status != 503:
                        raise
                    self.session.rollback()
            account = self._lock(lease, BrokerPermission.DISCONNECT)
            account.connection_generation += 1
            self._revoke(account, tuple(refs))
            config = self.session.get(BrokerAuthConfiguration, account_id)
            if not refs:
                account.configured = False
            if refs and config:
                self._activate(refs[0])
                config.secret_reference, config.secret_generation = (
                    refs[0],
                    account.connection_generation,
                )
            connection = self._connection(account_id)
            connection.secret_reference, connection.expires_at = None, None
            connection.authentication_state, connection.read_health = "DISCONNECTED", "UNKNOWN"
            self._audit(account, "LOCAL_DISCONNECTED")
            self._commit()
        except Exception:
            self._discard(refs)
            raise
        self.cleanup(account_id)
