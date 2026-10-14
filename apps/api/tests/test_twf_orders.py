"""OE-1 contracts, ownership, authority, concurrency and durable audit."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, select

from twf.config.settings import Settings
from twf.discovery.domain import (
    InstrumentIdentity,
    RevisionRef,
    SourceReference,
    UnderlyingIdentity,
)
from twf.infrastructure.database import Base, create_database_engine, create_session_factory
from twf.infrastructure.identity import AuthSession, User
from twf.infrastructure.twf_order import TWFOrderEventRecord, TWFOrderRecord
from twf.orders.context import OrderContext, _SubsystemOriginIssuer, _TrustedSubsystemOrigin
from twf.orders.contracts import (
    AssetClass,
    CreateOrder,
    DraftChanges,
    EventType,
    OrderInstrument,
    OrderProvenance,
    OrderState,
    OrderTerms,
    OrderType,
    OrderView,
    Product,
    Side,
    Source,
)
from twf.orders.errors import OrderError, OrderErrorCode
from twf.orders.resolution import (
    TrustedCanonicalInstrumentAuthority,
    _bind_trusted_canonical_resolver,
)
from twf.orders.service import OrderService

CANONICAL: dict[UUID, InstrumentIdentity] = {}
SESSIONS: dict[UUID, str] = {}


class TrustedTestResolver:
    """Test-side server reference, never supplied by a create request."""

    def resolve(self, instrument_id: UUID) -> InstrumentIdentity | None:
        return CANONICAL.get(instrument_id)


def owner(engine: Engine) -> UUID:
    key = uuid4()
    token_hash = uuid4().hex + uuid4().hex
    SESSIONS[key] = token_hash
    now = datetime.now(UTC)
    with create_session_factory(engine)() as db, db.begin():
        db.add(
            User(
                id=key,
                username=key.hex,
                display_name="Order owner",
                password_hash="unused",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.flush()
        db.add(
            AuthSession(
                token_hash=token_hash,
                user_id=key,
                created_at=now,
                expires_at=now + timedelta(hours=1),
                revoked_at=None,
            )
        )
    return key


def service_for(engine: Engine, key: UUID, source: Source = Source.MANUAL) -> OrderService:
    factory = create_session_factory(engine)
    with factory() as db:
        user = db.get(User, key)
        login = db.get(AuthSession, SESSIONS[key])
        assert user is not None and login is not None
        if source == Source.MANUAL:
            context = OrderContext.from_authenticated_session(user, login)
        else:
            issuer = _SubsystemOriginIssuer(
                source, lambda owner_id, ref: owner_id == key and ref == "source-123"
            )
            context = OrderContext.from_trusted_subsystem(
                user, login, issuer.issue(key, "source-123")
            )
    return OrderService(factory, context, _bind_trusted_canonical_resolver(TrustedTestResolver()))


@pytest.fixture
def store(tmp_path: Path) -> tuple[OrderService, UUID, Engine]:
    engine = create_database_engine(
        Settings(database_url=f"sqlite+pysqlite:///{tmp_path / 'orders.db'}")
    )
    Base.metadata.create_all(engine)
    key = owner(engine)
    return service_for(engine, key), key, engine


def instrument(asset: AssetClass = AssetClass.EQUITY) -> OrderInstrument:
    native = SourceReference(namespace="nse", native_id=uuid4().hex, revision="v1")
    underlying = UnderlyingIdentity(
        underlying_id=uuid4(), source=native, mapping=RevisionRef(id="mapping", version="v1")
    )
    identity = InstrumentIdentity(
        instrument_id=uuid4(),
        underlying=underlying,
        native=native,
        symbol="ABC",
        exchange="NSE",
        segment="NFO" if asset != AssetClass.EQUITY else "EQ",
        instrument_type={
            AssetClass.EQUITY: "EQUITY",
            AssetClass.FUTURES: "FUTSTK",
            AssetClass.OPTION: "OPTSTK",
        }[asset],
        expiry_date=date(2026, 10, 29) if asset != AssetClass.EQUITY else None,
        lot_size=25 if asset != AssetClass.EQUITY else None,
        tick_size=Decimal("0.05") if asset != AssetClass.EQUITY else None,
        strike=Decimal("2500") if asset == AssetClass.OPTION else None,
        right="CALL" if asset == AssetClass.OPTION else None,
    )
    result = OrderInstrument.from_canonical(identity, asset)
    CANONICAL[result.instrument_id] = identity
    return result


def request(
    asset: AssetClass = AssetClass.EQUITY,
    source: Source = Source.MANUAL,
    *,
    quantity: int | None = None,
) -> CreateOrder:
    return CreateOrder(
        instrument=instrument(asset),
        terms=OrderTerms(
            side=Side.BUY,
            quantity=quantity or (1 if asset == AssetClass.EQUITY else 25),
            order_type=OrderType.MARKET,
            product=Product.DELIVERY if asset == AssetClass.EQUITY else Product.CARRY_FORWARD,
        ),
        provenance=OrderProvenance(source=source, source_ref="source-123", references={"run": "x"}),
    )


def create(service: OrderService, order: CreateOrder) -> OrderView:
    return service.create_order(order)


@pytest.mark.parametrize("asset", list(AssetClass))
def test_create_round_trip_and_restart(
    store: tuple[OrderService, UUID, Engine], asset: AssetClass
) -> None:
    service, key, engine = store
    created = create(service, request(asset))
    assert created.state == OrderState.DRAFT and created.version == 1
    assert created.owner_id == key and created.provenance.source_ref == "source-123"
    assert (
        created.instrument.instrument_id
        and created.twf_order_id != created.instrument.instrument_id
    )
    reopened = service_for(engine, key)
    assert reopened.get_order(created.twf_order_id) == created
    assert reopened.list_orders() == (created,)
    events = reopened.get_order_history(created.twf_order_id)
    assert len(events) == 1 and events[0].event_type == EventType.ORDER_CREATED
    assert events[0].authority == "TWF_DOMAIN"
    provenance = events[0].details["provenance"]
    assert isinstance(provenance, dict) and provenance["references"] == {"run": "x"}
    assert events[0].occurred_at.tzinfo is not None
    if asset != AssetClass.EQUITY:
        assert created.instrument.expiry == date(2026, 10, 29)
        assert created.instrument.lot_size == 25
        assert created.instrument.tick_size == Decimal("0.05")
    if asset == AssetClass.OPTION:
        assert created.instrument.strike == Decimal("2500")
        assert created.instrument.option_type == "CE"


@pytest.mark.parametrize("source", list(Source))
def test_all_sources_are_provenance_only(
    store: tuple[OrderService, UUID, Engine], source: Source
) -> None:
    _, key, engine = store
    service = service_for(engine, key, source)
    row = create(service, request(source=source))
    assert row.provenance.source == source and row.state == OrderState.DRAFT


def test_structural_validation_and_readiness(store: tuple[OrderService, UUID, Engine]) -> None:
    service, key, _ = store
    with pytest.raises(ValidationError):
        OrderTerms(side=Side.BUY, quantity=0, order_type=OrderType.MARKET, product=Product.INTRADAY)
    with pytest.raises(ValidationError):
        OrderTerms(side=Side.BUY, quantity=1, order_type=OrderType.LIMIT, product=Product.INTRADAY)
    with pytest.raises(ValidationError):
        OrderTerms(
            side=Side.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
            limit_price=Decimal("10"),
            product=Product.INTRADAY,
        )
    for asset in (AssetClass.FUTURES, AssetClass.OPTION):
        payload = instrument(asset).model_dump()
        payload.pop("expiry")
        with pytest.raises(ValidationError):
            OrderInstrument.model_validate(payload)
    payload = instrument(AssetClass.OPTION).model_dump()
    payload.pop("strike")
    with pytest.raises(ValidationError):
        OrderInstrument.model_validate(payload)
    draft = create(service, request(AssetClass.FUTURES, quantity=26))
    result = service.validate_for_readiness(draft.twf_order_id, expected_version=1)
    assert result.ready is False and result.violations == ("QUANTITY_NOT_LOT_MULTIPLE",)
    assert result.order_version == 2
    assert service.get_order(draft.twf_order_id).version == 2
    with pytest.raises(OrderError) as err:
        service.transition_order(draft.twf_order_id, OrderState.READY, expected_version=2)
    assert err.value.code == OrderErrorCode.INVALID_ORDER
    assert service.get_order(draft.twf_order_id).state == OrderState.DRAFT


def test_draft_edit_ready_and_history(store: tuple[OrderService, UUID, Engine]) -> None:
    service, key, engine = store
    draft = create(service, request())
    terms = OrderTerms(
        side=Side.SELL,
        quantity=2,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("125.50"),
        product=Product.INTRADAY,
    )
    edited = service.update_draft_order(
        draft.twf_order_id, DraftChanges(terms=terms, notes="reviewed"), expected_version=1
    )
    assert edited.version == 2 and edited.terms == terms and (edited.notes == "reviewed")
    assert edited.provenance == draft.provenance
    ready = service.transition_order(draft.twf_order_id, OrderState.READY, expected_version=2)
    assert ready.version == 3 and ready.state == OrderState.READY
    with pytest.raises(OrderError) as err:
        service.update_draft_order(
            draft.twf_order_id, DraftChanges(notes="changed"), expected_version=3
        )
    assert err.value.code == OrderErrorCode.IMMUTABLE_FIELD
    events = service.get_order_history(draft.twf_order_id)
    assert [event.event_type for event in events] == [
        EventType.ORDER_CREATED,
        EventType.ORDER_UPDATED,
        EventType.ORDER_VALIDATED,
        EventType.STATE_TRANSITIONED,
    ]
    assert [event.sequence for event in events] == [1, 2, 3, 4]
    before, after = (events[1].details["before"], events[1].details["after"])
    assert isinstance(before, dict) and before["notes"] == ""
    assert isinstance(after, dict) and after["notes"] == "reviewed"
    assert events[-1].from_state == OrderState.DRAFT
    assert events[-1].to_state == OrderState.READY
    reopened = service_for(engine, key)
    assert reopened.get_order(draft.twf_order_id) == ready
    assert reopened.get_order_history(draft.twf_order_id) == events


def test_authority_terminal_and_reason_guards(store: tuple[OrderService, UUID, Engine]) -> None:
    service, key, _ = store
    draft = create(service, request())
    for target in (
        OrderState.QUEUED,
        OrderState.SUBMITTING,
        OrderState.BROKER_ACCEPTED,
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
    ):
        with pytest.raises(OrderError) as err:
            service.transition_order(draft.twf_order_id, target, expected_version=1)
        assert err.value.code == OrderErrorCode.INVALID_TRANSITION_AUTHORITY
    ready = service.transition_order(draft.twf_order_id, OrderState.READY, expected_version=1)
    for target in (OrderState.QUEUED, OrderState.BROKER_ACCEPTED, OrderState.FILLED):
        with pytest.raises(OrderError) as err:
            service.transition_order(draft.twf_order_id, target, expected_version=ready.version)
        assert err.value.code == OrderErrorCode.INVALID_TRANSITION_AUTHORITY
    with pytest.raises(OrderError) as err:
        service.transition_order(
            draft.twf_order_id, OrderState.CANCELLED, expected_version=ready.version
        )
    assert err.value.code == OrderErrorCode.INVALID_ORDER
    with pytest.raises(OrderError) as err:
        service.transition_order(
            draft.twf_order_id,
            OrderState.CANCELLED,
            expected_version=ready.version,
            reason_code="bad reason",
            reason="Invalid code",
        )
    assert err.value.code == OrderErrorCode.INVALID_ORDER
    cancelled = service.transition_order(
        draft.twf_order_id,
        OrderState.CANCELLED,
        expected_version=ready.version,
        reason_code="CANCELLED_BY_USER",
        reason="User cancelled before queue admission",
    )
    assert cancelled.state_reason_code == "CANCELLED_BY_USER"
    with pytest.raises(OrderError) as err:
        service.transition_order(
            draft.twf_order_id, OrderState.READY, expected_version=cancelled.version
        )
    assert err.value.code == OrderErrorCode.TERMINAL_ORDER
    assert len(service.get_order_history(draft.twf_order_id)) == 4


def test_owner_isolation_and_stale_version(store: tuple[OrderService, UUID, Engine]) -> None:
    service, key, engine = store
    other = owner(engine)
    other_service = service_for(engine, other)
    draft = create(service, request())
    assert other_service.list_orders() == ()
    for call in (
        lambda: other_service.get_order(draft.twf_order_id),
        lambda: other_service.get_order_history(draft.twf_order_id),
        lambda: other_service.update_draft_order(
            draft.twf_order_id, DraftChanges(notes="x"), expected_version=1
        ),
        lambda: other_service.transition_order(
            draft.twf_order_id, OrderState.READY, expected_version=1
        ),
    ):
        with pytest.raises(OrderError) as err:
            call()
        assert err.value.code == OrderErrorCode.ORDER_NOT_FOUND
    service.update_draft_order(draft.twf_order_id, DraftChanges(notes="first"), expected_version=1)
    with pytest.raises(OrderError) as err:
        service.update_draft_order(
            draft.twf_order_id, DraftChanges(notes="lost"), expected_version=1
        )
    assert err.value.code == OrderErrorCode.VERSION_CONFLICT
    assert service.get_order(draft.twf_order_id).notes == "first"
    assert len(service.get_order_history(draft.twf_order_id)) == 2


def test_transition_rolls_back_if_audit_fails(
    store: tuple[OrderService, UUID, Engine], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, key, engine = store
    draft = create(service, request())

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("audit storage failed")

    monkeypatch.setattr(OrderService, "_append", staticmethod(fail))
    with pytest.raises(RuntimeError):
        service.transition_order(draft.twf_order_id, OrderState.READY, expected_version=1)
    with create_session_factory(engine)() as db:
        row = db.scalar(
            select(TWFOrderRecord).where(TWFOrderRecord.twf_order_id == draft.twf_order_id)
        )
        assert row is not None and row.state == "DRAFT" and (row.version == 1)
        events = db.scalars(select(TWFOrderEventRecord)).all()
        assert len(events) == 1


def test_order_migration_upgrade_downgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    database = tmp_path / "migrated.db"
    monkeypatch.setenv("TWF_DATABASE_URL", f"sqlite+pysqlite:///{database}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0022_derivative_templates")
    command.upgrade(config, "0023_twf_orders")
    engine = create_database_engine(Settings(database_url=f"sqlite+pysqlite:///{database}"))
    try:
        assert {"twf_orders", "twf_order_events"} <= set(inspect(engine).get_table_names())
        constraints = inspect(engine).get_foreign_keys("twf_order_events")
        assert any(
            fk["constrained_columns"] == ["twf_order_id", "owner_id"]
            and fk["referred_columns"] == ["twf_order_id", "owner_id"]
            for fk in constraints
        )
        command.downgrade(config, "0022_derivative_templates")
        assert "twf_orders" not in inspect(engine).get_table_names()
        assert "twf_order_events" not in inspect(engine).get_table_names()
        command.upgrade(config, "0023_twf_orders")
        assert {"twf_orders", "twf_order_events"} <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_shared_canonical_identity_projection_omits_provider_token() -> None:
    native = SourceReference(namespace="dhan", native_id="secret-native-token", revision="v1")
    underlying = UnderlyingIdentity(
        underlying_id=uuid4(),
        source=SourceReference(namespace="nse", native_id="ABC", revision="v1"),
        mapping=RevisionRef(id="mapping", version="v1"),
    )
    canonical = InstrumentIdentity(
        instrument_id=uuid4(),
        underlying=underlying,
        native=native,
        symbol="ABC OCT 2500 CE",
        exchange="NSE",
        segment="NFO",
        instrument_type="OPTSTK",
        expiry=datetime(2026, 10, 29, tzinfo=UTC),
        expiry_date=date(2026, 10, 29),
        lot_size=25,
        tick_size=Decimal("0.05"),
        strike=Decimal("2500"),
        right="CALL",
    )
    projected = OrderInstrument.from_canonical(canonical, AssetClass.OPTION)
    assert projected.instrument_id == canonical.instrument_id
    assert projected.underlying_id == underlying.underlying_id
    assert projected.option_type == "CE" and projected.expiry == date(2026, 10, 29)
    assert "secret-native-token" not in projected.model_dump_json()


def test_revoked_context_cannot_create(store: tuple[OrderService, UUID, Engine]) -> None:
    service, key, engine = store
    with create_session_factory(engine)() as db, db.begin():
        login = db.get(AuthSession, SESSIONS[key])
        assert login is not None
        login.revoked_at = datetime.now(UTC)
    with pytest.raises(OrderError) as err:
        create(service, request())
    assert err.value.code == OrderErrorCode.UNAUTHORIZED
    with create_session_factory(engine)() as db:
        assert db.scalar(select(TWFOrderRecord)) is None
        assert db.scalar(select(TWFOrderEventRecord)) is None


def test_explicit_exchange_expiry_rejects_datetime_coercion() -> None:
    from zoneinfo import ZoneInfo

    native = SourceReference(namespace="nse", native_id="ABC", revision="v1")
    with pytest.raises(ValidationError):
        InstrumentIdentity(
            instrument_id=uuid4(),
            underlying=UnderlyingIdentity(
                underlying_id=uuid4(),
                source=native,
                mapping=RevisionRef(id="mapping", version="v1"),
            ),
            native=native,
            symbol="ABC",
            exchange="NSE",
            segment="NFO",
            instrument_type="FUTSTK",
            expiry_date=datetime(2026, 10, 29, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        )


@pytest.mark.parametrize("asset", [AssetClass.FUTURES, AssetClass.OPTION])
@pytest.mark.parametrize("hour", [0, 15])
def test_exchange_expiry_date_survives_timezone_projection(
    store: tuple[OrderService, UUID, Engine], asset: AssetClass, hour: int
) -> None:
    from zoneinfo import ZoneInfo

    service, _, _ = store
    order = request(asset)
    original = CANONICAL[order.instrument.instrument_id]
    local_expiry = datetime(2026, 10, 29, hour, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    canonical = InstrumentIdentity.model_validate(
        {
            **original.model_dump(),
            "expiry": local_expiry,
            "expiry_date": date(2026, 10, 29),
        }
    )
    assert canonical.expiry is not None
    if hour == 0:
        assert canonical.expiry.date() == date(2026, 10, 28)
    projected = OrderInstrument.from_canonical(canonical, asset)
    assert projected.expiry == date(2026, 10, 29)
    equivalent = InstrumentIdentity.model_validate(
        {**canonical.model_dump(), "expiry": local_expiry.astimezone(UTC)}
    )
    assert OrderInstrument.from_canonical(equivalent, asset).expiry == date(2026, 10, 29)
    CANONICAL[order.instrument.instrument_id] = canonical
    persisted = service.create_order(order)
    assert service.get_order(persisted.twf_order_id).instrument.expiry == date(2026, 10, 29)


@pytest.mark.parametrize(
    "field,value",
    [
        ("lot_size", 1),
        ("tick_size", Decimal("0.01")),
        ("expiry", date(2026, 10, 28)),
        ("strike", Decimal("2550")),
        ("option_type", "PE"),
    ],
)
def test_conflicting_canonical_contract_facts_rejected(
    store: tuple[OrderService, UUID, Engine], field: str, value: object
) -> None:
    service, _, _ = store
    original = request(AssetClass.OPTION)
    conflicting = original.instrument.model_copy(update={field: value})
    order = original.model_copy(update={"instrument": conflicting})
    with pytest.raises(OrderError) as err:
        service.create_order(order)
    assert err.value.code == OrderErrorCode.INVALID_ORDER
    assert service.list_orders() == ()


@pytest.mark.parametrize("asset", [AssetClass.EQUITY, AssetClass.FUTURES, AssetClass.OPTION])
def test_canonical_instrument_type_cannot_be_reclassified(
    store: tuple[OrderService, UUID, Engine], asset: AssetClass
) -> None:
    service, _, _ = store
    order = request(asset)
    canonical = CANONICAL[order.instrument.instrument_id]
    wrong_kind = {
        AssetClass.EQUITY: "FUTSTK",
        AssetClass.FUTURES: "EQUITY",
        AssetClass.OPTION: "FUTSTK",
    }[asset]
    conflicting = canonical.model_copy(update={"instrument_type": wrong_kind})
    with pytest.raises(OrderError) as err:
        CANONICAL[order.instrument.instrument_id] = conflicting
        service.create_order(order)
    assert err.value.code == OrderErrorCode.INVALID_ORDER
    assert service.list_orders() == ()


def test_ambiguous_canonical_identity_rejected(store: tuple[OrderService, UUID, Engine]) -> None:
    service, _, _ = store
    order = request(AssetClass.FUTURES)
    canonical = CANONICAL[order.instrument.instrument_id]
    ambiguous = canonical.model_copy(
        update={"underlying": canonical.underlying.model_copy(update={"ambiguous": True})}
    )
    with pytest.raises(OrderError) as err:
        CANONICAL[order.instrument.instrument_id] = ambiguous
        service.create_order(order)
    assert err.value.code == OrderErrorCode.INVALID_ORDER
    assert service.list_orders() == ()


def test_create_rejects_view_and_subclass_payload(store: tuple[OrderService, UUID, Engine]) -> None:
    service, _, _ = store
    existing = create(service, request())
    with pytest.raises(OrderError) as err:
        service.create_order(existing)
    assert err.value.code == OrderErrorCode.INVALID_ORDER

    class ForgedCreate(CreateOrder):
        broker_order_id: str = "fake"
        state: OrderState = OrderState.FILLED

    forged = ForgedCreate.model_validate(
        {
            **request().model_dump(mode="json"),
            "broker_order_id": "fake",
            "state": "FILLED",
        }
    )
    with pytest.raises(OrderError) as err:
        service.create_order(forged)
    assert err.value.code == OrderErrorCode.INVALID_ORDER
    assert len(service.list_orders()) == 1
    service.update_draft_order(
        existing.twf_order_id, DraftChanges(notes="still editable"), expected_version=1
    )


def test_context_actor_source_and_session_binding(store: tuple[OrderService, UUID, Engine]) -> None:
    service, key, engine = store
    manual = create(service, request())
    assert manual.created_by == f"USER:{key}"
    assert service.get_order_history(manual.twf_order_id)[0].actor == f"USER:{key}"
    scanner = service_for(engine, key, Source.SCANNER)
    with pytest.raises(OrderError) as err:
        create(scanner, request())
    assert err.value.code == OrderErrorCode.INVALID_ORDER
    scanner_order = create(scanner, request(source=Source.SCANNER))
    assert scanner_order.provenance.source_ref == "source-123"
    with pytest.raises(ValidationError):
        OrderProvenance(source=Source.SCANNER)
    with pytest.raises(ValidationError):
        OrderProvenance(source=Source.SCANNER, source_ref="   ")
    with pytest.raises(TypeError):
        service.transition_order(
            manual.twf_order_id, OrderState.READY, expected_version=1, actor="BROKER_RECONCILIATION"
        )  # type: ignore[call-arg]


def test_numeric_sanity_bounds() -> None:
    with pytest.raises(ValidationError):
        OrderTerms(
            side=Side.BUY, quantity=10**100, order_type=OrderType.MARKET, product=Product.INTRADAY
        )
    for price in (
        Decimal("1e100"),
        Decimal("0." + "1" * 1000),
        Decimal("1.000000001"),
        Decimal("Infinity"),
        Decimal("NaN"),
    ):
        with pytest.raises(ValidationError):
            OrderTerms(
                side=Side.BUY,
                quantity=1,
                order_type=OrderType.LIMIT,
                limit_price=price,
                product=Product.INTRADAY,
            )
    assert (
        OrderTerms(
            side=Side.BUY,
            quantity=1_000_000,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("123456.12345678"),
            product=Product.INTRADAY,
        ).quantity
        == 1_000_000
    )
    with pytest.raises(ValidationError):
        OrderInstrument.model_validate(
            {
                **instrument(AssetClass.OPTION).model_dump(),
                "strike": Decimal("1e100"),
            }
        )


def test_mismatched_event_owner_rejected_by_database(
    store: tuple[OrderService, UUID, Engine],
) -> None:
    from sqlalchemy.exc import IntegrityError

    service, key, engine = store
    other = owner(engine)
    order = create(service, request())
    with pytest.raises(IntegrityError), create_session_factory(engine)() as db, db.begin():
        db.add(
            TWFOrderEventRecord(
                event_id=uuid4(),
                twf_order_id=order.twf_order_id,
                owner_id=other,
                sequence=2,
                order_version=1,
                event_type=EventType.ORDER_UPDATED.value,
                from_state=None,
                to_state=None,
                actor="USER:wrong",
                authority="TWF_DOMAIN",
                reason_code=None,
                reason=None,
                correlation_id=None,
                details={},
                occurred_at=datetime.now(UTC),
            )
        )
    assert key != other
    assert len(service.get_order_history(order.twf_order_id)) == 1


@pytest.mark.parametrize("operation", ["create", "update"])
def test_database_audit_insert_failure_rolls_back(
    store: tuple[OrderService, UUID, Engine], operation: str
) -> None:
    from sqlalchemy.exc import IntegrityError

    service, _, engine = store
    order = create(service, request()) if operation == "update" else None
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TRIGGER deny_order_event BEFORE INSERT ON twf_order_events "
            "BEGIN SELECT RAISE(ABORT, 'audit denied'); END"
        )
    try:
        with pytest.raises(IntegrityError):
            if operation == "create":
                create(service, request())
            else:
                assert order is not None
                service.update_draft_order(
                    order.twf_order_id, DraftChanges(notes="change"), expected_version=1
                )
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TRIGGER deny_order_event")
    if operation == "create":
        assert service.list_orders() == ()
    else:
        assert order is not None
        assert service.get_order(order.twf_order_id).version == 1
        assert len(service.get_order_history(order.twf_order_id)) == 1


@pytest.mark.parametrize("kind", ["draft_update", "ready_cancel"])
def test_sqlite_same_version_races_are_typed_and_single_commit(
    store: tuple[OrderService, UUID, Engine], kind: str
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    service, _, _ = store
    conflicts = {OrderErrorCode.VERSION_CONFLICT, OrderErrorCode.RETRYABLE_CONCURRENCY_CONFLICT}
    for iteration in range(5):
        order = create(service, request())
        barrier = Barrier(2)

        def attempt(
            which: int,
            barrier: Barrier = barrier,
            order_id: UUID = order.twf_order_id,
            iteration: int = iteration,
        ) -> OrderState | OrderErrorCode:
            barrier.wait()
            try:
                if kind == "draft_update":
                    service.update_draft_order(
                        order_id,
                        DraftChanges(notes=f"{iteration}:{which}"),
                        expected_version=1,
                    )
                    return OrderState.DRAFT
                if which == 0:
                    service.transition_order(order_id, OrderState.READY, expected_version=1)
                    return OrderState.READY
                service.transition_order(
                    order_id,
                    OrderState.CANCELLED,
                    expected_version=1,
                    reason_code="USER_CANCEL",
                    reason="User cancelled",
                )
                return OrderState.CANCELLED
            except OrderError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(attempt, 0)
            second = pool.submit(attempt, 1)
            outcomes = (first.result(), second.result())
        assert sum(result in conflicts for result in outcomes) == 1
        assert service.get_order(order.twf_order_id).version == 2
        expected_events = 2 if kind == "draft_update" or OrderState.CANCELLED in outcomes else 3
        assert len(service.get_order_history(order.twf_order_id)) == expected_events


@pytest.mark.parametrize(
    "asset,field,value",
    [
        (AssetClass.FUTURES, "expiry", date(2026, 10, 30)),
        (AssetClass.FUTURES, "lot_size", 1),
        (AssetClass.FUTURES, "tick_size", Decimal("0.01")),
        (AssetClass.OPTION, "strike", Decimal("2600")),
        (AssetClass.OPTION, "option_type", "PE"),
        (AssetClass.FUTURES, "asset_class", AssetClass.OPTION),
    ],
)
def test_request_cannot_forge_canonical_facts_with_valid_uuid(
    store: tuple[OrderService, UUID, Engine], asset: AssetClass, field: str, value: object
) -> None:
    service, _, _ = store
    valid = request(asset)
    forged = valid.model_copy(
        update={"instrument": valid.instrument.model_copy(update={field: value})}
    )
    with pytest.raises(OrderError) as err:
        service.create_order(forged)
    assert err.value.code == OrderErrorCode.INVALID_ORDER
    assert service.list_orders() == ()


def test_raw_canonical_argument_and_unknown_uuid_have_no_authority(
    store: tuple[OrderService, UUID, Engine],
) -> None:
    service, _, _ = store
    valid = request(AssetClass.FUTURES)
    forged_canonical = CANONICAL[valid.instrument.instrument_id].model_copy(
        update={"expiry_date": date(2026, 10, 30), "lot_size": 1, "tick_size": Decimal("0.01")}
    )
    with pytest.raises(TypeError):
        service.create_order(valid, canonical_identity=forged_canonical)  # type: ignore[call-arg]
    unknown = valid.model_copy(
        update={"instrument": valid.instrument.model_copy(update={"instrument_id": uuid4()})}
    )
    with pytest.raises(OrderError) as err:
        service.create_order(unknown)
    assert err.value.code == OrderErrorCode.INVALID_ORDER
    assert service.list_orders() == ()


@pytest.mark.parametrize("claimed", [Source.WEBHOOK, Source.SCANNER, Source.AGENT])
def test_user_session_cannot_claim_subsystem_source(
    store: tuple[OrderService, UUID, Engine], claimed: Source
) -> None:
    service, key, engine = store
    with create_session_factory(engine)() as db:
        user = db.get(User, key)
        login = db.get(AuthSession, SESSIONS[key])
        assert user is not None and login is not None
        with pytest.raises(TypeError):
            OrderContext.from_authenticated_session(user, login, source=claimed)  # type: ignore[call-arg]
    with pytest.raises(OrderError) as err:
        create(service, request(source=claimed))
    assert err.value.code == OrderErrorCode.INVALID_ORDER
    assert service.list_orders() == ()


@pytest.mark.parametrize("source", [Source.WEBHOOK, Source.SCANNER])
def test_verified_subsystem_origin_binds_source_and_reference(
    store: tuple[OrderService, UUID, Engine], source: Source
) -> None:
    service, key, engine = store
    with create_session_factory(engine)() as db:
        user = db.get(User, key)
        login = db.get(AuthSession, SESSIONS[key])
        assert user is not None and login is not None
        issuer = _SubsystemOriginIssuer(
            source, lambda owner_id, ref: owner_id == key and ref == "verified-event"
        )
        with pytest.raises(OrderError):
            issuer.issue(key, "arbitrary-source-ref")
        context = OrderContext.from_trusted_subsystem(
            user, login, issuer.issue(key, "verified-event")
        )
    delegated = OrderService(
        create_session_factory(engine),
        context,
        _bind_trusted_canonical_resolver(TrustedTestResolver()),
    )
    valid = request(source=source)
    with pytest.raises(OrderError) as err:
        delegated.create_order(valid)
    assert err.value.code == OrderErrorCode.INVALID_ORDER
    valid = valid.model_copy(
        update={"provenance": OrderProvenance(source=source, source_ref="verified-event")}
    )
    draft = create(delegated, valid)
    assert draft.created_by == f"USER:{key}"
    assert draft.provenance.source == source
    assert draft.provenance.source_ref == "verified-event"
    assert delegated.get_order_history(draft.twf_order_id)[0].actor == f"USER:{key}"
    with pytest.raises(ValidationError):
        OrderProvenance(source=source)
    for protected in (OrderState.QUEUED, OrderState.BROKER_ACCEPTED, OrderState.FILLED):
        with pytest.raises(OrderError) as err:
            delegated.transition_order(draft.twf_order_id, protected, expected_version=1)
        assert err.value.code == OrderErrorCode.INVALID_TRANSITION_AUTHORITY


def test_unissued_and_cross_owner_subsystem_origins_rejected(
    store: tuple[OrderService, UUID, Engine],
) -> None:
    _, key, engine = store
    with create_session_factory(engine)() as db:
        user = db.get(User, key)
        login = db.get(AuthSession, SESSIONS[key])
        assert user is not None and login is not None
        fabricated = object.__new__(_TrustedSubsystemOrigin)
        object.__setattr__(fabricated, "owner_id", key)
        object.__setattr__(fabricated, "source", Source.WEBHOOK)
        object.__setattr__(fabricated, "reference", "forged")
        with pytest.raises(OrderError) as err:
            OrderContext.from_trusted_subsystem(user, login, fabricated)
        assert err.value.code == OrderErrorCode.UNAUTHORIZED
        other = uuid4()
        issuer = _SubsystemOriginIssuer(Source.WEBHOOK, lambda owner_id, ref: True)
        with pytest.raises(OrderError) as err:
            OrderContext.from_trusted_subsystem(user, login, issuer.issue(other, "event"))
        assert err.value.code == OrderErrorCode.UNAUTHORIZED


@pytest.mark.parametrize("asset", list(AssetClass))
def test_trusted_canonical_identity_can_reach_ready(
    store: tuple[OrderService, UUID, Engine], asset: AssetClass
) -> None:
    service, _, _ = store
    proposed = request(asset)
    trusted = CANONICAL[proposed.instrument.instrument_id]
    draft = create(service, proposed)
    ready = service.transition_order(draft.twf_order_id, OrderState.READY, expected_version=1)
    assert ready.instrument.instrument_id == trusted.instrument_id
    assert ready.instrument.expiry == trusted.expiry_date
    assert ready.instrument.lot_size == trusted.lot_size
    assert ready.instrument.tick_size == trusted.tick_size
    if asset == AssetClass.OPTION:
        assert ready.instrument.strike == trusted.strike
        assert ready.instrument.option_type == "CE"
    assert ready.state == OrderState.READY


def test_valid_looking_asset_reclassification_and_combined_futures_forgery_rejected(
    store: tuple[OrderService, UUID, Engine],
) -> None:
    service, _, _ = store
    valid = request(AssetClass.FUTURES)
    option_like = valid.instrument.model_copy(
        update={"asset_class": AssetClass.OPTION, "strike": Decimal("2500"), "option_type": "CE"}
    )
    OrderInstrument.model_validate(option_like.model_dump(mode="json"))
    forged_option = valid.model_copy(update={"instrument": option_like})
    with pytest.raises(OrderError) as err:
        service.create_order(forged_option)
    assert err.value.code == OrderErrorCode.INVALID_ORDER
    forged_future = valid.instrument.model_copy(
        update={"expiry": date(2026, 10, 30), "lot_size": 1, "tick_size": Decimal("0.01")}
    )
    OrderInstrument.model_validate(forged_future.model_dump(mode="json"))
    with pytest.raises(OrderError) as err:
        service.create_order(valid.model_copy(update={"instrument": forged_future}))
    assert err.value.code == OrderErrorCode.INVALID_ORDER
    assert service.list_orders() == ()


def test_unissued_canonical_authority_rejected_at_service_construction(
    store: tuple[OrderService, UUID, Engine],
) -> None:
    service, _, _ = store
    forged = object.__new__(TrustedCanonicalInstrumentAuthority)
    object.__setattr__(forged, "_resolver", TrustedTestResolver())
    with pytest.raises(OrderError) as err:
        OrderService(service.sessions, service.context, forged)
    assert err.value.code == OrderErrorCode.UNAUTHORIZED
