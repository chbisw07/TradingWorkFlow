# S2-1 Domain Contracts & Synthetic Provider Foundation

> **Current status — 2026-09-29: ACCEPTED / FROZEN.** The [focused independent re-review](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_REREVIEW.md) closes S21-01/02/03 and records `GO_S2_2`. S2-2 Internal Scanner V0 is ACTIVE / NEXT; later slices remain pending. This is milestone acceptance, not a new Git commit/tag. The implementation/remediation account below retains its pre-review claims and gate history.

**2026-09-29 — IMPLEMENTED / REMEDIATED / READY FOR RE-REVIEW.** Sprint 2 remains ACTIVE.
This record supplies implementation evidence, not independent acceptance. The next
review must decide `GO_S2_2` or `HOLD_S2_1`; no freeze is claimed.

## Preflight and authority

Implementation started on `main` at
`7704261c6387c9de420ccf7c564e952bce6a72c4`, with a clean worktree.
The accepted architecture tag `twf-scan-discover-architecture-v0.2` resolves to
`6db608c`; the [independent architecture review](TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md)
records `GO_S2_SD_IMPLEMENTATION`. Broker V2 remains accepted/frozen under
`twf-broker-v2` at `69a643e`. No commits, tags, pushes or branch changes were made.

Governing semantics remain in the [S&D architecture](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md),
[opportunity domain](TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md) and
[accepted delivery plan](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md).
The README's later, user-approved S2-0…S2-8 milestone breakdown refines the delivery
plan's original S2-0…S2-6 grouping. S2-1's scope is unchanged. In current tracking,
market context is S2-4, discovery evaluation is S2-5, optional LLM is S2-6,
persistence/history/settings/product UX is S2-7, and final acceptance is S2-8.
The older plan groups discovery/history at S2-4, interpretation/settings at S2-5,
and UX/acceptance at S2-6. Its dependency and external-provider gates still apply;
this implementation does not waive or rewrite them. Dated architecture-review
statements that implementation had not started remain historical evidence.

## Scope and placement

One backend package, `twf.discovery`, establishes immutable contracts, guarded
lifecycle operations, five deterministic synthetic adapters and direct-call proofs.
It has no FastAPI routes, app-startup registration, database tables or migrations.
The accepted plan defers durable discovery history: S2-1 therefore uses an explicitly
in-memory repository rather than speculative SQL schema.

| New source file                                            | Responsibility                                                                                                    |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| [**init**.py](../apps/api/src/twf/discovery/__init__.py)   | Package boundary                                                                                                  |
| [domain.py](../apps/api/src/twf/discovery/domain.py)       | Identities, intent, horizon/window, evidence, relevance, scan, episode/snapshot/candidate and tolerance contracts |
| [lifecycle.py](../apps/api/src/twf/discovery/lifecycle.py) | Pure transition validation and immutable transition events                                                        |
| [memory.py](../apps/api/src/twf/discovery/memory.py)       | Owner-scoped history, immutable append, revision conflicts and projection                                         |
| [providers.py](../apps/api/src/twf/discovery/providers.py) | Provider protocols, envelopes and capability/version/error boundary                                               |
| [synthetic.py](../apps/api/src/twf/discovery/synthetic.py) | Fixed-universe synthetic providers                                                                                |
| [service.py](../apps/api/src/twf/discovery/service.py)     | Fixture-only orchestration; deliberately absent from public app composition                                       |

**Existing runtime source files modified: none.** No dependency, lockfile,
configuration, frontend, broker, TI or TM source was modified.

## Domain semantics

- `UnderlyingIdentity` and `InstrumentIdentity` preserve source-native references,
  mapping revision and exact listing identity. No broker catalog or identity is
  imported. Separate intents can coexist for one underlying/listing.
- `DiscoveryIntent` has direction, objective, setup family and a canonical semantic
  fingerprint. Intent identity remains separate from episode identity.
- `HorizonSpec` is the accepted canonical name; `TimeHorizon` is an alias. Named
  presets and custom elapsed, trading-session, calendar and event-relative ranges
  are representable. Calendar/event references and time zones are explicit. This
  does not calculate exchange sessions or silently reinterpret legacy horizon strings.
