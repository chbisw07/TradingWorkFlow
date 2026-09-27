"""Native catalog regression fixtures; never contacts a broker."""

import asyncio
import gzip
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from time import monotonic
from typing import cast
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.engine import Connection, ExecutionContext
from sqlalchemy.exc import OperationalError
from test_broker_auth import HEADERS, account, bind, configure, login
from test_broker_auth import browser as browser
from test_broker_auth import database as database

from twf.broker_auth import BrokerAuth
from twf.brokers.catalog_contracts import (
    CatalogFailure,
    CatalogPayload,
    FailureCode,
)
from twf.brokers.foundation_contracts import BrokerPermission, PersonalBrokerPermissionPolicy
from twf.brokers.zerodha_catalog import KiteCatalogClient
from twf.catalog import BrokerCatalog
from twf.infrastructure.broker_foundation import BrokerAccountRecord, BrokerAuditEvent
from twf.infrastructure.catalog import CatalogInstrument, CatalogPointer, CatalogSnapshot
from twf.secrets import SecretValue

HEADER = (
    "instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,"
    "strike,tick_size,lot_size,instrument_type,segment,exchange\n"
)
ROWS = [
    "1,11,HAL,HINDUSTAN AERONAUTICS,0,,,0.05,1,EQ,NSE,NSE\n",
    "2,12,HAL26OCTFUT,HAL,0,2026-10-29,,0.05,150,FUT,NFO-FUT,NFO\n",
    "3,13,HAL26OCT4500CE,HAL,0,2026-10-29,4500,0.05,150,CE,NFO-OPT,NFO\n",
    "4,14,HAL26OCT4500PE,HAL,0,2026-10-29,4500,0.05,150,PE,NFO-OPT,NFO\n",
]
CSV = (HEADER + "".join(ROWS)).encode()


class Bytes(httpx.AsyncByteStream):
    def __init__(self, body: bytes, delay: float = 0) -> None:
        self.body, self.delay, self.closed = body, delay, False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for offset in range(0, len(self.body), 16):
            if self.delay:
                await asyncio.sleep(self.delay)
            yield self.body[offset : offset + 16]

    async def aclose(self) -> None:
        self.closed = True


class CatalogFixture:
    def __init__(self) -> None:
        self.body = CSV
        self.failure: FailureCode | None = None
        self.calls = 0

    def fetch(self, api_key: str, token: SecretValue) -> CatalogPayload:
        assert api_key == "appkey" and token.reveal() == "raw-access-token"
        self.calls += 1
        if self.failure:
            raise CatalogFailure(self.failure)
        return KiteCatalogClient().parse(self.body, monotonic() + 30)


@pytest.fixture
def catalog(browser: TestClient) -> Iterator[tuple[TestClient, str, CatalogFixture]]:
    aid = account(browser)
    configure(browser, aid)
    bind(browser, aid)
    provider = CatalogFixture()
    cast(FastAPI, browser.app).state.catalog_provider = provider
    yield browser, aid, provider


def path(aid: str, action: str = "instruments") -> str:
    return f"/api/v1/broker-catalog/accounts/{aid}/{action}"


def refresh(client: TestClient, aid: str) -> dict[str, object]:
    response = client.post(path(aid, "refresh"), headers=HEADERS)
    assert response.status_code == 200, response.text
    return cast(dict[str, object], response.json())


def test_csv_native_equity_and_derivative_identity() -> None:
    payload = KiteCatalogClient().parse(CSV, monotonic() + 30)
    assert len(payload.instruments) == payload.total_rows == 4
    assert {row.derivative_kind for row in payload.instruments} == {None, "CE", "PE", "FUT"}
    assert all(
        row.canonical_id is None and len(row.fingerprint) == 64 for row in payload.instruments
    )
    assert {row.exchange for row in payload.instruments} == {"NSE", "NFO"}
    assert {row.native_id for row in payload.instruments} == {"1", "2", "3", "4"}


