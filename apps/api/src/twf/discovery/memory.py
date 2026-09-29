"""Owner-scoped in-memory contract proof only; no durability or multi-worker claims."""

from datetime import datetime
from threading import RLock
from uuid import UUID

from twf.discovery.domain import (
    DiscoveryCandidate,
    DiscoveryEpisode,
    DiscoveryEvidence,
    DiscoverySnapshot,
    FreshnessState,
    RejectionReason,
    digest,
    freshness,
)
from twf.discovery.domain import (
    DiscoveryLifecycleState as State,
)
from twf.discovery.lifecycle import (
    TransitionAssessment,
    TransitionEvent,
    effective_state,
    transition,
)


class HistoryConflict(ValueError):
    """Safe conflict without backend/provider exception text."""


def required_freshness(snapshot: DiscoverySnapshot, as_of: datetime, ttl: int) -> FreshnessState:
    # Foundation fixture policy: input evidence is required; enrichments stay separate.
    states = tuple(freshness(e, as_of, ttl) for e in snapshot.evidence)
    if FreshnessState.UNKNOWN in states:
        return FreshnessState.UNKNOWN
    return FreshnessState.STALE if FreshnessState.STALE in states else FreshnessState.FRESH


def evidence_basis(item: DiscoveryEvidence) -> str:
    """Compatibility identity, excluding changing measurements and capture/observation IDs."""
    return digest(
        {
            "subject": str(item.subject_id),
            "category": item.category.value,
            "basis": item.observation_basis,
            "provenance": item.provenance.model_dump(mode="json", exclude={"observation_key"}),
            "measurements": sorted((m.name, m.unit) for m in item.measures),
        }
    )


def evidence_by_basis(snapshot: DiscoverySnapshot) -> dict[str, DiscoveryEvidence]:
    result = {evidence_basis(item): item for item in snapshot.evidence}
    if len(result) != len(snapshot.evidence):
        raise HistoryConflict("Ambiguous repeated evidence basis")
    return result


def scan_context(snapshot: DiscoverySnapshot) -> str | None:
    return snapshot.lineage.scan.comparison_key if snapshot.lineage.scan else None