- `OpportunityWindow` is a fixed interval. Refresh cannot move it. The episode key
  pins owner, exact instrument, observation basis, intent semantics and policy series.
- `DiscoverySnapshot` freezes identity, sequence/predecessor, evidence, producer,
  observed/source/evaluated/recorded times and relevance. Nested contracts are frozen
  and collections are tuples. A later capture cannot overwrite S1; a canonical
  content hash supports comparison.
- Evidence carries structured measures/units, availability, category, polarity,
  provenance, source timing, citations and grounding. All ten requested categories
  and `GROUNDED`, `PARTIALLY_GROUNDED`, `CONTEXT_ONLY` are represented. Missing or
  unknown source time remains explicit; reception time does not make old data fresh.
- `DiscoveryRelevance` is attention relevance, never probability of profit.
  Decimal values are rounded HALF_UP to two decimal places **before** banding:
  LOW ≤ 0.60, MEDIUM ≤ 0.90, HIGH > 0.90. Thresholds are versionable contract inputs.
  Missing required inputs produce a null score/band, not zero. Band/displayed value
  are derived properties; the serialized contract preserves the underlying value,
  policy and thresholds.
- `CandidateToleranceEnvelope` represents typed dimensions, reference basis,
  criteria, confirmation and recovery-policy references. No calibrated tolerance
  evaluator or indicator engine is introduced.
- Scan definition/profile/run/match contracts pin owner, definition revision,
  request, safe typed criteria, source mode, timeframe and required capabilities.
  Flat ALL/ANY expressions are data contracts; this is not an executable query DSL.

## Lifecycle and in-memory proof policy

Durable states are NEW, CURRENT, DEFUNCT, EXPIRED and REJECTED. STALE is a read
projection over CURRENT when required freshness is lost; missing evidence never
proves deterioration. Effective precedence is REJECTED, EXPIRED, DEFUNCT, NEW,
then CURRENT/STALE. Reads do not mutate history.

The fixture policy is `synthetic-discovery-proof` version `1`: required evidence
TTL is 300 seconds, relevance is a fabricated fixed `0.75` only when those inputs
are fresh, and recurrence cooldown is 60 seconds. These are proof fixtures, not
approved market policies. Two distinct comparable source observations are required
for CURRENT. Repeated polling, repeated source timestamps or reissued observation
keys cannot manufacture evolution. Changed producer version, normalization version,
measurement units/basis or identity cannot silently extend the same series.

Material breach and verified recovery require explicit assessments and fresh cited
history. User dismissal requires the owning actor. Expiry prevents recovery;
REJECTED never reopens. A subsequent nomination must link the latest closed episode,
wait the cooldown and supply a genuinely later observation. An expired projection
must be explicitly closed before recurrence. Rejection reason is preserved separately.
Saved/reviewed interaction state is not a lifecycle state and is deferred with UX.

Repository operations use a process-local lock and expected revisions. Snapshot/head
append is atomic; transition/head/event update is atomic. Assessments are trusted
application-policy inputs with structural, ownership, citation and freshness checks;
S2-1 does not implement production breach/confirmation evaluation. The fixture flow
performs append and any promotion as separate repository operations. This is **not**
a durable, multi-worker transaction protocol. Production persistence must atomically
commit capture/evaluation/head/event as required by the accepted architecture, and
prove crash/retry/concurrency behavior before exposing a production discovery API.

## Provider contracts and existing-foundation reuse

Ports: `UniverseProvider`, `CandidateSource`, `ScanProvider`,
`MarketIntelligenceProvider`, `CandidateIntelligenceProvider`. A future optional
`LLMService` protocol is declared only; it is neither bound nor called.

The package reuses TWF-1.6 `Contract`, `Identifier`, `RequestContext`, `ErrorCode`,
`Health` and `DeploymentMode`, and TWF-1.5 `CapabilityPolicy`. Its manifests and
batches carry domain capability/schema versions rather than extending or pretending
to implement the finite `foundation.health.v1` protocol. `ProducerIdentity` is a
versioned domain producer reference, not a competing service registry. There is no
new configuration store, generic client framework or secret handling.

