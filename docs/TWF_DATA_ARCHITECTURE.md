# TradingWorkFlow (TWF) — Data Architecture

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
