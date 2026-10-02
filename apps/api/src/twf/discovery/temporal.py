"""Durable scan-driven temporal observations and rebuildable candidate projections."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from twf.discovery.domain import (
    DiscoveryLifecycleState,
    DiscoveryObservation,
    DiscoveryObservationKind,
    EvaluationCoverage,
    InstrumentIdentity,
    ObservationComparison,
    RelevanceBand,
    RevisionRef,
    ScanComparabilityDescriptor,
    SourceNovelty,
    digest,
)
from twf.discovery.product import (
    TemporalHistoryPage,
    TemporalObservationView,
    TemporalSummary,
    WindowStatus,
)
from twf.infrastructure.discovery import (
    DiscoveryActiveSlotRecord,
    DiscoveryComparisonScopeRecord,
    DiscoveryEpisodeRecord,
    DiscoveryObservationRecord,
    DiscoveryProjectionCheckpointRecord,
    DiscoveryScanAdmissionRecord,
    DiscoveryTemporalLaneRecord,
    DiscoveryTransitionRecord,
)

logger = logging.getLogger("twf.discovery.temporal")
TERMINAL = {
    DiscoveryLifecycleState.EXPIRED.value,
    DiscoveryLifecycleState.REJECTED.value,
}


class TemporalConflict(Exception):
    pass


@dataclass(frozen=True)
class RunAdmission:
    run_id: UUID
    scope_id: UUID
    sequence: int
    status: str
    replay: bool


def aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def scope_uuid(owner_id: UUID, fingerprint: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"twf-discovery-scope:{owner_id}:{fingerprint}")


def policy_series(policy: RevisionRef | None) -> str | None:
    return None if policy is None else f"{policy.id}@{policy.version}"


class TemporalStore:
    """Persistence protocol; caller owns commit boundaries except admission."""

    def __init__(self, session: Session, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    def admit_run(
        self,
        descriptor: ScanComparabilityDescriptor,
        *,
        run_id: UUID,
        request_key: str,
        request_digest: str,
        as_of: datetime,
        payload: dict[str, Any],
        retry: bool = True,
    ) -> RunAdmission:
        try:
            existing = self.session.scalar(
                select(DiscoveryScanAdmissionRecord).where(
                    DiscoveryScanAdmissionRecord.user_id == self.owner_id,
                    DiscoveryScanAdmissionRecord.request_key == request_key,
                )
            )
            if existing is not None:
                if existing.request_digest != request_digest:
                    raise TemporalConflict("IDEMPOTENCY_CONFLICT")
                self.session.rollback()
                return RunAdmission(
                    existing.run_id,
                    existing.scope_id,
                    existing.sequence,
                    existing.status,
                    True,
                )

            fingerprint = descriptor.fingerprint
            scope_id = scope_uuid(self.owner_id, fingerprint)
            scope = self.session.get(DiscoveryComparisonScopeRecord, scope_id)
            if scope is None:
                scope = DiscoveryComparisonScopeRecord(
                    id=scope_id,
                    user_id=self.owner_id,
                    digest=fingerprint,
                    schema_version=descriptor.schema_version,
                    created_at=as_of,
                    descriptor=descriptor.model_dump(mode="json"),
                )
                self.session.add(scope)
                self.session.flush()
            elif scope.user_id != self.owner_id or scope.digest != fingerprint:
                raise TemporalConflict("COMPARISON_SCOPE_CONFLICT")

            lane = self.session.scalar(
                select(DiscoveryTemporalLaneRecord)
                .where(
                    DiscoveryTemporalLaneRecord.scope_id == scope_id,
                    DiscoveryTemporalLaneRecord.user_id == self.owner_id,
                )
                .with_for_update()
            )
            if lane is None:
                lane = DiscoveryTemporalLaneRecord(
                    scope_id=scope_id,
                    user_id=self.owner_id,
                    next_sequence=2,
                    finalized_sequence=0,
                    revision=1,
                    last_as_of=as_of,
                )
                self.session.add(lane)
                sequence = 1
            else:
                sequence = lane.next_sequence
                lane.next_sequence += 1
                lane.revision += 1
                lane.last_as_of = max(aware(lane.last_as_of), as_of) if lane.last_as_of else as_of
            self.session.add(
                DiscoveryScanAdmissionRecord(
                    run_id=run_id,
                    user_id=self.owner_id,
                    scope_id=scope_id,
                    sequence=sequence,
                    status="ADMITTED",
                    request_key=request_key,
                    request_digest=request_digest,
                    admitted_at=as_of,
                    as_of=as_of,
                    payload=payload,
                )
            )
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            if not retry:
                raise TemporalConflict("CONCURRENT_ADMISSION") from None
            return self.admit_run(
                descriptor,
                run_id=run_id,
                request_key=request_key,
                request_digest=request_digest,
                as_of=as_of,
                payload=payload,
                retry=False,
            )
        except OperationalError as exc:
            self.session.rollback()
            contention = "locked" in str(exc).lower() or "busy" in str(exc).lower()
            if not retry or not contention:
                raise
            return self.admit_run(
                descriptor,
                run_id=run_id,
                request_key=request_key,
                request_digest=request_digest,
                as_of=as_of,
                payload=payload,
                retry=False,
            )
        logger.info(
            "discovery_scan_admitted",
            extra={"run_id": str(run_id), "scope_id": str(scope_id), "sequence": sequence},
        )
        return RunAdmission(run_id, scope_id, sequence, "ADMITTED", False)

    def cached_response(self, run_id: UUID) -> dict[str, Any] | None:
        row = self.session.get(DiscoveryScanAdmissionRecord, run_id)
        if row is None or row.user_id != self.owner_id:
            return None
        response = row.payload.get("response")
        return response if isinstance(response, dict) else None

    def store_response(self, run_id: UUID, response: dict[str, Any]) -> None:
        row = self.session.get(DiscoveryScanAdmissionRecord, run_id)
        if row is None or row.user_id != self.owner_id:
            raise TemporalConflict("RUN_ADMISSION_NOT_FOUND")
        row.payload = {**row.payload, "response": response}

    def seal_run(self, admission: RunAdmission, result_payload: dict[str, Any]) -> None:
        self.session.flush()
        row = self.session.scalar(
            select(DiscoveryScanAdmissionRecord)
            .where(DiscoveryScanAdmissionRecord.run_id == admission.run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None or row.user_id != self.owner_id:
            raise TemporalConflict("RUN_ADMISSION_NOT_FOUND")
        result_digest = digest(result_payload)
        if row.status in {"SEALED", "FINALIZED"}:
            if row.result_digest != result_digest:
                raise TemporalConflict("SEALED_RESULT_CONFLICT")
            return
        if row.status != "ADMITTED":
            raise TemporalConflict("RUN_NOT_ADMITTED")
        row.status = "SEALED"
        row.sealed_at = datetime.now(UTC)
        row.result_digest = result_digest
        row.payload = {**row.payload, "result": result_payload}

    def fail_run(self, run_id: UUID, reason: str) -> None:
        row = self.session.get(DiscoveryScanAdmissionRecord, run_id)
        if row is None or row.user_id != self.owner_id or row.status != "ADMITTED":
            self.session.rollback()
            return
        row.status = "FAILED"
        row.sealed_at = datetime.now(UTC)
        row.payload = {**row.payload, "failure_reason": reason}
        self.session.commit()

    def finalize_run(self, admission: RunAdmission) -> None:
        self.session.flush()
        row = self.session.scalar(
            select(DiscoveryScanAdmissionRecord)
            .where(DiscoveryScanAdmissionRecord.run_id == admission.run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None or row.user_id != self.owner_id:
            raise TemporalConflict("RUN_ADMISSION_NOT_FOUND")
        if row.status == "FINALIZED":
            return
        if row.status != "SEALED":
            raise TemporalConflict("RUN_NOT_SEALED")
        row.status = "FINALIZED"
        lane = self.session.scalar(
            select(DiscoveryTemporalLaneRecord)
            .where(DiscoveryTemporalLaneRecord.scope_id == admission.scope_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if lane is not None:
            # This is the largest applied sequence, not proof that earlier remote work stopped.
            lane.finalized_sequence = max(lane.finalized_sequence, admission.sequence)
            lane.revision += 1

    def active_episode(self, scope_id: UUID, instrument_id: UUID) -> DiscoveryEpisodeRecord | None:
        slot = self.session.get(
            DiscoveryActiveSlotRecord,
            (self.owner_id, scope_id, instrument_id),
        )
        if slot is None:
            return None
        episode = self.session.get(DiscoveryEpisodeRecord, slot.episode_id)
        if episode is None or episode.user_id != self.owner_id or episode.state in TERMINAL:
            return None
        return episode

    def episode_for_observation(
        self, scope_id: UUID, instrument_id: UUID, run_sequence: int
    ) -> DiscoveryEpisodeRecord | None:
        """Resolve the active episode or the historical episode that already passed a late run."""

        active = self.active_episode(scope_id, instrument_id)
        if active is not None:
            return active
        rows = self.session.scalars(
            select(DiscoveryEpisodeRecord)
            .where(
                DiscoveryEpisodeRecord.user_id == self.owner_id,
                DiscoveryEpisodeRecord.comparison_scope_id == scope_id,
                DiscoveryEpisodeRecord.instrument_id == instrument_id,
            )
            .order_by(DiscoveryEpisodeRecord.opened_at.desc())
            .limit(20)
        )
        for row in rows:
            projected = int(row.payload.get("temporal", {}).get("projected_sequence", 0))
            if projected >= run_sequence:
                return row
        return None

    def claim_active_slot(self, scope_id: UUID, episode: DiscoveryEpisodeRecord) -> None:
        current = self.session.get(
            DiscoveryActiveSlotRecord,
            (self.owner_id, scope_id, episode.instrument_id),
        )
        if current is None:
            self.session.add(
                DiscoveryActiveSlotRecord(
                    user_id=self.owner_id,
                    scope_id=scope_id,
                    instrument_id=episode.instrument_id,
                    episode_id=episode.id,
                    revision=1,
                )
            )
        elif current.episode_id != episode.id:
            raise TemporalConflict("ACTIVE_EPISODE_CONFLICT")

    def release_active_slot(self, scope_id: UUID, instrument_id: UUID, episode_id: UUID) -> None:
        slot = self.session.get(
            DiscoveryActiveSlotRecord,
            (self.owner_id, scope_id, instrument_id),
        )
        if slot is not None and slot.episode_id == episode_id:
            self.session.delete(slot)

    def source_novelty(
        self,
        episode_id: UUID | None,
        source_sample_key: str | None,
        source_data_time: datetime | None,
        run_sequence: int,
    ) -> SourceNovelty:
        if episode_id is None or source_sample_key is None:
            return SourceNovelty.UNKNOWN
        prior = self.session.scalar(
            select(DiscoveryObservationRecord)
            .where(
                DiscoveryObservationRecord.user_id == self.owner_id,
                DiscoveryObservationRecord.episode_id == episode_id,
                DiscoveryObservationRecord.run_sequence < run_sequence,
            )
            .order_by(DiscoveryObservationRecord.run_sequence.desc())
        )
        if prior is None:
            return SourceNovelty.NOVEL
        if prior.source_sample_key == source_sample_key:
            return SourceNovelty.DUPLICATE
        if (
            source_data_time is not None
            and prior.source_data_time is not None
            and aware(source_data_time) < aware(prior.source_data_time)
        ):
            return SourceNovelty.REGRESSED
        return SourceNovelty.NOVEL

    def append_observation(
        self,
        *,
        admission: RunAdmission,
        instrument: InstrumentIdentity,
        kind: DiscoveryObservationKind,
        coverage: EvaluationCoverage,
        reason: str,
        observed_at: datetime,
        source_data_time: datetime | None,
        source_sample_key: str | None,
        episode: DiscoveryEpisodeRecord | None,
        scan_match_id: UUID | None = None,
        snapshot_id: UUID | None = None,
        relevance_score: Decimal | None = None,
        relevance_band: RelevanceBand | None = None,
        relevance_policy: RevisionRef | None = None,
        evidence_ids: tuple[UUID, ...] = (),
        context_id: UUID | None = None,
        provider: str | None = None,
        lifecycle_override: DiscoveryLifecycleState | None = None,
    ) -> DiscoveryObservationRecord:
        if episode is not None:
            self.session.flush()
            locked_episode = self.session.scalar(
                select(DiscoveryEpisodeRecord)
                .where(
                    DiscoveryEpisodeRecord.id == episode.id,
                    DiscoveryEpisodeRecord.user_id == self.owner_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if locked_episode is None:
                raise TemporalConflict("EPISODE_NOT_FOUND")
            episode = locked_episode
        previous = self.session.scalar(
            select(DiscoveryObservationRecord).where(
                DiscoveryObservationRecord.user_id == self.owner_id,
                DiscoveryObservationRecord.scope_id == admission.scope_id,
                DiscoveryObservationRecord.instrument_id == instrument.instrument_id,
                DiscoveryObservationRecord.run_id == admission.run_id,
            )
        )
        if previous is not None:
            logger.info(
                "discovery_observation_replay_ignored", extra={"run_id": str(admission.run_id)}
            )
            return previous

        novelty = self.source_novelty(
            episode.id if episode else None,
            source_sample_key,
            source_data_time,
            admission.sequence,
        )
        late = bool(
            episode is not None
            and admission.sequence
            <= int(episode.payload.get("temporal", {}).get("projected_sequence", 0))
        )
        lifecycle_after = self.reduce_next(episode, kind, novelty, admission.sequence)
        if lifecycle_override is not None and novelty == SourceNovelty.NOVEL and not late:
            lifecycle_after = lifecycle_override
        effective_reason = "late-observation-quarantined" if late else reason
        observation = DiscoveryObservation(
            observation_id=uuid4(),
            owner_id=self.owner_id,
            comparison_scope_id=admission.scope_id,
            episode_id=episode.id if episode else None,
            candidate_id=episode.candidate_id if episode else None,
            run_id=admission.run_id,
            run_sequence=admission.sequence,
            instrument_id=instrument.instrument_id,
            kind=kind,
            comparison=ObservationComparison.COMPARABLE,
            coverage=coverage,
            novelty=novelty,
            source_sample_key=source_sample_key,
            observed_at=observed_at,
            source_data_time=source_data_time,
            recorded_at=datetime.now(UTC),
            scan_match_id=scan_match_id,
            snapshot_id=snapshot_id,
            relevance_score=relevance_score,
            relevance_band=relevance_band,
            relevance_policy=relevance_policy,
            lifecycle_after=lifecycle_after,
            reason=effective_reason,
            evidence_ids=evidence_ids,
            context_id=context_id,
        )
        row = DiscoveryObservationRecord(
            id=observation.observation_id,
            user_id=self.owner_id,
            scope_id=admission.scope_id,
            episode_id=observation.episode_id,
            candidate_id=observation.candidate_id,
            run_id=admission.run_id,
            run_sequence=admission.sequence,
            instrument_id=instrument.instrument_id,
            kind=kind.value,
            observed_at=observed_at,
            source_data_time=source_data_time,
            recorded_at=observation.recorded_at,
            source_sample_key=source_sample_key,
            payload={
                "observation": observation.model_dump(mode="json"),
                "instrument": instrument.model_dump(mode="json"),
                "provider": provider,
                "comparison_scope_version": 1,
            },
        )
        try:
            self.session.add(row)
            self.session.flush()
            if episode is not None:
                self.apply_projection(episode, observation)
        except IntegrityError:
            self.session.rollback()
            replay = self.session.scalar(
                select(DiscoveryObservationRecord).where(
                    DiscoveryObservationRecord.user_id == self.owner_id,
                    DiscoveryObservationRecord.scope_id == admission.scope_id,
                    DiscoveryObservationRecord.instrument_id == instrument.instrument_id,
                    DiscoveryObservationRecord.run_id == admission.run_id,
                )
            )
            if replay is not None:
                logger.info(
                    "discovery_observation_replay_ignored",
                    extra={"run_id": str(admission.run_id)},
                )
                return replay
            self.fail_run(admission.run_id, "PROJECTION_PERSISTENCE_FAILURE")
            raise
        except BaseException:
            # Admission commits before provider work. If observation/projection persistence
            # fails, roll back every local result and durably close that admission as failed.
            self.session.rollback()
            self.fail_run(admission.run_id, "PROJECTION_PERSISTENCE_FAILURE")
            raise
        logger.info(
            "discovery_observation_appended",
            extra={"run_id": str(admission.run_id), "kind": kind.value},
        )
        return row

    def reduce_next(
        self,
        episode: DiscoveryEpisodeRecord | None,
        kind: DiscoveryObservationKind,
        novelty: SourceNovelty,
        run_sequence: int,
    ) -> DiscoveryLifecycleState | None:
        if episode is None:
            return None
        current = DiscoveryLifecycleState(episode.state)
        temporal = episode.payload.get("temporal", {})
        if run_sequence <= int(temporal.get("projected_sequence", 0)):
            return current
        if current in {DiscoveryLifecycleState.EXPIRED, DiscoveryLifecycleState.REJECTED}:
            return current
        if novelty != SourceNovelty.NOVEL:
            return current
        if kind == DiscoveryObservationKind.NOT_EVALUATED:
            return current
        if kind == DiscoveryObservationKind.ABSENT:
            return (
                current
                if current == DiscoveryLifecycleState.DEFUNCT
                else DiscoveryLifecycleState.STALE
            )
        present_count = int(temporal.get("distinct_present_count", 0)) + 1
        if current == DiscoveryLifecycleState.DEFUNCT:
            return current
        return (
            DiscoveryLifecycleState.CURRENT if present_count >= 2 else DiscoveryLifecycleState.NEW
        )

    def apply_projection(
        self, episode: DiscoveryEpisodeRecord, observation: DiscoveryObservation
    ) -> None:
        temporal = dict(episode.payload.get("temporal", {}))
        projected_sequence = int(temporal.get("projected_sequence", 0))
        if observation.run_sequence <= projected_sequence:
            logger.info(
                "discovery_late_observation_quarantined",
                extra={"run_id": str(observation.run_id), "episode_id": str(episode.id)},
            )
            return
        old_state = episode.state
        new_state = (observation.lifecycle_after or DiscoveryLifecycleState(old_state)).value
        if observation.novelty == SourceNovelty.NOVEL:
            if observation.kind == DiscoveryObservationKind.PRESENT:
                temporal["distinct_present_count"] = (
                    int(temporal.get("distinct_present_count", 0)) + 1
                )
                temporal["latest_present_run_id"] = str(observation.run_id)
                previous_relevance = temporal.get("last_known_relevance")
                previous_model = temporal.get("relevance_model")
                current_model = policy_series(observation.relevance_policy)
                temporal["relevance_delta"] = (
                    str(observation.relevance_score - Decimal(str(previous_relevance)))
                    if observation.relevance_score is not None
                    and previous_relevance is not None
                    and previous_model == current_model
                    else None
                )
                temporal["last_known_relevance"] = (
                    None
                    if observation.relevance_score is None
                    else str(observation.relevance_score)
                )
                temporal["relevance_model"] = current_model
            elif observation.kind == DiscoveryObservationKind.ABSENT:
                temporal["distinct_absent_count"] = (
                    int(temporal.get("distinct_absent_count", 0)) + 1
                )
                temporal["latest_absent_run_id"] = str(observation.run_id)
        temporal.update(
            {
                "projected_sequence": observation.run_sequence,
                "head_observation_id": str(observation.observation_id),
                "latest_attempted_run_id": str(observation.run_id),
                "latest_observation_kind": observation.kind.value,
                "last_attempted_at": observation.observed_at.isoformat(),
            }
        )
        if observation.kind != DiscoveryObservationKind.NOT_EVALUATED:
            temporal["latest_comparable_run_id"] = str(observation.run_id)
            temporal["last_observed_at"] = observation.observed_at.isoformat()
        episode.state = new_state
        if projected_sequence > 0 or old_state != new_state:
            episode.revision += 1
        episode.updated_at = observation.recorded_at
        stored_episode = dict(episode.payload.get("episode", {}))
        stored_episode.update(
            {
                "lifecycle": new_state,
                "revision": episode.revision,
                "evaluated_at": observation.recorded_at.isoformat(),
            }
        )
        episode.payload = {
            **episode.payload,
            "episode": stored_episode,
            "temporal": temporal,
            "lifecycle_reason": observation.reason,
        }
        if old_state != new_state:
            self.session.add(
                DiscoveryTransitionRecord(
                    episode_id=episode.id,
                    user_id=self.owner_id,
                    revision=episode.revision,
                    occurred_at=observation.recorded_at,
                    payload={
                        "event_type": "OBSERVATION_REDUCTION",
                        "observation_id": str(observation.observation_id),
                        "run_sequence": observation.run_sequence,
                        "from_state": old_state,
                        "to_state": new_state,
                        "reason": observation.reason,
                        "rule": "scan-driven-temporal-v1",
                    },
                )
            )
        self.update_checkpoint(episode, observation)

    def update_checkpoint(
        self, episode: DiscoveryEpisodeRecord, observation: DiscoveryObservation
    ) -> None:
        row = self.session.get(DiscoveryProjectionCheckpointRecord, episode.id)
        previous_digest = row.prefix_digest if row else ""
        prefix_digest = hashlib.sha256(
            f"{previous_digest}:{observation.observation_id}".encode()
        ).hexdigest()
        payload = {
            "state": episode.state,
            "revision": episode.revision,
            "temporal": episode.payload.get("temporal", {}),
            "policy": "scan-driven-temporal-v1",
        }
        if row is None:
            self.session.add(
                DiscoveryProjectionCheckpointRecord(
                    episode_id=episode.id,
                    user_id=self.owner_id,
                    through_sequence=observation.run_sequence,
                    prefix_digest=prefix_digest,
                    updated_at=observation.recorded_at,
                    payload=payload,
                )
            )
        else:
            row.through_sequence = observation.run_sequence
            row.prefix_digest = prefix_digest
            row.updated_at = observation.recorded_at
            row.payload = payload

    def rebuild_projection(self, episode: DiscoveryEpisodeRecord) -> DiscoveryLifecycleState:
        locked_episode = self.session.scalar(
            select(DiscoveryEpisodeRecord)
            .where(
                DiscoveryEpisodeRecord.id == episode.id,
                DiscoveryEpisodeRecord.user_id == self.owner_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked_episode is None:
            raise TemporalConflict("EPISODE_NOT_FOUND")
        episode = locked_episode
        rows = tuple(
            self.session.scalars(
                select(DiscoveryObservationRecord)
                .where(
                    DiscoveryObservationRecord.user_id == self.owner_id,
                    DiscoveryObservationRecord.episode_id == episode.id,
                )
                .order_by(
                    DiscoveryObservationRecord.run_sequence.asc(),
                    DiscoveryObservationRecord.recorded_at.asc(),
                )
            )
        )
        if not rows:
            return DiscoveryLifecycleState(episode.state)
        controls = tuple(
            self.session.scalars(
                select(DiscoveryTransitionRecord)
                .where(
                    DiscoveryTransitionRecord.user_id == self.owner_id,
                    DiscoveryTransitionRecord.episode_id == episode.id,
                )
                .order_by(DiscoveryTransitionRecord.occurred_at.asc())
            )
        )
        owner_controls = [
            row for row in controls if row.payload.get("event_type") == "OWNER_ACTION"
        ]
        state = DiscoveryLifecycleState.NEW
        present_count = 0
        absent_count = 0
        temporal: dict[str, Any] = {}
        digest_value = ""
        control_index = 0
        last_reason = "projection-rebuilt"
        for row in rows:
            item = DiscoveryObservation.model_validate(row.payload["observation"])
            digest_value = hashlib.sha256(
                f"{digest_value}:{item.observation_id}".encode()
            ).hexdigest()
            if item.novelty == SourceNovelty.NOVEL:
                if item.kind == DiscoveryObservationKind.PRESENT:
                    present_count += 1
                    if state != DiscoveryLifecycleState.DEFUNCT:
                        state = (
                            DiscoveryLifecycleState.CURRENT
                            if present_count >= 2
                            else DiscoveryLifecycleState.NEW
                        )
                    temporal["latest_present_run_id"] = str(item.run_id)
                    previous_relevance = temporal.get("last_known_relevance")
                    previous_model = temporal.get("relevance_model")
                    current_model = policy_series(item.relevance_policy)
                    temporal["relevance_delta"] = (
                        str(item.relevance_score - Decimal(str(previous_relevance)))
                        if item.relevance_score is not None
                        and previous_relevance is not None
                        and previous_model == current_model
                        else None
                    )
                    temporal["last_known_relevance"] = (
                        None if item.relevance_score is None else str(item.relevance_score)
                    )
                    temporal["relevance_model"] = current_model
                elif item.kind == DiscoveryObservationKind.ABSENT:
                    absent_count += 1
                    if state != DiscoveryLifecycleState.DEFUNCT:
                        state = DiscoveryLifecycleState.STALE
                    temporal["latest_absent_run_id"] = str(item.run_id)
                if item.lifecycle_after == DiscoveryLifecycleState.DEFUNCT:
                    state = DiscoveryLifecycleState.DEFUNCT
                elif (
                    state == DiscoveryLifecycleState.DEFUNCT
                    and item.lifecycle_after == DiscoveryLifecycleState.CURRENT
                ):
                    state = DiscoveryLifecycleState.CURRENT
            temporal.update(
                {
                    "projected_sequence": item.run_sequence,
                    "head_observation_id": str(item.observation_id),
                    "latest_attempted_run_id": str(item.run_id),
                    "latest_observation_kind": item.kind.value,
                    "last_attempted_at": item.observed_at.isoformat(),
                    "distinct_present_count": present_count,
                    "distinct_absent_count": absent_count,
                }
            )
            if item.kind != DiscoveryObservationKind.NOT_EVALUATED:
                temporal["latest_comparable_run_id"] = str(item.run_id)
                temporal["last_observed_at"] = item.observed_at.isoformat()
            last_reason = item.reason
            while (
                control_index < len(owner_controls)
                and int(owner_controls[control_index].payload.get("after_sequence", 0))
                <= item.run_sequence
            ):
                control = owner_controls[control_index]
                state = DiscoveryLifecycleState(str(control.payload["to_state"]))
                last_reason = str(control.payload.get("reason", "owner-action"))
                control_index += 1
        while control_index < len(owner_controls):
            control = owner_controls[control_index]
            state = DiscoveryLifecycleState(str(control.payload["to_state"]))
            last_reason = str(control.payload.get("reason", "owner-action"))
            control_index += 1
        episode.state = state.value
        episode.revision += 1
        episode.updated_at = datetime.now(UTC)
        stored_episode = dict(episode.payload.get("episode", {}))
        stored_episode.update(
            {
                "lifecycle": state.value,
                "revision": episode.revision,
                "evaluated_at": episode.updated_at.isoformat(),
            }
        )
        episode.payload = {
            **episode.payload,
            "episode": stored_episode,
            "temporal": temporal,
            "lifecycle_reason": last_reason,
        }
        checkpoint = self.session.get(DiscoveryProjectionCheckpointRecord, episode.id)
        payload = {
            "state": state.value,
            "revision": episode.revision,
            "temporal": temporal,
            "policy": "scan-driven-temporal-v1",
        }
        if checkpoint is None:
            self.session.add(
                DiscoveryProjectionCheckpointRecord(
                    episode_id=episode.id,
                    user_id=self.owner_id,
                    through_sequence=rows[-1].run_sequence,
                    prefix_digest=digest_value,
                    updated_at=episode.updated_at,
                    payload=payload,
                )
            )
        else:
            checkpoint.through_sequence = rows[-1].run_sequence
            checkpoint.prefix_digest = digest_value
            checkpoint.updated_at = episode.updated_at
            checkpoint.payload = payload
        logger.info("discovery_projection_rebuilt", extra={"episode_id": str(episode.id)})
        return state

    @staticmethod
    def view(row: DiscoveryObservationRecord, hot: bool) -> TemporalObservationView:
        item = DiscoveryObservation.model_validate(row.payload["observation"])
        return TemporalObservationView(
            observation_id=item.observation_id,
            run_id=item.run_id,
            run_sequence=item.run_sequence,
            observed_at=item.observed_at,
            source_data_time=item.source_data_time,
            kind=item.kind,
            coverage=item.coverage.value,
            novelty=item.novelty,
            relevance_score=item.relevance_score,
            relevance_band=item.relevance_band,
            relevance_model=policy_series(item.relevance_policy),
            lifecycle_after=item.lifecycle_after,
            reason=item.reason,
            comparison_scope_version=int(row.payload.get("comparison_scope_version", 1)),
            provider=row.payload.get("provider"),
            is_hot=hot,
        )

    def history_page(
        self,
        episode_id: UUID,
        *,
        limit: int,
        offset: int,
        hot_size: int,
    ) -> TemporalHistoryPage:
        total = int(
            self.session.scalar(
                select(func.count())
                .select_from(DiscoveryObservationRecord)
                .where(
                    DiscoveryObservationRecord.user_id == self.owner_id,
                    DiscoveryObservationRecord.episode_id == episode_id,
                )
            )
            or 0
        )
        rows = tuple(
            self.session.scalars(
                select(DiscoveryObservationRecord)
                .where(
                    DiscoveryObservationRecord.user_id == self.owner_id,
                    DiscoveryObservationRecord.episode_id == episode_id,
                )
                .order_by(
                    DiscoveryObservationRecord.run_sequence.desc(),
                    DiscoveryObservationRecord.recorded_at.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        )
        if total > hot_size:
            logger.info(
                "discovery_hot_window_rolled_over",
                extra={
                    "episode_id": str(episode_id),
                    "hot_size": hot_size,
                    "cold_count": total - hot_size,
                },
            )
        cold_rows = max(0, min(offset + len(rows), total) - max(offset, hot_size))
        if cold_rows:
            logger.info(
                "discovery_logical_cold_history_read",
                extra={
                    "episode_id": str(episode_id),
                    "offset": offset,
                    "row_count": cold_rows,
                },
            )
        return TemporalHistoryPage(
            items=tuple(
                self.view(row, offset + index < hot_size) for index, row in enumerate(rows)
            ),
            total=total,
            limit=limit,
            offset=offset,
            hot_size=hot_size,
            as_of=datetime.now(UTC),
        )

    def summaries(
        self, episodes: tuple[DiscoveryEpisodeRecord, ...], hot_size: int
    ) -> dict[UUID, TemporalSummary]:
        if not episodes:
            return {}
        episode_ids = tuple(item.id for item in episodes)
        ranked = (
            select(
                DiscoveryObservationRecord.id.label("observation_id"),
                DiscoveryObservationRecord.episode_id.label("episode_id"),
                func.row_number()
                .over(
                    partition_by=DiscoveryObservationRecord.episode_id,
                    order_by=(
                        DiscoveryObservationRecord.run_sequence.desc(),
                        DiscoveryObservationRecord.recorded_at.desc(),
                    ),
                )
                .label("recent_rank"),
            )
            .where(
                DiscoveryObservationRecord.user_id == self.owner_id,
                DiscoveryObservationRecord.episode_id.in_(episode_ids),
            )
            .subquery()
        )
        recent = tuple(
            self.session.scalars(
                select(DiscoveryObservationRecord)
                .join(ranked, DiscoveryObservationRecord.id == ranked.c.observation_id)
                .where(ranked.c.recent_rank <= hot_size)
                .order_by(
                    DiscoveryObservationRecord.episode_id.asc(),
                    DiscoveryObservationRecord.run_sequence.desc(),
                )
            )
        )
        counts = {
            episode_id: int(total)
            for episode_id, total in self.session.execute(
                select(
                    DiscoveryObservationRecord.episode_id,
                    func.count(DiscoveryObservationRecord.id),
                )
                .where(
                    DiscoveryObservationRecord.user_id == self.owner_id,
                    DiscoveryObservationRecord.episode_id.in_(episode_ids),
                )
                .group_by(DiscoveryObservationRecord.episode_id)
            )
            if episode_id is not None
        }
        grouped: dict[UUID, list[DiscoveryObservationRecord]] = {}
        for row in recent:
            if row.episode_id is not None:
                grouped.setdefault(row.episode_id, []).append(row)
        result: dict[UUID, TemporalSummary] = {}
        for episode in episodes:
            summary = self._summary_from_rows(
                episode, tuple(grouped.get(episode.id, ())), counts.get(episode.id, 0), hot_size
            )
            if summary is not None:
                result[episode.id] = summary
        return result

    def summary(self, episode: DiscoveryEpisodeRecord, hot_size: int) -> TemporalSummary | None:
        rows = tuple(
            self.session.scalars(
                select(DiscoveryObservationRecord)
                .where(
                    DiscoveryObservationRecord.user_id == self.owner_id,
                    DiscoveryObservationRecord.episode_id == episode.id,
                )
                .order_by(DiscoveryObservationRecord.run_sequence.desc())
                .limit(hot_size)
            )
        )
        total = int(
            self.session.scalar(
                select(func.count())
                .select_from(DiscoveryObservationRecord)
                .where(
                    DiscoveryObservationRecord.user_id == self.owner_id,
                    DiscoveryObservationRecord.episode_id == episode.id,
                )
            )
            or 0
        )
        return self._summary_from_rows(episode, rows, total, hot_size)

    def _summary_from_rows(
        self,
        episode: DiscoveryEpisodeRecord,
        rows: tuple[DiscoveryObservationRecord, ...],
        total: int,
        hot_size: int,
    ) -> TemporalSummary | None:
        if not rows:
            return None
        items = tuple(
            DiscoveryObservation.model_validate(row.payload["observation"]) for row in rows
        )
        latest = items[0]
        projection = episode.payload.get("temporal", {})
        effective = next(
            (item for item in items if item.kind != DiscoveryObservationKind.NOT_EVALUATED),
            None,
        )
        latest_comparable = projection.get("latest_comparable_run_id")
        last_observed = projection.get("last_observed_at")
        if latest_comparable is None or last_observed is None:
            latest_comparable = str((effective or latest).run_id)
            last_observed = (effective or latest).observed_at.isoformat()
        latest_present_run = projection.get("latest_present_run_id")
        last_known_relevance = projection.get("last_known_relevance")
        window = episode.payload.get("episode", {}).get("window", {})
        ends_at = window.get("ends_at")
        now = datetime.now(UTC)
        window_status = WindowStatus.UNKNOWN
        if ends_at:
            window_status = (
                WindowStatus.ENDED
                if datetime.fromisoformat(str(ends_at)) <= now
                else WindowStatus.OPEN
            )
        observed_at = datetime.fromisoformat(str(last_observed))
        return TemporalSummary(
            latest_observation_kind=latest.kind,
            last_observed_at=observed_at,
            latest_comparable_run_id=UUID(str(latest_comparable)),
            latest_attempted_run_id=latest.run_id,
            latest_present_run_id=(
                UUID(str(latest_present_run)) if latest_present_run is not None else None
            ),
            last_known_relevance=(
                Decimal(str(last_known_relevance)) if last_known_relevance is not None else None
            ),
            relevance_delta=(
                Decimal(str(projection["relevance_delta"]))
                if projection.get("relevance_delta") is not None
                else None
            ),
            relevance_model=projection.get("relevance_model"),
            hot_count=min(total, hot_size),
            total_count=total,
            window_status=window_status,
            observation_age_seconds=max(0, int((now - aware(observed_at)).total_seconds())),
            recent_observations=tuple(self.view(row, True) for row in reversed(rows)),
        )