@pytest.mark.parametrize(
    "body,code",
    [
        (HEADER.encode(), "EMPTY"),
        (b"wrong,headers\n1,2\n", "INVALID_RESPONSE"),
        ((HEADER + ROWS[0] + ROWS[0]).encode(), "PARTIAL_RESPONSE"),
        (CSV.replace(b"0.05", b"NaN", 1), "PARTIAL_RESPONSE"),
        (CSV.replace(b",150,CE", b",0,CE"), "PARTIAL_RESPONSE"),
        (CSV.replace(b",4500,", b",oops,", 1), "PARTIAL_RESPONSE"),
        (CSV.replace(b"2026-10-29", b"invalid", 1), "PARTIAL_RESPONSE"),
        ((HEADER + '"unterminated').encode(), "INVALID_RESPONSE"),
    ],
)
def test_invalid_catalog_never_publishes(body: bytes, code: str) -> None:
    with pytest.raises(CatalogFailure) as failure:
        KiteCatalogClient().parse(body, monotonic() + 30)
    assert failure.value.code == code
    if code == "PARTIAL_RESPONSE":
        assert failure.value.rejected > 0


def test_optional_fields_unknown_type_and_stable_fingerprint() -> None:
    client = KiteCatalogClient()
    value = client.parse(CSV, monotonic() + 30)
    assert (
        client.parse((HEADER + "".join(reversed(ROWS))).encode(), monotonic() + 30).fingerprint
        == value.fingerprint
    )
    optional = client.parse(
        (HEADER + "1,,HAL,,0,,,0.05,1,NEW,NEWSEG,NSE\n").encode(), monotonic() + 30
    ).instruments[0]
    assert (
        optional.name is None and optional.exchange_id is None and optional.derivative_kind is None
    )
    assert optional.instrument_type == "NEW" and optional.segment == "NEWSEG"


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "AUTH_REQUIRED"),
        (403, "AUTH_REQUIRED"),
        (429, "RATE_LIMITED"),
        (500, "UNAVAILABLE"),
        (302, "UNAVAILABLE"),
    ],
)
def test_transport_errors_are_safe(status: int, code: str) -> None:
    with pytest.raises(CatalogFailure) as failure:
        KiteCatalogClient(
            httpx.MockTransport(lambda _: httpx.Response(status, stream=Bytes(b"raw-secret")))
        ).fetch("app", SecretValue("raw-secret"))
    assert failure.value.code == code and "raw-secret" not in str(failure.value)


@pytest.mark.parametrize("compressed", [False, True])
def test_bounded_fetch_and_authorization(compressed: bool) -> None:
    stream = Bytes(gzip.compress(CSV) if compressed else CSV)

    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.kite.trade/instruments"
        assert request.headers["authorization"] == "token app:token"
        assert request.extensions["timeout"] == dict.fromkeys(
            ("connect", "read", "write", "pool"), 5.0
        )
        return httpx.Response(
            200, stream=stream, headers={"content-encoding": "gzip" if compressed else "identity"}
        )

    result = KiteCatalogClient(httpx.MockTransport(respond)).fetch("app", SecretValue("token"))
    assert len(result.instruments) == 4 and stream.closed


@pytest.mark.parametrize("case", ["size", "wire", "rows", "slow", "parse", "gzip"])
def test_resource_bounds(case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    stream = Bytes(
        gzip.compress(CSV)[:-4] if case == "gzip" else CSV, delay=0.02 if case == "slow" else 0
    )
    client = KiteCatalogClient(
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                stream=stream,
                headers={"content-encoding": "gzip" if case == "gzip" else "identity"},
            )
        )
    )
    if case == "size":
        client.MAX_BYTES = 20
    if case == "wire":
        client.MAX_WIRE_BYTES = 20
    if case == "rows":
        client.MAX_ROWS = 2
    if case == "slow":
        client.TOTAL_DEADLINE_SECONDS = 0.05
    if case == "parse":
        original = client.parse

        def late(body: bytes, deadline: float) -> CatalogPayload:
            return original(body, monotonic() - 1)

        monkeypatch.setattr(client, "parse", late)
    started = monotonic()
    with pytest.raises(CatalogFailure) as failure:
        client.fetch("app", SecretValue("token"))
    assert failure.value.code == (
        "TIMEOUT"
        if case in ("slow", "parse")
        else "INVALID_RESPONSE"
        if case == "gzip"
        else "TOO_LARGE"
    )
    assert monotonic() - started < 1 and stream.closed