The operation boundary checks enablement and owner permission before invocation,
contract version, advertised capability, result ownership/correlation/producer,
source mode, item limits and typed structure. Permission is rechecked after awaiting
the provider. Batches distinguish COMPLETE/PARTIAL and carry limitation/cursor fields.
Optional partial enrichment is explicitly reported and cannot change core score or
state. No fallback silently changes producer identity.

Existing errors cover `UNSUPPORTED_CAPABILITY`, `SERVICE_UNAVAILABLE` (provider
unavailable), `TIMEOUT`, `AUTHENTICATION_FAILED`, `AUTHORIZATION_FAILED`,
`CONTRACT_MISMATCH` and `INVALID_RESPONSE`. Domain codes add invalid request,
stale data, rate limit, provenance mismatch and cancellation vocabulary. Failures
carry safe code, provider, operation and request identity without vendor exception text.
Cancellation propagates; cooperative async deadlines are bounded to at most ten
seconds. This local guard is not an HTTP transport, response-byte limiter or a
preemptive deadline for blocking adapters. Those controls belong to future external
adapter gates. Local deployment metadata does not replace synthetic provenance.

## Synthetic proofs

All providers use fixed UUID-derived identities, caller-controlled UTC time and
explicit SYNTHETIC provenance. The universe is SYNTHETIC-HAL, SYNTHETIC-BEL,
SYNTHETIC-HINDALCO and SYNTHETIC-KAYNES on exchange `SIM`, segment `FIXTURE`.
No current prices or real instruments are represented.

1. **Scan only:** synthetic universe → one supported ordinal GTE criterion →
   deterministic matches, without creating discovery history. Unsupported operators,
   combinations, metrics, timeframes or identities fail explicitly. The contract's
   wider expression vocabulary does not claim adapter support.
2. **Scan + discovery:** matches normalize to `CandidateInput`; S1 creates NEW,
   a later comparable S2 produces CURRENT; S1 bytes remain unchanged.
3. **Discovery without scan:** `SyntheticCandidateSource` nominates an input with
   no scan-match reference and the same episode/snapshot semantics.
4. **Optional enrichment:** fabricated neutral market context, normal volatility,
   sector-strength measure and deterministic candidate annotation are returned
   separately. Missing, failed or partial providers remain visible. No LLM is needed.

## Tests and validation

Exact new test files:

| File                                                                         | Evidence                                                                                                                                                                                                            |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [discovery_support.py](../apps/api/tests/discovery_support.py)               | Fixed clock, owner identities, grants, intent/window/run builders; no environment/database dependency                                                                                                               |
| [test_discovery_domain.py](../apps/api/tests/test_discovery_domain.py)       | Horizon/time/evidence validation, immutable values, relevance boundaries/nulls, tolerance and identities                                                                                                            |
| [test_discovery_providers.py](../apps/api/tests/test_discovery_providers.py) | Five provider contracts, typed wire round-trips, health/capability/version checks, denied/revoked permission, bounded timeout, malformed output and sanitized failures                                              |
| [test_discovery_flows.py](../apps/api/tests/test_discovery_flows.py)         | Three composable flows, deterministic S1/S2, stale/expiry projection, legal/illegal transitions, terminal recurrence, isolation/CAS, concurrent append, incomparable observations and optional-provider degradation |

No existing tests were modified. Synthetic provider/flow tests reject socket
connections; no live broker, LLM, MCP or market-data calls were made.

Initial implementation and independent review recorded **489 passed** (394 prior
backend tests plus 95 original S2-1 cases). Post-remediation validation from `apps/api`:

- `pytest -q`: **518 passed** (394 prior backend tests plus 95 original S2-1 cases and 29 remediation cases).
- `ruff check src tests alembic`: passed.
- `ruff format --check src tests alembic`: passed.
- Strict `mypy`: passed.
- `python -m compileall -q src tests`: passed.
- `python -m pip check`: passed.
- Offline package build: `python -m pip wheel --no-build-isolation --no-deps --no-index . -w /tmp/twf-s21-remediated-wheel`: passed.
- README and new implementation-record Prettier checks: passed. The documentation
  index has a pre-existing whole-file Prettier warning (also reproduced from HEAD);
  its existing table style is preserved to avoid unrelated formatting churn. All
  three changed Markdown files and the preserved acceptance review parse, local
  links resolve, and `git diff --check` passes.

