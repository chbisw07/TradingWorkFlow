"""BW-2.2 deterministic official-shaped auth fixtures; never contacts Kite."""

import asyncio
import sqlite3
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import cast
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.engine import Connection, ExecutionContext, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import CreateSchema, DropSchema

from twf.auth import create_user, token_digest
from twf.broker_auth import BrokerAuth
from twf.broker_foundation import BrokerFoundationFailure
from twf.brokers.foundation_contracts import BrokerPermission, PersonalBrokerPermissionPolicy
from twf.brokers.zerodha_auth import KiteAuthClient, ProviderAuthFailure, ProviderAuthTimeout
from twf.config.settings import Settings
from twf.infrastructure.broker_auth import BrokerAuthAttempt, BrokerSecretLifecycle
from twf.infrastructure.broker_foundation import BrokerAccountRecord, BrokerAuditEvent
from twf.infrastructure.database import create_database_engine, create_session_factory
from twf.main import create_app
from twf.secrets import (
    MemorySecretStore,
    SecretAccessDenied,
    SecretScope,
    SecretValue,
    StoredSecret,
)

ORIGIN = "http://testserver"
HEADERS = {"Origin": ORIGIN}
PASSWORD = "test-only-auth-password"


class TestVault:
    """Explicit test double, not a deployed production store."""

    __test__ = False
    production_safe = True

    def __init__(self) -> None:
        self.memory = MemorySecretStore()
        self.fail_delete = False
        self.deny_delete = False

    def put(self, scope: SecretScope, value: SecretValue) -> StoredSecret:
        return self.memory.put(scope, value)

    def get(self, scope: SecretScope, reference: str) -> SecretValue:
        return self.memory.get(scope, reference)

    def exists(self, scope: SecretScope, reference: str) -> bool:
        return self.memory.exists(scope, reference)

    def delete(self, scope: SecretScope, reference: str) -> bool:
        if self.deny_delete:
            raise SecretAccessDenied("raw-access-token")
        if self.fail_delete:
            raise RuntimeError("raw-api-secret raw-access-token raw-request-token")
        return self.memory.delete(scope, reference)


class ProviderFixture:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.subject = "AB1234"
        self.profile_subject = "AB1234"
        self.failure: int | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.failure:
            return httpx.Response(self.failure, json={"message": "raw-access-token"})
        if request.url.path == "/session/token":
            assert request.method == "POST" and not request.url.query
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "broker": "ZERODHA",
                        "user_id": self.subject,
                        "api_key": "appkey",
                        "access_token": "raw-access-token",
                    },
                },
            )
        assert request.method == "GET" and request.url.path == "/user/profile"
        assert request.headers["Authorization"] == "token appkey:raw-access-token"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"broker": "ZERODHA", "user_id": self.profile_subject},
            },
        )


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch, pytestconfig: pytest.Config) -> Iterator[None]:
    url = pytestconfig.getoption("--broker-postgres-url")
    if not url:
        yield
        return
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql"
    schema = "bw22_test_" + uuid4().hex
    admin = create_database_engine(Settings(database_url=url))
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = parsed.update_query_dict({"options": f"-csearch_path={schema}"})
    monkeypatch.setenv("TWF_DATABASE_URL", isolated.render_as_string(hide_password=False))
    try:
        yield
    finally:
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


@pytest.fixture
def browser(database: None) -> Iterator[TestClient]:
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    settings = Settings(
        environment="test",
        cors_origins=(ORIGIN,),
        zerodha_auth_enabled=True,
        zerodha_web_origin=ORIGIN,
        zerodha_callback_url=ORIGIN + "/api/v1/broker-auth/callback",
    )
    engine = create_database_engine(settings)
    with create_session_factory(engine)() as session:
        create_user(session, "alice", "Alice", PASSWORD)
        create_user(session, "bob", "Bob", PASSWORD)
        session.commit()
    fixture = ProviderFixture()
    app = create_app(
        settings,
        engine_factory=lambda _: engine,
        secret_store=TestVault(),
        broker_auth_provider=KiteAuthClient(httpx.MockTransport(fixture)),
    )
    app.state.provider_fixture = fixture
    with TestClient(app) as client:
        login(client)
        yield client
    engine.dispose()


