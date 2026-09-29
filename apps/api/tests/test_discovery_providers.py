import asyncio
import socket
from typing import Any

import pytest
from discovery_support import OTHER, FixtureGrants, context, replace, scan_run
from pydantic import ValidationError

from twf.discovery.domain import CandidateInput, DiscoveryEvidence, InstrumentIdentity, SourceMode
from twf.discovery.providers import (
    CandidateIntelligenceProvider,
    CandidateSource,
    DomainErrorCode,
    MarketIntelligenceProvider,
    ProviderAccess,
    ProviderBatch,
    ProviderFailure,
    ScanProvider,
    UniverseProvider,
)
from twf.discovery.synthetic import (
    SyntheticCandidateIntelligenceProvider,
    SyntheticCandidateSource,
    SyntheticMarketIntelligenceProvider,
    SyntheticScanProvider,
    SyntheticUniverseProvider,
    fixture_instruments,
)
from twf.integrations.contracts import DeploymentMode, ErrorCode, Health


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("S2-1 must never connect to a network")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def test_all_five_protocols_have_deterministic_typed_results() -> None:
    async def run() -> None:
        u: UniverseProvider = SyntheticUniverseProvider()
        s: ScanProvider = SyntheticScanProvider()
        m: MarketIntelligenceProvider = SyntheticMarketIntelligenceProvider()
        c: CandidateSource = SyntheticCandidateSource()
        i: CandidateIntelligenceProvider = SyntheticCandidateIntelligenceProvider()
        access, ctx = ProviderAccess(FixtureGrants()), context()
        universe = await access.call(
            u, ctx, "sd.universe", "sd.universe.v1", lambda: u.resolve(ctx)
        )
        assert [x.symbol for x in universe.items] == [
            "SYNTHETIC-HAL",
            "SYNTHETIC-BEL",
            "SYNTHETIC-HINDALCO",
            "SYNTHETIC-KAYNES",
        ]
        assert all(
            x.exchange == "SIM" and x.native.namespace == "twf-fixture" for x in universe.items
        )
        assert await u.resolve(ctx) == universe
        matches = await access.call(
            s, ctx, "sd.scan", "sd.scan.v1", lambda: s.scan(ctx, scan_run(), universe.items)
        )
        assert [x.instrument.symbol for x in matches.items] == [
            "SYNTHETIC-HINDALCO",
            "SYNTHETIC-KAYNES",
        ]
        assert all(x.provenance.producer == s.manifest.identity for x in matches.items)
        inputs = await access.call(
            c, ctx, "sd.candidate-source", "sd.candidate-source.v1", lambda: c.nominate(ctx)
        )
        market = await access.call(
            m,
            ctx,
            "sd.market-context",
            "sd.market-context.v1",
            lambda: m.observe(ctx, universe.items),
        )
        annotated = await access.call(
            i,
            ctx,
            "sd.candidate-intelligence",
            "sd.candidate-intelligence.v1",
            lambda: i.annotate(ctx, inputs.items),
        )
        assert market.items[0].measures[0].value == "neutral-synthetic"
        assert annotated.items[0].measures[0].value == "deterministic-fixture-only"
        for provider in (u, s, m, c, i):
            health = await provider.health(ctx)
            assert (
                health.identity == provider.manifest.identity and health.health == Health.AVAILABLE
            )
            assert health.as_of == ctx.as_of and health.source_mode == SourceMode.SYNTHETIC
        assert ProviderBatch[CandidateInput].model_validate_json(inputs.model_dump_json()) == inputs
        assert (
            ProviderBatch[DiscoveryEvidence].model_validate_json(market.model_dump_json()) == market
        )

    asyncio.run(run())


@pytest.mark.parametrize(
    "code",
    [
        ErrorCode.SERVICE_UNAVAILABLE,
        ErrorCode.AUTHENTICATION_FAILED,
        ErrorCode.AUTHORIZATION_FAILED,
        ErrorCode.TIMEOUT,
        ErrorCode.CONTRACT_MISMATCH,
        DomainErrorCode.STALE_DATA,
        DomainErrorCode.INVALID_REQUEST,
        DomainErrorCode.RATE_LIMITED,
    ],
)
def test_typed_errors_preserve_only_safe_code_and_correlation(
    code: ErrorCode | DomainErrorCode,
) -> None:
    provider = SyntheticUniverseProvider()
    provider.failure = code
    with pytest.raises(ProviderFailure) as exc:
        asyncio.run(
            ProviderAccess(FixtureGrants()).call(
                provider,
                context(),
                "sd.universe",
                "sd.universe.v1",
                lambda: provider.resolve(context()),
            )
        )
    assert exc.value.error.code == code
    assert exc.value.error.provider_id == provider.manifest.identity.service_id
    assert exc.value.error.request_id == context().correlation.request_id
    assert str(exc.value) == code.value


