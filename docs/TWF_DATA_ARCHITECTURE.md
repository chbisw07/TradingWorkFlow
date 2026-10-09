# TradingWorkFlow (TWF) — Data Architecture

> **2026-09-29 S&D architecture acceptance:** The dated S&D extension below is **ACCEPTED / IMPLEMENTATION AUTHORIZED** within the [Sprint-2 delivery plan](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md). The [independent acceptance record](TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md) supersedes its 2026-09-28 proposal status. Sprint 2 is **ACTIVE / NEXT; implementation not started**. Earlier acceptance history and separate TI/TM/provider/security gates remain unchanged; proposal wording in the dated extension records its origin, not the current review status.

## Status
**TWF-0 accepted data baseline, with configuration ownership clarification dated 2026-09-25**

## 1. Purpose
Define TWF data ownership, persistence boundaries, repository abstractions, SQLite-to-PostgreSQL portability, auditability, and multi-user readiness.

## 2. Core Data Principle
> TWF persists TWF-owned workflow state and immutable references/captures required for UX/history; it does not silently become the authoritative store for TI, TM, broker, or scanner internals.

## 3. Data Ownership Classes
### TWF-owned durable data
- users/accounts;
- workspaces;
- preferences;
- watchlists;
- workflow/candidate state;
- service configuration;
- notification preferences;
- audit events;
- correlation/linkage records.

### External-authoritative data
- TI model/scientific artifacts;
- TM authoritative position/risk/authority state;
- broker order/fill/position truth;
- scanner-native internal state.

TWF may cache/reference external data but must preserve ownership/source.

## 4. Persistence Architecture
```text
Domain / Application Services
          ↓
Repository Interfaces
          ↓
Persistence Adapters
          ↓
SQLAlchemy 2.x
       /       \
   SQLite     PostgreSQL
```

Application services must not depend on database-specific behavior.

## 5. Initial Repository Interfaces
Potential repositories:
- UserRepository
- WorkspaceRepository
- WatchlistRepository
- WorkflowRepository
- CandidateRepository
- SettingsRepository
- ServiceConfigRepository
- AuditRepository
- NotificationRepository

Avoid creating repositories as ceremony where simple direct unit-of-work patterns are cleaner.

## 6. Core Entity Direction
Conceptual entities:
```text
User
Workspace
Watchlist
WatchlistItem
Candidate
Workflow
WorkflowStep / WorkflowEvent
ServiceConfiguration
UserPreference
Notification
AuditEvent
ExternalReference
```

Exact schema remains to be normalized during implementation design.

## 7. Identity Strategy
Prefer application-generated UUID/ULID-style identifiers for domain entities where stable cross-service identity is needed.

Separate:
- TWF IDs;
- TI IDs;
- TM IDs;
- broker IDs;
- scanner IDs.

Link them through explicit correlation/reference tables or value objects.

## 8. User / Workspace Ownership
All user-scoped records must carry explicit ownership through `user_id`, `workspace_id`, or a clear tenant/account relation.

Do not assume global singleton resources.

## 9. SQLite Development Rules
SQLite is allowed initially, but:
- no SQLite-specific SQL in domain/application code;
- avoid permissive typing assumptions;
- enforce foreign keys;
- use UTC/offset-aware timestamp discipline;
- test uniqueness/constraints explicitly;
- avoid concurrency patterns that will not translate to PostgreSQL.

## 10. PostgreSQL Production Direction
PostgreSQL becomes the production DB when:
- multi-user concurrency;
- cloud deployment;
- stronger locking/transactions;
- observability/backup;
- scaling;
- operational robustness
justify the migration.

Migration should primarily change configuration/infrastructure, not domain logic.

## 11. Schema Migrations
Use Alembic from the first persistent schema.

Every schema change should have:
- forward migration;
- downgrade policy where safe;
- test coverage;
- data migration note if semantics change.

## 12. Transaction Boundary
TWF should use explicit application transaction boundaries.

Do not attempt distributed transactions across TI/TM/broker services.

Use:
- local DB transaction;
- correlation IDs;
- idempotent remote actions;
- workflow state transitions;
- reconciliation.

## 13. Event / Audit Model
Audit events should capture meaningful TWF workflow transitions:
```text
candidate_created
ti_analysis_requested
ti_response_linked
sent_to_tm
risk_rejected
trader_approved
execution_requested
position_adopted
workflow_closed
```

Audit history should be append-oriented.

Do not confuse audit log with service event replication.

## 14. External References
Use typed external references:
```text
system = TI / TM / BROKER / SCANNER
entity_type
external_id
service_version / contract version where relevant
captured_at
```

## 15. Snapshot vs Reference
TWF may store:
### Reference only
when external service remains authoritative and current lookup is sufficient.

### Immutable snapshot/capture
when:
- trader saw the state and history must reproduce it;
- workflow decision depended on it;
- later IFL/audit needs exact evidence.

The policy should be explicit per object type.

## 16. Market Data
TWF should not become a market-data warehouse initially.

Persist only:
- workflow-relevant references/snapshots;
- cached display data if needed;
- derived UI state.

