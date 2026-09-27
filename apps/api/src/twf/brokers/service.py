"""Short explicit transactions surround network work; generation CAS rejects stale results."""

import asyncio
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from urllib.parse import urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from twf.auth import token_digest
from twf.brokers.contracts import (
    Account,
    BrokerAdapter,
    BrokerFailure,
    CatalogPage,
    Credentials,
    Funds,
    Holding,
    Order,
    Overview,
    Position,
    Search,
    Snapshot,
)
from twf.brokers.secrets import ALGORITHM, EncryptedSecretStore
from twf.config.settings import Settings
from twf.infrastructure.broker import BrokerAccount, BrokerAttempt, BrokerSecret
from twf.infrastructure.identity import AuthSession, User


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def stale() -> BrokerFailure:
    return BrokerFailure(
        "BROKER_STATE_CONFLICT",
        "Connection changed or login was already used. Reconnect to continue.",
        409,
    )


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    session_hash: str


def public(row: BrokerAccount) -> Account:
    now = datetime.now(UTC)
    state = row.state
    if (state == "connected" and (not row.expires_at or utc(row.expires_at) <= now)) or (
        state == "connecting" and utc(row.updated_at) + timedelta(minutes=5) <= now
    ):
        state = "reauth_required"
    return Account.model_validate(
        {
            "id": row.id,
            "provider": row.provider,
            "name": row.name,
            "identity": row.identity,
            "state": state,
            "health": row.health,
            "generation": row.generation,
            "updated_at": utc(row.updated_at),
            "last_read_at": utc(row.last_read_at) if row.last_read_at else None,
        }
    )


