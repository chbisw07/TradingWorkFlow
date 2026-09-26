"""Two fictional native layouts normalized only inside the adapter boundary."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from twf.brokers.contracts import (
    BrokerAccount,
    BrokerFailure,
    BrokerOrder,
    BrokerSnapshot,
    FailureCode,
    FundsDataset,
    FundsSnapshot,
    Health,
    Holding,
    HoldingsDataset,
    Instrument,
    ObservationMetadata,
    OperationHealth,
    OrdersDataset,
    Position,
    PositionsDataset,
)

D = Decimal


class Scenario(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    UNAVAILABLE = "UNAVAILABLE"
    EMPTY = "EMPTY"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    STALE = "STALE"
    FUNDS_UNKNOWN = "FUNDS_UNKNOWN"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    DENIED = "DENIED"
    INCOMPATIBLE = "INCOMPATIBLE"


POLICIES = {"holdings": 10800, "positions": 60, "orders": 30, "funds": 120}


def metadata(
    account: BrokerAccount,
    now: datetime,
    dataset: str,
    *,
    health: Health = Health.AVAILABLE,
    stale: bool = False,
    partial: bool = False,
    missing: bool = False,
) -> ObservationMetadata:
    age = POLICIES[dataset] + 1 if stale else 0
    return ObservationMetadata(
        source=account.provider_id,
        broker_account_id=account.broker_account_id,
        source_as_of=None if missing else now - timedelta(seconds=age),
        fetched_at=now,
        health=health,
        freshness="UNKNOWN" if missing else "STALE" if stale else "FRESH",
        completeness="MISSING" if missing else "PARTIAL" if partial else "COMPLETE",
        freshness_policy_seconds=POLICIES[dataset],
        revision="bw1-fixture.v1",
    )


def unavailable(
    account: BrokerAccount, request_id: str, now: datetime, code: FailureCode
) -> BrokerSnapshot:
    def meta(dataset: str) -> ObservationMetadata:
        return metadata(account, now, dataset, health=Health.UNAVAILABLE, missing=True)

    return BrokerSnapshot(
        request_id=request_id,
        account=account,
        operation=OperationHealth(
            connection="AUTH_EXPIRED" if code == FailureCode.AUTH_EXPIRED else "UNAVAILABLE",
            read=Health.UNAVAILABLE,
            error=code,
        ),
        holdings=HoldingsDataset(metadata=meta("holdings"), rows=None),
        positions=PositionsDataset(metadata=meta("positions"), rows=None),
        orders=OrdersDataset(metadata=meta("orders"), rows=None),
        funds=FundsDataset(metadata=meta("funds"), values=None),
    )


@dataclass(frozen=True)
class NormalizedFixture:
    holdings: tuple[Holding, ...]
    positions: tuple[Position, ...]
    orders: tuple[BrokerOrder, ...]
    funds: FundsSnapshot


class SyntheticAdapter:
    def __init__(self, scenarios: dict[str, Scenario] | None = None) -> None:
        self.scenarios = dict(scenarios or {})

    def normalize(self, account: BrokerAccount, now: datetime) -> NormalizedFixture:
        raise NotImplementedError

    def read(self, account: BrokerAccount, request_id: str, now: datetime) -> BrokerSnapshot:
        scenario = self.scenarios.get(account.label, Scenario.HEALTHY)
        if scenario.value in FailureCode._value2member_map_:
            raise BrokerFailure(FailureCode(scenario.value))
        fixture = self.normalize(account, now)
        degraded = scenario == Scenario.DEGRADED
        health = Health.DEGRADED if degraded else Health.AVAILABLE
        empty = scenario == Scenario.EMPTY
        missing = scenario == Scenario.MISSING

        def meta(dataset: str) -> ObservationMetadata:
            return metadata(
                account,
                now,
                dataset,
                health=health,
                stale=scenario == Scenario.STALE
                or (degraded and dataset in {"positions", "funds"}),
                partial=scenario == Scenario.PARTIAL or degraded,
                missing=missing and dataset == "holdings",
            )

        funds = fixture.funds
        if scenario == Scenario.FUNDS_UNKNOWN or degraded:
            funds = FundsSnapshot(
                available_cash=None, used_margin=funds.used_margin, collateral=None
            )
        return BrokerSnapshot(
            request_id=request_id,
            account=account,
            operation=OperationHealth(connection="CONNECTED", read=health),
            holdings=HoldingsDataset(
                metadata=meta("holdings"),
                rows=None if missing else () if empty else fixture.holdings,
            ),
            positions=PositionsDataset(
                metadata=meta("positions"), rows=() if empty else fixture.positions
            ),
            orders=OrdersDataset(metadata=meta("orders"), rows=() if empty else fixture.orders),
            funds=FundsDataset(metadata=meta("funds"), values=funds),
        )


def holding(instrument: Instrument, qty: Decimal, cost: Decimal, price: Decimal) -> Holding:
    value = qty * price
    pnl = value - qty * cost
    return Holding(
        instrument=instrument,
        quantity=qty,
        average_cost=cost,
        last_price=price,
        current_value=value,
        pnl=pnl,
        pnl_percent=None if not cost or not qty else pnl / (qty * cost) * 100,
    )


@dataclass(frozen=True)
class AlphaNative:
    ticker: str
    token: str
    net_units: str
    cost: str
    mark: str


class AlphaAdapter(SyntheticAdapter):
    def normalize(self, account: BrokerAccount, now: datetime) -> NormalizedFixture:
        native = AlphaNative(
            "HAL-EQ", "alpha-1001", "100" if account.label == "Alpha A1" else "25", "4000", "4100"
        )
        instrument = Instrument(
            canonical_id="NSE:HAL",
            exchange="NSE",
            broker_symbol=native.ticker,
            native_id=native.token,
        )
        quantity = D(native.net_units)
        position = Position(
            instrument=instrument,
            product="INTRADAY",
            quantity=quantity,
            average_price=D(native.cost),
            last_price=D(native.mark),
            realized_pnl=D("0"),
            unrealized_pnl=quantity * (D(native.mark) - D(native.cost)),
            broker_state="NET",
        )
        # Alpha publishes textual states; Beta publishes numeric execution codes.
        states = {
            "working": "OPEN",
            "queued": "PENDING",
            "partial": "PARTIALLY_FILLED",
            "done": "COMPLETE",
            "declined": "REJECTED",
            "void": "CANCELLED",
            "new-vendor-state": "UNKNOWN",
        }
        orders = tuple(
            BrokerOrder.model_validate(
                {
                    "broker_order_id": f"{account.label.replace(' ', '-')}-{raw}",
                    "instrument": instrument,
                    "side": "BUY",
                    "quantity": "10",
                    "filled_quantity": "10"
                    if state == "COMPLETE"
                    else "4"
                    if state == "PARTIALLY_FILLED"
                    else "0",
                    "remaining_quantity": "0"
                    if state == "COMPLETE"
                    else "6"
                    if state == "PARTIALLY_FILLED"
                    else "10",
                    "price": "4000",
                    "status": state,
                    "observed_at": now,
                    "reason": "Synthetic provider rejection" if state == "REJECTED" else None,
                }
            )
            for raw, state in states.items()
        )
        return NormalizedFixture(
            (holding(instrument, D("10"), D(native.cost), D(native.mark)),),
            (position,),
            orders,
            FundsSnapshot(available_cash=D("125000"), used_margin=D("10000"), collateral=D("5000")),
        )


@dataclass(frozen=True)
class BetaSecurity:
    venue: str
    display_code: str
    security_key: int
    canonical: str | None


@dataclass(frozen=True)
class BetaLot:
    security: BetaSecurity
    signed_lots: int
    basis_minor: int
    last_minor: int


class BetaAdapter(SyntheticAdapter):
    def normalize(self, account: BrokerAccount, now: datetime) -> NormalizedFixture:
        inventory = (
            BetaLot(BetaSecurity("NSE", "HAL.N", 912, "NSE:HAL"), -20, 400000, 410000),
            BetaLot(BetaSecurity("NSE", "UNMAPPED.N", 913, None), 7, 12000, 12500),
        )
        positions = []
        for lot in inventory:
            instrument = Instrument(
                canonical_id=lot.security.canonical,
                exchange=lot.security.venue,
                broker_symbol=lot.security.display_code,
                native_id=str(lot.security.security_key),
            )
            basis, mark = D(lot.basis_minor) / 100, D(lot.last_minor) / 100
            positions.append(
                Position(
                    instrument=instrument,
                    product="INTRADAY",
                    quantity=D(lot.signed_lots),
                    average_price=basis,
                    last_price=mark,
                    realized_pnl=D("0"),
                    unrealized_pnl=D(lot.signed_lots) * (mark - basis),
                    broker_state="NET_POSITION",
                )
            )
        states = {
            11: "OPEN",
            12: "PENDING",
            21: "PARTIALLY_FILLED",
            22: "COMPLETE",
            31: "REJECTED",
            32: "CANCELLED",
            99: "UNKNOWN",
        }
        orders = tuple(
            BrokerOrder.model_validate(
                {
                    "broker_order_id": f"B1-{code}",
                    "instrument": positions[0].instrument,
                    "side": "SELL",
                    "quantity": "10",
                    "filled_quantity": "10"
                    if state == "COMPLETE"
                    else "4"
                    if state == "PARTIALLY_FILLED"
                    else "0",
                    "remaining_quantity": "0"
                    if state == "COMPLETE"
                    else "6"
                    if state == "PARTIALLY_FILLED"
                    else "10",
                    "price": "4000",
                    "status": state,
                    "observed_at": now,
                    "reason": "Synthetic provider rejection" if state == "REJECTED" else None,
                }
            )
            for code, state in states.items()
        )
        # Native Beta valuation is integer minor currency units, unlike Alpha decimal strings.
        cash_minor, margin_minor = 7500000, 200000
        return NormalizedFixture(
            (holding(positions[0].instrument, D("5"), D("4000"), D("4100")),),
            tuple(positions),
            orders,
            FundsSnapshot(
                available_cash=D(cash_minor) / 100,
                used_margin=D(margin_minor) / 100,
                collateral=None,
            ),
        )
