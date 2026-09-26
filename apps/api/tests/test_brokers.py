"""BW-1 semantics, normalization, security and optional-account isolation."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from twf.auth import create_user
from twf.brokers.contracts import BrokerAccount, BrokerSnapshot, FailureCode, Health
from twf.brokers.service import REFERENCE_TIME, BrokerService
from twf.brokers.synthetic import AlphaAdapter, BetaAdapter, Scenario
from twf.config.settings import Settings
from twf.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from twf.main import create_app

OWNER = UUID("00000000-0000-4000-8000-000000000001")


def test_topology_ownership_and_determinism() -> None:
    service = BrokerService()
    first = service.overview(OWNER, "one")
    assert first == service.overview(OWNER, "one")
    assert len(first.providers) == 2
    assert [item.account.label for item in first.accounts] == ["Alpha A1", "Alpha A2", "Beta B1"]
    assert [item.account.provider_id for item in first.accounts].count("synthetic-alpha") == 2
    assert len({item.account.broker_account_id for item in first.accounts}) == 3
    assert all(
        item.account.mode == "SYNTHETIC" and not item.account.capabilities.commands
        for item in first.accounts
    )
    other = service.accounts(uuid4())
    assert not {a.broker_account_id for a in other} & {
        s.account.broker_account_id for s in first.accounts
    }
    with pytest.raises(LookupError):
        service.room(other[0].owner_user_id, first.accounts[0].account.broker_account_id, "denied")


@pytest.mark.parametrize("adapter_type,slot", [(AlphaAdapter, 0), (BetaAdapter, 2)])
@pytest.mark.parametrize("scenario", list(Scenario))
def test_scenario_contract(
    adapter_type: type[AlphaAdapter] | type[BetaAdapter], slot: int, scenario: Scenario
) -> None:
    base = BrokerService()
    account = base.accounts(OWNER)[slot]
    service = BrokerService(
        clients={
            "synthetic-alpha": AlphaAdapter(),
            "synthetic-beta": BetaAdapter(),
            account.provider_id: adapter_type({account.label: scenario}),
        }
    )
    result = service.room(OWNER, account.broker_account_id, "scenario")
    assert result.request_id == "scenario" and result.account == account
    for data in (result.holdings, result.positions, result.orders, result.funds):
        assert data.metadata.source == account.provider_id
        assert data.metadata.broker_account_id == account.broker_account_id
        assert data.metadata.fetched_at == REFERENCE_TIME
        assert data.metadata.revision == "bw1-fixture.v1"
    if scenario.value in {code.value for code in FailureCode}:
        assert result.operation.error == FailureCode(scenario.value)
        assert result.operation.read == Health.UNAVAILABLE
        assert result.positions.rows is None and result.funds.values is None
        assert result.holdings.metadata.freshness == "UNKNOWN"
        assert result.operation.connection == (
            "AUTH_EXPIRED" if scenario == Scenario.AUTH_EXPIRED else "UNAVAILABLE"
        )
    elif scenario == Scenario.EMPTY:
        assert result.holdings.rows == ()
        assert result.positions.rows == ()
        assert result.orders.rows == ()
        assert result.positions.metadata.completeness == "COMPLETE"
    elif scenario == Scenario.MISSING:
        assert result.holdings.rows is None
        assert result.holdings.metadata.completeness == "MISSING"
        assert result.positions.rows
    elif scenario == Scenario.PARTIAL:
        assert result.holdings.rows and result.holdings.metadata.completeness == "PARTIAL"
    elif scenario == Scenario.STALE:
        assert result.operation.read == Health.AVAILABLE
        assert result.positions.metadata.freshness == "STALE"
        assert result.positions.metadata.source_as_of == REFERENCE_TIME - timedelta(seconds=61)
        assert result.holdings.metadata.source_as_of == REFERENCE_TIME - timedelta(seconds=10801)
    elif scenario == Scenario.FUNDS_UNKNOWN:
        assert result.funds.values and result.funds.values.available_cash is None
    elif scenario == Scenario.DEGRADED:
        assert result.operation.read == Health.DEGRADED
        assert result.positions.metadata.freshness == "STALE"
        assert result.positions.metadata.completeness == "PARTIAL"
    else:
        assert result.operation.read == Health.AVAILABLE
        assert result.positions.metadata.freshness == "FRESH"
        assert result.positions.rows


def test_native_normalization_and_qualified_aggregation() -> None:
    data = BrokerService().overview(OWNER, "normalization")
    a1, a2, beta = data.accounts
    assert a1.positions.rows and a2.positions.rows and beta.positions.rows
    assert [item.positions.rows[0].quantity for item in data.accounts if item.positions.rows] == [
        Decimal("100"),
        Decimal("25"),
        Decimal("-20"),
    ]
    assert a1.positions.rows[0].instrument.native_id == "alpha-1001"
    assert beta.positions.rows[0].instrument.native_id == "912"
    assert a1.positions.rows[0].last_price == beta.positions.rows[0].last_price == Decimal("4100")
    for snapshot in data.accounts:
        assert snapshot.holdings.rows and snapshot.orders.rows
        for row in snapshot.holdings.rows:
            assert row.current_value == row.quantity * row.last_price
            assert row.pnl == row.quantity * (row.last_price - row.average_cost)
        assert {row.status for row in snapshot.orders.rows} == {
            "OPEN",
            "PENDING",
            "PARTIALLY_FILLED",
            "COMPLETE",
            "REJECTED",
            "CANCELLED",
            "UNKNOWN",
        }
        assert all(
            row.quantity == row.filled_quantity + row.remaining_quantity
            for row in snapshot.orders.rows
        )
    (aggregate,) = data.position_aggregates
    assert aggregate.quantity == Decimal("105") and aggregate.qualified
    assert len(aggregate.contributions) == 3
    assert aggregate.quantity_unit == "SHARES" and aggregate.product == "INTRADAY"
    assert data.unmapped_position_count == 1
    assert beta.positions.rows[1].instrument.canonical_id is None
    assert beta.positions.rows[1].quantity == 7
    assert beta.funds.values and beta.funds.values.available_cash is None
    healthy_beta = BetaAdapter().read(beta.account, "healthy", REFERENCE_TIME)
    assert healthy_beta.funds.values and healthy_beta.funds.values.available_cash == Decimal(
        "75000"
    )


@pytest.mark.parametrize(
    "scenario",
    [
        Scenario.UNAVAILABLE,
        Scenario.TIMEOUT,
        Scenario.AUTH_EXPIRED,
        Scenario.DENIED,
        Scenario.INCOMPATIBLE,
        Scenario.RATE_LIMITED,
    ],
)
def test_failure_isolation_preserves_siblings(scenario: Scenario) -> None:
    service = BrokerService(
        clients={
            "synthetic-alpha": AlphaAdapter({"Alpha A1": scenario}),
            "synthetic-beta": BetaAdapter(),
        }
    )
    data = service.overview(OWNER, "isolation")
    assert data.accounts[0].positions.rows is None
    assert all(item.positions.rows for item in data.accounts[1:])
    assert data.missing_position_accounts == 1
    assert data.position_aggregates[0].quantity == 5
    assert data.position_aggregates[0].qualified
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:"), broker_service=service)
    with TestClient(app) as browser:
        assert browser.get("/ready").status_code == 200


class MisboundAdapter(AlphaAdapter):
    def read(self, account: BrokerAccount, request_id: str, now: datetime) -> BrokerSnapshot:
        result = super().read(account, request_id, now)
        return result.model_copy(
            update={"account": account.model_copy(update={"owner_user_id": uuid4()})}
        )


class BrokenAdapter(AlphaAdapter):
    def read(self, account: BrokerAccount, request_id: str, now: datetime) -> BrokerSnapshot:
        raise RuntimeError("private diagnostic secret")


@pytest.mark.parametrize(
    "adapter,code",
    [(MisboundAdapter(), FailureCode.INCOMPATIBLE), (BrokenAdapter(), FailureCode.UNAVAILABLE)],
)
def test_bad_adapter_is_sanitized_and_isolated(adapter: AlphaAdapter, code: FailureCode) -> None:
    result = BrokerService(
        clients={"synthetic-alpha": adapter, "synthetic-beta": BetaAdapter()}
    ).overview(OWNER, "safe")
    assert result.accounts[0].operation.error == code
    assert result.accounts[2].positions.rows
    assert "private" not in result.model_dump_json()


def test_clock_is_injected_and_requires_timezone() -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    result = BrokerService(clock=lambda: now).overview(OWNER, "clock")
    assert result.scenario_time == now
    assert result.accounts[0].holdings.metadata.source_as_of == now
    with pytest.raises(ValueError, match="timezone-aware"):
        BrokerService(clock=lambda: datetime(2030, 1, 1)).overview(OWNER, "clock")


@pytest.fixture
def browser() -> Iterator[TestClient]:
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    settings = Settings(cors_origins=("https://web.example",))
    engine = create_database_engine(settings)
    with session_scope(create_session_factory(engine)) as session:
        create_user(session, "alice", "Alice", "test-only-broker-password")
        create_user(session, "bob", "Bob", "test-only-broker-password")
        session.commit()
    with TestClient(create_app(settings, engine_factory=lambda _: engine)) as client:
        yield client


def test_api_real_sessions_idor_read_only_and_openapi(browser: TestClient) -> None:
    assert browser.get("/api/v1/brokers/overview").status_code == 401
    assert browser.get(f"/api/v1/brokers/accounts/{uuid4()}").status_code == 401

    def login(name: str) -> None:
        assert (
            browser.post(
                "/api/v1/auth/login",
                headers={"Origin": "https://web.example"},
                json={"username": name, "password": "test-only-broker-password"},
            ).status_code
            == 200
        )

    login("alice")
    overview = browser.get("/api/v1/brokers/overview", headers={"X-Request-ID": "broker-read"})
    assert overview.headers["Cache-Control"] == "no-store"
    alice = overview.json()["accounts"][0]
    path = f"/api/v1/brokers/accounts/{alice['account']['broker_account_id']}"
    assert browser.get(path, headers={"X-Request-ID": "broker-read"}).json() == alice
    assert browser.post(path).status_code == 405
    login("bob")
    denied = browser.get(
        path, headers={"X-User-ID": alice["account"]["owner_user_id"], "X-Request-ID": "idor-test"}
    )
    assert denied.status_code == 404
    assert denied.json()["error"] == {
        "code": "HTTP_404",
        "message": "Not Found",
        "request_id": "idor-test",
        "details": None,
    }
    assert browser.get("/api/v1/brokers/accounts/not-a-uuid").status_code == 422
    assert (
        browser.get("/api/v1/brokers/overview").json()["accounts"][0]["account"] != alice["account"]
    )
    schema = browser.get("/openapi.json").json()
    paths = {
        key: value for key, value in schema["paths"].items() if key.startswith("/api/v1/brokers")
    }
    assert len(paths) == 2 and all(set(value) == {"get"} for value in paths.values())
    assert all(
        "401" in value["get"]["responses"] and "404" in value["get"]["responses"]
        for value in paths.values()
    )
    assert browser.get("/ready").status_code == 200


@pytest.mark.parametrize("mode", ["SYNTHETIC", "SANDBOX", "LIVE"])
def test_account_modes_are_bounded_read_only_contracts(mode: str) -> None:
    data = BrokerService().accounts(OWNER)[0].model_dump()
    data["mode"] = mode
    account = BrokerAccount.model_validate(data)
    assert account.mode == mode
    assert not account.capabilities.commands


def test_invalid_account_mode_is_rejected() -> None:
    from pydantic import ValidationError

    data = BrokerService().accounts(OWNER)[0].model_dump()
    data["mode"] = "PAPER_OR_ANYTHING"
    with pytest.raises(ValidationError):
        BrokerAccount.model_validate(data)


@pytest.mark.parametrize("revision", ["bw1-fixture.v1", "provider-alpha.snapshot.v2", "x" * 128])
def test_source_revision_is_independent_of_contract_version(revision: str) -> None:
    data = BrokerService().overview(OWNER, "revision").accounts[0].model_dump()
    for field in ("holdings", "positions", "orders", "funds"):
        data[field]["metadata"]["revision"] = revision
    snapshot = BrokerSnapshot.model_validate(data)
    assert snapshot.positions.metadata.revision == revision
    assert snapshot.contract_version == "broker.read.v1"


@pytest.mark.parametrize("revision", ["", "x" * 129, "has space", "<script>", "x\n", 123, None])
def test_invalid_source_revision_is_rejected(revision: object) -> None:
    from pydantic import ValidationError

    data = BrokerService().overview(OWNER, "invalid").accounts[0].model_dump()
    data["positions"]["metadata"]["revision"] = revision
    with pytest.raises(ValidationError):
        BrokerSnapshot.model_validate(data)


def test_non_synthetic_contract_passes_existing_service_boundary() -> None:
    """Contract double only: no provider transport, credentials or live runtime."""
    from twf.brokers.contracts import BrokerReadClient

    data = BrokerService().accounts(OWNER)[0].model_dump()
    data["mode"] = "LIVE"
    account = BrokerAccount.model_validate(data)

    class ContractDouble:
        def read(self, account: BrokerAccount, request_id: str, now: datetime) -> BrokerSnapshot:
            payload = AlphaAdapter().read(account, request_id, now).model_dump()
            for field in ("holdings", "positions", "orders", "funds"):
                payload[field]["metadata"]["revision"] = "provider-alpha.snapshot.v2"
            return BrokerSnapshot.model_validate(payload)

    client: BrokerReadClient = ContractDouble()
    service = BrokerService(clients={account.provider_id: client})
    result = service._read(account, "extension-proof", REFERENCE_TIME)
    assert result.account.mode == "LIVE"
    assert result.operation.read == Health.AVAILABLE
    assert result.positions.metadata.revision == "provider-alpha.snapshot.v2"
    assert not result.account.capabilities.commands
    overview = BrokerService().overview(OWNER, "extension-proof").model_dump()
    overview["accounts"] = [result.model_dump()]
    from twf.brokers.contracts import UnifiedBrokerSnapshot

    assert UnifiedBrokerSnapshot.model_validate(overview).accounts[0] == result