def test_publication_idempotency_and_token_reuse(
    catalog: tuple[TestClient, str, CatalogFixture],
) -> None:
    client, aid, provider = catalog
    first = refresh(client, aid)
    assert first["freshness"] == "FRESH" and first["completeness"] == "COMPLETE"
    assert refresh(client, aid)["version"] == first["version"]
    provider.body = CSV.replace(b"HAL26OCT4500CE", b"HAL26NOV4500CE").replace(
        b"2026-10-29", b"2026-11-26"
    )
    second = refresh(client, aid)
    assert second["version"] != first["version"] and second["fingerprint"] != first["fingerprint"]
    old = client.get(
        path(aid), params={"version": str(first["version"]), "derivative_kind": "CE"}
    ).json()
    new = client.get(path(aid), params={"derivative_kind": "CE"}).json()
    assert old["instruments"][0]["native_id"] == new["instruments"][0]["native_id"] == "3"
    assert old["instruments"][0]["fingerprint"] != new["instruments"][0]["fingerprint"]
    assert old["instruments"][0]["symbol"] == "HAL26OCT4500CE"


@pytest.mark.parametrize(
    "filters,count",
    [
        ({"text": "HAL"}, 4),
        ({"exchange": "NSE"}, 1),
        ({"segment": "NFO-OPT"}, 2),
        ({"instrument_type": "FUT"}, 1),
        ({"expiry": "2026-10-29"}, 3),
        ({"strike": "4500"}, 2),
        ({"derivative_kind": "CE"}, 1),
        ({"name": "AERONAUTICS"}, 1),
        ({"symbol": "4500PE"}, 1),
        ({"text": "%"}, 0),
        ({"text": "nothing"}, 0),
    ],
)
def test_all_search_filters(
    catalog: tuple[TestClient, str, CatalogFixture], filters: dict[str, str], count: int
) -> None:
    client, aid, _ = catalog
    refresh(client, aid)
    response = client.get(path(aid), params=filters)
    assert response.status_code == 200 and response.json()["matched"] == count
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "failure", ["TIMEOUT", "UNAVAILABLE", "AUTH_REQUIRED", "RATE_LIMITED", "EMPTY"]
)
def test_last_good_survives_provider_failure(
    catalog: tuple[TestClient, str, CatalogFixture], failure: FailureCode
) -> None:
    client, aid, provider = catalog
    first = refresh(client, aid)
    provider.failure = failure
    failed = refresh(client, aid)
    assert (
        failed["version"] == first["version"]
        and failed["freshness"] == "STALE"
        and failed["failure_code"] == failure
    )
    assert client.get(path(aid)).json()["matched"] == 4


def test_partial_response_counts_and_prior_version(
    catalog: tuple[TestClient, str, CatalogFixture],
) -> None:
    client, aid, provider = catalog
    first = refresh(client, aid)
    provider.body = CSV.replace(b"0.05", b"bad", 1)
    failed = refresh(client, aid)
    assert failed["version"] == first["version"]
    assert (
        failed["attempt_total_rows"],
        failed["attempt_accepted_rows"],
        failed["attempt_rejected_rows"],
        failed["attempt_completeness"],
    ) == (4, 3, 1, "PARTIAL")


def test_search_security_and_bounds(catalog: tuple[TestClient, str, CatalogFixture]) -> None:
    client, aid, _ = catalog
    version = refresh(client, aid)["version"]
    for params in (
        {"limit": 101},
        {"offset": 10001},
        {"text": "x" * 129},
        {"strike": "NaN"},
        {"unknown": "secret"},
    ):
        assert client.get(path(aid), params=params).status_code == 422
    result = client.get(path(aid), params={"limit": 1, "offset": 1, "version": str(version)}).json()
    assert len(result["instruments"]) == 1 and result["matched"] == 4
    assert client.post(path(aid, "refresh")).status_code == 403
    login(client, "bob")
    assert client.get(path(aid)).status_code == 404
    assert client.post(path(aid, "refresh"), headers=HEADERS).status_code == 404
    own = account(client, "Bob")
    assert client.get(path(own), params={"version": str(version)}).status_code == 404
    client.cookies.clear()
    assert client.get(path(aid)).status_code == 401


