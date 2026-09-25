"""Shared logical outcomes; transport causes remain adapter-specific."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from twf.api.services import service_principal
from twf.config.settings import Settings
from twf.integrations.adapters import (
    LocalAdapter,
    RemoteAdapter,
    SyntheticAdapter,
    SyntheticLLMService,
    SyntheticScannerService,
    SyntheticScenario,
    SyntheticTIService,
    SyntheticTMService,
)
from twf.integrations.config import ServiceDescriptor
from twf.integrations.contracts import (
    DeploymentMode,
    ErrorCode,
    Health,
    HealthResult,
    RequestContext,
    ServiceClient,
    ServiceFailure,
)
from twf.integrations.registry import ServiceRegistry
from twf.main import create_app

REFERENCE = datetime(2026, 9, 25, 12, tzinfo=UTC)
IDENTITY = SyntheticTIService().identity
ORIGIN = "https://fixture.test"
OUTCOMES = [
    (SyntheticScenario.AVAILABLE, Health.AVAILABLE, None, REFERENCE),
    (SyntheticScenario.DEGRADED, Health.DEGRADED, None, REFERENCE),
    (SyntheticScenario.UNAVAILABLE, Health.UNAVAILABLE, ErrorCode.SERVICE_UNAVAILABLE, None),
    (SyntheticScenario.TIMEOUT, Health.UNAVAILABLE, ErrorCode.TIMEOUT, None),
    (SyntheticScenario.DENIED, Health.UNAVAILABLE, ErrorCode.AUTHORIZATION_FAILED, None),
    (SyntheticScenario.INCOMPATIBLE, Health.UNAVAILABLE, ErrorCode.CONTRACT_MISMATCH, None),
    (SyntheticScenario.STALE, Health.AVAILABLE, None, REFERENCE - timedelta(minutes=10)),
    (SyntheticScenario.EMPTY, Health.UNKNOWN, None, REFERENCE),
]


@pytest.mark.parametrize("mode", list(DeploymentMode))
@pytest.mark.parametrize("scenario,health,error,as_of", OUTCOMES)
def test_shared_logical_outcome(
    mode: DeploymentMode,
    scenario: SyntheticScenario,
    health: Health,
    error: ErrorCode | None,
    as_of: datetime | None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="matrix")
    context = RequestContext(request_id=f"matrix-{mode.value}-{scenario.value}")

    async def local(request: RequestContext) -> HealthResult:
        # A local operation can report a logical failure, without simulating HTTP.
        assert request == context
        if error:
            raise ServiceFailure(error)
        assert as_of is not None
        return HealthResult(
            identity=IDENTITY,
            request_id=request.request_id,
            health=health,
            as_of=as_of,
            synthetic=True,
        )

    def remote(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Request-ID"] == context.request_id
        if scenario == SyntheticScenario.TIMEOUT:
            raise httpx.ReadTimeout("controlled timeout", request=request)
        if scenario == SyntheticScenario.DENIED:
            return httpx.Response(403)
        if scenario == SyntheticScenario.UNAVAILABLE:
            return httpx.Response(503)
        if scenario == SyntheticScenario.INCOMPATIBLE:
            return httpx.Response(200, json={"identity": {"contract_version": "future.v2"}})
        assert as_of is not None
        return httpx.Response(
            200,
            json=HealthResult(
                identity=IDENTITY,
                request_id=context.request_id,
                health=health,
                as_of=as_of,
                synthetic=True,
            ).model_dump(mode="json"),
        )

    descriptor = ServiceDescriptor(
        identity=IDENTITY,
        mode=mode,
        enabled=True,
        endpoint=ORIGIN if mode == DeploymentMode.REMOTE else None,
    )
    client: ServiceClient
    if mode == DeploymentMode.LOCAL:
        client = LocalAdapter(IDENTITY, local)
    elif mode == DeploymentMode.REMOTE:
        client = RemoteAdapter(
            descriptor, allowed_origins=(ORIGIN,), transport=httpx.MockTransport(remote)
        )
    else:
        client = SyntheticAdapter(IDENTITY, scenario=scenario, reference_time=REFERENCE)
    if error:
        with pytest.raises(ServiceFailure) as failure:
            asyncio.run(client.health(context))
        assert failure.value.code == error
        assert str(failure.value) == error.value
    registry = ServiceRegistry((descriptor,), allowed_origins=(ORIGIN,), clients=(client,))
    result = asyncio.run(registry.statuses(uuid4(), context, logging.getLogger("matrix")))[0]
    operation = next(record for record in caplog.records if record.msg == "service_operation")
    assert operation.__dict__["operation_request_id"] == context.request_id
    assert operation.__dict__["outcome"] == (error.value if error else health.value)
    assert result.identity == IDENTITY
    assert result.mode == mode
    assert result.configured and result.enabled and result.active
    assert result.health == health
    assert result.error == error
    if error:
        assert result.observation is None
    else:
        assert as_of is not None
        assert result.observation == HealthResult(
            identity=IDENTITY,
            request_id=context.request_id,
            health=health,
            as_of=as_of,
            synthetic=True,
        )


@pytest.mark.parametrize(
    "factory",
    [SyntheticScannerService, SyntheticTIService, SyntheticTMService, SyntheticLLMService],
)
@pytest.mark.parametrize("scenario,health,error,as_of", OUTCOMES)
def test_all_families_are_deterministic(
    factory: type[SyntheticScannerService]
    | type[SyntheticTIService]
    | type[SyntheticTMService]
    | type[SyntheticLLMService],
    scenario: SyntheticScenario,
    health: Health,
    error: ErrorCode | None,
    as_of: datetime | None,
) -> None:
    client = factory(scenario=scenario, reference_time=REFERENCE)
    for request_id in ("first-call", "second-call"):
        context = RequestContext(request_id=request_id)
        if error:
            with pytest.raises(ServiceFailure) as failure:
                asyncio.run(client.health(context))
            assert failure.value.code == error
        else:
            result = asyncio.run(client.health(context))
            assert result.identity == client.identity
            assert result.request_id == request_id
            assert result.health == health
            assert result.as_of == as_of
            assert result.synthetic is True


def test_synthetic_reference_time_requires_timezone() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SyntheticTIService(reference_time=datetime(2026, 9, 25))
    client = SyntheticTIService(
        reference_time=REFERENCE.astimezone(timezone(timedelta(hours=5, minutes=30)))
    )
    assert asyncio.run(client.health(RequestContext())).as_of == REFERENCE


def test_synthetic_failures_leave_siblings_and_application_ready() -> None:
    clients = tuple(
        SyntheticAdapter(
            IDENTITY.model_copy(update={"service_id": f"fixture-{scenario.value.lower()}"}),
            scenario=scenario,
            reference_time=REFERENCE,
        )
        for scenario in SyntheticScenario
    )
    descriptors = tuple(
        ServiceDescriptor(identity=client.identity, mode=DeploymentMode.SYNTHETIC, enabled=True)
        for client in clients
    )
    app = create_app(
        Settings(database_url="sqlite+pysqlite:///:memory:"),
        service_registry=ServiceRegistry(descriptors, clients=clients),
    )
    app.dependency_overrides[service_principal] = uuid4
    with TestClient(app) as browser:
        assert browser.get("/ready").status_code == 200
        response = browser.get("/api/v1/services", headers={"X-Request-ID": "isolated-scenarios"})
        assert response.status_code == 200
        results = response.json()["services"]
        assert len(results) == 8
        assert {item["error"] for item in results if item["error"]} == {
            "SERVICE_UNAVAILABLE",
            "TIMEOUT",
            "AUTHORIZATION_FAILED",
            "CONTRACT_MISMATCH",
        }
        observations = [item["observation"] for item in results if item["observation"]]
        assert len(observations) == 4
        assert all(item["request_id"] == "isolated-scenarios" for item in observations)
        assert browser.get("/ready").status_code == 200
