"""Fixed-clock fixtures for S2-1. No environment settings or database access."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from twf.discovery.domain import (
    Comparison,
    Criterion,
    DiscoveryIntent,
    HorizonBasis,
    HorizonSpec,
    OpportunityWindow,
    ScanDefinition,
    ScanProfileReference,
    ScanRun,
    SourceMode,
)
from twf.discovery.memory import InMemoryDiscoveryHistory
from twf.discovery.providers import OperationContext, ProviderAccess
from twf.discovery.service import SyntheticFoundationProof
from twf.discovery.synthetic import fixture_id
from twf.integrations.contracts import RequestContext

NOW = datetime(2026, 1, 5, 10, tzinfo=UTC)
OWNER = fixture_id("owner")
OTHER = fixture_id("other-owner")
EPISODE = fixture_id("episode")


def replace[T: BaseModel](original: T, **changes: Any) -> T:
    return type(original).model_validate({**original.model_dump(), **changes})


def context(seconds: int = 0, owner: UUID = OWNER) -> OperationContext:
    return OperationContext(
        owner_id=owner,
        correlation=RequestContext(request_id="fixture-run"),
        as_of=NOW + timedelta(seconds=seconds),
    )


def intent(owner: UUID = OWNER) -> DiscoveryIntent:
    return DiscoveryIntent(
        intent_id=fixture_id("intent"),
        owner_id=owner,
        revision=1,
        created_at=NOW,
        direction="LONG",
        objective="attention",
        setup_family="fixture",
        horizon=HorizonSpec(
            preset="next-30-minutes",
            basis=HorizonBasis.ELAPSED,
            minimum=1800,
            maximum=1800,
            unit="seconds",
            cadence_seconds=60,
        ),
    )


def window() -> OpportunityWindow:
    return OpportunityWindow(starts_at=NOW, ends_at=NOW + timedelta(minutes=30))


def scan_run(ctx: OperationContext | None = None) -> ScanRun:
    ctx = ctx or context()
    return ScanRun(
        run_id=fixture_id("run-" + ctx.as_of.isoformat()),
        owner_id=ctx.owner_id,
        request_id=ctx.correlation.request_id,
        as_of=ctx.as_of,
        profile=ScanProfileReference(
            profile_id=fixture_id("profile"), owner_id=ctx.owner_id, applied_revision=1
        ),
        definition=ScanDefinition(
            definition_id=fixture_id("definition"),
            revision=1,
            criteria=(
                Criterion(
                    metric="fixture.ordinal",
                    operator=Comparison.GTE,
                    threshold=Decimal(3),
                    unit="fixture-index",
                ),
            ),
            timeframe="fixture-step",
            source_mode=SourceMode.SYNTHETIC,
            required_capabilities=("sd.scan",),
        ),
    )


class FixtureGrants:
    def __init__(self, owner: UUID = OWNER) -> None:
        self.owner = owner
        self.enabled = True

    def allows(self, user_id: UUID, capability: str) -> bool:
        return (
            self.enabled
            and user_id == self.owner
            and capability
            in {
                "sd.universe",
                "sd.scan",
                "sd.candidate-source",
                "sd.market-context",
                "sd.candidate-intelligence",
            }
        )


def proof() -> SyntheticFoundationProof:
    return SyntheticFoundationProof(ProviderAccess(FixtureGrants()), InMemoryDiscoveryHistory())