@pytest.mark.parametrize(
    "case,code",
    [
        ("unknown-capability", ErrorCode.UNSUPPORTED_CAPABILITY),
        ("version", ErrorCode.CONTRACT_MISMATCH),
        ("disabled", ErrorCode.AUTHORIZATION_FAILED),
        ("other-owner", ErrorCode.AUTHORIZATION_FAILED),
    ],
)
def test_admission_rejects_before_invoking_provider(case: str, code: ErrorCode) -> None:
    provider = SyntheticUniverseProvider()
    called = False

    async def invoke() -> ProviderBatch[InstrumentIdentity]:
        nonlocal called
        called = True
        return await provider.resolve(context())

    with pytest.raises(ProviderFailure) as exc:
        asyncio.run(
            ProviderAccess(FixtureGrants()).call(
                provider,
                context(owner=OTHER) if case == "other-owner" else context(),
                "sd.scan" if case == "unknown-capability" else "sd.universe",
                "sd.universe.v2" if case == "version" else "sd.universe.v1",
                invoke,
                enabled=case != "disabled",
            )
        )
    assert exc.value.error.code == code and not called


def test_provider_unavailable_is_not_empty_success() -> None:
    provider = SyntheticUniverseProvider()
    provider.available = False
    assert asyncio.run(provider.health(context())).health == Health.UNAVAILABLE
    with pytest.raises(ProviderFailure) as exc:
        asyncio.run(provider.resolve(context()))
    assert exc.value.error.code == ErrorCode.SERVICE_UNAVAILABLE


def test_timeout_and_unexpected_errors_are_sanitized() -> None:
    provider = SyntheticUniverseProvider()
    cancelled = False

    async def slow() -> ProviderBatch[InstrumentIdentity]:
        nonlocal cancelled
        try:
            await asyncio.sleep(1)
            return await provider.resolve(context())
        finally:
            cancelled = True

    with pytest.raises(ProviderFailure) as exc:
        asyncio.run(
            ProviderAccess(FixtureGrants(), timeout_seconds=0.01).call(
                provider, context(), "sd.universe", "sd.universe.v1", slow
            )
        )
    assert exc.value.error.code == ErrorCode.TIMEOUT and cancelled

    async def broken() -> ProviderBatch[InstrumentIdentity]:
        raise RuntimeError("private-token=do-not-disclose")

    with pytest.raises(ProviderFailure) as error:
        asyncio.run(
            ProviderAccess(FixtureGrants()).call(
                provider, context(), "sd.universe", "sd.universe.v1", broken
            )
        )
    assert error.value.error.code == ErrorCode.INVALID_RESPONSE
    assert "private-token" not in str(error.value) + error.value.error.model_dump_json()


@pytest.mark.parametrize(
    "mutation", ["identity", "owner", "correlation", "time", "mode", "limit", "cursor"]
)
def test_untrusted_result_envelope_is_checked(mutation: str) -> None:
    provider = SyntheticUniverseProvider()

    async def malformed() -> ProviderBatch[InstrumentIdentity]:
        result = await provider.resolve(context())
        fields: dict[str, Any] = {
            "identity": {"identity": replace(result.identity, service_version="wrong")},
            "owner": {"owner_id": OTHER},
            "correlation": {"request_id": "wrong"},
            "time": {"as_of": context(1).as_of},
            "mode": {"source_mode": SourceMode.LIVE_SNAPSHOT},
            "limit": {"items": result.items * 2},
            "cursor": {"next_cursor": "not-complete"},
        }
        return replace(result, **fields[mutation])

    with pytest.raises(ProviderFailure):
        asyncio.run(
            ProviderAccess(FixtureGrants()).call(
                provider, context(), "sd.universe", "sd.universe.v1", malformed
            )
        )


def test_permissions_rechecked_after_provider_returns() -> None:
    grants = FixtureGrants()
    provider = SyntheticUniverseProvider()

    async def revoked() -> ProviderBatch[InstrumentIdentity]:
        result = await provider.resolve(context())
        grants.enabled = False
        return result

    with pytest.raises(ProviderFailure) as exc:
        asyncio.run(
            ProviderAccess(grants).call(
                provider, context(), "sd.universe", "sd.universe.v1", revoked
            )
        )
    assert exc.value.error.code == ErrorCode.AUTHORIZATION_FAILED


def test_local_placement_does_not_change_producer_semantics() -> None:
    provider = SyntheticUniverseProvider()
    synthetic = asyncio.run(provider.resolve(context()))
    provider.mode = DeploymentMode.LOCAL
    local = asyncio.run(
        ProviderAccess(FixtureGrants()).call(
            provider,
            context(),
            "sd.universe",
            "sd.universe.v1",
            lambda: provider.resolve(context()),
        )
    )
    assert local == synthetic and local.source_mode == SourceMode.SYNTHETIC


@pytest.mark.parametrize(
    "field,value", [("metric", "vendor.secret"), ("operator", "LT"), ("unit", "INR")]
)
def test_unsupported_scan_criteria_are_not_silently_dropped(field: str, value: str) -> None:
    run = scan_run()
    criterion = replace(run.definition.criteria[0], **{field: value})
    run = replace(run, definition=replace(run.definition, criteria=(criterion,)))
    with pytest.raises(ProviderFailure) as exc:
        asyncio.run(SyntheticScanProvider().scan(context(), run, fixture_instruments()))
    assert exc.value.error.code == ErrorCode.UNSUPPORTED_CAPABILITY


def test_malformed_unknown_fields_and_operator_are_rejected() -> None:
    run = scan_run()
    with pytest.raises(ValidationError):
        replace(run.definition, sql="DELETE FROM instruments")
    with pytest.raises(ValidationError):
        replace(run.definition.criteria[0], operator="eval")