class BrokerService:
    def __init__(
        self, factory: sessionmaker[Session], settings: Settings, adapter: BrokerAdapter
    ) -> None:
        self.factory, self.settings, self.adapter = factory, settings, adapter
        self.secrets = EncryptedSecretStore(settings)

    def transaction[T](self, operation: Callable[[Session], T]) -> T:
        for attempt in range(3):
            try:
                with self.factory() as db:
                    if db.get_bind().dialect.name == "sqlite":
                        # Reserve writes before reads to avoid SQLITE_BUSY_SNAPSHOT.
                        # No transaction remains open across provider I/O.
                        db.connection().exec_driver_sql("PRAGMA busy_timeout=200")
                        db.execute(
                            update(BrokerAccount)
                            .where(BrokerAccount.id == UUID(int=0))
                            .values(generation=0)
                        )
                    result = operation(db)
                    db.commit()
                    return result
            except IntegrityError:
                raise stale() from None
            except OperationalError as exc:
                if (
                    not self.settings.database_url.startswith("sqlite")
                    or "locked" not in str(exc.orig).lower()
                ):
                    raise BrokerFailure(
                        "BROKER_STORAGE_UNAVAILABLE", "Connection storage is unavailable.", 503
                    ) from None
                if attempt == 2:
                    raise stale() from None
                time.sleep(0.025 * (attempt + 1))
        raise stale()

    async def write[T](self, operation: Callable[[Session], T]) -> T:
        return await asyncio.to_thread(self.transaction, operation)

    @staticmethod
    def authorize(db: Session, who: Principal) -> None:
        login = db.get(AuthSession, who.session_hash, with_for_update=True)
        user = db.get(User, who.user_id)
        if (
            not login
            or login.user_id != who.user_id
            or login.revoked_at
            or utc(login.expires_at) <= datetime.now(UTC)
            or not user
            or not user.is_active
        ):
            raise BrokerFailure("UNAUTHORIZED", "Please sign in again.", 401)

    @staticmethod
    def owned(db: Session, who: Principal, account_id: UUID) -> BrokerAccount:
        BrokerService.authorize(db, who)
        row = db.scalar(
            select(BrokerAccount)
            .where(BrokerAccount.id == account_id, BrokerAccount.user_id == who.user_id)
            .with_for_update()
        )
        if not row:
            raise BrokerFailure("BROKER_NOT_FOUND", "Broker account not found.", 404)
        return row

    def list_accounts(self, who: Principal) -> list[Account]:
        with self.factory() as db:
            self.authorize(db, who)
            return [
                public(row)
                for row in db.scalars(
                    select(BrokerAccount)
                    .where(BrokerAccount.user_id == who.user_id)
                    .order_by(BrokerAccount.updated_at, BrokerAccount.id)
                )
            ]

    async def configure(
        self, who: Principal, name: str, credentials: Credentials, account_id: UUID | None
    ) -> Account:
        ciphertext = self.secrets.seal(credentials)

        def save(db: Session) -> Account:
            self.authorize(db, who)
            now = datetime.now(UTC)
            if account_id:
                row = self.owned(db, who, account_id)
                secret = db.get(BrokerSecret, row.secret_id)
                assert secret
                secret.ciphertext = ciphertext
                secret.algorithm = ALGORITHM
                row.name, row.state, row.health = name, "configured", "unknown"
                row.generation += 1
                row.updated_at, row.expires_at, row.last_read_at = now, None, None
            else:
                secret = BrokerSecret(ciphertext=ciphertext)
                db.add(secret)
                db.flush()
                row = BrokerAccount(
                    user_id=who.user_id,
                    provider="zerodha",
                    name=name,
                    secret_id=secret.id,
                    state="configured",
                    updated_at=now,
                )
                db.add(row)
            db.flush()
            return public(row)

        return await self.write(save)

    async def connect(self, who: Principal, account_id: UUID) -> str:
        state = secrets.token_urlsafe(32)

        def begin(db: Session) -> str:
            row = self.owned(db, who, account_id)
            secret = db.get(BrokerSecret, row.secret_id)
            assert secret
            credentials = self.secrets.open(secret.ciphertext, secret.algorithm)
            credentials.access_token = None
            secret.ciphertext = self.secrets.seal(credentials)
            row.generation += 1
            row.state, row.health, row.expires_at = "connecting", "unknown", None
            row.updated_at = datetime.now(UTC)
            db.execute(delete(BrokerAttempt).where(BrokerAttempt.expires_at < row.updated_at))
            db.add(
                BrokerAttempt(
                    state_hash=token_digest(state),
                    user_id=who.user_id,
                    session_hash=who.session_hash,
                    account_id=row.id,
                    generation=row.generation,
                    expires_at=row.updated_at + timedelta(minutes=5),
                )
            )
            return credentials.api_key.get_secret_value()

        key = await self.write(begin)
        return "https://kite.zerodha.com/connect/login?" + urlencode(
            {"v": "3", "api_key": key, "redirect_params": urlencode({"state": state})}
        )

    async def deadline[T](self, operation: Awaitable[T]) -> T:
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.settings.broker_deadline_seconds):
                result = await operation
                if time.monotonic() - started >= self.settings.broker_deadline_seconds:
                    raise TimeoutError
                return result
        except TimeoutError:
            raise BrokerFailure("PROVIDER_TIMEOUT", "Broker request timed out.", 504) from None

    async def callback(self, who: Principal, state: str, request_token: str | None) -> Account:
        def claim(db: Session) -> tuple[UUID, int, Credentials]:
            self.authorize(db, who)
            attempt = db.scalar(
                select(BrokerAttempt).where(
                    BrokerAttempt.state_hash == token_digest(state),
                    BrokerAttempt.user_id == who.user_id,
                    BrokerAttempt.session_hash == who.session_hash,
                )
            )
            if not attempt or attempt.consumed_at or utc(attempt.expires_at) <= datetime.now(UTC):
                raise stale()
            row = self.owned(db, who, attempt.account_id)
            if row.generation != attempt.generation or row.state != "connecting":
                raise stale()
            claimed = db.execute(
                update(BrokerAttempt)
                .where(
                    BrokerAttempt.state_hash == attempt.state_hash,
                    BrokerAttempt.consumed_at.is_(None),
                )
                .values(consumed_at=datetime.now(UTC))
            )
            if cast(CursorResult[object], claimed).rowcount != 1:
                raise stale()
            secret = db.get(BrokerSecret, row.secret_id)
            assert secret
            return row.id, row.generation, self.secrets.open(secret.ciphertext, secret.algorithm)

        account_id, generation, credentials = await self.write(claim)
        try:
            if request_token is None:
                raise BrokerFailure(
                    "BROKER_LOGIN_CANCELLED", "Broker login was cancelled. You can reconnect.", 409
                )
            binding = await self.deadline(self.adapter.authenticate(credentials, request_token))

            def bind(db: Session) -> Account:
                row = self.owned(db, who, account_id)
                if row.generation != generation or row.state != "connecting":
                    raise stale()
                if row.identity and row.identity != binding.identity:
                    raise BrokerFailure(
                        "ACCOUNT_MISMATCH", "Sign in to the originally linked broker account.", 409
                    )
                # CAS also protects PostgreSQL writers which do not use SQLite's reservation.
                changed = db.execute(
                    update(BrokerAccount)
                    .where(
                        BrokerAccount.id == row.id,
                        BrokerAccount.generation == generation,
                        BrokerAccount.state == "connecting",
                    )
                    .values(generation=generation + 1)
                )
                if cast(CursorResult[object], changed).rowcount != 1:
                    raise stale()
                secret = db.get(BrokerSecret, row.secret_id)
                assert secret
                credentials.access_token = binding.access_token
                secret.ciphertext = self.secrets.seal(credentials)
                now = datetime.now(UTC)
                tomorrow = now.astimezone(ZoneInfo("Asia/Kolkata")) + timedelta(days=1)
                row.expires_at = tomorrow.replace(
                    hour=6, minute=0, second=0, microsecond=0
                ).astimezone(UTC)
                row.identity, row.state, row.health = binding.identity, "connected", "unknown"
                row.updated_at, row.last_read_at = now, None
                db.flush()
                return public(row)

            return await self.write(bind)
        except BrokerFailure:
            await self.mark_failure(who, account_id, generation, "reauth_required")
            raise

    async def mark_failure(
        self,
        who: Principal,
        account_id: UUID,
        generation: int,
        state: str | None = None,
        started: datetime | None = None,
    ) -> None:
        def mark(db: Session) -> None:
            condition = [
                BrokerAccount.id == account_id,
                BrokerAccount.user_id == who.user_id,
                BrokerAccount.generation == generation,
            ]
            if started is not None:
                condition.append(
                    (BrokerAccount.last_read_at.is_(None)) | (BrokerAccount.last_read_at <= started)
                )
            values: dict[str, object] = {"health": "degraded", "updated_at": datetime.now(UTC)}
            if started:
                values["last_read_at"] = started
            if state:
                values.update(state=state, generation=generation + 1)
            db.execute(update(BrokerAccount).where(*condition).values(**values))

        try:
            await self.write(mark)
        except BrokerFailure:
            # Preserve the original safe rejection if SQLite contention also blocks bookkeeping.
            import logging

            logging.getLogger("twf.brokers").warning("broker_failure_state_not_persisted")

    async def disconnect(self, who: Principal, account_id: UUID) -> Account:
        def clear(db: Session) -> Account:
            row = self.owned(db, who, account_id)
            secret = db.get(BrokerSecret, row.secret_id)
            assert secret
            credentials = self.secrets.open(secret.ciphertext, secret.algorithm)
            credentials.access_token = None
            secret.ciphertext = self.secrets.seal(credentials)
            row.generation += 1
            row.state, row.health, row.expires_at = "disconnected", "unknown", None
            row.updated_at, row.last_read_at = datetime.now(UTC), None
            db.flush()
            return public(row)

        return await self.write(clear)

    def capture(self, who: Principal, account_id: UUID) -> tuple[Account, Credentials]:
        with self.factory() as db:
            row = self.owned(db, who, account_id)
            account = public(row)
            if account.state != "connected":
                raise BrokerFailure(
                    "BROKER_REAUTH_REQUIRED", "Connect this broker account to view data.", 409
                )
            secret = db.get(BrokerSecret, row.secret_id)
            assert secret
            credentials = self.secrets.open(secret.ciphertext, secret.algorithm)
            if not credentials.access_token:
                raise stale()
            return account, credentials

    async def read[T](
        self, who: Principal, account_id: UUID, operation: Callable[[Credentials], Awaitable[T]]
    ) -> Snapshot[T]:
        account, credentials = await asyncio.to_thread(self.capture, who, account_id)
        started = datetime.now(UTC)
        try:
            result = await self.deadline(operation(credentials))
        except BrokerFailure as exc:
            await self.mark_failure(
                who,
                account_id,
                account.generation,
                "reauth_required" if exc.code == "BROKER_REAUTH_REQUIRED" else None,
                started,
            )
            raise

        def accept(db: Session) -> Account:
            row = self.owned(db, who, account_id)
            if row.generation != account.generation or public(row).state != "connected":
                raise stale()
            db.execute(
                update(BrokerAccount)
                .where(
                    BrokerAccount.id == row.id,
                    BrokerAccount.generation == account.generation,
                    (BrokerAccount.last_read_at.is_(None))
                    | (BrokerAccount.last_read_at <= started),
                )
                .values(health="healthy", last_read_at=started, updated_at=datetime.now(UTC))
                .execution_options(synchronize_session=False)
            )
            db.refresh(row)
            if row.generation != account.generation or public(row).state != "connected":
                raise stale()
            return public(row)

        current = await self.write(accept)
        return Snapshot(account=current, fetched_at=datetime.now(UTC), data=result)

    async def overview(self, credentials: Credentials) -> Overview:
        # Sequential requests remain inside a SINGLE total deadline supplied by read().
        holdings = await self.adapter.get_holdings(credentials)
        positions = await self.adapter.get_positions(credentials)
        orders = await self.adapter.get_orders(credentials)
        funds = await self.adapter.get_funds(credentials)
        from decimal import Decimal

        return Overview(
            cash=sum((x.cash for x in funds if x.enabled and x.cash is not None), Decimal(0))
            if all(x.cash is not None for x in funds if x.enabled) and any(x.enabled for x in funds)
            else None,
            holdings_value=sum((x.value for x in holdings if x.value is not None), Decimal(0))
            if all(x.value is not None for x in holdings)
            else None,
            positions=len([x for x in positions if x.quantity != 0])
            if all(x.quantity is not None for x in positions)
            else None,
            open_orders=sum(x.status not in {"COMPLETE", "REJECTED", "CANCELLED"} for x in orders)
            if all(x.status for x in orders)
            else None,
        )

    async def portfolio(
        self,
        who: Principal,
        account_id: UUID,
        kind: Literal["overview", "holdings", "positions", "orders", "funds", "instruments"],
        query: Search,
    ) -> Snapshot[
        Overview | list[Holding] | list[Position] | list[Order] | list[Funds] | CatalogPage
    ]:
        async def operation(
            credentials: Credentials,
        ) -> Overview | list[Holding] | list[Position] | list[Order] | list[Funds] | CatalogPage:
            if kind == "instruments":
                await self.adapter.get_profile(credentials)
                return await self.adapter.search_instruments(credentials, query)
            # Enrich derivative identity without hiding rows if the catalog is unavailable.
            try:
                await self.adapter.search_instruments(credentials, Search(limit=1))
            except BrokerFailure as exc:
                if exc.code == "BROKER_REAUTH_REQUIRED":
                    raise
            if kind == "overview":
                return await self.overview(credentials)
            if kind == "holdings":
                return await self.adapter.get_holdings(credentials)
            if kind == "positions":
                return await self.adapter.get_positions(credentials)
            if kind == "orders":
                return await self.adapter.get_orders(credentials)
            return await self.adapter.get_funds(credentials)

        return await self.read(who, account_id, operation)