def login(browser: TestClient, username: str = "alice") -> None:
    assert (
        browser.post(
            "/api/v1/auth/login", headers=HEADERS, json={"username": username, "password": PASSWORD}
        ).status_code
        == 200
    )


def account(browser: TestClient, label: str = "Zerodha") -> str:
    response = browser.post(
        "/api/v1/broker-accounts", headers=HEADERS, json={"provider_id": "zerodha", "label": label}
    )
    assert response.status_code == 201, response.text
    return str(response.json()["broker_account_id"])


def configure(browser: TestClient, account_id: str, revision: int = 1, generation: int = 0) -> None:
    response = browser.post(
        f"/api/v1/broker-auth/accounts/{account_id}/configure",
        headers=HEADERS,
        json={
            "api_key": "appkey",
            "api_secret": "raw-api-secret",
            "expected_revision": revision,
            "expected_generation": generation,
        },
    )
    assert response.status_code == 200, response.text
    assert "raw-api-secret" not in response.text


def initiate(browser: TestClient, account_id: str) -> str:
    response = browser.post(f"/api/v1/broker-auth/accounts/{account_id}/connect", headers=HEADERS)
    assert response.status_code == 200, response.text
    parsed = urlsplit(str(response.json()["login_url"]))
    assert parsed.scheme == "https" and parsed.netloc == "kite.zerodha.com"
    return parse_qs(parse_qs(parsed.query)["redirect_params"][0])["state"][0]


