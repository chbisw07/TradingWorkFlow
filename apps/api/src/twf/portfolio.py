"""On-demand owned observations; no durable portfolio state or trading authority."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from twf.broker_auth import BrokerAuth
from twf.broker_foundation import BrokerFoundationFailure
from twf.brokers.foundation_contracts import BrokerPermission
from twf.brokers.portfolio_contracts import (
    DatasetName,
    NativeDataset,
    NativeObservation,
    NativePortfolio,
    PortfolioFailure,
    PortfolioProvider,
    PortfolioSummary,
    ReadMetadata,
)
from twf.catalog import BrokerCatalog
from twf.infrastructure.catalog import CatalogInstrument, CatalogPointer, CatalogSnapshot


class BrokerPortfolio:
    def __init__(self, auth: BrokerAuth, provider: PortfolioProvider):
        self.auth, self.provider = auth, provider

    def read(self, account_id: UUID) -> NativePortfolio:
        auth = self.auth
        lease = auth._lease(account_id, BrokerPermission.READ)
        label = auth._account(account_id, BrokerPermission.READ).label
        auth.session.rollback()
        datasets: dict[DatasetName, NativeDataset] = {}
        connection_state = lease.auth_state
        for name, ttl in (("holdings", 60), ("positions", 15)):
            dataset: DatasetName = "holdings" if name == "holdings" else "positions"
            metadata = ReadMetadata(
                provider_id="zerodha",
                broker_account_id=account_id,
                source=f"Kite {dataset}",
                attempted_at=datetime.now(UTC),
                connection_generation=lease.generation,
                freshness="UNKNOWN",
                freshness_policy_seconds=ttl,
                health="UNAVAILABLE",
                completeness="MISSING",
            )
            try:
                auth._check(lease, BrokerPermission.READ)
                if (
                    not auth.available()
                    or not lease.enabled
                    or not lease.api_key
                    or not lease.active_ref
                    or lease.auth_state != "CONNECTED"
                ):
                    raise PortfolioFailure("AUTH_REQUIRED")
                connection = auth._connection(account_id)
                expired = bool(
                    connection.expires_at
                    and auth._aware(connection.expires_at) <= datetime.now(UTC)
                )
                auth.session.rollback()
                if expired:
                    raise PortfolioFailure("AUTH_EXPIRED")
                token = auth.resolve(
                    lease, lease.active_ref, "access", permission=BrokerPermission.READ
                )
                observation = self.provider.read(dataset, lease.api_key, token)
                # Discard late results and never return revoked-generation observations.
                auth._check(lease, BrokerPermission.READ)
                datasets[dataset] = NativeDataset(
                    metadata=metadata.model_copy(
                        update={
                            "received_at": observation.received_at,
                            "freshness": "FRESH",
                            "health": "DEGRADED" if observation.rejected_rows else "AVAILABLE",
                            "completeness": "PARTIAL" if observation.rejected_rows else "COMPLETE",
                            "failure_code": "PARTIAL_RESPONSE"
                            if observation.rejected_rows
                            else None,
                            "rejected_rows": observation.rejected_rows,
                            "total_rows": observation.total_rows,
                        }
                    ),
                    rows=observation.rows,
                    activity_rows=observation.activity_rows if dataset == "positions" else None,
                )
            except PortfolioFailure as failure:
                auth._check(lease, BrokerPermission.READ)
                if failure.code == "AUTH_EXPIRED":
                    connection_state = "REAUTH_REQUIRED"
                datasets[dataset] = NativeDataset(
                    metadata=metadata.model_copy(update={"failure_code": failure.code}), rows=None
                )
        self._enrich(account_id, datasets)
        auth._check(lease, BrokerPermission.READ)
        now = datetime.now(UTC)
        for name, value in datasets.items():
            if (
                value.rows is not None
                and value.metadata.received_at is not None
                and (now - value.metadata.received_at).total_seconds()
                > value.metadata.freshness_policy_seconds
            ):
                datasets[name] = value.model_copy(
                    update={"metadata": value.metadata.model_copy(update={"freshness": "STALE"})}
                )
        holdings, positions = datasets["holdings"], datasets["positions"]

        def complete(value: NativeDataset) -> bool:
            return value.rows is not None and value.metadata.completeness == "COMPLETE"

        def total(value: NativeDataset, field: str) -> Decimal | None:
            if not complete(value):
                return None
            numbers = [getattr(row, field) for row in value.rows or ()]
            if any(number is None for number in numbers):
                return None
            return sum(numbers, Decimal(0))

        return NativePortfolio(
            broker_account_id=account_id,
            provider_id="zerodha",
            account_label=label,
            connection_state=connection_state,
            holdings=holdings,
            positions=positions,
            summary=PortfolioSummary(
                holdings_count=len(holdings.rows or ()) if complete(holdings) else None,
                holdings_value=total(holdings, "current_value"),
                open_positions_count=sum(row.quantity != 0 for row in positions.rows or ())
                if complete(positions)
                else None,
                realized_pnl=total(positions, "realized_pnl"),
                unrealized_pnl=total(positions, "unrealized_pnl"),
                position_pnl=total(positions, "pnl"),
            ),
        )

    def _enrich(self, account_id: UUID, datasets: dict[DatasetName, NativeDataset]) -> None:
        session = self.auth.session
        pointer = session.get(CatalogPointer, account_id)
        snapshot = (
            session.get(CatalogSnapshot, pointer.snapshot_id)
            if pointer and pointer.snapshot_id
            else None
        )
        if not snapshot:
            session.rollback()
            return
        if snapshot.broker_account_id != account_id or snapshot.provider_id != "zerodha":
            session.rollback()
            raise BrokerFoundationFailure(409)
        verified = (
            self.auth._aware(pointer.verified_at)
            if pointer and pointer.verified_at
            else snapshot.fetched_at
        )
        fresh = BrokerCatalog._fresh(self.auth._aware(verified), datetime.now(UTC)) and not (
            pointer and pointer.failure_code
        )
        tokens = {
            row.instrument.native_id
            for value in datasets.values()
            for row in (*(value.rows or ()), *(value.activity_rows or ()))
        }
        instruments: dict[tuple[str, str, str], CatalogInstrument] = {}
        # Bound SQL parameter batches for SQLite; never scan an entire master per row.
        ordered = sorted(tokens)
        for start in range(0, len(ordered), 400):
            for item in session.scalars(
                select(CatalogInstrument).where(
                    CatalogInstrument.snapshot_id == snapshot.id,
                    CatalogInstrument.native_id.in_(ordered[start : start + 400]),
                )
            ):
                instruments[(item.native_id, item.exchange, item.symbol)] = item

        def enrich(row: NativeObservation) -> NativeObservation:
            native = row.instrument
            item = instruments.get((native.native_id, native.exchange, native.symbol))
            update: dict[str, object] = {"catalog_state": "UNMAPPED"}
            if item:
                update.update(
                    {
                        "catalog_state": "FRESH" if fresh else "STALE",
                        "catalog_version": snapshot.id,
                        "catalog_fingerprint": snapshot.fingerprint,
                        "instrument_fingerprint": item.fingerprint,
                        **{
                            field: getattr(item, field)
                            for field in (
                                "name",
                                "segment",
                                "instrument_type",
                                "expiry",
                                "strike",
                                "derivative_kind",
                                "lot_size",
                                "tick_size",
                                "canonical_id",
                            )
                        },
                    }
                )
            return row.model_copy(update={"instrument": native.model_copy(update=update)})

        for name, value in datasets.items():
            datasets[name] = value.model_copy(
                update={
                    "rows": tuple(enrich(row) for row in value.rows)
                    if value.rows is not None
                    else None,
                    "activity_rows": tuple(enrich(row) for row in value.activity_rows)
                    if value.activity_rows is not None
                    else None,
                }
            )
        session.rollback()
