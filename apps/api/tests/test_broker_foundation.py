"""BW-2.1 secure provider/account foundation, negatives, and frozen-boundary tests."""

import json
import logging
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import StringIO
from pathlib import Path
from threading import Barrier
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from twf.auth import create_user
from twf.broker_foundation import BrokerFoundation, BrokerFoundationFailure
from twf.brokers.foundation_contracts import (
    BrokerAccountConfiguration,
    BrokerAccountCreate,
    BrokerPermission,
    PersonalBrokerPermissionPolicy,
    ProviderAuthMethod,
    ProviderCapabilities,
    ProviderDefinition,
)
from twf.config.settings import Settings
from twf.infrastructure.broker_foundation import (
    BrokerAccountRecord,
    BrokerAuditEvent,
    BrokerConnectionRecord,
)
from twf.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from twf.main import create_app
from twf.observability import JsonFormatter
from twf.secrets import (
    MemorySecretStore,
    SecretAccessDenied,
    SecretScope,
    SecretStoreUnavailable,
    SecretValue,
    UnavailableSecretStore,
    default_secret_store,
)

ORIGIN = "https://web.example"
HEADERS = {"Origin": ORIGIN}
PASSWORD = "test-only-broker-foundation-password"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, pytestconfig: pytest.Config) -> Iterator[TestClient]:
    # Never inherit a deployment URL: conftest sets disposable SQLite. PostgreSQL is opt-in
    # through a CLI argument and each test owns a unique schema, never public/developer tables.
    postgres_url = pytestconfig.getoption("--broker-postgres-url")
    admin = None
    schema = "bw21_test_" + uuid4().hex
    if postgres_url:
        url = make_url(postgres_url)
        if url.get_backend_name() != "postgresql":
            pytest.fail("--broker-postgres-url requires PostgreSQL")
        admin = create_database_engine(Settings(database_url=postgres_url))
        with admin.begin() as connection:
            connection.execute(CreateSchema(schema))
        isolated = url.update_query_dict({"options": f"-csearch_path={schema}"})
        monkeypatch.setenv("TWF_DATABASE_URL", isolated.render_as_string(hide_password=False))
    try:
        command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
        settings = Settings(environment="test", cors_origins=(ORIGIN,))
        engine = create_database_engine(settings)
        try:
            with session_scope(create_session_factory(engine)) as session:
                create_user(session, "alice", "Alice", PASSWORD)
                create_user(session, "bob", "Bob", PASSWORD)
                session.commit()
            with TestClient(create_app(settings, engine_factory=lambda _: engine)) as browser:
                yield browser
        finally:
            engine.dispose()
    finally:
        if admin is not None:
            with admin.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            admin.dispose()