def test_freshness_expiry_and_permission(catalog: tuple[TestClient, str, CatalogFixture]) -> None:
    client, aid, _ = catalog
    refresh(client, aid)
    app = cast(FastAPI, client.app)
    with app.state.session_factory() as session:
        session.get(CatalogPointer, UUID(aid)).verified_at = datetime.now(UTC) - timedelta(hours=25)
        session.commit()
    assert client.get(path(aid)).json()["catalog"]["freshness"] == "STALE"

    class Deny(PersonalBrokerPermissionPolicy):
        def allows(
            self, actor_user_id: UUID, permission: BrokerPermission, owner_user_id: UUID
        ) -> bool:
            return False

    app.state.broker_permission_policy = Deny()
    assert client.get(path(aid)).status_code == 403


def test_unconnected_catalog_is_unavailable(browser: TestClient) -> None:
    aid = account(browser)
    response = browser.get(path(aid)).json()
    assert response["catalog"]["failure_code"] == "AUTH_REQUIRED" and response["instruments"] == []
    assert refresh(browser, aid)["failure_code"] == "AUTH_REQUIRED"


def test_atomic_rollback(catalog: tuple[TestClient, str, CatalogFixture]) -> None:
    client, aid, provider = catalog
    first = refresh(client, aid)
    provider.body = CSV.replace(b"4500", b"4600")
    app = cast(FastAPI, client.app)

    def fail(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: ExecutionContext,
        executemany: bool,
    ) -> None:
        if statement.startswith("INSERT INTO catalog_instruments"):
            raise OperationalError(statement, {}, RuntimeError("private database detail"))

    event.listen(app.state.database_engine, "before_cursor_execute", fail)
    try:
        response = client.post(path(aid, "refresh"), headers=HEADERS)
        assert response.status_code == 200 and "private" not in response.text
        assert response.json()["failure_code"] == "UNAVAILABLE"
    finally:
        event.remove(app.state.database_engine, "before_cursor_execute", fail)
    assert client.get(path(aid)).json()["catalog"]["version"] == first["version"]
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(CatalogSnapshot)) == 1
        assert session.scalar(select(func.count()).select_from(CatalogInstrument)) == 4


def test_concurrent_refresh_and_generation_fence(
    catalog: tuple[TestClient, str, CatalogFixture],
) -> None:
    client, aid, provider = catalog
    first = refresh(client, aid)
    app = cast(FastAPI, client.app)
    entered, release = Event(), Event()

    class Blocking(CatalogFixture):
        def fetch(self, api_key: str, token: SecretValue) -> CatalogPayload:
            entered.set()
            assert release.wait(10)
            return super().fetch(api_key, token)

    app.state.catalog_provider = Blocking()
    with app.state.session_factory() as session:
        owner = session.get(BrokerAccountRecord, UUID(aid)).owner_user_id

    def run() -> object:
        with app.state.session_factory() as session:
            auth = BrokerAuth(
                session, owner, app.state.broker_permission_policy, app.state.secret_store, "test"
            ).setup(app.state.settings, app.state.broker_auth_provider)
            return BrokerCatalog(auth, app.state.catalog_provider).refresh(UUID(aid))

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run)
        assert entered.wait(5)
        try:
            assert client.post(path(aid, "refresh"), headers=HEADERS).status_code == 409
            assert (
                client.post(
                    f"/api/v1/broker-auth/accounts/{aid}/disconnect",
                    headers=HEADERS,
                    json={"expected_generation": 1},
                ).status_code
                == 200
            )
        finally:
            release.set()
        future.result(10)
    result = client.get(path(aid)).json()["catalog"]
    assert result["version"] == first["version"] and result["failure_code"] == "STALE_CONNECTION"
    with app.state.session_factory() as session:
        events = list(session.scalars(select(BrokerAuditEvent.event_type)))
    assert events.count("CATALOG_VERSION_ACTIVATED") == 1 and "CATALOG_REFRESH_FAILED" in events


