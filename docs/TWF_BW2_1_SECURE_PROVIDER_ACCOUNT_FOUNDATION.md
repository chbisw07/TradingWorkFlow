# TWF BW-2.1 — Secure Provider / Account Foundation

## Status

**REMEDIATED / PENDING INDEPENDENT RE-REVIEW — 2026-09-26**

The initial independent review returned `HOLD_BW2_1`. The bounded fixes below
address its seven findings; they do not constitute acceptance or authorization for
BW-2.2. BW-1 remains accepted/frozen.

BW-2.1 establishes the provider/account security and persistence boundary required by
the [BW-2 Zerodha plan](TWF_BW2_ONE_REAL_BROKER_READ_ONLY_PLAN.md). It does **not**
enable real Zerodha connectivity. There is no login redirect, callback, token
exchange, provider HTTP transport, catalog download, market/account read, or broker
command endpoint. Zerodha remains `connectable=false`, `commands=false`, and
`trading_enabled=false`.

Starting repository state: branch `main`, HEAD
`44e53d5a30f13d4c3ad6fc66da192db828fec5c4`, with BW-1 accepted/frozen at annotated
tag `twf-bw1-synthetic-broker-readonly`. The expected uncommitted BW-2 v0.2 planning
and status-reconciliation documents were present; no unrelated change was found.
No commit, tag, or push is part of this implementation.

## Bounded implementation

| Requirement                                          | Artifact                                                                                                                 | Verification                                                                                        |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- |
| Provider-neutral secret boundary                     | `twf.secrets.SecretStore`, `SecretScope`, opaque `StoredSecret`, redacted `SecretValue`                                  | Deterministic create/read/exists/delete, wrong-scope denial, repr/log redaction tests               |
| Safe local store and production fail-closed behavior | `MemorySecretStore` for explicit development/test environments; `UnavailableSecretStore` in production without injection | Default production denial plus explicit dev-store injection rejection tests                         |
| Explicit operation permissions                       | `BrokerPermission`, `PersonalBrokerPermissionPolicy`                                                                     | Owner-only read/configure/connect/disconnect; trade/cancel-modify/resolve-unknown always denied     |
| Durable provider/account/connection/audit state      | SQLAlchemy models and Alembic `0004_broker_foundation`                                                                   | Fresh/repeat upgrade, downgrade/re-upgrade, metadata diff, SQLite and offline PostgreSQL SQL checks |
| Zerodha provider registration                        | Immutable provider-neutral registry and seeded provider-configuration row                                                | Auth method metadata, LIVE-only mode, read/catalog capability, command/connect/trading false tests  |
| Revision/generation primitives                       | Optimistic account configuration update; internal secret-reference replacement and local invalidation fencing            | SQLite/PostgreSQL CAS races, stale conflicts, rollback, cleanup failure and audit tests             |
| Ownership and IDOR                                   | Existing authenticated user/session dependency plus owner-scoped queries and policy                                      | Cross-user list isolation, configuration 404, secret-reference attachment denial                    |
| Foundation API                                       | `GET /api/v1/broker-providers`, `GET/POST /api/v1/broker-accounts`, `PATCH /api/v1/broker-accounts/{id}/configuration`   | Authentication, Origin/CSRF, validation, no-store and OpenAPI tests                                 |
| BW-1 preservation                                    | Existing broker service and `broker.read.v1` untouched                                                                   | Alpha A1/A2, Beta B1, room/overview, aggregation, states and isolation regression suite             |

## Secret-store architecture

`SecretStore` exposes `put`, `get`, `exists`, and `delete`, plus an explicit
`production_safe` composition capability. Every reference has an immutable
`owner_user_id + provider_id + broker_account_id + environment + connection_generation`
scope. A new candidate for an account at generation N is stored for target N+1. The returned reference is
opaque. Secret values use a wrapper whose string and representation are always
redacted. Broker relational records can contain an opaque reference and metadata;
they have no API-secret or access-token column. API response models contain neither
the reference nor the value.

`MemorySecretStore` is process-local and suitable for development/test only; it is
not durable and is not a vault. `create_app` validates the selected store before
application initialization. Production rejects `MemorySecretStore` (including a
subclass trying to override the capability), as well as any injected store without
an explicit `production_safe=True` capability. Production without an injection
uses `UnavailableSecretStore`, whose operations remain unavailable rather than
falling back to memory. A future approved production adapter must implement the
same immutable-scope contract and declare its capability; the marker is a composition
contract, not independent vault certification. BW-2.1 adds no production vault.
Even an injected store would not make Zerodha connectable in this slice because no
connect/auth route or provider transport exists.