class InMemoryDiscoveryHistory:
    def __init__(
        self, *, freshness_ttl_seconds: int = 300, recurrence_cooldown_seconds: int = 60
    ) -> None:
        if not 0 < freshness_ttl_seconds <= 86400 or not 0 <= recurrence_cooldown_seconds <= 86400:
            raise ValueError("Invalid fixture history bounds")
        self.freshness_ttl_seconds = freshness_ttl_seconds
        self.recurrence_cooldown_seconds = recurrence_cooldown_seconds
        self._episodes: dict[UUID, DiscoveryEpisode] = {}
        self._snapshots: dict[UUID, tuple[DiscoverySnapshot, ...]] = {}
        self._events: dict[UUID, tuple[TransitionEvent, ...]] = {}
        self._lock = RLock()

    def episode(self, owner_id: UUID, episode_id: UUID) -> DiscoveryEpisode:
        with self._lock:
            episode = self._episodes.get(episode_id)
            if episode is None or episode.owner_id != owner_id:
                raise LookupError("Episode unavailable")
            return episode

    def snapshots(self, owner_id: UUID, episode_id: UUID) -> tuple[DiscoverySnapshot, ...]:
        with self._lock:
            self.episode(owner_id, episode_id)
            return self._snapshots[episode_id]

    def events(self, owner_id: UUID, episode_id: UUID) -> tuple[TransitionEvent, ...]:
        with self._lock:
            self.episode(owner_id, episode_id)
            return self._events[episode_id]

    def open(self, episode: DiscoveryEpisode, snapshot: DiscoverySnapshot) -> DiscoveryEpisode:
        with self._lock:
            if episode.episode_id in self._episodes or any(
                e.candidate_id == episode.candidate_id for e in self._episodes.values()
            ):
                raise HistoryConflict("Episode/candidate identity already exists")
            if (
                episode.lifecycle != State.NEW
                or episode.revision != 1
                or episode.head_snapshot_id is not None
            ):
                raise HistoryConflict("New history must start with an unmodified NEW episode")
            prior = [e for e in self._episodes.values() if e.active_key == episode.active_key]
            if any(e.lifecycle != State.REJECTED for e in prior):
                raise HistoryConflict("An unclosed episode already owns this key")
            if prior:
                predecessor = max(prior, key=lambda e: e.opened_at)
                if episode.previous_episode_id != predecessor.episode_id:
                    raise HistoryConflict("Recurrence must link the latest terminal episode")
                previous = self._snapshots[predecessor.episode_id][-1]
                if (
                    episode.opened_at <= predecessor.evaluated_at
                    or (episode.opened_at - predecessor.evaluated_at).total_seconds()
                    < self.recurrence_cooldown_seconds
                ) or (
                    snapshot.source_data_time is None
                    or previous.source_data_time is None
                    or snapshot.source_data_time <= previous.source_data_time
                    or snapshot.provenance.observation_key == previous.provenance.observation_key
                ):
                    raise HistoryConflict("Recurrence requires a genuinely later observation")
            elif episode.previous_episode_id is not None:
                raise HistoryConflict("Predecessor must belong to this owner and episode key")
            self._validate_snapshot(episode, snapshot, ())
            head = DiscoveryEpisode.model_validate(
                {
                    **episode.model_dump(),
                    "head_snapshot_id": snapshot.snapshot_id,
                    "evaluated_at": snapshot.evaluated_at,
                }
            )
            self._episodes[head.episode_id] = head
            self._snapshots[head.episode_id] = (snapshot,)
            self._events[head.episode_id] = ()
            return head

    def _validate_snapshot(
        self,
        episode: DiscoveryEpisode,
        snapshot: DiscoverySnapshot,
        history: tuple[DiscoverySnapshot, ...],
    ) -> None:
        if (
            snapshot.owner_id != episode.owner_id
            or snapshot.episode_id != episode.episode_id
            or snapshot.instrument != episode.instrument
            or snapshot.intent_fingerprint != episode.intent.fingerprint
            or snapshot.observation_basis != episode.observation_basis
            or snapshot.relevance.policy != episode.policy_series
        ):
            raise HistoryConflict("Snapshot identity or policy mismatch")
        if (
            snapshot.sequence != len(history) + 1
            or snapshot.previous_snapshot_id != episode.head_snapshot_id
        ):
            raise HistoryConflict("Snapshot does not extend the current head")
        if (
            snapshot.evaluated_at < episode.evaluated_at
            or snapshot.evaluated_at >= episode.window.ends_at
        ):
            raise HistoryConflict("Snapshot outside the active evaluation window")
        if any(
            s.snapshot_id == snapshot.snapshot_id
            for values in self._snapshots.values()
            for s in values
        ):
            raise HistoryConflict("Snapshot identity already exists")
        if history and (
            snapshot.provenance.producer != history[0].provenance.producer
            or snapshot.provenance.transformation != history[0].provenance.transformation
            or snapshot.provenance.source != history[0].provenance.source
            or snapshot.provenance.mode != history[0].provenance.mode
            or scan_context(snapshot) != scan_context(history[0])
        ):
            raise HistoryConflict("Incomparable observations require a separate series")
        incoming = evidence_by_basis(snapshot)
        if history and not evidence_by_basis(history[0]).keys() <= incoming.keys():
            raise HistoryConflict("Incomparable evidence requires a separate series")
        for previous in history:
            previous_items = evidence_by_basis(previous)
            by_id = {e.evidence_id: e for e in previous.evidence}
            for basis, item in incoming.items():
                if item.evidence_id in by_id and item != by_id[item.evidence_id]:
                    raise HistoryConflict("Evidence identity cannot rewrite an earlier observation")
                old = previous_items.get(basis)
                if (
                    old is not None
                    and old.source_data_time is not None
                    and (
                        item.source_data_time is None
                        or item.source_data_time < old.source_data_time
                    )
                ):
                    raise HistoryConflict("Late observations require a reconciliation policy")

    def append(
        self, owner_id: UUID, snapshot: DiscoverySnapshot, expected_revision: int
    ) -> DiscoveryEpisode:
        with self._lock:
            episode = self.episode(owner_id, snapshot.episode_id)
            if episode.revision != expected_revision or episode.lifecycle in (
                State.REJECTED,
                State.EXPIRED,
            ):
                raise HistoryConflict("Episode revision or lifecycle conflict")
            history = self._snapshots[episode.episode_id]
            self._validate_snapshot(episode, snapshot, history)
            updated = DiscoveryEpisode.model_validate(
                {
                    **episode.model_dump(),
                    "head_snapshot_id": snapshot.snapshot_id,
                    "evaluated_at": snapshot.evaluated_at,
                    "revision": episode.revision + 1,
                }
            )
            self._snapshots[episode.episode_id] = (*history, snapshot)
            self._episodes[episode.episode_id] = updated
            return updated

    def comparable_observations(self, owner_id: UUID, episode_id: UUID) -> int:
        history = self.snapshots(owner_id, episode_id)
        # S1 fixes the required comparison cohort. Additional independent sources can
        # be retained, but cannot manufacture a second observation of that cohort.
        bases = evidence_by_basis(history[0]).keys()
        keys: dict[str, set[str]] = {basis: set() for basis in bases}
        times: dict[str, set[datetime]] = {basis: set() for basis in bases}
        count = 0
        for snapshot in history:
            items = evidence_by_basis(snapshot)
            if all(
                items[basis].availability == "PRESENT"
                and items[basis].source_data_time is not None
                and items[basis].source_data_time not in times[basis]
                and items[basis].provenance.observation_key not in keys[basis]
                for basis in bases
            ):
                count += 1
                for basis in bases:
                    item = items[basis]
                    assert item.source_data_time is not None
                    times[basis].add(item.source_data_time)
                    keys[basis].add(item.provenance.observation_key)
        return count

    def transition(
        self,
        owner_id: UUID,
        episode_id: UUID,
        expected_revision: int,
        target: State,
        at: datetime,
        assessment: TransitionAssessment,
        rejection_reason: RejectionReason | None = None,
    ) -> DiscoveryEpisode:
        with self._lock:
            episode = self.episode(owner_id, episode_id)
            if episode.revision != expected_revision:
                raise HistoryConflict("Episode revision conflict")
            known_ids = {e.evidence_id for s in self._snapshots[episode_id] for e in s.evidence}
            if not set(assessment.evidence_ids) <= known_ids:
                raise HistoryConflict("Transition cites unknown evidence")
            if assessment.comparable_observations > self.comparable_observations(
                owner_id, episode_id
            ):
                raise HistoryConflict("Unsupported observation count")
            needs_fresh = (
                target in (State.NEW, State.CURRENT, State.DEFUNCT)
                or rejection_reason == RejectionReason.DEFUNCT_CONFIRMED
            )
            if needs_fresh:
                head = self._snapshots[episode_id][-1]
                if required_freshness(head, at, self.freshness_ttl_seconds) != FreshnessState.FRESH:
                    raise HistoryConflict("Stale/unknown history cannot prove a thesis transition")
            updated, event = transition(episode, target, at, assessment, rejection_reason)
            self._episodes[episode_id] = updated
            self._events[episode_id] = (*self._events[episode_id], event)
            return updated

    def candidate(
        self, owner_id: UUID, episode_id: UUID, as_of: datetime, ttl_seconds: int
    ) -> DiscoveryCandidate:
        with self._lock:
            episode = self.episode(owner_id, episode_id)
            head = self._snapshots[episode_id][-1]
            age = required_freshness(head, as_of, ttl_seconds)
            return DiscoveryCandidate(
                candidate_id=episode.candidate_id,
                owner_id=owner_id,
                episode_id=episode_id,
                revision=episode.revision,
                instrument=episode.instrument,
                intent=episode.intent,
                head_snapshot_id=head.snapshot_id,
                lifecycle=effective_state(episode, age, as_of),
                freshness=age,
                relevance=head.relevance,
                window=episode.window,
                evaluated_at=episode.evaluated_at,
                projected_at=as_of,
            )