Dedicated market-data/history storage remains a separate concern.

## 17. Sensitive Data
Classify separately:
- user credentials/password hashes;
- session secrets;
- broker connection references/tokens;
- API secrets;
- subscription/billing data.

Sensitive secrets should not live in ordinary domain tables where avoidable.

## 18. Multi-Tenant Readiness
Future subscription deployment requires:
- tenant/user scoping;
- authorization on every scoped repository query;
- unique constraints that include tenant scope where appropriate;
- no cross-user cache leakage;
- migration path to tenant/account concepts.

The accepted TWF-1.4 foundation has persistent user identities. Personal settings may use explicit user ownership; shared tenant data requires verified account membership before exposure.

## 19. Caching
Do not make cache authoritative.

Possible later caches:
- service health;
- instrument metadata;
- user session data;
- scanner results;
- display snapshots.

Redis is optional and deferred until justified.

## 20. Retention
Define later by class:
- audit history;
- workflow history;
- console logs;
- notifications;
- snapshots;
- service events.

Do not retain sensitive/debug data indefinitely by default.

## 21. Backup / Recovery
Production PostgreSQL should support:
- automated backups;
- point-in-time recovery where justified;
- migration backup discipline;
- restore drills.

SQLite development DBs are disposable unless explicitly marked persistent.

## 22. Data Consistency
TWF must distinguish:
- current authoritative external state;
- last known external state;
- TWF workflow state;
- cached display state.

UI should expose staleness rather than pretending eventual consistency is immediate consistency.

## 23. Data Access Testing
Tests should cover:
- SQLite repository behavior;
- migration correctness;
- PostgreSQL compatibility before production;
- tenant scoping;
- idempotency;
- uniqueness;
- transaction rollback;
- external reference integrity.

## 24. Portability Acceptance
Before PostgreSQL migration is considered easy/valid:
1. no DB-specific domain logic;
2. repository/infrastructure boundary exists;
3. Alembic migrations are clean;
4. PostgreSQL integration tests pass;
5. concurrency-sensitive flows are reviewed.

## 25. Data Invariants
1. Ownership is explicit.
2. External authority is not silently copied.
3. TWF IDs and external IDs remain distinguishable.
4. Database choice is infrastructure, not domain semantics.
5. Audit history is append-oriented.
6. Secrets are isolated.
7. Staleness is representable.
8. Cross-service actions use idempotency/correlation, not distributed DB transactions.

## 26. Configuration Ownership and Revision Model

The [configuration architecture v0.6](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md) owns the full conceptual model. Keep principal identity, account/tenant ownership and role bindings separate. TWF-1.5 may implement personal settings without accounts; future account backfill must map verified ownership explicitly and test isolation, never assume every user belongs to one tenant or that user/account IDs are interchangeable.

Setting descriptors define typed values, schema versions, permitted scopes and override policy. Stored desired values, effective results, profile selections, applied revisions and health observations remain distinct. Profiles carry owner/scope, capability/schema identity and revision. An update uses an expected revision/ETag and an explicit transaction; reject stale writers. Reset removes an override, and validation is tied to exact revisions. HOT apply can be atomic; WARM apply needs a durable change record and recovery before integrations use it.

Plan versions/grants, rollout and configuration schemas evolve independently. Entitlement removal retains configuration inactive under retention policy, and restoration requires revalidation. Rollback records a compensating revision without deleting audit or restoring revoked rights. Provider upgrades require tested schema migrations preserving original values and provenance. Secret stores own values; settings contain authorized references only.

Queries, indexes, references, exports, jobs, caches and realtime topics include the applicable realm/account/user boundary. Cache keys also include configuration/policy/entitlement revisions where results depend on them. Define audit/profile/support/export/backup retention and account-deletion semantics before production sharing. Audit diffs and effective-value explanations are redacted. Alembic still owns DB evolution; configuration migrations are explicit semantic transformations, not startup auto-migration.

## 27. Broker Workspace Persistence Clarification — 2026-09-26

[Broker Workspace v0.3](TWF_BROKER_WORKSPACE_ARCHITECTURE.md) sections 9, 11–12, 15, 19 and 26 define the broker data boundary. TWF owns account configuration/secret references, immutable canonical/listing/derivative identities, versioned native bindings, TWF broker-watchlist membership, order intents, confirmation evidence, idempotency/dispatch claims, reconciliation progress and audit. Broker snapshots remain observations with source/as-of/received timestamps and completeness, never replacement execution truth. TM alone owns its managed-state records.

Canonical mapping is optional for a valid native order; native identity and current binding revision are mandatory. Symbol changes, token reuse and contract-term changes do not rewrite historical orders/fills. Broker order/fill IDs are scoped to provider, account and environment (and provider-defined reuse epoch when needed). External orders may have no TWF intent. Account deletion, retention and quota changes cannot erase unresolved commands or orphan exposure.

Before live submission, commit durable intent/confirmation/idempotency and an exclusive fenced dispatch claim before external I/O. No DB transaction spans broker network calls. Crash recovery treats possibly sent work as unknown and reconciles before considering another command; a stale worker cannot reclaim dispatch rights by itself. Reconciliation and audit survive process restart, backups and retention jobs. A bounded backend recovery loop is sufficient initially; no queue framework is mandated.