Broker V2 regression evidence is the unchanged broker implementation plus the full
existing backend suite, using fake transports. No live trading smoke was performed.
No schema/persistence, frontend or container configuration changed: additional
PostgreSQL migration, frontend browser/build and Docker smoke checks were not run.
The API package build verifies inclusion of the new modules. No dependency was added;
no network vulnerability audit or real credential access was needed.

Documentation changes are this new record, README status/link and documentation
index registration. Sequencing is unchanged; older accepted planning/acceptance
records remain historical. No DOCX file was changed.

## Focused remediation after independent HOLD — 2026-09-29

The [independent acceptance review](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_ACCEPTANCE_REVIEW.md)
returned `HOLD_S2_1`. It remains unchanged historical evidence. This remediation
addresses only S21-01, S21-02 and S21-03 and requests independent re-review;
it does not accept/freeze S2-1 or authorize S2-2.

Remediation began on `main` at the same HEAD recorded above. The incoming worktree
contained the seven S2-1 source modules, four test/support files, implementation
record and acceptance review as untracked files, plus README/index updates.
There were no unrelated runtime changes. Relative to that incoming state, this
remediation modifies only `domain.py`, `providers.py`, `memory.py`, `synthetic.py`,
`service.py`, README, the index and this record. It adds only
[test_discovery_remediation.py](../apps/api/tests/test_discovery_remediation.py).
Original tests, `lifecycle.py`, `__init__.py`, broker code and dependencies are unchanged.

### S21-01: operation-owned validation and coherent provenance

`ProviderAccess` selects the expected versioned operation schema before invoking
the provider; the returned model's generic specialization cannot choose its own
schema. The five mappings are universe → `InstrumentIdentity`, scan → `ScanMatch`,
candidate source → `CandidateInput`, and market/candidate intelligence →
`DiscoveryEvidence`, each within `ProviderBatch`. Invalid items, absent required
fields and malformed structures produce `ProviderFailure(INVALID_RESPONSE)`;
contradictory identities/modes produce `PROVENANCE_MISMATCH`. Errors preserve
operation, declared provider and request correlation, without raw adapter exceptions.
The proof orchestration also rejects partial core batches and mismatched scan
run/definition/profile/configuration or enrichment subject scope through typed errors.

The batch producer must match the declared provider; each result item's own producer
and source mode must match its batch. A SYNTHETIC deployment cannot claim real data.
Nested contributed evidence retains its own producer/source identity. Synthetic and
real source modes cannot be mixed; evidence attributed to the batch producer must
also use the batch mode. A distinct upstream producer may retain a different real
freshness mode (for example DELAYED evidence in an EOD result). Thus valid upstream
contributions remain representable without weakening result provenance. These are
contract proofs with local test doubles, not real data integrations.

### S21-02: comparable evidence and replay-safe observation counting

The S1 evidence cohort anchors continuation. Each basis includes subject, category,
observation basis, nested producer/version/schema, source reference/revision,
source mode, transformation/version, dependence group and measurement names/units.
Measurement values, observation keys, evidence IDs and timestamps may change without
changing that compatibility basis. The outer producer/source/mode/normalization and
scan configuration context must also remain compatible. Existing episode identity,
intent, window, sequence, ownership and revision guards remain in force.

Later captures must retain every S1 basis. Replacing a required producer/source,
normalization or configuration rejects the append without mutating history; such
input needs a separate compatible series, not an implicit continuation. Duplicate
bases are rejected as ambiguous. Reusing an evidence ID with changed contents is
rejected. Known per-basis source times cannot regress or become unknown.

A capture counts only when **every S1 basis** is PRESENT and has both a known source
time and observation key not already counted for that basis. New envelope time,
input ID, evidence ID or outer observation key alone cannot supply S2. Replays are
retained as immutable audit captures but do not increment the comparable count or
promote NEW to CURRENT. New independent evidence can accompany that cohort and is
preserved, but cannot substitute for a second observation of the original cohort.
This conservative fixture policy is not a production multi-source fusion algorithm.