## Permission and capability boundary

Permissions are operation-specific and checked server-side against the authenticated
personal owner:

| Permission               | BW-2.1 policy                                                            |
| ------------------------ | ------------------------------------------------------------------------ |
| `broker.read`            | owner only                                                               |
| `broker.configure`       | owner only                                                               |
| `broker.connect`         | modeled for future internal use; owner only; no public connect operation |
| `broker.disconnect`      | modeled for future local fencing; owner only; no public endpoint         |
| `broker.trade`           | denied                                                                   |
| `broker.cancel_modify`   | denied                                                                   |
| `broker.resolve_unknown` | denied                                                                   |

LIVE mode, enabled/configured state, subscription, provider support, or an application
role cannot elevate these permissions. The provider response independently reports
supported/configured/connectable/trading dimensions. Thus the repository can truthfully
say “Zerodha supported” while saying “real connection unavailable.” Shared account and
delegated role semantics remain deferred.

## Persistence and migration

Alembic revision `0004_broker_foundation` adds:

- `broker_provider_configurations`: provider enable/configuration revision and optional
  opaque platform secret reference; seeded Zerodha row remains disabled/unconfigured;
- `broker_accounts`: immutable TWF UUID, personal owner FK, provider/environment,
  nullable pre-binding provider account ID, LIVE mode, label, enabled/configured,
  configuration revision and connection generation;
- `broker_connections`: separate authentication state, read health, applied revision,
  opaque secret reference/version, expiry and read/failure observations;
- `broker_audit_events`: append-oriented safe action metadata, revisions, generation,
  correlation request ID and outcome, without raw secrets or secret references.

Constraints cover ownership/provider relations, provider/environment/external-account
uniqueness, owner/provider/label uniqueness, positive revisions, nonnegative generations,
and LIVE-only real account mode. SQLAlchemy metadata and the migration are aligned.
The design uses portable UUID, string, Boolean, integer and timezone-aware timestamp
types supported by SQLite and PostgreSQL. Application startup still never creates or
migrates schema.

Configuration begins at revision 1 and generation 0. A configuration mutation uses
an expected revision and atomically increments only that revision. Reads are
non-mutating. Connection mutation remains an internal primitive, with a required
keyword-only `expected_generation`; no new HTTP mutation route was added.

Both reference replacement and local invalidation authorize the owner, end the read
transaction, and execute a database compare-and-swap equivalent to:

```sql
UPDATE broker_accounts
SET connection_generation = connection_generation + 1, updated_at = :now
WHERE id = :account AND owner_user_id = :owner
  AND environment = :environment AND connection_generation = :expected;
```

Exactly one affected row is required; zero rows means a typed 409 conflict and
rollback. The account write lock remains held until the connection state and audit
record commit in the same transaction. The audit records the refreshed, committed
resulting generation. There is no process-local locking. Two writers using N cannot
both succeed: one commits N+1 and the other conflicts. A failed mutation rolls back
the generation and audit together.

Replacement accepts only a reference whose exact immutable store scope targets N+1.
After commit, the old N reference is no longer eligible for attachment and physical
deletion is attempted. Disconnect commits N+1 with no active reference, then attempts
to delete the previous reference. A transaction failure does not delete the previous
active secret. A stale reference cannot be relabelled for a later generation.

If physical deletion fails, the committed generation still revokes the reference at
the application boundary; reuse is rejected even with a fresh expected generation.
A constant `broker_secret_cleanup_failed` warning reports the cleanup failure without
rendering the exception, secret or reference. Successful database mutation is not
rolled back or reported failed merely because cleanup failed. A retained value may
still exist in the low-level store under its historical scope until cleanup; it is
not an eligible active application credential. No automatic cleanup worker or claim
of guaranteed physical erasure during an outage is made in this slice. Production
vault operation/recovery remains a later prerequisite.

No schema change was needed: the existing durable account generation is the fence,
and secret scope metadata belongs to the store. Alembic `0004_broker_foundation` and
accepted migration history were not changed by remediation.

## API and security properties

