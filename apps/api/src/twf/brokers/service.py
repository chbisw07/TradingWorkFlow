"""Owned read-only rooms and qualified, compatible position aggregation."""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid5

from twf.brokers.contracts import (
    BrokerAccount,
    BrokerFailure,
    BrokerProvider,
    BrokerReadClient,
    BrokerSnapshot,
    CanonicalPositionAggregate,
    FailureCode,
    PositionContribution,
    UnifiedBrokerSnapshot,
)
from twf.brokers.synthetic import AlphaAdapter, BetaAdapter, Scenario, unavailable

REFERENCE_TIME = datetime(2026, 9, 26, 12, tzinfo=UTC)
PROVIDERS = (
    BrokerProvider(provider_id="synthetic-alpha", name="Provider Alpha"),
    BrokerProvider(provider_id="synthetic-beta", name="Provider Beta"),
)


class BrokerService:
    def __init__(
        self,
        *,
        clients: Mapping[str, BrokerReadClient] | None = None,
        clock: Callable[[], datetime] = lambda: REFERENCE_TIME,
    ) -> None:
        self.clients: Mapping[str, BrokerReadClient] = (
            dict(clients)
            if clients is not None
            else {
                "synthetic-alpha": AlphaAdapter(),
                "synthetic-beta": BetaAdapter({"Beta B1": Scenario.DEGRADED}),
            }
        )
        self.clock = clock

    def accounts(self, owner: UUID) -> tuple[BrokerAccount, ...]:
        return tuple(
            BrokerAccount(
                broker_account_id=uuid5(owner, f"bw1:{label}"),
                provider_id=provider,
                owner_user_id=owner,
                label=label,
            )
            for provider, label in (
                ("synthetic-alpha", "Alpha A1"),
                ("synthetic-alpha", "Alpha A2"),
                ("synthetic-beta", "Beta B1"),
            )
        )

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Broker scenario clock must be timezone-aware")
        return now.astimezone(UTC)

    def _read(self, account: BrokerAccount, request_id: str, now: datetime) -> BrokerSnapshot:
        try:
            result = self.clients[account.provider_id].read(account, request_id, now)
            if result.account != account or result.request_id != request_id:
                raise BrokerFailure(FailureCode.INCOMPATIBLE)
            for dataset in (result.holdings, result.positions, result.orders, result.funds):
                if (
                    dataset.metadata.broker_account_id != account.broker_account_id
                    or dataset.metadata.source != account.provider_id
                ):
                    raise BrokerFailure(FailureCode.INCOMPATIBLE)
            return result
        except BrokerFailure as exc:
            return unavailable(account, request_id, now, exc.code)
        except Exception:
            # A defective optional adapter remains isolated; no raw diagnostics in DTOs.
            return unavailable(account, request_id, now, FailureCode.UNAVAILABLE)

    def room(self, owner: UUID, account_id: UUID, request_id: str) -> BrokerSnapshot:
        account = next(
            (item for item in self.accounts(owner) if item.broker_account_id == account_id), None
        )
        if account is None:
            raise LookupError("Broker account not found")
        return self._read(account, request_id, self._now())

    def overview(self, owner: UUID, request_id: str) -> UnifiedBrokerSnapshot:
        now = self._now()
        snapshots = tuple(self._read(account, request_id, now) for account in self.accounts(owner))
        groups: dict[tuple[str, str, str, str, str], list[PositionContribution]] = {}
        unmapped = 0
        missing = sum(snapshot.positions.rows is None for snapshot in snapshots)
        for snapshot in snapshots:
            for row in snapshot.positions.rows or ():
                instrument = row.instrument
                if instrument.canonical_id is None:
                    unmapped += 1
                    continue
                key = (
                    instrument.canonical_id,
                    instrument.exchange,
                    row.product,
                    instrument.currency,
                    instrument.quantity_unit,
                )
                groups.setdefault(key, []).append(
                    PositionContribution(
                        broker_account_id=snapshot.account.broker_account_id,
                        quantity=row.quantity,
                        metadata=snapshot.positions.metadata,
                    )
                )
        aggregates = tuple(
            CanonicalPositionAggregate(
                canonical_id=key[0],
                exchange=key[1],
                product=key[2],
                currency=key[3],
                quantity_unit=key[4],
                quantity=sum((item.quantity for item in values), Decimal(0)),
                contributions=tuple(values),
                qualified=bool(missing)
                or any(
                    item.metadata.freshness != "FRESH" or item.metadata.completeness != "COMPLETE"
                    for item in values
                ),
            )
            for key, values in sorted(groups.items())
        )
        return UnifiedBrokerSnapshot(
            providers=PROVIDERS,
            accounts=snapshots,
            position_aggregates=aggregates,
            unmapped_position_count=unmapped,
            missing_position_accounts=missing,
            scenario_time=now,
        )
