"""Pure transition guards; assessments are inputs, not a production discovery evaluator."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from twf.discovery.domain import (
    DiscoveryEpisode,
    FreshnessState,
    Instant,
    RejectionReason,
    RevisionRef,
)
from twf.discovery.domain import (
    DiscoveryLifecycleState as State,
)
from twf.integrations.contracts import Contract, Identifier


class TransitionAssessment(Contract):
    policy: RevisionRef
    freshness: FreshnessState = FreshnessState.UNKNOWN
    comparable_observations: int = Field(default=0, strict=True, ge=0)
    eligible: bool = False
    material_breach: bool = False
    recovery_verified: bool = False
    insufficient_evidence_confirmed: bool = False
    identity_invalid: bool = False
    reason: Identifier
    evidence_ids: tuple[UUID, ...] = ()
    actor_id: UUID | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.material_breach and self.recovery_verified:
            raise ValueError("Breach and recovery cannot both be established")
        return self


class TransitionEvent(Contract):
    episode_id: UUID
    owner_id: UUID
    from_state: State
    to_state: State
    at: Instant
    revision: int
    assessment: TransitionAssessment
    rejection_reason: RejectionReason | None


def effective_state(episode: DiscoveryEpisode, freshness: FreshnessState, as_of: datetime) -> State:
    if as_of.tzinfo is None or as_of < episode.evaluated_at:
        raise ValueError("Projection requires an aware, non-retroactive clock")
    if episode.lifecycle == State.REJECTED:
        return State.REJECTED
    if episode.lifecycle == State.EXPIRED or as_of >= episode.window.ends_at:
        return State.EXPIRED
    if episode.lifecycle in (State.DEFUNCT, State.NEW):
        return episode.lifecycle
    return State.CURRENT if freshness == FreshnessState.FRESH else State.STALE


def transition(
    episode: DiscoveryEpisode,
    target: State,
    at: datetime,
    assessment: TransitionAssessment,
    rejection_reason: RejectionReason | None = None,
) -> tuple[DiscoveryEpisode, TransitionEvent]:
    if at.tzinfo is None or at < episode.evaluated_at:
        raise ValueError("Transition time cannot precede the current evaluation")
    source = episode.lifecycle
    if source == State.REJECTED or source == target or target == State.STALE:
        raise ValueError("Illegal lifecycle transition")
    if assessment.policy != episode.policy_series:
        raise ValueError("Transition must use the pinned policy")
    expired = source == State.EXPIRED or at >= episode.window.ends_at
    if expired and target not in (State.EXPIRED, State.REJECTED):
        raise ValueError("Expired windows cannot recover")
    if target == State.EXPIRED:
        if not expired:
            raise ValueError("Window has not expired")
    elif target == State.REJECTED:
        if rejection_reason is None:
            raise ValueError("Rejection needs a reason")
        if expired and rejection_reason != RejectionReason.EXPIRED:
            raise ValueError("Expiry closure must preserve its reason")
        if rejection_reason == RejectionReason.EXPIRED and not expired:
            raise ValueError("Cannot reject as expired before window end")
        if (
            rejection_reason == RejectionReason.USER_DISMISSED
            and assessment.actor_id != episode.owner_id
        ):
            raise ValueError("Dismissal requires the owning actor")
        if rejection_reason == RejectionReason.DEFUNCT_CONFIRMED and (
            source != State.DEFUNCT
            or not assessment.material_breach
            or assessment.freshness != FreshnessState.FRESH
        ):
            raise ValueError("Defunct confirmation needs fresh breach evidence")
        if (
            rejection_reason == RejectionReason.INSUFFICIENT_EVIDENCE
            and not assessment.insufficient_evidence_confirmed
        ):
            raise ValueError("Insufficient evidence needs explicit policy confirmation")
        if rejection_reason == RejectionReason.IDENTITY_INVALID and not assessment.identity_invalid:
            raise ValueError("Invalid identity needs explicit confirmation")
    elif target == State.DEFUNCT:
        if (
            not assessment.material_breach
            or assessment.freshness != FreshnessState.FRESH
            or not assessment.evidence_ids
        ):
            raise ValueError("Aging or missing data cannot prove a material breach")
    elif target in (State.NEW, State.CURRENT):
        if source not in (State.NEW, State.DEFUNCT):
            raise ValueError("Cannot reset a current episode to provisional")
        if (
            not assessment.eligible
            or assessment.freshness != FreshnessState.FRESH
            or not assessment.evidence_ids
        ):
            raise ValueError("Promotion/recovery requires fresh eligible evidence")
        if source == State.DEFUNCT and not assessment.recovery_verified:
            raise ValueError("Recovery must satisfy the pinned recovery policy")
        required = State.CURRENT if assessment.comparable_observations >= 2 else State.NEW
        if target != required:
            raise ValueError("Evolution needs distinct comparable observations")
    else:
        raise ValueError("Unknown transition")
    if target != State.REJECTED and rejection_reason is not None:
        raise ValueError("Only rejection carries a rejection reason")
    updated = DiscoveryEpisode.model_validate(
        {
            **episode.model_dump(),
            "lifecycle": target,
            "evaluated_at": at,
            "revision": episode.revision + 1,
            "rejection_reason": rejection_reason,
        }
    )
    event = TransitionEvent(
        episode_id=episode.episode_id,
        owner_id=episode.owner_id,
        from_state=source,
        to_state=target,
        at=at,
        revision=updated.revision,
        assessment=assessment,
        rejection_reason=rejection_reason,
    )
    return updated, event