def receive(browser: TestClient, state: str) -> None:
    response = browser.get(
        "/api/v1/broker-auth/callback",
        params={"state": state, "request_token": "raw-request-token"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == ORIGIN + "/broker-auth/complete"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "raw-request-token" not in response.text + str(response.headers)


def bind(browser: TestClient, account_id: str) -> None:
    receive(browser, initiate(browser, account_id))
    response = browser.post("/api/v1/broker-auth/finalize", headers=HEADERS)
    assert response.status_code == 200, response.text


def test_full_flow_only_verifies_profile(browser: TestClient) -> None:
    aid = account(browser)
    configure(browser, aid)
    bind(browser, aid)
    view = browser.get("/api/v1/broker-auth/accounts").json()[0]
    assert view["account"]["authentication_state"] == "CONNECTED"
    assert view["account"]["provider_account_id"] == "AB1234"
    assert view["account"]["connection_generation"] == 1
    assert view["account"]["read_health"] == "UNKNOWN"
    assert view["account"]["trading_enabled"] is False
    assert view["bound_at"] and view["last_auth_success_at"]
    fixture = cast(FastAPI, browser.app).state.provider_fixture
    assert [r.url.path for r in fixture.requests] == ["/session/token", "/user/profile"]


def test_callback_requires_clean_same_session_finalization(browser: TestClient) -> None:
    aid = account(browser)
    configure(browser, aid)
    state = initiate(browser, aid)
    original = browser.cookies.get("twf_session")
    assert original is not None
    browser.cookies.delete("twf_session")
    receive(browser, state)
    nonce = browser.cookies.get("twf_broker_finalize")
    assert nonce is not None
    assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code == 401
    browser.cookies.set("twf_broker_finalize", nonce, domain="testserver.local", path="/")
    browser.cookies.set("twf_session", original, domain="testserver.local", path="/")
    assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code == 200
    assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code != 200


def test_callback_replay_does_not_exchange_twice(browser: TestClient) -> None:
    aid = account(browser)
    configure(browser, aid)
    state = initiate(browser, aid)
    receive(browser, state)
    nonce = browser.cookies.get("twf_broker_finalize")
    assert nonce is not None
    receive(browser, state)
    assert len(cast(FastAPI, browser.app).state.provider_fixture.requests) == 1
    browser.cookies.set("twf_broker_finalize", nonce, domain="testserver.local", path="/")
    assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code == 200


@pytest.mark.parametrize("action", ["configure", "connect", "disconnect", "cleanup"])
def test_origin_required(browser: TestClient, action: str) -> None:
    aid = account(browser)
    response = browser.post(f"/api/v1/broker-auth/accounts/{aid}/{action}", json={})
    assert response.status_code == 403


def test_finalization_origin_required(browser: TestClient) -> None:
    assert browser.post("/api/v1/broker-auth/finalize").status_code == 403


def test_wrong_owner_and_new_session_rejected(browser: TestClient) -> None:
    aid = account(browser)
    configure(browser, aid)
    receive(browser, initiate(browser, aid))
    nonce = browser.cookies.get("twf_broker_finalize")
    assert nonce is not None
    login(browser, "bob")
    assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code == 404
    assert (
        browser.post(f"/api/v1/broker-auth/accounts/{aid}/connect", headers=HEADERS).status_code
        == 404
    )
    login(browser)
    browser.cookies.set("twf_broker_finalize", nonce, domain="testserver.local", path="/")
    assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code != 200


@pytest.mark.parametrize("change", ["configure", "disconnect", "disable"])
def test_stale_callback_cannot_bind(browser: TestClient, change: str) -> None:
    aid = account(browser)
    configure(browser, aid)
    state = initiate(browser, aid)
    if change == "configure":
        configure(browser, aid, 2)
    elif change == "disconnect":
        assert (
            browser.post(
                f"/api/v1/broker-auth/accounts/{aid}/disconnect",
                headers=HEADERS,
                json={"expected_generation": 0},
            ).status_code
            == 200
        )
    else:
        assert (
            browser.patch(
                f"/api/v1/broker-accounts/{aid}/configuration",
                headers=HEADERS,
                json={"label": "Zerodha", "expected_revision": 2, "enabled": False},
            ).status_code
            == 200
        )
    receive(browser, state)
    assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code != 200
    assert not cast(FastAPI, browser.app).state.provider_fixture.requests


@pytest.mark.parametrize("status", [403, 429, 500, 302])
def test_provider_failure_sanitized(browser: TestClient, status: int) -> None:
    aid = account(browser)
    configure(browser, aid)
    cast(FastAPI, browser.app).state.provider_fixture.failure = status
    receive(browser, initiate(browser, aid))
    data = browser.get("/api/v1/broker-auth/accounts").json()
    assert data[0]["account"]["authentication_state"] == (
        "REAUTH_REQUIRED" if status == 403 else "ERROR"
    )
    assert "raw-access-token" not in str(data)
    assert data[0]["account"]["connection_generation"] == 0


def test_profile_mismatch_and_duplicate_binding(browser: TestClient) -> None:
    aid = account(browser)
    configure(browser, aid)
    fixture = cast(FastAPI, browser.app).state.provider_fixture
    fixture.profile_subject = "DIFFERENT"
    receive(browser, initiate(browser, aid))
    assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code == 409
    fixture.profile_subject = "AB1234"
    bind(browser, aid)
    second = account(browser, "Second")
    configure(browser, second)
    receive(browser, initiate(browser, second))
    assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code == 409


def test_rebinding_to_different_identity_rejected(browser: TestClient) -> None:
    aid = account(browser)
    configure(browser, aid)
    bind(browser, aid)
    assert (
        browser.post(
            f"/api/v1/broker-auth/accounts/{aid}/disconnect",
            headers=HEADERS,
            json={"expected_generation": 1},
        ).status_code
        == 200
    )
    fixture = cast(FastAPI, browser.app).state.provider_fixture
    fixture.subject = fixture.profile_subject = "DIFFERENT"
    receive(browser, initiate(browser, aid))
    assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code == 409


@pytest.mark.parametrize("denied", [False, True])
def test_cleanup_retry_and_stale_secret_resolution(
    browser: TestClient, caplog: pytest.LogCaptureFixture, denied: bool
) -> None:
    aid = account(browser)
    configure(browser, aid)
    bind(browser, aid)
    app = cast(FastAPI, browser.app)
    vault = cast(TestVault, app.state.secret_store)
    with app.state.session_factory() as session:
        row = session.get(BrokerAccountRecord, UUID(aid))
        owner = row.owner_user_id
        use = BrokerAuth(session, owner, PersonalBrokerPermissionPolicy(), vault, "test").setup(
            app.state.settings, app.state.broker_auth_provider
        )
        lease = use._lease(UUID(aid), BrokerPermission.CONNECT)
        assert lease.active_ref is not None
        assert use.resolve(lease, lease.active_ref, "access").reveal() == "raw-access-token"
    vault.fail_delete = True
    vault.deny_delete = denied
    assert (
        browser.post(
            f"/api/v1/broker-auth/accounts/{aid}/disconnect",
            headers=HEADERS,
            json={"expected_generation": 1},
        ).status_code
        == 200
    )
    assert browser.get("/api/v1/broker-auth/accounts").json()[0]["cleanup_pending"] > 0
    with app.state.session_factory() as session:
        use = BrokerAuth(session, owner, PersonalBrokerPermissionPolicy(), vault, "test").setup(
            app.state.settings, app.state.broker_auth_provider
        )
        with pytest.raises(BrokerFoundationFailure):
            use.resolve(lease, lease.active_ref, "access")
        audits = list(session.scalars(select(BrokerAuditEvent)))
        assert "raw-access-token" not in repr([a.event_type for a in audits])
    assert "raw-access-token" not in caplog.text
    vault.fail_delete = False
    vault.deny_delete = False
    result = browser.post(f"/api/v1/broker-auth/accounts/{aid}/cleanup", headers=HEADERS)
    assert result.json()["cleanup_pending"] == 0


@pytest.mark.parametrize(
    "query",
    [
        "state=wrong&request_token=secret",
        "state=x&state=y&request_token=z",
        "return_to=https://evil.example",
        "request_token=<script>",
    ],
)
def test_callback_invalid_input_always_clean_redirect(browser: TestClient, query: str) -> None:
    response = browser.get("/api/v1/broker-auth/callback?" + query, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == ORIGIN + "/broker-auth/complete"
    assert not cast(FastAPI, browser.app).state.provider_fixture.requests


def test_expired_attempt_does_not_exchange(browser: TestClient) -> None:
    aid = account(browser)
    configure(browser, aid)
    state = initiate(browser, aid)
    with cast(FastAPI, browser.app).state.session_factory() as session:
        attempt = session.get(BrokerAuthAttempt, token_digest(state))
        attempt.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    receive(browser, state)
    assert not cast(FastAPI, browser.app).state.provider_fixture.requests


def test_missing_approved_store_gates_real_connect(browser: TestClient) -> None:
    aid = account(browser)
    configure(browser, aid)
    cast(FastAPI, browser.app).state.secret_store = MemorySecretStore()
    assert (
        browser.post(f"/api/v1/broker-auth/accounts/{aid}/connect", headers=HEADERS).status_code
        == 503
    )
    assert not cast(FastAPI, browser.app).state.provider_fixture.requests


def test_adapter_bounds_and_fixed_destinations() -> None:
    for payload in ({"status": "success", "data": {"access_token": "secret"}}, "x" * 70000):

        def handler(request: httpx.Request, fixture_payload: object = payload) -> httpx.Response:
            assert request.url.host == "api.kite.trade" and request.url.path == "/session/token"
            return httpx.Response(200, json=fixture_payload)

        client = KiteAuthClient(httpx.MockTransport(handler))
        with pytest.raises(ProviderAuthFailure):
            client.exchange("appkey", SecretValue("secret"), SecretValue("oneuse"))


@pytest.mark.parametrize("phase", ["exchange", "profile"])
def test_disconnect_during_provider_io_fences_result(browser: TestClient, phase: str) -> None:
    from twf.brokers.zerodha_auth import AuthGrant

    aid = account(browser)
    configure(browser, aid)
    app = cast(FastAPI, browser.app)
    delegate = app.state.broker_auth_provider
    with app.state.session_factory() as session:
        owner = session.get(BrokerAccountRecord, UUID(aid)).owner_user_id

    def invalidate() -> None:
        with app.state.session_factory() as session:
            use = BrokerAuth(
                session, owner, PersonalBrokerPermissionPolicy(), app.state.secret_store, "test"
            ).setup(app.state.settings, delegate)
            use.disconnect(UUID(aid), 0)

    class Interleaved:
        def exchange(
            self, api_key: str, secret: SecretValue, request_token: SecretValue
        ) -> AuthGrant:
            grant = cast(AuthGrant, delegate.exchange(api_key, secret, request_token))
            if phase == "exchange":
                invalidate()
            return grant

        def profile(self, api_key: str, token: SecretValue) -> str:
            subject = str(delegate.profile(api_key, token))
            if phase == "profile":
                invalidate()
            return subject

    app.state.broker_auth_provider = Interleaved()
    receive(browser, initiate(browser, aid))
    assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code != 200
    row = browser.get("/api/v1/broker-auth/accounts").json()[0]["account"]
    assert row["connection_generation"] == 1
    assert row["authentication_state"] == "DISCONNECTED"
    assert row["provider_account_id"] is None


@pytest.mark.parametrize(
    "permission,action",
    [
        (BrokerPermission.CONFIGURE, "configure"),
        (BrokerPermission.CONNECT, "connect"),
        (BrokerPermission.DISCONNECT, "disconnect"),
    ],
)
def test_operation_permissions_cannot_be_inferred(
    browser: TestClient, permission: BrokerPermission, action: str
) -> None:
    aid = account(browser)
    configure(browser, aid)

    class DenyOne(PersonalBrokerPermissionPolicy):
        def allows(
            self, actor_user_id: UUID, operation: BrokerPermission, owner_user_id: UUID
        ) -> bool:
            return operation != permission and super().allows(
                actor_user_id, operation, owner_user_id
            )

    cast(FastAPI, browser.app).state.broker_permission_policy = DenyOne()
    body = (
        {"expected_generation": 0}
        if action == "disconnect"
        else {
            "expected_revision": 2,
            "expected_generation": 0,
            "api_key": "appkey",
            "api_secret": "raw-api-secret",
        }
        if action == "configure"
        else {}
    )
    assert (
        browser.post(
            f"/api/v1/broker-auth/accounts/{aid}/{action}", headers=HEADERS, json=body
        ).status_code
        == 403
    )


def test_vault_read_outage_cannot_prevent_disconnect(
    browser: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    aid = account(browser)
    configure(browser, aid)
    bind(browser, aid)
    vault = cast(TestVault, cast(FastAPI, browser.app).state.secret_store)

    def unavailable(scope: SecretScope, reference: str) -> SecretValue:
        raise RuntimeError("raw-access-token")

    monkeypatch.setattr(vault, "get", unavailable)
    vault.fail_delete = True
    result = browser.post(
        f"/api/v1/broker-auth/accounts/{aid}/disconnect",
        headers=HEADERS,
        json={"expected_generation": 1},
    )
    assert result.status_code == 200
    row = browser.get("/api/v1/broker-auth/accounts").json()[0]
    assert row["account"]["authentication_state"] == "DISCONNECTED"
    assert row["account"]["configured"] is False
    assert row["cleanup_pending"] > 0


def test_pending_expiry_cleanup_survives_new_service_instance(browser: TestClient) -> None:
    aid = account(browser)
    configure(browser, aid)
    state = initiate(browser, aid)
    receive(browser, state)
    app = cast(FastAPI, browser.app)
    with app.state.session_factory() as session:
        attempt = session.get(BrokerAuthAttempt, token_digest(state))
        attempt.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        ref = attempt.pending_reference
        session.commit()
    assert (
        browser.post(f"/api/v1/broker-auth/accounts/{aid}/cleanup", headers=HEADERS).status_code
        == 200
    )
    with app.state.session_factory() as session:
        assert session.get(BrokerSecretLifecycle, ref).state == "DELETED"
    assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code != 200


def test_expired_access_token_requires_reauthentication(browser: TestClient) -> None:
    from twf.infrastructure.broker_foundation import BrokerConnectionRecord

    aid = account(browser)
    configure(browser, aid)
    bind(browser, aid)
    app = cast(FastAPI, browser.app)
    with app.state.session_factory() as session:
        connection = session.get(BrokerConnectionRecord, UUID(aid))
        connection.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    assert (
        browser.get("/api/v1/broker-auth/accounts").json()[0]["account"]["authentication_state"]
        == "REAUTH_REQUIRED"
    )
    state = initiate(browser, aid)
    receive(browser, state)
    assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code == 200


@pytest.mark.parametrize("iteration", range(8))
@pytest.mark.parametrize("phase", ["callback", "finalize"])
def test_two_workers_cannot_consume_same_attempt(
    browser: TestClient, phase: str, iteration: int
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, local

    from sqlalchemy import event
    from sqlalchemy.engine import Connection, ExecutionContext

    aid = account(browser)
    configure(browser, aid)
    state = initiate(browser, aid)
    if phase == "finalize":
        receive(browser, state)
    app = cast(FastAPI, browser.app)
    nonce = browser.cookies.get("twf_broker_finalize") or ""
    session_hash = token_digest(browser.cookies.get("twf_session") or "")
    with app.state.session_factory() as session:
        owner = session.get(BrokerAccountRecord, UUID(aid)).owner_user_id
    barrier = Barrier(2)
    thread = local()

    def synchronize(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: ExecutionContext,
        executemany: bool,
    ) -> None:
        if statement.startswith("UPDATE broker_accounts SET updated_at=") and not getattr(
            thread, "reached", False
        ):
            thread.reached = True
            barrier.wait(timeout=15)

    event.listen(app.state.database_engine, "before_cursor_execute", synchronize)

    def run(_: int) -> int:
        with app.state.session_factory() as session:
            use = BrokerAuth(
                session, owner, PersonalBrokerPermissionPolicy(), app.state.secret_store, "test"
            ).setup(app.state.settings, app.state.broker_auth_provider)
            try:
                if phase == "callback":
                    use.receive(state, SecretValue("raw-request-token"))
                else:
                    use.finalize(nonce, session_hash)
                return 200
            except BrokerFoundationFailure as error:
                return error.status

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = sorted(pool.map(run, (0, 1)))
    finally:
        event.remove(app.state.database_engine, "before_cursor_execute", synchronize)
    assert outcomes == [200, 409]
    fixture = cast(ProviderFixture, app.state.provider_fixture)
    assert len([r for r in fixture.requests if r.url.path == "/session/token"]) == 1
    if phase == "finalize":
        assert len([r for r in fixture.requests if r.url.path == "/user/profile"]) == 1


def test_actual_logging_and_durable_records_exclude_raw_secrets(browser: TestClient) -> None:
    import logging
    from io import StringIO

    from twf.infrastructure.broker_auth import BrokerAuthConfiguration
    from twf.observability import JsonFormatter

    app = cast(FastAPI, browser.app)
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonFormatter(app.state.settings))
    app.state.logger.addHandler(handler)
    try:
        aid = account(browser)
        configure(browser, aid)
        bind(browser, aid)
        cast(TestVault, app.state.secret_store).fail_delete = True
        response = browser.post(
            f"/api/v1/broker-auth/accounts/{aid}/disconnect",
            headers=HEADERS,
            json={"expected_generation": 1},
        )
        assert response.status_code == 200
        assert "broker_secret_cleanup_failed" in output.getvalue()
        assert "request_completed" in output.getvalue()
        with app.state.session_factory() as session:
            values: list[list[object]] = []
            for model in (
                BrokerAccountRecord,
                BrokerAuditEvent,
                BrokerAuthAttempt,
                BrokerAuthConfiguration,
                BrokerSecretLifecycle,
            ):
                values.extend(
                    [getattr(row, column.name) for column in model.__table__.columns]
                    for row in session.scalars(select(model))
                )
            rendered = repr(values)
        for secret in ("raw-api-secret", "raw-request-token", "raw-access-token"):
            assert secret not in output.getvalue() + rendered + response.text
    finally:
        app.state.logger.removeHandler(handler)


class SlowAuthStream(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.closed = False
        self.chunks = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for _ in range(1000):
            await asyncio.sleep(0.005)
            self.chunks += 1
            yield b" "

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize("phase", ["exchange", "profile"])
def test_total_deadline_cancels_slow_chunks(phase: str) -> None:
    stream = SlowAuthStream()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.extensions["timeout"] == dict.fromkeys(
            ("connect", "read", "write", "pool"), 5.0
        )
        return httpx.Response(200, stream=stream)

    client = KiteAuthClient(httpx.MockTransport(handler))
    client.TOTAL_DEADLINE_SECONDS = 0.05
    started = monotonic()
    with pytest.raises(ProviderAuthTimeout, match="^PROVIDER_TIMEOUT$"):
        if phase == "exchange":
            client.exchange("appkey", SecretValue("secret"), SecretValue("oneuse"))
        else:
            client.profile("appkey", SecretValue("token"))
    assert monotonic() - started < 1.0
    assert 0 < stream.chunks < 1000
    assert stream.closed


@pytest.mark.parametrize("stage", ["headers", "json"])
def test_total_deadline_covers_header_wait_and_parsing(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    import json

    from twf.brokers import zerodha_auth

    async def handler(request: httpx.Request) -> httpx.Response:
        if stage == "headers":
            await asyncio.sleep(10)
        return httpx.Response(
            200, content=b'{"status":"success","data":{"user_id":"A1","broker":"ZERODHA"}}'
        )

    client = KiteAuthClient(httpx.MockTransport(handler))
    client.TOTAL_DEADLINE_SECONDS = 0.05
    if stage == "json":
        clock = [0.0]
        monkeypatch.setattr(zerodha_auth, "monotonic", lambda: clock[0])
        original = json.loads

        def late_parse(body: bytes | bytearray) -> object:
            parsed = original(body)
            clock[0] = 1.0
            return parsed

        monkeypatch.setattr(json, "loads", late_parse)
    started = monotonic()
    with pytest.raises(ProviderAuthTimeout):
        client.profile("appkey", SecretValue("token"))
    assert monotonic() - started < 1.0


def test_total_deadline_does_not_wait_for_cancelled_resolver_worker() -> None:
    from threading import Event

    entered, release, finished = Event(), Event(), Event()

    def blocked_resolver() -> None:
        entered.set()
        release.wait(timeout=2)
        finished.set()

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.get_running_loop().run_in_executor(None, blocked_resolver)
        pytest.fail("Cancelled resolution must not continue the provider request")

    client = KiteAuthClient(httpx.MockTransport(handler))
    client.TOTAL_DEADLINE_SECONDS = 0.05
    started = monotonic()
    try:
        with pytest.raises(ProviderAuthTimeout):
            client.profile("appkey", SecretValue("token"))
        assert monotonic() - started < 1.0
        assert entered.is_set()
        assert not finished.is_set()
    finally:
        release.set()
        assert finished.wait(timeout=2)


def test_httpx_timeout_is_typed_and_redacted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("raw-access-token raw-api-secret")

    with pytest.raises(ProviderAuthTimeout, match="^PROVIDER_TIMEOUT$"):
        KiteAuthClient(httpx.MockTransport(handler)).profile("appkey", SecretValue("token"))


@pytest.mark.parametrize("phase", ["exchange", "profile"])
def test_total_timeout_leaves_no_partial_binding(browser: TestClient, phase: str) -> None:
    from twf.infrastructure.broker_auth import BrokerAuthConfiguration
    from twf.infrastructure.broker_foundation import BrokerConnectionRecord

    aid = account(browser)
    configure(browser, aid)
    app = cast(FastAPI, browser.app)
    fixture = cast(ProviderFixture, app.state.provider_fixture)
    stream = SlowAuthStream()

    def handler(request: httpx.Request) -> httpx.Response:
        target = "/session/token" if phase == "exchange" else "/user/profile"
        return (
            httpx.Response(200, stream=stream) if request.url.path == target else fixture(request)
        )

    client = KiteAuthClient(httpx.MockTransport(handler))
    client.TOTAL_DEADLINE_SECONDS = 0.05
    app.state.broker_auth_provider = client
    state = initiate(browser, aid)
    receive(browser, state)
    assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code == 409
    with app.state.session_factory() as session:
        row = session.get(BrokerAccountRecord, UUID(aid))
        connection = session.get(BrokerConnectionRecord, UUID(aid))
        config = session.get(BrokerAuthConfiguration, UUID(aid))
        attempt = session.get(BrokerAuthAttempt, token_digest(state))
        assert row.connection_generation == 0 and row.provider_account_id is None
        assert config.bound_at is None and config.last_auth_success_at is None
        assert connection.secret_reference is None and connection.authentication_state == "ERROR"
        assert attempt.status == "REJECTED"
        tokens = list(
            session.scalars(
                select(BrokerSecretLifecycle).where(
                    BrokerSecretLifecycle.purpose.in_(("pending", "access"))
                )
            )
        )
        assert all(token.state in {"REVOKED", "DELETED"} for token in tokens)
        assert not session.scalar(
            select(BrokerAuditEvent.id).where(BrokerAuditEvent.event_type == "ACCOUNT_BOUND")
        )
    assert stream.closed


@pytest.mark.parametrize("phase", ["callback", "finalize"])
def test_rejection_audit_contention_preserves_safe_response(
    browser: TestClient, phase: str, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    aid = account(browser)
    configure(browser, aid)
    state = initiate(browser, aid)
    receive(browser, state)
    nonce = browser.cookies.get("twf_broker_finalize")
    assert nonce
    if phase == "finalize":
        assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code == 200
        browser.cookies.set("twf_broker_finalize", nonce, domain="testserver.local", path="/")
    app = cast(FastAPI, browser.app)
    original_logger = app.state.logger
    app.state.logger = logging.getLogger("bw22.contention.test")
    writes = []

    def busy_audit(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: ExecutionContext,
        executemany: bool,
    ) -> None:
        if statement.startswith("INSERT INTO broker_audit_events") and "SELECT" in statement:
            writes.append(statement)
            error = sqlite3.OperationalError("database is locked raw-access-token")
            error.sqlite_errorcode = sqlite3.SQLITE_BUSY
            raise OperationalError(statement, {}, error)

    event.listen(app.state.database_engine, "before_cursor_execute", busy_audit)
    try:
        if phase == "callback":
            receive(browser, state)
        else:
            result = browser.post("/api/v1/broker-auth/finalize", headers=HEADERS)
            assert result.status_code == 409
            assert "locked" not in result.text and "raw-access-token" not in result.text
        assert len(writes) == 1  # No auth replay or unbounded audit retries.
        assert "broker_callback_rejection_audit_contended" in caplog.text
        assert "locked" not in caplog.text and "raw-access-token" not in caplog.text
    finally:
        event.remove(app.state.database_engine, "before_cursor_execute", busy_audit)
        app.state.logger = original_logger
    if phase == "callback":
        browser.cookies.set("twf_broker_finalize", nonce, domain="testserver.local", path="/")
        assert browser.post("/api/v1/broker-auth/finalize", headers=HEADERS).status_code == 200
    assert (
        browser.get("/api/v1/broker-auth/accounts").json()[0]["account"]["connection_generation"]
        == 1
    )


def test_sqlite_busy_claim_is_safe_conflict(browser: TestClient) -> None:
    aid = account(browser)
    configure(browser, aid)
    state = initiate(browser, aid)
    app = cast(FastAPI, browser.app)
    with app.state.session_factory() as session:
        owner = session.get(BrokerAccountRecord, UUID(aid)).owner_user_id

    def busy_claim(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: ExecutionContext,
        executemany: bool,
    ) -> None:
        if statement.startswith("UPDATE broker_accounts SET updated_at="):
            error = sqlite3.OperationalError("database is locked raw-access-token")
            error.sqlite_errorcode = sqlite3.SQLITE_BUSY
            raise OperationalError(statement, {}, error)

    event.listen(app.state.database_engine, "before_cursor_execute", busy_claim)
    try:
        with app.state.session_factory() as session:
            use = BrokerAuth(
                session, owner, PersonalBrokerPermissionPolicy(), app.state.secret_store, "test"
            ).setup(app.state.settings, app.state.broker_auth_provider)
            with pytest.raises(BrokerFoundationFailure) as failure:
                use.receive(state, SecretValue("raw-request-token"))
            assert failure.value.status == 409
    finally:
        event.remove(app.state.database_engine, "before_cursor_execute", busy_claim)
    assert not cast(ProviderFixture, app.state.provider_fixture).requests
