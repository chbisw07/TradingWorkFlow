"""Durable personal connections; short locked transactions surround external I/O."""

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import anyio
from pydantic import JsonValue, SecretStr, TypeAdapter
from sqlalchemy import delete, event, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from twf.auth import token_digest
from twf.brokers.secrets import CredentialCipher
from twf.config.settings import Settings
from twf.infrastructure.identity import AuthSession, User
from twf.infrastructure.mcp import MCPConnection, MCPOAuthAttempt, MCPOperation, MCPSecret
from twf.integrations.contracts import Health
from twf.integrations.mcp.client import SDKClient, ToolClient
from twf.integrations.mcp.contracts import (
    AuthMode,
    Authorization,
    Code,
    ConnectionView,
    Context,
    Failure,
    ProviderConfig,
    State,
    TokenBundle,
    Tool,
    ToolPolicy,
)
from twf.integrations.mcp.http import HTTPFactory, dispatch_fence, mapped, suppress_library_logs
from twf.integrations.mcp.lifecycle import Operation, Operations
from twf.integrations.mcp.lifecycle import operation as active_operation
from twf.integrations.mcp.oauth import ApiKeyAuth, AuthStrategy, NoAuth, OAuth21Auth, nonce
from twf.settings_contracts import SecretReference

TOOLS = TypeAdapter(tuple[Tool, ...])
DENY_ALL = ToolPolicy()
DRAINING = {State.DISCONNECTING, State.REAUTH_DRAINING}


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def fingerprint(config: ProviderConfig) -> str:
    return hashlib.sha256(config.model_dump_json().encode()).hexdigest()