def login(client: TestClient, username: str) -> UUID:
    response = client.post(
        "/api/v1/auth/login",
        headers=HEADERS,
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200
    return UUID(response.json()["id"])


def create_account(client: TestClient, label: str = "Primary Zerodha") -> dict[str, object]:
    response = client.post(
        "/api/v1/broker-accounts",
        headers=HEADERS,
        json={"provider_id": "zerodha", "label": label},
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


def test_zerodha_registration_is_truthful_and_no_connect_routes(client: TestClient) -> None:
    assert client.get("/api/v1/broker-providers").status_code == 401
    login(client, "alice")
    response = client.get("/api/v1/broker-providers")
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == [
        {
            "provider_id": "zerodha",
            "display_name": "Zerodha",
            "supported_modes": ["LIVE"],
            "auth_method": "BROWSER_REDIRECT_CALLBACK",
            "capabilities": {"read": True, "catalog": True, "search": True, "commands": False},
            "supported": True,
            "configured": False,
            "connectable": False,
            "trading_enabled": False,
        }
    ]
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v1/broker-providers" in paths
    assert "/api/v1/broker-accounts" in paths
    assert not any(
        path.startswith("/api/v1/broker-")
        and any(word in path for word in ("connect", "callback", "token", "logout"))
        for path in paths
    )


def test_account_creation_revision_and_read_do_not_mutate(client: TestClient) -> None:
    owner = login(client, "alice")
    account = create_account(client)
    assert account == {
        "broker_account_id": account["broker_account_id"],
        "owner_user_id": str(owner),
        "provider_id": "zerodha",
        "provider_account_id": None,
        "mode": "LIVE",
        "label": "Primary Zerodha",
        "enabled": False,
        "configured": False,
        "configuration_revision": 1,
        "connection_generation": 0,
        "authentication_state": "NOT_CONFIGURED",
        "read_health": "UNKNOWN",
        "last_successful_read_at": None,
        "last_failure_at": None,
        "connectable": False,
        "trading_enabled": False,
        "created_at": account["created_at"],
        "updated_at": account["updated_at"],
    }
    first = client.get("/api/v1/broker-accounts").json()
    second = client.get("/api/v1/broker-accounts").json()
    assert first == second == [account]
    path = f"/api/v1/broker-accounts/{account['broker_account_id']}/configuration"
    updated = client.patch(
        path,
        headers=HEADERS,
        json={"expected_revision": 1, "label": "Primary", "enabled": True},
    )
    assert updated.status_code == 200
    assert updated.json()["configuration_revision"] == 2
    assert updated.json()["connection_generation"] == 0
    assert updated.json()["enabled"] is True
    assert updated.json()["configured"] is False
    stale = client.patch(
        path,
        headers=HEADERS,
        json={"expected_revision": 1, "label": "Stale", "enabled": False},
    )
    assert stale.status_code == 409
    assert client.get("/api/v1/broker-accounts").json()[0]["configuration_revision"] == 2


def test_account_api_csrf_validation_uniqueness_and_idor(client: TestClient) -> None:
    assert client.post("/api/v1/broker-accounts", headers=HEADERS, json={}).status_code == 401
    login(client, "alice")
    assert (
        client.post(
            "/api/v1/broker-accounts",
            json={"provider_id": "zerodha", "label": "No origin"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/broker-accounts",
            headers=HEADERS,
            json={"provider_id": "unknown", "label": "Unknown"},
        ).status_code
        == 422
    )
    account = create_account(client)
    assert (
        client.post(
            "/api/v1/broker-accounts",
            headers=HEADERS,
            json={"provider_id": "zerodha", "label": "Primary Zerodha"},
        ).status_code
        == 409
    )
    login(client, "bob")
    assert client.get("/api/v1/broker-accounts").json() == []
    response = client.patch(
        f"/api/v1/broker-accounts/{account['broker_account_id']}/configuration",
        headers=HEADERS,
        json={"expected_revision": 1, "label": "Stolen", "enabled": True},
    )
    assert response.status_code == 404
    assert str(account["owner_user_id"]) not in response.text


def test_permission_model_never_infers_commands() -> None:
    policy = PersonalBrokerPermissionPolicy()
    owner, other = uuid4(), uuid4()
    assert all(
        policy.allows(owner, permission, owner)
        for permission in (
            BrokerPermission.READ,
            BrokerPermission.CONFIGURE,
            BrokerPermission.CONNECT,
            BrokerPermission.DISCONNECT,
        )
    )
    assert all(
        not policy.allows(owner, permission, owner)
        for permission in (
            BrokerPermission.TRADE,
            BrokerPermission.CANCEL_MODIFY,
            BrokerPermission.RESOLVE_UNKNOWN,
        )
    )
    assert all(not policy.allows(other, permission, owner) for permission in BrokerPermission)


def test_memory_secret_store_scope_lifecycle_and_redaction() -> None:
    references = iter(("opaque-ref-1", "opaque-ref-2"))
    store = MemorySecretStore(lambda: next(references))
    owner, other, account = uuid4(), uuid4(), uuid4()
    scope = SecretScope(owner, "zerodha", account, "test", 1)
    wrong_scope = SecretScope(other, "zerodha", account, "test", 1)
    raw = "raw-super-secret-token"
    value = SecretValue(raw)
    saved = store.put(scope, value)
    assert saved.reference == "opaque-ref-1" and raw not in repr(value) and raw not in str(value)
    assert store.exists(scope, saved.reference)
    assert not store.exists(wrong_scope, saved.reference)
    assert store.get(scope, saved.reference).reveal() == raw
    with pytest.raises(SecretAccessDenied):
        store.get(wrong_scope, saved.reference)
    with pytest.raises(SecretAccessDenied):
        store.delete(wrong_scope, saved.reference)
    assert store.delete(scope, saved.reference)
    assert not store.exists(scope, saved.reference)


def test_production_secret_store_fails_closed() -> None:
    store = default_secret_store(Settings(environment="production"))
    assert isinstance(store, UnavailableSecretStore)
    scope = SecretScope(uuid4(), "zerodha", uuid4(), "production", 1)
    assert not store.exists(scope, "opaque")
    with pytest.raises(SecretStoreUnavailable):
        store.put(scope, SecretValue("never-stored"))
    app = create_app(Settings(environment="production"))
    assert isinstance(app.state.secret_store, UnavailableSecretStore)


def test_reference_replacement_generation_disconnect_and_audit(client: TestClient) -> None:
    owner = login(client, "alice")
    created = create_account(client)
    account_id = UUID(str(created["broker_account_id"]))
    app = cast(FastAPI, client.app)
    store = cast(MemorySecretStore, app.state.secret_store)
    scope = SecretScope(owner, "zerodha", account_id, "test", 1)
    raw = "future-only-secret"
    saved = store.put(scope, SecretValue(raw))
    with session_scope(app.state.session_factory) as session:
        use = BrokerFoundation(
            session,
            owner,
            PersonalBrokerPermissionPolicy(),
            store,
            "test",
            "secret-replace",
        )
        use.replace_secret_reference(account_id, saved.reference, expected_generation=0)
    with session_scope(app.state.session_factory) as session:
        account = session.get(BrokerAccountRecord, account_id)
        connection = session.get(BrokerConnectionRecord, account_id)
        assert account and connection
        assert account.connection_generation == 1
        assert connection.secret_reference == saved.reference
        events = list(
            session.scalars(
                select(BrokerAuditEvent)
                .where(BrokerAuditEvent.broker_account_id == account_id)
                .order_by(BrokerAuditEvent.created_at)
            )
        )
        serialized = " ".join(
            f"{event.event_type} {event.request_id} {event.outcome}" for event in events
        )
        assert [event.event_type for event in events] == [
            "BROKER_ACCOUNT_CREATED",
            "SECRET_REFERENCE_REPLACED",
        ]
        assert raw not in serialized and saved.reference not in serialized
    with session_scope(app.state.session_factory) as session:
        generation = BrokerFoundation(
            session, owner, PersonalBrokerPermissionPolicy(), store, "test", "disconnect"
        ).invalidate_connection(account_id, expected_generation=1)
        assert generation == 2
    assert not store.exists(scope, saved.reference)
    with session_scope(app.state.session_factory) as session:
        connection = session.get(BrokerConnectionRecord, account_id)
        events = list(
            session.scalars(
                select(BrokerAuditEvent).where(BrokerAuditEvent.broker_account_id == account_id)
            )
        )
        assert connection and connection.secret_reference is None
        assert [event.event_type for event in events][-1] == "CONNECTION_INVALIDATED"
        assert session.bind is not None
        columns = {
            column["name"]
            for table in ("broker_accounts", "broker_audit_events")
            for column in inspect(session.bind).get_columns(table)
        }
        assert "access_token" not in columns and "api_secret" not in columns


def test_wrong_user_cannot_attach_another_users_secret(client: TestClient) -> None:
    owner = login(client, "alice")
    created = create_account(client)
    account_id = UUID(str(created["broker_account_id"]))
    app = cast(FastAPI, client.app)
    store = cast(MemorySecretStore, app.state.secret_store)
    saved = store.put(
        SecretScope(owner, "zerodha", account_id, "test", 1), SecretValue("owner-only-token")
    )
    other = login(client, "bob")
    with session_scope(app.state.session_factory) as session:
        use = BrokerFoundation(
            session, other, PersonalBrokerPermissionPolicy(), store, "test", "idor"
        )
        with pytest.raises(BrokerFoundationFailure) as caught:
            use.replace_secret_reference(account_id, saved.reference, expected_generation=0)
        assert caught.value.status == 404


def test_migration_schema_and_zerodha_seed(client: TestClient) -> None:
    login(client, "alice")
    app = cast(FastAPI, client.app)
    with session_scope(app.state.session_factory) as session:
        assert session.bind is not None
        inspector = inspect(session.bind)
        assert {
            "broker_provider_configurations",
            "broker_accounts",
            "broker_connections",
            "broker_audit_events",
        }.issubset(inspector.get_table_names())
        provider = client.get("/api/v1/broker-providers").json()[0]
        assert provider["provider_id"] == "zerodha" and not provider["connectable"]


def test_production_rejects_injected_development_store() -> None:
    class DisguisedMemoryStore(MemorySecretStore):
        production_safe = True

    for store in (MemorySecretStore(), DisguisedMemoryStore()):
        with pytest.raises(SecretStoreUnavailable, match="not approved for production"):
            create_app(Settings(environment="production"), secret_store=store)
    for environment in ("test", "development"):
        store = MemorySecretStore()
        assert (
            create_app(Settings(environment=environment), secret_store=store).state.secret_store
            is store
        )


def test_custom_store_requires_explicit_production_capability() -> None:
    class FutureStore(UnavailableSecretStore):
        production_safe = False

    store = FutureStore()
    with pytest.raises(SecretStoreUnavailable):
        create_app(Settings(environment="production"), secret_store=store)
    store.production_safe = True
    assert (
        create_app(Settings(environment="production"), secret_store=store).state.secret_store
        is store
    )


@pytest.mark.parametrize("auth_method", list(ProviderAuthMethod))
def test_provider_metadata_can_describe_different_providers(
    auth_method: ProviderAuthMethod,
) -> None:
    provider = ProviderDefinition(
        provider_id="metadata-fixture",
        display_name="Metadata only",
        auth_method=auth_method,
        capabilities=ProviderCapabilities(read=False, catalog=True, search=False, commands=True),
    )
    assert provider.capabilities.model_dump() == {
        "read": False,
        "catalog": True,
        "search": False,
        "commands": True,
    }
    assert provider.auth_method == auth_method
    # Defining metadata grants no operation permission and does not register an adapter.
    owner = uuid4()
    assert not PersonalBrokerPermissionPolicy().allows(owner, BrokerPermission.TRADE, owner)


@pytest.mark.parametrize("label", ["", "   ", "\t\n", "x" * 81])
def test_normalized_invalid_labels_rejected_on_create_and_update(
    client: TestClient, label: str
) -> None:
    login(client, "alice")
    account = create_account(client)
    response = client.post(
        "/api/v1/broker-accounts", headers=HEADERS, json={"provider_id": "zerodha", "label": label}
    )
    assert response.status_code == 422
    response = client.patch(
        f"/api/v1/broker-accounts/{account['broker_account_id']}/configuration",
        headers=HEADERS,
        json={"expected_revision": 1, "label": label, "enabled": True},
    )
    assert response.status_code == 422
    assert client.get("/api/v1/broker-accounts").json() == [account]


def test_normalization_shared_by_contract_service_and_api(client: TestClient) -> None:
    owner = login(client, "alice")
    app = cast(FastAPI, client.app)
    payload = BrokerAccountCreate(provider_id="zerodha", label="  Alpha  ")
    assert payload.label == "Alpha"
    with session_scope(app.state.session_factory) as session:
        account = BrokerFoundation(
            session, owner, PersonalBrokerPermissionPolicy(), app.state.secret_store, "test"
        ).create_account(payload)
    assert account.label == "Alpha"
    updated = client.patch(
        f"/api/v1/broker-accounts/{account.broker_account_id}/configuration",
        headers=HEADERS,
        json={"expected_revision": 1, "label": "  Beta  ", "enabled": False},
    )
    assert updated.status_code == 200 and updated.json()["label"] == "Beta"
    assert (
        BrokerAccountConfiguration(
            expected_revision=1, label=" " + "x" * 80 + " ", enabled=False
        ).label
        == "x" * 80
    )


def test_duplicate_patch_conflict_rolls_back_and_preserves_audit(client: TestClient) -> None:
    login(client, "alice")
    create_account(client, "Alpha")
    beta = create_account(client, "Beta")
    path = f"/api/v1/broker-accounts/{beta['broker_account_id']}/configuration"
    response = client.patch(
        path, headers=HEADERS, json={"expected_revision": 1, "label": " Alpha ", "enabled": True}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HTTP_409"
    assert "constraint" not in response.text.lower() and "sql" not in response.text.lower()
    assert client.get("/api/v1/broker-accounts").json()[1] == beta
    app = cast(FastAPI, client.app)
    with session_scope(app.state.session_factory) as session:
        events = list(
            session.scalars(
                select(BrokerAuditEvent).where(
                    BrokerAuditEvent.broker_account_id == UUID(str(beta["broker_account_id"]))
                )
            )
        )
        assert [e.event_type for e in events] == ["BROKER_ACCOUNT_CREATED"]
    success = client.patch(
        path, headers=HEADERS, json={"expected_revision": 1, "label": "Gamma", "enabled": True}
    )
    assert success.status_code == 200 and success.json()["configuration_revision"] == 2


def test_secret_supersession_disconnect_and_stale_reattachment(client: TestClient) -> None:
    owner = login(client, "alice")
    account_id = UUID(str(create_account(client)["broker_account_id"]))
    app = cast(FastAPI, client.app)
    store = cast(MemorySecretStore, app.state.secret_store)
    scopes = [
        SecretScope(owner, "zerodha", account_id, "test", generation) for generation in (1, 2)
    ]
    refs = [
        store.put(scope, SecretValue("lifecycle-secret-" + str(i))).reference
        for i, scope in enumerate(scopes)
    ]
    for expected, reference in enumerate(refs):
        with session_scope(app.state.session_factory) as session:
            generation = BrokerFoundation(
                session, owner, PersonalBrokerPermissionPolicy(), store, "test"
            ).replace_secret_reference(account_id, reference, expected_generation=expected)
            assert generation == expected + 1
    assert not store.exists(scopes[0], refs[0])
    with pytest.raises(SecretAccessDenied):
        store.get(scopes[0], refs[0])
    with session_scope(app.state.session_factory) as session:
        assert (
            BrokerFoundation(
                session, owner, PersonalBrokerPermissionPolicy(), store, "test"
            ).invalidate_connection(account_id, expected_generation=2)
            == 3
        )
    for scope, reference in zip(scopes, refs, strict=True):
        assert not store.exists(scope, reference)
        with session_scope(app.state.session_factory) as session:
            with pytest.raises(BrokerFoundationFailure) as caught:
                BrokerFoundation(
                    session, owner, PersonalBrokerPermissionPolicy(), store, "test"
                ).replace_secret_reference(account_id, reference, expected_generation=3)
            assert caught.value.status == 404
    with session_scope(app.state.session_factory) as session:
        account = session.get(BrokerAccountRecord, account_id)
        assert account and account.connection_generation == 3
        events = list(
            session.scalars(
                select(BrokerAuditEvent)
                .where(BrokerAuditEvent.broker_account_id == account_id)
                .order_by(BrokerAuditEvent.connection_generation)
            )
        )
        assert [e.connection_generation for e in events] == [0, 1, 2, 3]


@pytest.mark.parametrize("operation", ["replace", "disconnect"])
def test_stale_generation_conflict_leaves_state_and_secret_intact(
    client: TestClient, operation: str
) -> None:
    owner = login(client, "alice")
    account_id = UUID(str(create_account(client)["broker_account_id"]))
    app = cast(FastAPI, client.app)
    store = cast(MemorySecretStore, app.state.secret_store)
    scope = SecretScope(owner, "zerodha", account_id, "test", 1)
    ref = store.put(scope, SecretValue("stale-generation-secret")).reference
    with session_scope(app.state.session_factory) as session:
        BrokerFoundation(
            session, owner, PersonalBrokerPermissionPolicy(), store, "test"
        ).replace_secret_reference(account_id, ref, expected_generation=0)
    with session_scope(app.state.session_factory) as session:
        use = BrokerFoundation(session, owner, PersonalBrokerPermissionPolicy(), store, "test")
        with pytest.raises(BrokerFoundationFailure) as caught:
            if operation == "replace":
                use.replace_secret_reference(account_id, ref, expected_generation=0)
            else:
                use.invalidate_connection(account_id, expected_generation=0)
        assert caught.value.status == 409
        account = session.get(BrokerAccountRecord, account_id)
        connection = session.get(BrokerConnectionRecord, account_id)
        assert account and account.connection_generation == 1
        assert connection and connection.secret_reference == ref
        assert len(list(session.scalars(select(BrokerAuditEvent)))) == 2
    assert store.exists(scope, ref)


@pytest.mark.parametrize("operation", ["replace", "disconnect"])
def test_commit_failure_does_not_delete_active_secret(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    owner = login(client, "alice")
    account_id = UUID(str(create_account(client)["broker_account_id"]))
    app = cast(FastAPI, client.app)
    store = cast(MemorySecretStore, app.state.secret_store)
    scope = SecretScope(owner, "zerodha", account_id, "test", 1)
    ref = store.put(scope, SecretValue("must-survive-rollback")).reference
    candidate = store.put(
        replace(scope, connection_generation=2), SecretValue("uncommitted")
    ).reference
    with session_scope(app.state.session_factory) as session:
        BrokerFoundation(
            session, owner, PersonalBrokerPermissionPolicy(), store, "test"
        ).replace_secret_reference(account_id, ref, expected_generation=0)

    def fail_commit() -> None:
        raise RuntimeError("simulated database commit failure")

    with session_scope(app.state.session_factory) as session:
        use = BrokerFoundation(session, owner, PersonalBrokerPermissionPolicy(), store, "test")
        monkeypatch.setattr(use, "_commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated database"):
            if operation == "replace":
                use.replace_secret_reference(account_id, candidate, expected_generation=1)
            else:
                use.invalidate_connection(account_id, expected_generation=1)
    with session_scope(app.state.session_factory) as session:
        account = session.get(BrokerAccountRecord, account_id)
        connection = session.get(BrokerConnectionRecord, account_id)
        assert account and account.connection_generation == 1
        assert connection and connection.secret_reference == ref
        assert len(list(session.scalars(select(BrokerAuditEvent)))) == 2
    assert store.exists(scope, ref)


@pytest.mark.parametrize("second_operation", ["replace", "disconnect"])
def test_concurrent_generation_cas_and_audit(client: TestClient, second_operation: str) -> None:
    from sqlalchemy.engine import Connection, ExecutionContext

    owner = login(client, "alice")
    account_id = UUID(str(create_account(client)["broker_account_id"]))
    app = cast(FastAPI, client.app)
    store = cast(MemorySecretStore, app.state.secret_store)
    scope = SecretScope(owner, "zerodha", account_id, "test", 1)
    refs = [store.put(scope, SecretValue("race-secret-" + str(i))).reference for i in range(2)]
    barrier = Barrier(2)
    synchronized: list[bool] = []

    def synchronize(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: ExecutionContext,
        executemany: bool,
    ) -> None:
        if statement.startswith("UPDATE broker_accounts SET connection_generation="):
            barrier.wait(timeout=15)
            synchronized.append(True)

    engine = app.state.database_engine
    event.listen(engine, "before_cursor_execute", synchronize)

    def mutate(index: int) -> int:
        with session_scope(app.state.session_factory) as session:
            use = BrokerFoundation(session, owner, PersonalBrokerPermissionPolicy(), store, "test")
            try:
                if index == 1 and second_operation == "disconnect":
                    generation = use.invalidate_connection(account_id, expected_generation=0)
                else:
                    generation = use.replace_secret_reference(
                        account_id, refs[index], expected_generation=0
                    )
                assert generation == 1
                return 200
            except BrokerFoundationFailure as error:
                return error.status

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(mutate, (0, 1))) == [200, 409]
    finally:
        event.remove(engine, "before_cursor_execute", synchronize)
    assert len(synchronized) == 2  # Both transactions reached the CAS before either executed it.
    with session_scope(app.state.session_factory) as session:
        account = session.get(BrokerAccountRecord, account_id)
        assert account and account.connection_generation == 1
        events = list(
            session.scalars(
                select(BrokerAuditEvent)
                .where(BrokerAuditEvent.broker_account_id == account_id)
                .order_by(BrokerAuditEvent.connection_generation)
            )
        )
        assert [e.connection_generation for e in events] == [0, 1]


def test_cleanup_failure_fenced_and_real_logs_redacted(client: TestClient) -> None:
    owner = login(client, "alice")
    account_id = UUID(str(create_account(client)["broker_account_id"]))
    app = cast(FastAPI, client.app)
    raw = "raw-secret-that-must-never-be-rendered"

    class FailingDeleteStore(MemorySecretStore):
        def delete(self, scope: SecretScope, reference: str) -> bool:
            raise RuntimeError(raw)

    store = FailingDeleteStore()
    scopes = [SecretScope(owner, "zerodha", account_id, "test", g) for g in (1, 2)]
    refs = [store.put(scope, SecretValue(raw)).reference for scope in scopes]
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonFormatter(Settings(environment="test")))
    logger = app.state.logger
    logger.addHandler(handler)
    try:
        for expected, ref in enumerate(refs):
            with session_scope(app.state.session_factory) as session:
                BrokerFoundation(
                    session, owner, PersonalBrokerPermissionPolicy(), store, "test", logger=logger
                ).replace_secret_reference(account_id, ref, expected_generation=expected)
        with session_scope(app.state.session_factory) as session:
            BrokerFoundation(
                session, owner, PersonalBrokerPermissionPolicy(), store, "test", logger=logger
            ).invalidate_connection(account_id, expected_generation=2)
        # Physical deletion failed, but old scopes cannot be attached to any later generation.
        for scope, ref in zip(scopes, refs, strict=True):
            assert store.exists(scope, ref)
            with session_scope(app.state.session_factory) as session:
                with pytest.raises(BrokerFoundationFailure) as caught:
                    BrokerFoundation(
                        session,
                        owner,
                        PersonalBrokerPermissionPolicy(),
                        store,
                        "test",
                        logger=logger,
                    ).replace_secret_reference(account_id, ref, expected_generation=3)
                assert caught.value.status == 404
                assert raw not in str(caught.value) and raw not in repr(caught.value)
        invalid = client.post(
            "/api/v1/broker-accounts",
            headers=HEADERS,
            json={"provider_id": "zerodha", "label": "Invalid", "secret": raw},
        )
        assert invalid.status_code == 422 and raw not in invalid.text
        conflict = client.post(
            "/api/v1/broker-accounts",
            headers=HEADERS,
            json={"provider_id": "zerodha", "label": "Primary Zerodha"},
        )
        assert conflict.status_code == 409 and raw not in conflict.text
        response = client.get("/api/v1/broker-accounts")
        assert response.status_code == 200 and raw not in response.text
        with session_scope(app.state.session_factory) as session:
            rows = session.scalars(select(BrokerAuditEvent)).all()
            serialized = repr(
                [
                    {
                        column.name: getattr(row, column.name)
                        for column in BrokerAuditEvent.__table__.columns
                    }
                    for row in rows
                ]
            )
            assert raw not in serialized and all(ref not in serialized for ref in refs)
        logs = [json.loads(line) for line in output.getvalue().splitlines()]
        assert sum(row["event"] == "broker_secret_cleanup_failed" for row in logs) == 2
        assert {422, 409, 200}.issubset(
            {row.get("status_code") for row in logs if row["event"] == "request_completed"}
        )
        assert raw not in output.getvalue()
        assert all(ref not in output.getvalue() for ref in refs)
    finally:
        logger.removeHandler(handler)


def test_secret_scope_rejects_other_generation_environment_and_account() -> None:
    scope = SecretScope(uuid4(), "zerodha", uuid4(), "test", 1)
    store = MemorySecretStore()
    ref = store.put(scope, SecretValue("isolated-secret")).reference
    for wrong in (
        replace(scope, connection_generation=2),
        replace(scope, environment="production"),
        replace(scope, broker_account_id=uuid4()),
        replace(scope, provider_id="other"),
    ):
        assert not store.exists(wrong, ref)
        with pytest.raises(SecretAccessDenied):
            store.get(wrong, ref)