def test_catalog_publication_grace_is_not_generic_health_ttl() -> None:
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Asia/Kolkata")
    yesterday = datetime(2026, 9, 26, 9, tzinfo=zone)
    assert BrokerCatalog._fresh(yesterday, datetime(2026, 9, 27, 10, 29, tzinfo=zone))
    assert not BrokerCatalog._fresh(yesterday, datetime(2026, 9, 27, 10, 30, tzinfo=zone))
    assert BrokerCatalog._fresh(
        datetime(2026, 9, 27, 8, 31, tzinfo=zone), datetime(2026, 9, 27, 11, tzinfo=zone)
    )


def test_pagination_pins_history_across_refresh_and_token_reuse(
    catalog: tuple[TestClient, str, CatalogFixture],
) -> None:
    client, aid, provider = catalog
    first_version = refresh(client, aid)["version"]
    first = client.get(path(aid), params={"limit": 1}).json()
    assert first["catalog"]["version"] == first_version
    original = client.get(path(aid)).json()["instruments"]
    assert original == sorted(
        original, key=lambda row: (row["exchange"], row["segment"], row["symbol"], row["native_id"])
    )
    provider.body = CSV.replace(b"HAL26OCT4500CE", b"HAL26NOV4500CE").replace(
        b"2026-10-29", b"2026-11-26"
    )
    second_version = refresh(client, aid)["version"]
    assert first_version != second_version
    pages = [first["instruments"][0]]
    for offset in range(1, len(original)):
        response = client.get(
            path(aid), params={"limit": 1, "offset": offset, "version": str(first_version)}
        )
        assert response.status_code == 200
        page = response.json()
        assert page["catalog"]["version"] == first_version
        pages.extend(page["instruments"])
    assert pages == original  # Exact order, identities and no duplicates/missing rows.
    previous = client.get(
        path(aid), params={"limit": 1, "offset": 0, "version": str(first_version)}
    ).json()
    assert previous["instruments"] == first["instruments"]
    assert previous["catalog"]["version"] == first_version
    new = client.get(path(aid), params={"text": "HAL", "derivative_kind": "CE"}).json()
    assert new["catalog"]["version"] == second_version
    old_token = next(row for row in pages if row["native_id"] == "3")
    new_token = new["instruments"][0]
    assert old_token["native_id"] == new_token["native_id"]
    assert old_token["symbol"] == "HAL26OCT4500CE"
    assert new_token["symbol"] == "HAL26NOV4500CE"
    assert old_token["id"] != new_token["id"]
    assert old_token["fingerprint"] != new_token["fingerprint"]


@pytest.mark.parametrize(
    "version,status",
    [(None, 422), ("not-a-version", 422), ("00000000-0000-0000-0000-000000000000", 404)],
)
def test_pagination_rejects_missing_invalid_or_unknown_version(
    catalog: tuple[TestClient, str, CatalogFixture], version: str | None, status: int
) -> None:
    client, aid, _ = catalog
    refresh(client, aid)
    params = {"offset": "1", "limit": "1"}
    if version is not None:
        params["version"] = version
    response = client.get(path(aid), params=params)
    assert response.status_code == status
    body = response.json()
    assert "error" in body and "instruments" not in body
    assert "not-a-version" not in response.text


def test_pagination_version_cannot_cross_account_ownership(
    catalog: tuple[TestClient, str, CatalogFixture],
) -> None:
    client, aid, _ = catalog
    version = refresh(client, aid)["version"]
    params: dict[str, str | int] = {"version": str(version), "offset": 1, "limit": 1}
    other = account(client, "Other owned account")
    assert client.get(path(other), params=params).status_code == 404
    login(client, "bob")
    assert client.get(path(aid), params=params).status_code == 404
    own = account(client, "Bob")
    assert client.get(path(own), params=params).status_code == 404
    client.cookies.clear()
    assert client.get(path(aid), params=params).status_code == 401