class ConnectionManager:
    def __init__(
        self,
        factory: sessionmaker[Session],
        settings: Settings,
        providers: tuple[ProviderConfig, ...] = (),
        *,
        client: ToolClient | None = None,
        http: HTTPFactory | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if len({p.provider_id for p in providers}) != len(providers) or len(providers) > 16:
            raise Failure(Code.NOT_CONFIGURED)
        self.factory, self.settings = factory, settings
        self.worker_id = uuid4()
        self.operations = Operations()
        self.providers = {p.provider_id: p for p in providers}
        self.http = http or HTTPFactory()
        self.client = client or SDKClient(self.http)
        self.oauth = OAuth21Auth(self.http)
        self.strategies: dict[AuthMode, AuthStrategy] = {
            AuthMode.NONE: NoAuth(),
            AuthMode.API_KEY: ApiKeyAuth(),
            AuthMode.OAUTH_2_1: self.oauth,
        }
        self.logger = logger or logging.getLogger("twf.mcp")
        suppress_library_logs()

    def config(self, provider: str) -> ProviderConfig:
        if provider not in self.providers:
            raise Failure(Code.NOT_CONFIGURED)
        return self.providers[provider]

    def seal(self, data: dict[str, JsonValue]) -> str:
        try:
            return CredentialCipher(self.settings).encrypt(json.dumps(data).encode())
        except Exception:
            raise Failure(Code.STORAGE) from None

    def unseal(self, data: str) -> dict[str, JsonValue]:
        try:
            result = json.loads(CredentialCipher(self.settings).decrypt(data))
            if not isinstance(result, dict):
                raise ValueError
            return result
        except Exception:
            raise Failure(Code.STORAGE) from None

    def transaction[T](self, operation: Callable[[Session], T]) -> T:
        for attempt in range(3):
            try:
                with self.factory() as db:
                    if db.get_bind().dialect.name == "sqlite":
                        db.connection().exec_driver_sql("PRAGMA busy_timeout=200")
                        db.execute(
                            update(MCPConnection)
                            .where(MCPConnection.id == UUID(int=0))
                            .values(generation=0)
                        )
                    result = operation(db)
                    db.commit()
                    return result
            except IntegrityError:
                raise Failure(Code.STALE) from None
            except OperationalError as exc:
                if db.get_bind().dialect.name != "sqlite" or "locked" not in str(exc.orig).lower():
                    raise Failure(Code.STORAGE) from None
                if attempt == 2:
                    raise Failure(Code.STALE) from None
                time.sleep(0.025 * (attempt + 1))
        raise Failure(Code.STALE)

    async def write[T](self, operation: Callable[[Session], T]) -> T:
        # A cancelled invocation must still own its DB worker until commit/rollback;
        # otherwise final permit completion could race a still-running admission.
        task = asyncio.create_task(asyncio.to_thread(self.transaction, operation))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            with anyio.CancelScope(shield=True):
                await task
            raise

    @staticmethod
    def authorize(db: Session, who: Context) -> None:
        login = db.get(AuthSession, who.session_hash, with_for_update=True)
        user = db.get(User, who.owner_id, with_for_update=True)
        if (
            not login
            or login.user_id != who.owner_id
            or login.revoked_at
            or utc(login.expires_at) <= datetime.now(UTC)
            or not user
            or not user.is_active
        ):
            raise Failure(Code.DENIED)

    def owned(self, db: Session, who: Context, identity: UUID) -> MCPConnection:
        self.authorize(db, who)
        row = db.scalar(
            select(MCPConnection)
            .where(
                MCPConnection.id == identity,
                MCPConnection.owner_id == who.owner_id,
            )
            .with_for_update()
        )
        if row is None:
            raise Failure(Code.DENIED)
        return row

    def current(
        self, row: MCPConnection, generation: int, *, enabled: bool = True
    ) -> ProviderConfig:
        config = self.config(row.provider_id)
        if row.auth_invalidation_pending or row.state == State.REAUTH_DRAINING:
            raise Failure(Code.REAUTH_REQUIRED)
        if row.state == State.DISCONNECTING:
            raise Failure(Code.STALE)
        if row.generation != generation or row.config_fingerprint != fingerprint(config):
            raise Failure(Code.STALE)
        # The owner's row lock serializes this check with cleanup claims across
        # their connections to this provider. No DB lock spans provider I/O.
        with self.factory() as check:
            claimed = check.scalar(
                select(MCPConnection.id)
                .where(
                    MCPConnection.owner_id == row.owner_id,
                    MCPConnection.provider_id == row.provider_id,
                    MCPConnection.cleanup_until > datetime.now(UTC),
                )
                .limit(1)
            )
            cleanup_running = check.scalar(
                select(MCPOperation.id)
                .join(MCPConnection, MCPOperation.connection_id == MCPConnection.id)
                .where(
                    MCPConnection.owner_id == row.owner_id,
                    MCPConnection.provider_id == row.provider_id,
                    MCPOperation.kind == "REVOCATION",
                    (MCPOperation.state != "COMPLETE")
                    | MCPOperation.reconciliation_required.is_(True),
                )
                .limit(1)
            )
        if claimed or cleanup_running:
            raise Failure(Code.STALE)
        if enabled and not row.enabled:
            raise Failure(Code.CLOSED)
        return config

    def view(self, db: Session, row: MCPConnection) -> ConnectionView:
        pending = (
            db.scalar(
                select(MCPSecret.id)
                .where(MCPSecret.connection_id == row.id, MCPSecret.revoked.is_(True))
                .limit(1)
            )
            is not None
        )
        state, health = State(row.state), Health(row.health)
        error = Code(row.error) if row.error else None
        if row.state not in DRAINING and (
            (row.expires_at and utc(row.expires_at) <= datetime.now(UTC))
            or (
                state == State.CONNECTING
                and utc(row.updated_at) + timedelta(minutes=5) <= datetime.now(UTC)
            )
        ):
            state, health, error = State.REAUTH_REQUIRED, Health.DEGRADED, Code.REAUTH_REQUIRED
        configured = self.providers.get(row.provider_id)
        if configured is None or fingerprint(configured) != row.config_fingerprint:
            health, error = Health.UNAVAILABLE, Code.STALE
            if row.enabled:
                state = State.REAUTH_REQUIRED
        if row.auth_invalidation_pending:
            state, health, error = State.REAUTH_DRAINING, Health.UNAVAILABLE, Code.REAUTH_REQUIRED
        outstanding = self.pending(db, row.id)
        recovery_required = row.auth_invalidation_pending or any(
            p.reconciliation_required
            or p.state == "UNRESOLVED"
            or utc(p.deadline_at) <= datetime.now(UTC)
            for p in outstanding
        )
        if recovery_required and not row.auth_invalidation_pending:
            health, error = Health.DEGRADED, error or Code.STALE
        return ConnectionView(
            operations_pending=len(outstanding),
            recovery_required=recovery_required,
            id=row.id,
            owner_id=row.owner_id,
            provider_id=row.provider_id,
            display_name=row.display_name,
            enabled=row.enabled and not row.auth_invalidation_pending,
            generation=row.generation,
            state=state,
            health=health,
            tools=TOOLS.validate_json(row.tools_json),
            secret_ref=SecretReference(
                reference_id=row.secret_id, owner_id=row.owner_id, ownership="USER_MANAGED"
            )
            if row.secret_id
            else None,
            error=error,
            cleanup_pending=pending,
            created_at=utc(row.created_at),
            updated_at=utc(row.updated_at),
            last_success_at=utc(row.last_success_at) if row.last_success_at else None,
            expires_at=utc(row.expires_at) if row.expires_at else None,
        )

    def status(self, who: Context, identity: UUID) -> ConnectionView:
        with self.factory() as db:
            return self.view(db, self.owned(db, who, identity))

    def connections(
        self, who: Context, provider_id: str | None = None
    ) -> tuple[ConnectionView, ...]:
        """List only the caller's connections; never expose another owner's metadata."""
        with self.factory() as db:
            self.authorize(db, who)
            statement = select(MCPConnection).where(MCPConnection.owner_id == who.owner_id)
            if provider_id is not None:
                statement = statement.where(MCPConnection.provider_id == provider_id)
            rows = tuple(db.scalars(statement.order_by(MCPConnection.updated_at.desc())))
            return tuple(self.view(db, row) for row in rows)

    def audit(
        self, who: Context, identity: UUID, generation: int, operation: str, outcome: str
    ) -> None:
        self.logger.info(
            "mcp_operation",
            extra={
                "connection_id": str(identity),
                "generation": generation,
                "operation": operation,
                "outcome": outcome,
                "operation_request_id": who.correlation.request_id,
            },
        )

    async def create(self, who: Context, provider: str, name: str) -> ConnectionView:
        config = self.config(provider)
        if not name.strip() or len(name) > 80 or any(ord(c) < 32 for c in name):
            raise Failure(Code.INVALID_ARGUMENTS)

        def save(db: Session) -> ConnectionView:
            self.authorize(db, who)
            now = datetime.now(UTC)
            row = MCPConnection(
                id=uuid4(),
                owner_id=who.owner_id,
                provider_id=provider,
                config_fingerprint=fingerprint(config),
                display_name=name,
                enabled=False,
                generation=0,
                state=State.DISCONNECTED.value,
                health=Health.UNKNOWN.value,
                tools_json="[]",
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            return self.view(db, row)

        return await self.write(save)

    def retire(self, db: Session, row: MCPConnection, *, revoke: bool = True) -> None:
        if row.secret_id:
            secret = db.get(MCPSecret, row.secret_id)
            if secret:
                secret.revoked = True
                secret.revoke_pending = revoke
        row.secret_id = None
        row.expires_at = None
        row.tools_json = "[]"
        row.health = Health.UNKNOWN.value
        row.error = None
        row.updated_at = datetime.now(UTC)
        # No obsolete PKCE plaintext/encrypted verifier remains usable.
        db.execute(delete(MCPOAuthAttempt).where(MCPOAuthAttempt.connection_id == row.id))

    def make_secret(
        self,
        row: MCPConnection,
        bundle: TokenBundle,
        generation: int,
        *,
        revoked: bool = False,
    ) -> MCPSecret:
        identity = uuid4()
        ciphertext = self.seal(
            {
                "reference": str(identity),
                "connection": str(row.id),
                "owner": str(row.owner_id),
                "generation": generation,
                "provider": row.provider_id,
                "access_token": bundle.access_token.get_secret_value(),
                "refresh_token": bundle.refresh_token.get_secret_value()
                if bundle.refresh_token
                else None,
                "token_type": bundle.token_type,
                "scopes": list(bundle.scopes),
                "expires_at": bundle.expires_at.isoformat() if bundle.expires_at else None,
            }
        )
        return MCPSecret(
            id=identity,
            connection_id=row.id,
            generation=generation,
            ciphertext=ciphertext,
            revoked=revoked,
            revoke_pending=revoked,
            created_at=datetime.now(UTC),
        )

    def store(self, db: Session, row: MCPConnection, bundle: TokenBundle) -> None:
        secret = self.make_secret(row, bundle, row.generation)
        db.add(secret)
        row.secret_id, row.expires_at = secret.id, bundle.expires_at

    async def discard_late(
        self,
        who: Context,
        identity: UUID,
        generation: int,
        config: ProviderConfig,
        bundle: TokenBundle,
    ) -> None:
        await self.queue_token(who, identity, generation, config, bundle)
        try:
            await self.cleanup(who, identity)
        except Exception:
            self.audit(who, identity, generation, "late_token_cleanup", "PENDING")

    async def queue_token(
        self,
        who: Context,
        identity: UUID,
        generation: int,
        config: ProviderConfig,
        bundle: TokenBundle,
    ) -> UUID:
        # Receipt creates a cleanup obligation even after logout or disconnect.
        def queue(db: Session) -> UUID:
            row = db.get(MCPConnection, identity, with_for_update=True)
            if row is None or row.owner_id != who.owner_id or row.provider_id != config.provider_id:
                raise Failure(Code.DENIED)
            secret = self.make_secret(row, bundle, generation, revoked=True)
            db.add(secret)
            return secret.id

        return await self.write(queue)

    def open_secret(self, row: MCPConnection, secret: MCPSecret) -> TokenBundle:
        data = self.unseal(secret.ciphertext)
        if (
            data.pop("reference", None) != str(secret.id)
            or data.pop("connection", None) != str(row.id)
            or data.pop("owner", None) != str(row.owner_id)
            or data.pop("generation", None) != secret.generation
            or data.pop("provider", None) != row.provider_id
        ):
            raise Failure(Code.REVOKED)
        try:
            return TokenBundle.model_validate(data)
        except ValueError:
            raise Failure(Code.STORAGE) from None

    def active_token(self, db: Session, row: MCPConnection) -> TokenBundle:
        secret = db.get(MCPSecret, row.secret_id) if row.secret_id else None
        if (
            not secret
            or secret.connection_id != row.id
            or secret.revoked
            or secret.generation != row.generation
        ):
            raise Failure(Code.REVOKED)
        return self.open_secret(row, secret)

    async def connect(
        self,
        who: Context,
        identity: UUID,
        generation: int,
        api_key: SecretStr | None = None,
    ) -> ConnectionView:
        await self.operations.wait_receipts()

        def save(db: Session) -> ConnectionView:
            row = self.owned(db, who, identity)
            self.require_drained(db, row)
            config = self.current(row, generation, enabled=False)
            if config.auth_mode == AuthMode.OAUTH_2_1:
                raise Failure(Code.AUTH_REQUIRED)
            bundle = TokenBundle(access_token=api_key) if api_key else None
            self.strategies[config.auth_mode].headers(bundle)
            if config.auth_mode == AuthMode.NONE and api_key is not None:
                raise Failure(Code.INVALID_ARGUMENTS)
            self.retire(db, row)
            row.generation += 1
            row.enabled, row.state = True, State.CONNECTED.value
            if bundle:
                self.store(db, row, bundle)
            db.flush()
            return self.view(db, row)

        result = await self.write(save)
        self.audit(who, identity, result.generation, "connect", "SUCCEEDED")
        return result

    async def begin(self, who: Context, identity: UUID, generation: int) -> Authorization:
        await self.operations.wait_receipts()
        state, verifier = nonce(), nonce()

        def save(db: Session) -> Authorization:
            row = self.owned(db, who, identity)
            self.require_drained(db, row)
            config = self.current(row, generation, enabled=False)
            if config.auth_mode != AuthMode.OAUTH_2_1:
                raise Failure(Code.NOT_CONFIGURED)
            self.retire(db, row)
            row.generation += 1
            row.enabled, row.state = True, State.CONNECTING.value
            db.add(
                MCPOAuthAttempt(
                    state_hash=token_digest(state),
                    connection_id=row.id,
                    owner_id=who.owner_id,
                    session_hash=who.session_hash,
                    generation=row.generation,
                    verifier_ciphertext=self.seal(
                        {
                            "verifier": verifier,
                            "state": token_digest(state),
                            "connection": str(row.id),
                            "generation": row.generation,
                        }
                    ),
                    expires_at=datetime.now(UTC) + timedelta(minutes=5),
                    consumed=False,
                )
            )
            return Authorization(
                authorization_url=self.oauth.begin(config, state, verifier),
                generation=row.generation,
            )

        result = await self.write(save)
        self.audit(who, identity, result.generation, "authorize", "STARTED")
        return result

    async def callback(self, who: Context, identity: UUID, state: str, code: str) -> ConnectionView:
        timeout = min((p.timeout_seconds for p in self.providers.values()), default=0.05)
        return await self.operations.run(
            timeout, lambda: self._callback(who, identity, state, code)
        )

    async def _callback(
        self, who: Context, identity: UUID, state: str, code: str
    ) -> ConnectionView:
        if not state or len(state) > 128 or not code or len(code) > 2048:
            raise Failure(Code.AUTH_FAILED)

        def claim(db: Session) -> tuple[ProviderConfig, int, str]:
            row = self.owned(db, who, identity)
            attempt = db.get(MCPOAuthAttempt, token_digest(state), with_for_update=True)
            if not attempt:
                raise Failure(Code.STALE)
            if (
                attempt.owner_id != who.owner_id
                or attempt.session_hash != who.session_hash
                or attempt.connection_id != identity
            ):
                raise Failure(Code.AUTH_FAILED)
            config = self.current(row, attempt.generation)
            if (
                attempt.consumed
                or utc(attempt.expires_at) <= datetime.now(UTC)
                or row.state != State.CONNECTING
            ):
                raise Failure(Code.STALE)
            data = self.unseal(attempt.verifier_ciphertext)
            if (
                data.get("state") != attempt.state_hash
                or data.get("connection") != str(row.id)
                or data.get("generation") != row.generation
                or not isinstance(data.get("verifier"), str)
            ):
                raise Failure(Code.AUTH_FAILED)
            verifier = str(data["verifier"])
            attempt.consumed = True
            attempt.verifier_ciphertext = ""
            return config, row.generation, verifier

        config, generation, verifier = await self.write(claim)
        return await self.acquire(
            who,
            identity,
            generation,
            config,
            lambda: self.oauth.exchange(config, code, verifier, who.correlation.request_id),
        )

    async def acquire(
        self,
        who: Context,
        identity: UUID,
        generation: int,
        config: ProviderConfig,
        operation: Callable[[], Awaitable[TokenBundle]],
    ) -> ConnectionView:
        return await self.operations.run(
            config.timeout_seconds,
            lambda: self._acquire(who, identity, generation, config, operation),
        )

    async def _acquire(
        self,
        who: Context,
        identity: UUID,
        generation: int,
        config: ProviderConfig,
        operation: Callable[[], Awaitable[TokenBundle]],
    ) -> ConnectionView:
        bundle: TokenBundle | None = None
        scope = active_operation.get()
        assert scope is not None
        scope.finish = lambda item: self.completed(who, identity, item)

        def admission(db: Session) -> None:
            row = self.owned(db, who, identity)
            self.admit(db, who, row, generation)

        async def fence() -> None:
            def check(db: Session) -> None:
                row = self.owned(db, who, identity)
                self.permitted(db, who, row, generation)
                if row.state not in {State.CONNECTING, *DRAINING}:
                    raise Failure(Code.STALE)

            await self.write(check)

        binding = dispatch_fence.set(fence)
        binding_reset = False
        reference: UUID | None = None
        started = time.monotonic()
        try:
            await self.write(admission)
            bundle = await operation()
            scope.provider_outcome = "SUCCESS"
            if time.monotonic() - started > config.timeout_seconds:
                raise Failure(Code.TIMEOUT)

            reference = await self.queue_token(who, identity, generation, config, bundle)

            def save(db: Session) -> ConnectionView:
                row = self.owned(db, who, identity)
                scope.check()
                self.current(row, generation)
                if row.state != State.CONNECTING:
                    raise Failure(Code.STALE)
                secret = db.get(MCPSecret, reference)
                if secret is None or secret.generation != generation:
                    raise Failure(Code.STALE)
                secret.revoked, secret.revoke_pending = False, False
                row.secret_id, row.expires_at = secret.id, bundle.expires_at
                row.state, row.error = State.CONNECTED.value, None
                row.updated_at = datetime.now(UTC)
                db.flush()
                return self.view(db, row)

            result = await self.write(save)
            scope.success_audit = lambda: self.audit(
                who, identity, generation, "token", "SUCCEEDED"
            )
            return result
        except BaseException as exc:
            failure = mapped(exc)
            dispatch_fence.reset(binding)
            binding_reset = True
            with anyio.CancelScope(shield=True):
                if bundle:
                    try:
                        if reference is None:
                            await self.queue_token(who, identity, generation, config, bundle)
                        await self.cleanup(who, identity)
                    except Exception:
                        self.audit(who, identity, generation, "late_token_cleanup", "PENDING")
                await self.fail(who, identity, generation, failure.code, reauth=True)
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise failure from None
        finally:
            if not binding_reset:
                dispatch_fence.reset(binding)

    async def refresh(self, who: Context, identity: UUID, generation: int) -> ConnectionView:
        timeout = min((p.timeout_seconds for p in self.providers.values()), default=0.05)
        return await self.operations.run(
            timeout, lambda: self._reconciled_refresh(who, identity, generation)
        )

    async def _reconciled_refresh(
        self, who: Context, identity: UUID, generation: int
    ) -> ConnectionView:
        if self.status(who, identity).recovery_required:
            # A restarted worker cannot see another process's finished receipt task.
            # Reconcile only durable terminal evidence before rotating credentials.
            await self.recover(who, identity)
        return await self._refresh(who, identity, generation)

    async def _refresh(self, who: Context, identity: UUID, generation: int) -> ConnectionView:
        def claim(db: Session) -> tuple[ProviderConfig, TokenBundle, int]:
            row = self.owned(db, who, identity)
            self.require_drained(db, row)
            config = self.current(row, generation)
            if config.auth_mode != AuthMode.OAUTH_2_1 or row.state != State.CONNECTED:
                raise Failure(Code.REAUTH_REQUIRED)
            old = self.active_token(db, row)
            if not old.refresh_token:
                raise Failure(Code.REAUTH_REQUIRED)
            self.retire(db, row)  # Known credentials remain cleanup obligations until resolved.
            row.generation += 1
            row.state = State.CONNECTING.value
            return config, old, row.generation

        config, old, current = await self.write(claim)
        return await self.acquire(
            who,
            identity,
            current,
            config,
            lambda: self.oauth.refresh(config, old, who.correlation.request_id),
        )

    @staticmethod
    def pending(db: Session, identity: UUID) -> list[MCPOperation]:
        return list(
            db.scalars(
                select(MCPOperation).where(
                    MCPOperation.connection_id == identity,
                    (MCPOperation.state != "COMPLETE")
                    | MCPOperation.reconciliation_required.is_(True),
                )
            )
        )

    def require_drained(self, db: Session, row: MCPConnection) -> None:
        if row.auth_invalidation_pending or self.pending(db, row.id) or row.state in DRAINING:
            raise Failure(Code.STALE)

    def admit(self, db: Session, who: Context, row: MCPConnection, generation: int) -> None:
        scope = active_operation.get()
        assert scope is not None
        self.current(row, generation)
        scope.configure(self.config(row.provider_id).timeout_seconds)
        outstanding = self.pending(db, row.id)
        if any(
            p.state != "RUNNING" or utc(p.deadline_at) <= datetime.now(UTC) for p in outstanding
        ):
            raise Failure(Code.STALE)
        if len(outstanding) >= 8:
            raise Failure(Code.UNAVAILABLE)
        db.add(
            MCPOperation(
                id=scope.id,
                connection_id=row.id,
                owner_id=who.owner_id,
                generation=generation,
                session_hash=who.session_hash,
                worker_id=self.worker_id,
                state="RUNNING",
                cleanup_state="RUNNING",
                outcome=None,
                created_at=scope.created_at,
                deadline_at=scope.deadline_at,
            )
        )

    def permitted(self, db: Session, who: Context, row: MCPConnection, generation: int) -> None:
        scope = active_operation.get()
        assert scope is not None
        scope.check()
        permit = db.get(MCPOperation, scope.id)
        if (
            permit is None
            or permit.state != "RUNNING"
            or permit.owner_id != who.owner_id
            or permit.connection_id != row.id
            or permit.generation != generation
            or permit.session_hash != who.session_hash
            or permit.worker_id != self.worker_id
            or row.generation != generation
            or row.config_fingerprint != fingerprint(self.config(row.provider_id))
        ):
            raise Failure(Code.STALE)
        # DISCONNECTING rejects admission, but allows this previously admitted operation.
        if not row.enabled and row.state not in DRAINING:
            raise Failure(Code.CLOSED)

    def finish_disconnect(self, db: Session, row: MCPConnection) -> None:
        if row.state in DRAINING and not self.pending(db, row.id):
            reauth = row.state == State.REAUTH_DRAINING
            self.retire(db, row)
            row.enabled = False
            row.state = State.REAUTH_REQUIRED.value if reauth else State.DISCONNECTED.value
            row.generation += 1
            row.auth_invalidation_pending = False
            if reauth:
                row.health, row.error = Health.UNAVAILABLE.value, Code.REAUTH_REQUIRED.value

    async def completed(self, who: Context, identity: UUID, scope: Operation) -> None:
        def locked(db: Session) -> tuple[MCPConnection | None, MCPOperation | None]:
            db.get(AuthSession, who.session_hash, with_for_update=True)
            db.get(User, who.owner_id, with_for_update=True)
            row = db.get(MCPConnection, identity, with_for_update=True)
            permit = db.get(MCPOperation, scope.id, with_for_update=True)
            if permit and (not row or permit.worker_id != self.worker_id):
                raise Failure(Code.STORAGE)
            return row, permit

        def winner(row: MCPConnection, permit: MCPOperation) -> str:
            # Caller timeout/cancellation wins over provider evidence. Otherwise
            # the first DB-serialized negative decision is sticky across workers.
            outcome = scope.terminal or permit.outcome or scope.outcome
            if outcome == "SUCCESS":
                if utc(permit.deadline_at) <= datetime.now(UTC):
                    outcome = Code.TIMEOUT.value
                elif row.auth_invalidation_pending or row.state == State.REAUTH_DRAINING:
                    outcome = Code.REAUTH_REQUIRED.value
                elif row.state == State.DISCONNECTING or row.generation != permit.generation:
                    outcome = Code.STALE.value
            return outcome

        def finish(db: Session) -> None:
            row, permit = locked(db)
            if not row or not permit:
                return  # admission never committed
            if scope.auth_invalidation_required:
                row.auth_invalidation_pending = True
            outcome = winner(row, permit)
            permit.provider_outcome = scope.provider_outcome or permit.provider_outcome
            if outcome == "SUCCESS":
                permit.reconciliation_required = True
            # Provider completion is only evidence, never a SUCCESS decision.
            # A lost worker here leaves FINALIZING visible and blocks drain.
            if permit.state != "COMPLETE":
                permit.state = "FINALIZING"
            if outcome != "SUCCESS":
                permit.outcome = outcome

        def settle(db: Session) -> list[str]:
            row, permit = locked(db)
            result = [scope.terminal or scope.outcome]
            if not row or not permit:
                return result

            def decide(session: Session) -> None:
                # Arbitrate at the actual Session commit boundary, not when the
                # worker first acquired its locks. Caller cancellation/deadline
                # may have won while this local transaction was being prepared.
                outcome = winner(row, permit)
                result[0] = outcome
                permit.outcome = outcome
                permit.reconciliation_required = outcome == "SUCCESS"
                permit.cleanup_state = "FAILED_RETRYABLE" if scope.close_failed else "COMPLETE"
                permit.state = "UNRESOLVED" if scope.close_failed else "COMPLETE"
                permit.completed_at = None if scope.close_failed else datetime.now(UTC)
                if row.generation == permit.generation and outcome != "SUCCESS":
                    row.health, row.error = Health.UNAVAILABLE.value, outcome
                session.flush()
                self.finish_disconnect(session, row)

            event.listen(db, "before_commit", decide, once=True)
            return result

        try:
            await self.write(finish)
            persisted = (await self.write(settle))[0]
            # A commit/delivery can cross the public boundary. The owning task
            # must persist the negative winner before it releases ownership.
            if scope.terminal is None and time.monotonic() >= scope.deadline:
                scope.expire()
            if scope.terminal is not None and persisted != scope.terminal:
                persisted = (await self.write(settle))[0]
            scope.outcome = scope.terminal or persisted
            if scope.outcome == "SUCCESS":
                scope.confirm = lambda item: self.confirmed(who, identity, item)
        except Exception:
            scope.outcome = scope.terminal or Code.STORAGE.value
            self.audit(who, identity, 0, "permit_completion", "UNRESOLVED")

            def unresolved(db: Session) -> None:
                row, permit = locked(db)
                if permit:
                    permit.state, permit.cleanup_state = "UNRESOLVED", "FAILED_RETRYABLE"
                    permit.reconciliation_required = True
                    permit.provider_outcome = scope.provider_outcome or permit.provider_outcome
                    if row and row.generation == permit.generation:
                        row.health, row.error = Health.UNAVAILABLE.value, scope.outcome
                    permit.outcome = scope.terminal or (
                        permit.outcome
                        if permit.outcome not in {None, "SUCCESS"}
                        else Code.STORAGE.value
                    )
                    permit.completed_at = None

            try:
                await self.write(unresolved)
            except Exception:
                pass  # RUNNING/FINALIZING or the committed reconciliation marker remains.
            raise Failure(Code(scope.outcome)) from None

    async def confirmed(self, who: Context, identity: UUID, scope: Operation) -> None:
        """Post-return local receipt. Losing it leaves explicit recovery, not clean success."""

        def receipt(db: Session) -> None:
            db.get(AuthSession, who.session_hash, with_for_update=True)
            db.get(User, who.owner_id, with_for_update=True)
            row = db.get(MCPConnection, identity, with_for_update=True)
            permit = db.get(MCPOperation, scope.id, with_for_update=True)
            if (
                not row
                or not permit
                or permit.owner_id != who.owner_id
                or permit.worker_id != self.worker_id
            ):
                raise Failure(Code.STORAGE)
            if (
                not scope.delivered
                or scope.terminal
                or permit.outcome != "SUCCESS"
                or permit.state != "COMPLETE"
            ):
                raise Failure(Code.STORAGE)
            permit.reconciliation_required = False
            db.flush()
            self.finish_disconnect(db, row)

        try:
            await self.write(receipt)
        except Exception:
            self.audit(who, identity, 0, "delivery_receipt", "UNRESOLVED")
            raise Failure(Code.STORAGE) from None

    async def recover(self, who: Context, identity: UUID) -> ConnectionView:
        """Local bookkeeping only; never replay a tool, token exchange, or revocation."""

        def reconcile(db: Session) -> ConnectionView:
            row = self.owned(db, who, identity)
            if row.auth_invalidation_pending:
                row.enabled, row.state = False, State.REAUTH_DRAINING.value
                row.health, row.error = Health.UNAVAILABLE.value, Code.REAUTH_REQUIRED.value
                for permit in self.pending(db, identity):
                    if permit.outcome in {None, "SUCCESS"}:
                        permit.outcome = Code.REAUTH_REQUIRED.value
            for permit in self.pending(db, identity):
                # A fully committed provider/caller success has only lost its
                # post-return receipt. Clearing that marker is local,
                # idempotent bookkeeping: it never replays provider I/O and it
                # cannot promote a timed-out/cancelled invocation to success.
                if (
                    not row.auth_invalidation_pending
                    and permit.connection_id == row.id
                    and permit.owner_id == row.owner_id
                    and permit.generation == row.generation
                    and permit.state == "COMPLETE"
                    and permit.cleanup_state == "COMPLETE"
                    and permit.outcome == "SUCCESS"
                    and permit.provider_outcome == "SUCCESS"
                    and permit.completed_at is not None
                ):
                    permit.reconciliation_required = False
                    continue
                # A live owner may still reconcile. Time alone never proves a worker
                # stopped or a successful response was delivered to its caller.
                if utc(permit.deadline_at) <= datetime.now(UTC):
                    permit.reconciliation_required = True
                    permit.state, permit.cleanup_state = "UNRESOLVED", "FAILED_RETRYABLE"
                    if permit.outcome == "SUCCESS":
                        permit.outcome = None
                    permit.completed_at = None
            db.flush()
            self.finish_disconnect(db, row)
            db.flush()
            return self.view(db, row)

        result = await self.write(reconcile)
        self.audit(
            who,
            identity,
            result.generation,
            "reconciliation",
            "UNRESOLVED" if result.recovery_required else result.state.value,
        )
        return result

    async def disconnect(self, who: Context, identity: UUID, generation: int) -> ConnectionView:
        timeout = min((p.timeout_seconds for p in self.providers.values()), default=0.05)
        return await self.operations.run(
            timeout, lambda: self._disconnect(who, identity, generation)
        )

    async def _disconnect(self, who: Context, identity: UUID, generation: int) -> ConnectionView:
        def close_admission(db: Session) -> None:
            row = self.owned(db, who, identity)
            if row.generation != generation:
                raise Failure(Code.STALE)
            scope = active_operation.get()
            assert scope is not None
            scope.configure(self.config(row.provider_id).timeout_seconds)
            row.enabled, row.state = False, State.DISCONNECTING.value
            for permit in self.pending(db, identity):
                if utc(permit.deadline_at) <= datetime.now(UTC):
                    permit.state = "UNRESOLVED"
            self.finish_disconnect(db, row)

        await self.write(close_admission)
        # Bounded observation only. Returning DISCONNECTING is truthful, not completion.
        until = time.monotonic() + 0.05
        current = await asyncio.to_thread(self.status, who, identity)
        while current.state == State.DISCONNECTING and time.monotonic() < until:
            await asyncio.sleep(0.005)
            current = await asyncio.to_thread(self.status, who, identity)
        if current.state == State.DISCONNECTED:
            try:
                await self.cleanup(who, identity)
            except Exception:
                self.audit(who, identity, generation + 1, "cleanup", "PENDING")
            current = await asyncio.to_thread(self.status, who, identity)
        self.audit(who, identity, current.generation, "disconnect", current.state.value)
        return current

    def delete_secret(self, db: Session, identity: UUID) -> None:
        db.execute(delete(MCPSecret).where(MCPSecret.id == identity, MCPSecret.revoked.is_(True)))

    async def cleanup(self, who: Context, identity: UUID) -> None:
        timeout = min((p.timeout_seconds for p in self.providers.values()), default=0.05)
        return await self.operations.run(timeout, lambda: self._cleanup(who, identity))

    async def _cleanup(self, who: Context, identity: UUID) -> None:
        def claim(
            db: Session,
        ) -> tuple[ProviderConfig, datetime, list[tuple[UUID, TokenBundle]]] | None:
            row = self.owned(db, who, identity)
            config = self.config(row.provider_id)
            if fingerprint(config) != row.config_fingerprint:
                return None
            # Conservative grant identity: an owner/provider may receive identical
            # or related tokens across generations/connections. Protect ALL its
            # active/pending authority; never guess identity from raw token text.
            protected = db.scalar(
                select(MCPConnection.id)
                .where(
                    MCPConnection.owner_id == row.owner_id,
                    MCPConnection.provider_id == row.provider_id,
                    (
                        (
                            MCPConnection.state.in_(
                                [
                                    State.CONNECTED.value,
                                    State.CONNECTING.value,
                                    State.DISCONNECTING.value,
                                    State.REAUTH_DRAINING.value,
                                ]
                            )
                        )
                        | (MCPConnection.cleanup_until > datetime.now(UTC))
                    ),
                )
                .limit(1)
            )
            active = db.scalar(
                select(MCPOperation.id)
                .join(MCPConnection, MCPOperation.connection_id == MCPConnection.id)
                .where(
                    MCPConnection.owner_id == row.owner_id,
                    MCPConnection.provider_id == row.provider_id,
                    (MCPOperation.state != "COMPLETE")
                    | MCPOperation.reconciliation_required.is_(True),
                )
                .limit(1)
            )
            if protected or active:
                return None
            pending = [
                (secret.id, self.open_secret(row, secret))
                for secret in db.scalars(
                    select(MCPSecret)
                    .where(MCPSecret.connection_id == identity, MCPSecret.revoked.is_(True))
                    .limit(16)
                )
            ]
            if not pending:
                return None
            until = datetime.now(UTC) + timedelta(seconds=config.timeout_seconds + 1)
            row.cleanup_until = until
            scope = active_operation.get()
            assert scope is not None
            scope.configure(config.timeout_seconds)
            scope.finish = lambda item: self.completed(who, identity, item)
            db.add(
                MCPOperation(
                    id=scope.id,
                    connection_id=identity,
                    owner_id=who.owner_id,
                    generation=row.generation,
                    session_hash=who.session_hash,
                    worker_id=self.worker_id,
                    kind="REVOCATION",
                    state="RUNNING",
                    cleanup_state="RUNNING",
                    outcome=None,
                    created_at=scope.created_at,
                    deadline_at=scope.deadline_at,
                )
            )
            return config, until, pending

        captured = await self.write(claim)
        if captured is None:
            return
        config, until, pending = captured

        async def fence() -> None:
            def check(db: Session) -> None:
                row = self.owned(db, who, identity)
                if (
                    not row.cleanup_until
                    or utc(row.cleanup_until) != until
                    or datetime.now(UTC) >= until
                ):
                    raise Failure(Code.STALE)

            await self.write(check)

        binding = dispatch_fence.set(fence)
        completed: list[UUID] = []
        seen: set[str] = set()
        try:
            with anyio.fail_after(config.timeout_seconds):
                for reference, bundle in pending:
                    await self.oauth.revoke(config, bundle, who.correlation.request_id, seen=seen)
                    completed.append(reference)
        except asyncio.CancelledError:
            self.audit(who, identity, 0, "cleanup", "PENDING")
            raise
        except Exception:
            self.audit(who, identity, 0, "cleanup", "PENDING")
        finally:
            dispatch_fence.reset(binding)

            def finish(db: Session) -> None:
                row = db.get(MCPConnection, identity, with_for_update=True)
                if row and row.cleanup_until and utc(row.cleanup_until) == until:
                    for reference in completed:
                        self.delete_secret(db, reference)
                    row.cleanup_until = None

            # Local bookkeeping only; no detached task or remote I/O.
            try:
                await self.write(finish)
            finally:

                def release(db: Session) -> None:
                    row = db.get(MCPConnection, identity, with_for_update=True)
                    if row and row.cleanup_until and utc(row.cleanup_until) == until:
                        row.cleanup_until = None

                await self.write(release)

    async def fail(
        self, who: Context, identity: UUID, generation: int, code: Code, *, reauth: bool = False
    ) -> None:
        if reauth:
            scope = active_operation.get()
            if scope:
                scope.auth_invalidation_required = True

            def invalidate(db: Session) -> None:
                row = self.owned(db, who, identity)
                if row.generation == generation:
                    row.auth_invalidation_pending = True

            # This commit is the cross-worker invalidation linearization point.
            # A normal fence failure cannot erase this separate durable intent.
            await self.write(invalidate)

        def save(db: Session) -> None:
            row = self.owned(db, who, identity)
            if row.generation != generation or row.state in DRAINING:
                return
            row.health, row.error = Health.UNAVAILABLE.value, code.value
            if reauth:
                # Close admission while retaining authority for admitted G1 work.
                row.enabled, row.state = False, State.REAUTH_DRAINING.value
                scope = active_operation.get()
                for permit in self.pending(db, identity):
                    if permit.outcome is None:
                        permit.outcome = (
                            code.value
                            if scope and permit.id == scope.id
                            else Code.REAUTH_REQUIRED.value
                        )
                db.flush()
                self.finish_disconnect(db, row)

        try:
            await self.write(save)
        except Failure:
            pass
        self.audit(who, identity, generation, "operation", code.value)

    async def test_connection(
        self, who: Context, identity: UUID, generation: int
    ) -> ConnectionView:
        async def work() -> ConnectionView:
            tools, _ = await self.tools(who, identity, generation)
            discovered = {tool.name for tool in tools}

            def assess(db: Session) -> ConnectionView:
                row = self.owned(db, who, identity)
                config = self.current(row, generation)
                if set(config.required_tools) - discovered:
                    row.health = Health.DEGRADED.value
                    row.error = Code.TOOL_NOT_FOUND.value
                    row.updated_at = datetime.now(UTC)
                return self.view(db, row)

            return await self.write(assess)

        timeout = min((p.timeout_seconds for p in self.providers.values()), default=0.05)
        return await self.operations.run(timeout, work)

    async def tools(
        self,
        who: Context,
        identity: UUID,
        generation: int,
        *,
        policy: ToolPolicy = DENY_ALL,
        name: str | None = None,
        arguments: dict[str, JsonValue] | None = None,
    ) -> tuple[tuple[Tool, ...], dict[str, JsonValue] | None]:
        timeout = min((p.timeout_seconds for p in self.providers.values()), default=0.05)
        return await self.operations.run(
            timeout,
            lambda: self._tools(
                who, identity, generation, policy=policy, name=name, arguments=arguments
            ),
        )

    async def _tools(
        self,
        who: Context,
        identity: UUID,
        generation: int,
        *,
        policy: ToolPolicy = DENY_ALL,
        name: str | None = None,
        arguments: dict[str, JsonValue] | None = None,
    ) -> tuple[tuple[Tool, ...], dict[str, JsonValue] | None]:
        scope = active_operation.get()
        assert scope is not None
        scope.finish = lambda item: self.completed(who, identity, item)

        def capture(db: Session) -> tuple[ProviderConfig, dict[str, str]]:
            row = self.owned(db, who, identity)
            config = self.current(row, generation)
            if row.state != State.CONNECTED:
                raise Failure(Code.AUTH_REQUIRED)
            if row.expires_at and utc(row.expires_at) <= datetime.now(UTC):
                raise Failure(Code.REAUTH_REQUIRED)
            self.admit(db, who, row, generation)
            token = self.active_token(db, row) if config.auth_mode != AuthMode.NONE else None
            return config, {
                **self.strategies[config.auth_mode].headers(token),
                "X-Request-ID": who.correlation.request_id,
            }

        config, headers = await self.write(capture)

        async def fence() -> None:
            def check(db: Session) -> None:
                row = self.owned(db, who, identity)
                self.permitted(db, who, row, generation)

            await self.write(check)

        try:
            with anyio.fail_after(config.timeout_seconds):
                tools, result = await self.client.execute(
                    config, headers, fence, policy, name, arguments
                )

            scope.provider_outcome = "SUCCESS"

            def save(db: Session) -> None:
                row = self.owned(db, who, identity)
                self.current(row, generation)
                scope.check()
                row.tools_json = TOOLS.dump_json(tools).decode()
                row.health, row.error = Health.AVAILABLE.value, None
                row.last_success_at = row.updated_at = datetime.now(UTC)

            await self.write(save)
            scope.success_audit = lambda: self.audit(
                who, identity, generation, "tools", "SUCCEEDED"
            )
            return tools, result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failure = mapped(exc)
            await self.fail(
                who,
                identity,
                generation,
                failure.code,
                reauth=failure.code in {Code.AUTH_REQUIRED, Code.AUTH_FAILED},
            )
            raise failure from None