Alembic remains the schema authority. Test uniqueness, optimistic concurrency, rollback, worker fencing and restart recovery on PostgreSQL before live use, with SQLite as the development/test path. BW-1 can use immutable deterministic fixtures without new broker tables; durable persistence becomes mandatory at the specific later gates in the Broker Workspace architecture.


## 28. Discovery data ownership and immutable history — 2026-09-28

For new discovery work, section 6's generic Candidate becomes the distinct
[Opportunity-domain objects](TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md), not a schema
rename. TWF owns scan definitions/profile revisions, run/attempt records,
normalized match captures, discovery decisions (including declined nominations),
intents, episodes, immutable S1…Sn snapshots, relevance/lifecycle decisions,
annotations and configuration references. Providers retain authority over source
facts/native algorithms; TI/TM/broker ownership in sections 2–3 remains unchanged.

Stable underlying identity is distinct from venue listing, derivative contract and
broker-native execution identity. Ambiguous cross-source mappings cannot merge by
symbol. One subject can support multiple intents/horizons and recurring episodes;
terminal rejection is never undone. At least two comparable distinct observations
are necessary for evolution; repeat delivery of the same data is not a new sample.

Snapshots preserve original source, availability, received and evaluation times,
units, quality, evidence lineage/dependence, market context and exact policy/profile
versions. Corrections append superseding records. Persist snapshot/event/head-CAS
atomically; enforce active-episode uniqueness and reject late generations. Provider
calls stay outside write transactions. GET derives time-based freshness/expiry
without hidden commits. Test SQLite and PostgreSQL contention/restart semantics.

Licensed raw captures, normalized evidence, decision history and future evaluation
labels have separate explicit retention policies selected before production. Keep
audited tombstones/references when deletion or licensing prevents full replay;
never claim complete reproducibility afterward. No broad market-data warehouse is
introduced, and ephemeral Broker V2 LTP caches are not historical scanner data.
Future evaluation must include untraded candidates and missing/censored outcomes.

The [S&D persistence design](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md) is proposed;
no tables/migrations are created here. Alembic and existing ownership/session
boundaries remain mandatory. The data DOCX companion needs post-acceptance regeneration.

### Revision history addition

| Revision | Date | Status | Role / change |
| --- | --- | --- | --- |
| S&D reconciliation 1 | 2026-09-28 | PROPOSED / RECONCILED / READY FOR REVIEW | Normative design/planning extension: Discovery data ownership and immutable history; prior history and acceptance preserved |
| S&D acceptance 1 | 2026-09-29 | ACCEPTED / IMPLEMENTATION AUTHORIZED | Independent S&D architecture acceptance; staged Sprint-2 scope only, no runtime delivery or prior milestone change; see [review](TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md) |

## 29. Offline instrument metadata snapshots — 2026-10-09

TWF owns a project-local, offline NSE instrument metadata harvester under
[`tools/market_metadata/`](../tools/market_metadata/README.md). The harvester
uses the official NSE bulk equity list for instrument identity, an optional bulk
NSE/NSE Indices classification file, and optional Yahoo enrichment. Yahoo is not
a runtime Scanner or Watchlist dependency. The unreliable NSE per-symbol
quote-equity endpoint is outside this workflow.

Each validated snapshot carries one schema version, run identifier, and dataset
generation timestamp while retaining independent source/as-of provenance for
sector, industry, market cap, NSE classification, and TWF analytical benchmark
mapping. Relative rank/category metadata is generated only for full-universe
runs. Context benchmarks use exact mappings and do not assert official index
membership. Rights entitlements retain their own instrument identity and may
inherit company metadata from an exact resolved underlying.

Operational CSV, unresolved, summary, checkpoint, partial, and temporary files
live under ignored `var/market_metadata/`. Source code, documentation, and tiny
deterministic fixtures are tracked. The runtime importer independently validates
an accepted snapshot before transactionally upserting system-global current state
into `instrument_metadata`; `instrument_metadata_refreshes` retains import audit
status. No user, broker, or provider-session ownership is attached. Missing rows
are retained and marked outside the latest snapshot, and a successful dataset run
is idempotent.

The read-only instrument metadata service supports bounded symbol/ISIN lookups,
sector and context-benchmark resolution, and last-refresh status. Authenticated
API routes expose those bounded reads; import remains an explicit local CLI and
accepts no public filesystem path. Scanner V2 and Watchlists now consume this
same provenance-bearing service through one bounded bulk lookup per response.
Sector is visible by default, while industry, market cap, stored size bands, the
TWF analytical tier, and analytical context benchmark remain in detail views.
Stale rows retain explicitly labelled last-known metadata and missing values stay
unknown. Derivatives use metadata only when their canonical underlying is exact;
indices do not receive invented company metadata. These display enrichments do
not change Scanner matching, Market Context ranking, or Watchlist trading, and no
application request invokes Yahoo, NSE, or the harvester. Dynamic Sector Context
remains future work.