All foundation APIs require the accepted server-owned TWF session. Mutations also
require an allowed Origin through the existing authentication control. Account lists
are owner-filtered. A foreign account configuration attempt returns the same 404
surface as an unknown account. Inputs are bounded and strict; configuration updates
use optimistic concurrency. POST and PATCH use one `AccountLabel` contract that trims
before checking length/content: `" Alpha "` becomes `"Alpha"`, while whitespace-only
values return 422. Service methods consume that normalized contract directly.
Uniqueness conflicts during either flush/commit or the PATCH UPDATE roll back and
return the canonical 409 envelope, without SQL or constraint details. Responses are `no-store` and exclude secret references,
raw secrets, provider credentials, and provider-account identity before verified
future binding.

The OpenAPI surface deliberately contains no broker `/connect`, `/callback`, `/token`,
remote logout, command, order mutation, or provider-read endpoint. CORS permits the
new authenticated `POST` and `PATCH` methods for explicitly configured origins while
remaining credential-disabled at the generic CORS layer; application sessions and
Origin enforcement remain the accepted same-origin/proxy model.

## Provider metadata compatibility

The shared auth vocabulary is `BROWSER_REDIRECT_CALLBACK`, `API_KEY_SECRET`,
`OAUTH_AUTHORIZATION_CODE`, `MANUAL_TOKEN`, or `NONE`. Zerodha declares
`BROWSER_REDIRECT_CALLBACK`; no auth flow is implemented. Independent boolean
`read`, `catalog`, `search`, and `commands` flags can describe other providers without
changing the shared model. Zerodha declares true/true/true/false. The registry is
read-only and no second provider is registered. Capability metadata does not grant
permissions: command permissions and actual trading remain denied.

This changes only the unaccepted BW-2.1 metadata response: `KITE_REQUEST_TOKEN` is
replaced by the generic auth category and `catalog_search` becomes independent
`catalog` and `search` flags. Frozen `broker.read.v1` contracts are unchanged.

## Explicit non-goals retained

BW-2.1 does not implement Zerodha login, `request_token`, token exchange, profile,
holdings, positions, orders, funds, instrument catalog/search, watchlists, order
draft/preview, trading, cancellation/modification, streaming, paper trading, shared
accounts, billing, Scanner, TI, TM, or LLM behavior. No provider network dependency or
SDK was added. `broker.read.v1`, its three synthetic accounts, the unified overview,
and the responsive Broker Workspace remain unchanged.

## Initial validation evidence (before independent review)

These original checks passed but did not prove concurrent fencing, supersession,
or safe explicit production injection. The independent review found those gaps.
Historical validation completed on 2026-09-26:

- backend: 250 Pytest tests passed; Ruff lint and format checks passed; strict mypy
  passed across 54 source files; Python compilation and `pip check` passed;
- frontend: 89 Vitest tests across 12 files passed; TypeScript, ESLint and Prettier
  checks passed; the production build passed;
- browser regression: the combined Chromium and WebKit Playwright matrix passed all
  108 tests across both themes and the 390, 768, 1024, 1440, 1920 and 2560 pixel
  projects;
- contracts and migrations: OpenAPI constructed with 20 paths and no broker
  connect/callback/token/logout route; fresh/repeat SQLite upgrades and
  downgrade/re-upgrade passed; offline PostgreSQL SQL generation passed;
- PostgreSQL 16: an isolated real server reached `0004_broker_foundation`, repeated
  the head upgrade, seeded `zerodha:false:false`, created all four foundation tables,
  removed them on downgrade and restored them on re-upgrade;
- containers: clean API and web image builds passed; the migrated API image served
  `/health`, `/ready`, `/api/v1/status` and OpenAPI successfully, and the web image
  served the `TradingWorkFlow` page;
- repository: Compose validation, documentation link/index checks, secret-pattern
  review and `git diff --check` passed.

No real Zerodha connection, credential exchange, provider HTTP request or command was
performed or made available by these checks.

## Bounded remediation evidence

The preflight again verified `main` at `44e53d5a30f13d4c3ad6fc66da192db828fec5c4`;
no commit, tag or push occurred after review. Existing BW-2 planning and implementation
changes were retained. Broker Workspace architecture v0.3 and the frontend source
were not changed.

