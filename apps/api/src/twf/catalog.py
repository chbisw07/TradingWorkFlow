"""Owned native catalog reads and generation-fenced atomic publication."""

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, insert, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError

from twf.broker_auth import BrokerAuth
from twf.broker_foundation import BrokerFoundationFailure
from twf.brokers.catalog_contracts import (
    CatalogFailure,
    CatalogPayload,
    CatalogProvider,
    CatalogSearch,
    CatalogStatus,
    FailureCode,
    InstrumentQuery,
    InstrumentResult,
    NativeInstrument,
)
from twf.brokers.foundation_contracts import BrokerPermission
from twf.infrastructure.catalog import CatalogInstrument, CatalogPointer, CatalogSnapshot


class BrokerCatalog:
    # Daily 08:30 IST acquisition target with a two-hour operational grace window.
    # Provider source generation time is not supplied; this is retrieval freshness.
    @staticmethod
    def _fresh(verified: datetime, now: datetime) -> bool:
        local = now.astimezone(ZoneInfo("Asia/Kolkata"))
        expected = local.replace(hour=8, minute=30, second=0, microsecond=0)
        if local < expected + timedelta(hours=2):
            expected -= timedelta(days=1)
        return verified >= expected

    REFRESH_LEASE = timedelta(minutes=2)

    def __init__(self, auth: BrokerAuth, provider: CatalogProvider) -> None:
        self.auth, self.provider, self.session = auth, provider, auth.session

    def status(self, account_id: UUID, version: UUID | None = None) -> CatalogStatus:
        lease = self.auth._lease(account_id, BrokerPermission.READ)
        account = self.auth._account(account_id, BrokerPermission.READ)
        pointer = self.session.get(CatalogPointer, account_id)
        snapshot_id = version or (pointer.snapshot_id if pointer else None)
        snapshot = self.session.get(CatalogSnapshot, snapshot_id) if snapshot_id else None
        if version and (not snapshot or snapshot.broker_account_id != account_id):
            raise BrokerFoundationFailure(404)
        now = datetime.now(UTC)
        verified = (
            pointer.verified_at
            if pointer and snapshot_id == pointer.snapshot_id
            else (snapshot.fetched_at if snapshot else None)
        )
        failure = cast(FailureCode | None, pointer.failure_code if pointer else None)
        if (
            pointer
            and pointer.refresh_id
            and pointer.started_at
            and now - self.auth._aware(pointer.started_at) >= self.REFRESH_LEASE
        ):
            failure = "UNAVAILABLE"
        auth_required = (
            lease.auth_state != "CONNECTED"
            or not lease.active_ref
            or not lease.enabled
            or not self.auth.available()
        )
        connection = self.auth._connection(account_id)
        auth_required = auth_required or bool(
            connection.expires_at and self.auth._aware(connection.expires_at) <= now
        )
        fresh = bool(verified and self._fresh(self.auth._aware(verified), now))
        result = CatalogStatus(
            broker_account_id=account_id,
            account_label=account.label,
            provider_id=account.provider_id,
            version=snapshot.id if snapshot else None,
            fingerprint=snapshot.fingerprint if snapshot else None,
            freshness=("STALE" if failure or not fresh else "FRESH")
            if snapshot
            else ("UNAVAILABLE" if failure or auth_required else "UNKNOWN"),
            completeness="COMPLETE" if snapshot else "UNKNOWN",
            fetched_at=self.auth._aware(snapshot.fetched_at) if snapshot else None,
            verified_at=self.auth._aware(verified) if verified else None,
            source_at=self.auth._aware(snapshot.source_at)
            if snapshot and snapshot.source_at
            else None,
            row_count=snapshot.row_count if snapshot else 0,
            last_attempt_at=self.auth._aware(pointer.started_at)
            if pointer and pointer.started_at
            else None,
            failure_code=failure or ("AUTH_REQUIRED" if auth_required else None),
            attempt_total_rows=pointer.total_rows if pointer else 0,
            attempt_accepted_rows=pointer.accepted_rows if pointer else 0,
            attempt_rejected_rows=pointer.rejected_rows if pointer else 0,
            attempt_completeness=(
                "PARTIAL"
                if pointer.rejected_rows
                else "COMPLETE"
                if not failure and pointer.accepted_rows
                else "UNKNOWN"
            )
            if pointer
            else "UNKNOWN",
            refreshing=bool(
                pointer
                and pointer.refresh_id
                and pointer.started_at
                and now - self.auth._aware(pointer.started_at) < self.REFRESH_LEASE
            ),
            can_refresh=not auth_required
            and self.auth.policy.allows(
                self.auth.actor_user_id, BrokerPermission.CONFIGURE, lease.owner
            ),
        )
        self.session.rollback()
        return result

    def search(self, account_id: UUID, query: InstrumentQuery) -> CatalogSearch:
        status = self.status(account_id, query.version)
        conditions = [CatalogInstrument.snapshot_id == status.version]
        if query.text:
            conditions.append(
                or_(
                    CatalogInstrument.symbol.icontains(query.text, autoescape=True),
                    CatalogInstrument.name.icontains(query.text, autoescape=True),
                )
            )
        for key in (
            "exchange",
            "segment",
            "instrument_type",
            "expiry",
            "strike",
            "derivative_kind",
        ):
            value = getattr(query, key)
            if value is not None and value != "":
                conditions.append(getattr(CatalogInstrument, key) == value)
        for key in ("name", "symbol"):
            if value := getattr(query, key):
                conditions.append(getattr(CatalogInstrument, key).icontains(value, autoescape=True))
        count = (
            self.session.scalar(
                select(func.count()).select_from(CatalogInstrument).where(*conditions)
            )
            or 0
        )
        rows = self.session.scalars(
            select(CatalogInstrument)
            .where(*conditions)
            .order_by(
                CatalogInstrument.exchange,
                CatalogInstrument.segment,
                CatalogInstrument.symbol,
                CatalogInstrument.native_id,
            )
            .limit(query.limit)
            .offset(query.offset)
        )
        items = tuple(
            InstrumentResult(
                **{name: getattr(row, name) for name in NativeInstrument.model_fields},
                id=row.id,
                provider_id=status.provider_id,
                catalog_version=row.snapshot_id,
            )
            for row in rows
        )
        self.session.rollback()
        return CatalogSearch(
            catalog=status, instruments=items, matched=count, limit=query.limit, offset=query.offset
        )

    def refresh(self, account_id: UUID) -> CatalogStatus:
        lease = self.auth._lease(account_id, BrokerPermission.READ)
        self.auth._authorized(BrokerPermission.CONFIGURE, lease.owner)
        request_id, now = uuid4(), datetime.now(UTC)
        account = self.auth._lock(lease, BrokerPermission.READ)
        pointer = self.session.get(CatalogPointer, account_id, populate_existing=True)
        if pointer is None:
            pointer = CatalogPointer(broker_account_id=account_id)
            self.session.add(pointer)
        elif (
            pointer.refresh_id
            and pointer.started_at
            and now - self.auth._aware(pointer.started_at) < self.REFRESH_LEASE
        ):
            self.session.rollback()
            raise BrokerFoundationFailure(409)
        pointer.refresh_id, pointer.started_at = request_id, now
        self.auth._audit(account, "CATALOG_REFRESH_REQUESTED")
        self.auth._commit()
        try:
            if (
                not self.auth.available()
                or not lease.enabled
                or not lease.api_key
                or not lease.active_ref
            ):
                raise CatalogFailure("AUTH_REQUIRED")
            try:
                token = self.auth.resolve(
                    lease, lease.active_ref, "access", permission=BrokerPermission.READ
                )
            except BrokerFoundationFailure:
                raise CatalogFailure("AUTH_REQUIRED") from None
            payload = self.provider.fetch(lease.api_key, token)
            self.auth._check(lease, BrokerPermission.READ)
            account = self.auth._lock(lease, BrokerPermission.READ)
            pointer = self.session.get(CatalogPointer, account_id, populate_existing=True)
            if pointer is None or pointer.refresh_id != request_id:
                raise BrokerFoundationFailure(409)
            self._publish(account_id, pointer, payload)
            self.auth._audit(account, "CATALOG_REFRESH_SUCCEEDED")
            self.auth._audit(account, "CATALOG_VERSION_ACTIVATED")
            self.auth._commit()
        except (CatalogFailure, BrokerFoundationFailure) as error:
            self.session.rollback()
            failure = (
                error if isinstance(error, CatalogFailure) else CatalogFailure("STALE_CONNECTION")
            )
            self._failed(account_id, request_id, failure)
        except (IntegrityError, OperationalError):
            self.session.rollback()
            self._failed(account_id, request_id, CatalogFailure("UNAVAILABLE"))
        return self.status(account_id)

    def _failed(self, account_id: UUID, request_id: UUID, failure: CatalogFailure) -> None:
        current = self.auth._lease(account_id, BrokerPermission.READ)
        account = self.auth._lock(current, BrokerPermission.READ)
        pointer = self.session.get(CatalogPointer, account_id, populate_existing=True)
        if pointer and pointer.refresh_id == request_id:
            pointer.refresh_id = None
            pointer.failure_code = failure.code
            pointer.total_rows, pointer.accepted_rows, pointer.rejected_rows = (
                failure.total,
                failure.accepted,
                failure.rejected,
            )
            self.auth._audit(account, "CATALOG_REFRESH_FAILED")
            self.auth._commit()
        else:
            self.session.rollback()

    def _publish(self, account_id: UUID, pointer: CatalogPointer, payload: CatalogPayload) -> None:
        existing = self.session.scalar(
            select(CatalogSnapshot).where(
                CatalogSnapshot.broker_account_id == account_id,
                CatalogSnapshot.fingerprint == payload.fingerprint,
            )
        )
        if existing is None:
            snapshot_id = uuid4()
            self.session.add(
                CatalogSnapshot(
                    id=snapshot_id,
                    broker_account_id=account_id,
                    provider_id="zerodha",
                    fingerprint=payload.fingerprint,
                    fetched_at=payload.fetched_at,
                    source_at=payload.source_at,
                    row_count=len(payload.instruments),
                )
            )
            self.session.flush()
            # Bound each SQL batch; all batches and the pointer commit atomically.
            for offset in range(0, len(payload.instruments), 500):
                self.session.execute(
                    insert(CatalogInstrument),
                    [
                        dict(row.model_dump(), id=uuid4(), snapshot_id=snapshot_id)
                        for row in payload.instruments[offset : offset + 500]
                    ],
                )
        else:
            snapshot_id = existing.id
        pointer.snapshot_id = snapshot_id
        pointer.verified_at = payload.fetched_at
        pointer.failure_code, pointer.refresh_id = None, None
        pointer.total_rows = pointer.accepted_rows = payload.total_rows
        pointer.rejected_rows = 0