Snapshot time summaries must agree with evidence: `observed_at` is the latest
nested observation time; `source_data_time` is the earliest nested source time
when all are known, otherwise null. Fabricated envelope summaries fail validation.
Promotion still requires freshness; rejection/recurrence and lifecycle semantics
remain covered by the unchanged original tests.

### S21-03: immutable input and scan lineage

`CandidateLineage` retains input ID, owner, producer and source reference on every
snapshot, including discovery without scan. Optional `ScanLineage` preserves run
ID, match ID, definition ID/revision, the typed profile reference (including schema
and applied revisions), and a canonical SHA-256 configuration fingerprint. The
fingerprint covers the normalized definition and profile, including criteria;
it excludes per-observation run IDs and cutoff times. Comparison excludes run/match
IDs while retaining configuration context, permitting later runs of the same
configuration and rejecting silent configuration changes.

The synthetic scanner fills those references; `scan_input` carries them through
`CandidateInput`; discovery captures them in `DiscoverySnapshot`. Scan-match and
lineage references must agree, profile ownership is checked, and snapshot source
and producer must agree with its lineage. Nested values are frozen typed contracts;
no raw provider payload or mutable configuration dictionary is stored in snapshots.

### Focused regression evidence

The new test module adds **29 cases**: wrong generic/item schemas across all five
operations, downstream scan safety, typed provenance failures, valid upstream
contributions, incompatible nested provenance, replay/reissued keys, forged summary
times, genuine continuation, additional independent evidence, full S1/S2 scan lineage,
configuration changes and immutable/non-scan lineage. Socket access is prohibited
in these tests. All **95 original S2-1 tests** remain unchanged and pass.

## Implementation evidence checklist

These are implementation claims for independent verification, not self-acceptance.

```ini
DOMAIN_CONTRACTS_IMPLEMENTED = YES
PROVIDER_CONTRACTS_IMPLEMENTED = YES
SYNTHETIC_UNIVERSE_PROVIDER = YES
SYNTHETIC_SCAN_PROVIDER = YES
SYNTHETIC_MARKET_CONTEXT_PROVIDER = YES
SYNTHETIC_CANDIDATE_INTELLIGENCE_PROVIDER = YES
SCAN_ONLY_FLOW_PROVEN = YES
SCAN_DISCOVERY_FLOW_PROVEN = YES
DISCOVERY_WITHOUT_SCAN_PROVEN = YES
SNAPSHOT_IMMUTABILITY_PROVEN = YES
DISCOVERY_EPISODE_MODEL_PROVEN = YES
LIFECYCLE_TRANSITIONS_PROVEN = YES
RELEVANCE_SEMANTICS_PROVEN = YES
PROVENANCE_PRESERVED = YES
CAPABILITY_NEGOTIATION_PROVEN = YES
TYPED_FAILURES_PROVEN = YES
NO_EXTERNAL_PROVIDER_REQUIRED = YES
NO_LLM_REQUIRED = YES
NO_BROKER_AUTHORITY_ADDED = YES
BROKER_V2_REGRESSION_FREE = YES
TESTS_PASS = YES
READY_FOR_S2_1_REREVIEW = YES
```

## Deferred work and next gate

Architecture deviations: **NONE**. The deliberately in-memory and fixture-only
boundaries follow S2-1 scope; they must not be deployed as a production evaluator.

Deferred: Internal Scanner V0 and real data/calendar policies, TradingView MCP or
other real adapters, production context/relevance/tolerance/lifecycle computation,
durable transaction/history/retention semantics, settings UI, product API/UX,
optional LLM integration and final browser/container acceptance. Provider/data/policy
approvals still precede their dependent slices.

There is no trade construction, broker execution, TI/TM integration, LOB, alerts,
continuous monitoring, realtime stream, production ML or IFL runtime in this change.
An independent S2-1 remediation re-review is next; S2-2…S2-8 remain PENDING.