| Reviewed finding                  | Bounded fix                                                              | Focused proof                                                                                                                                                                                      |
| --------------------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lost generation updates           | Owner/environment/expected-generation SQL compare-and-swap               | Synchronized replacement/replacement and replacement/disconnect races; one success, one 409, generation N+1, one successful mutation audit                                                         |
| Superseded secrets reusable       | Immutable generation scopes; post-commit deletion                        | A replaced by B; A deleted; disconnect deletes B; both reattachments denied; deletion-outage case remains fenced                                                                                   |
| Production dev-store injection    | Composition validation and explicit production capability                | Memory and disguised memory subclass rejected; unapproved custom store rejected; explicit future contract accepted                                                                                 |
| Duplicate-label PATCH 500         | Catch database UPDATE uniqueness conflict and roll back                  | 409 safe envelope, unchanged account/audit, subsequent valid update succeeds                                                                                                                       |
| Provider-specific shared metadata | Generic auth categories and independent capability flags                 | Five auth categories and differing boolean capabilities represented without adapter registration                                                                                                   |
| Empty normalized labels           | Shared trim-before-validation label type                                 | Create/PATCH reject empty/whitespace/overlength; API and service persist normalized labels                                                                                                         |
| Overstated tests/docs             | Actual request and lifecycle logging tests; documented failure semantics | Validation 422, conflict 409, successful response and cleanup warning captured through real JSON logging; raw secret absent from logs, rendered public failure, all audit fields and API responses |

The focused file runs with disposable SQLite by default. PostgreSQL is explicitly
opt-in through `--broker-postgres-url`; it does not inherit deployment credentials.
Each PostgreSQL fixture creates and removes a randomly named test schema. Run it
against a disposable server, for example:

```sh
cd apps/api
.venv/bin/pytest -q tests/test_broker_foundation.py --broker-postgres-url='<disposable PostgreSQL URL>'
```

Remediation validation completed on 2026-09-26:

- Full backend suite: **272 passed**, including **31 focused BW-2.1 cases** (the
  accepted 241-test baseline plus 31 focused cases). The strengthened synchronized
  SQLite race tests additionally passed **2/2**.
- PostgreSQL 16: the same focused file passed **31/31** using isolated schemas.
  Both writers are explicitly synchronized before the CAS executes. For concurrent
  replacement/replacement and replacement/disconnect at expected generation 0,
  results are exactly one success and one 409, stored generation 1, and exactly one
  successful mutation audit at generation 1. Sequential replacement/disconnect
  produces audit generations 0, 1, 2, 3; stale operations do not add audit or advance
  generation. No skipped PostgreSQL cases are counted as passed.
- Ruff lint/format (**60 files**), strict mypy including Alembic (**59 source files**),
  Python compilation and `pip check`: passed.
- Frontend: **89 tests across 12 files**; TypeScript, ESLint, Prettier and production
  build: passed. Frontend checks used a temporary source copy to avoid generated
  declaration churn in the repository.
- Combined Playwright: **108 passed**, Chromium **54/54**, WebKit **54/54**, at 390,
  768, 1024, 1440, 1920 and 2560 widths. The existing Linux host workaround
  `env -u GIO_MODULE_DIR` was used; this does not claim native Safari validation.
- SQLite and PostgreSQL migration checks: an existing revision-0003 user survived
  upgrade, repeat upgrade, downgrade to 0003 and re-upgrade; metadata comparison was
  empty. Fresh databases also reached `0004_broker_foundation` in tests/container
  setup. No developer database was migrated.
- API/web Docker builds and Compose validation: passed. API container health,
  application-only readiness, status, anonymous 401, authenticated provider/account
  API, normalized labels, duplicate PATCH 409, whitespace 422 and recovery after
  conflict passed. Web container login returned HTTP 200.
- OpenAPI: **20 paths**, generic auth categories and boolean capabilities; no broker
  connect/callback/token/logout route.
- Documentation: **242 local links/anchors**, **74 tables**, **15 Mermaid fences**,
  and **45 indexed documents** checked successfully. Documentation Prettier and
  `git diff --check` passed; whitespace checks included untracked files.
- Worktree audit: exactly **eight files** changed relative to the independent review.
  Architecture v0.3, migration 0004, persistence schema, frontend source and dependency
  files were unchanged. No commit, tag or push was performed.

BW-2.1 remains pending independent re-review. These fixes do not accept/freeze it or
advance the project to BW-2.2.
