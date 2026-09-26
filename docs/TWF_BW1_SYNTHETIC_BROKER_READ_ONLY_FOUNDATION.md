# BW-1 — Synthetic Broker Read-Only Foundation

## Status and authority

Implemented on 2026-09-26; **pending independent acceptance review**. This is an
implementation record, not an architecture acceptance or freeze record. No commit,
tag or push was made. BW-2–6 and the separate TWF-5 managed-workflow gate remain pending.

[Broker Workspace Architecture v0.3, section 34.1](TWF_BROKER_WORKSPACE_ARCHITECTURE.md#341-first-implementation-target-bw-1)
is normative. The accepted architecture Markdown and synchronized DOCX remain
unchanged. [README](../README.md), the [detailed roadmap](TWF_DETAILED_ROADMAP.md),
[UX bucket roadmap](TWF_UX_BUCKET_ROADMAP.md) and
[documentation index](TWF_DOCUMENTATION_INDEX.md) record current delivery status.

## Preflight and requirement mapping

Before source edits: branch `main`, clean working tree, starting HEAD
`e8bbcbe7f51dcac65c4fa6d4072495cd02dc7866` (`TWF: reconcile Broker Workspace workstream and BW roadmap`).
Documentation reconciliation was committed. Repository evidence agreed with the prompt:
TWF-0/TWF-1 accepted/frozen, Broker Workspace v0.3 accepted/tagged at `0b73492`,
UX-B1 partial, UX-B2/B3 planned, BW-1 next, BW-2–6 pending. No unrelated changes existed.

The requirement/artifact/test matrix was communicated before modifying source;
this record preserves the mapping with final artifact names.

| Requirement                                                                 | Implementation artifact                             | Evidence                                                                                                          |
| --------------------------------------------------------------------------- | --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Two providers, three accounts, same-provider account separation             | `brokers/contracts.py`, `brokers/service.py`        | Backend topology, determinism and ownership tests; browser navigation                                             |
| Different native provider layouts normalized to one versioned read contract | `brokers/synthetic.py`, `BrokerReadClient`          | Both adapters tested against every scenario; native ID, quantity, money, holding and seven order-state assertions |
| Authenticated owned read-only rooms and overview                            | `api/brokers.py`, `main.py`, web broker route/proxy | Real Alice/Bob sessions, unauthenticated denial, cross-user IDOR, safe errors, GET-only OpenAPI, proxy allowlist  |
| Dataset health, freshness, completeness and provenance                      | `ObservationMetadata`, injected adapter clock       | Deterministic scenarios, source/owner binding, distinct freshness policies; UI state tests                        |
| Compatible canonical aggregation and visible unmapped observations          | `BrokerService.overview` and overview UI            | HAL 100 + 25 - 20 = 105, source contributions, unmapped exclusion/visibility, failed-account qualification        |
| Sibling failure isolation and truthful missing values                       | Adapter failure boundary, nullable datasets/funds   | Six failure types; Alpha A1 failure preserves A2/B1; `/ready` remains 200; frontend missing/empty/unknown tests   |
| Dashboard, Holdings, Positions, Orders, Funds                               | `broker-workspace.tsx`, `brokers.ts`                | Five component views and real-session browser journey                                                             |
| Both themes and responsive shell composition                                | `brokers.css`, existing tokens/navigation           | Chromium at 390/768/1024/1440/1920/2560; both themes; overflow, account-link containment and screenshots          |

Paths in the first two columns are relative to `apps/api/src/twf` for Python and
`apps/web/src` for frontend files; complete inventory follows.

## Runtime boundary and contracts

```text
Authenticated browser → same-origin Next.js read proxy → FastAPI broker router
→ BrokerService (owned account lookup and aggregation)
→ BrokerReadClient protocol → AlphaAdapter / BetaAdapter
```

The router offers exactly two broker operations:

- `GET /api/v1/brokers/overview`: the authenticated user's three room snapshots,
  provider roster and qualified analytical position aggregates.
- `GET /api/v1/brokers/accounts/{account_id}`: one owned room's snapshot.

Responses are typed Pydantic contracts, version `broker.read.v1`. Contracts include
provider, account, read capability, connection/operation health, observation
metadata, holding, position, observed order, funds, room and unified snapshots.
Models forbid extra fields and are frozen; quantities and money use Decimal and
serialize to JSON strings. Snapshot payloads include request correlation.
`BrokerReadClient.read(account, request_id, now)` is injectable into `BrokerService`;
`create_app(..., broker_service=...)` supplies a testable application boundary.
Provider-native fixtures stay inside the adapter module. No vendor DTO, SDK,
network transport, cookie or secret enters those adapters.

Existing foundation service-health contracts, registry and `/api/v1/services`
remain unchanged. Broker data has a separate versioned read contract and router.
`/ready` remains application-only and does not depend on broker availability.
The BW-1 feature introduced no new dependencies, settings, tables or migrations.
A subsequent user-requested TestClient dependency follow-up is recorded below.

## Topology and normalization

| Provider                           | Owned room | Default read state                                  | Canonical HAL position |
| ---------------------------------- | ---------- | --------------------------------------------------- | ---------------------- |
| Provider Alpha (`synthetic-alpha`) | Alpha A1   | Connected, available, fresh, complete               | +100                   |
| Provider Alpha (`synthetic-alpha`) | Alpha A2   | Connected, available, fresh, complete               | +25                    |
| Provider Beta (`synthetic-beta`)   | Beta B1    | Connected, degraded, partial; positions/funds stale | -20                    |

Every authenticated user receives their own three deterministic fixture accounts.
Account UUIDs derive from the authenticated user's UUID and fixture label. Provider
identity is separate from account identity; Alpha A1 and A2 share a provider but
retain different account IDs, source rows and room navigation. No shared account
or ACS tenant model is implied. Every account and room is explicitly SYNTHETIC.

Alpha normalizes flat native ticker/token/string-money records. Beta normalizes
nested security/lot records, integer minor-unit money and numeric native order
states. The normalized contract never exposes these native layouts. Both map
seven observed order states: OPEN, PENDING, PARTIALLY_FILLED, COMPLETE, REJECTED,
CANCELLED and UNKNOWN; filled plus remaining quantity equals observed quantity.
These are fixtures of broker observations, not TWF order intents.

Beta also contains an unmapped position (quantity 7). It remains visible in the
room but is excluded from canonical netting. The overview groups only compatible
canonical ID, exchange, product, currency and quantity-unit positions. HAL's 105
is explicitly an analytical quantity, qualified because Beta contributes stale,
partial observations. Contributions retain account identity and metadata. Holdings
remain separate; funds are shown per account and are never treated as transferable
or fungible across accounts. No broker selection or execution authority derives
from an analytical aggregate.

## Scenario clock, metadata and failures

Default scenario time is fixed at `2026-09-26T12:00:00Z`, visibly labelled in the UI.
This is synthetic observation time, not current market time. Tests inject a
separate timezone-aware clock without sleeps or network calls. Every dataset carries
provider/source, broker account ID, optional source time, fetched time, independent
health/freshness/completeness, fixture revision `bw1-fixture.v1` and policy seconds.
Freshness policies differ: holdings 10,800s, positions 60s, orders 30s, funds 120s.
A stale fixture's source time is one second beyond its dataset policy. These are
bounded fixture policies, not production broker freshness commitments.

Both adapters cover HEALTHY, DEGRADED, AUTH_EXPIRED, UNAVAILABLE, EMPTY, PARTIAL,
MISSING, STALE, FUNDS_UNKNOWN, RATE_LIMITED, TIMEOUT, DENIED and INCOMPATIBLE.
Empty tuples mean a successful empty observation; null rows mean no observation.
MISSING demonstrates absent holdings while positions remain available. Partial
rows retain PARTIAL metadata; stale observations retain data and STALE metadata.
Unknown cash/collateral remains null and renders as Unknown, never zero.
The default degraded Beta fixture makes stale/partial/unknown states reviewable
without exposing a user-controlled failure or provider-selection endpoint.

Each adapter result is checked against the requested account/owner/provider,
request ID and dataset account/source binding. Safe failure codes produce an
unavailable snapshot for that account; unexpected diagnostics are not returned.
Alpha A1 failures leave Alpha A2 and Beta B1 usable, with qualified aggregate
subtotals and a missing-account count. No optional broker failure changes readiness.

## Security and UI

Existing session authentication resolves the user server-side. Owned-account lookup
precedes adapter execution. Unauthenticated requests receive 401; another user's
account ID receives canonical 404, including when a spoofed user header is supplied.
Invalid API UUIDs receive canonical 422. POST is unsupported (405). Success responses
and the web proxy are no-store. The proxy only routes overview or a UUID account
path, forwards the selected validated session cookie to TWF's API plus a bounded
request ID, strips arbitrary authorization/identity headers, disallows redirects,
and uses a bounded timeout. Cookies are never passed to adapters.

The protected route `/brokers/[[...path]]` supports `/brokers` and
`/brokers/{account_id}/{dashboard|holdings|positions|orders|funds}`. Invalid routes
use the existing not-found behavior. Loading, recovery, empty, unavailable, degraded,
stale, partial and unknown states are visible. Changing rooms aborts old requests;
route keys remount the view so old account data cannot persist under a new room URL.

Dashboard counts, values and P&L derive from the same snapshot rows as detailed
views. Tables use captions, column headers and labelled keyboard-focusable local
scroll regions. Navigation uses links and `aria-current`; focus/theme tokens are
reused. No broker-specific color overrides were added. Small screens wrap account
and view navigation and stack cards. Wider screens add columns; desktop adds a
separate account rail and side-by-side aggregate contributions. The existing shell
retains its support rail, console and bounded ultrawide composition.

Visual QA found and corrected a desktop flex-wrap overlap in the account rail.
A browser regression assertion now checks every account link stays within its
navigation bounds, in addition to page overflow checks. Watchlist, Instrument
Search and New Order are plain unavailable text, with no active command controls.

## File inventory

Created:

```text
apps/api/src/twf/api/brokers.py
apps/api/src/twf/brokers/__init__.py
apps/api/src/twf/brokers/contracts.py
apps/api/src/twf/brokers/service.py
apps/api/src/twf/brokers/synthetic.py
apps/api/tests/test_brokers.py
apps/web/src/app/(protected)/brokers/[[...path]]/page.tsx
apps/web/src/app/api/v1/brokers/[...path]/route.ts
apps/web/src/components/brokers/broker-workspace.tsx
apps/web/src/lib/brokers.ts
apps/web/src/styles/brokers.css
apps/web/tests/broker-fixtures.ts
apps/web/tests/brokers-proxy.test.tsx
apps/web/tests/brokers.test.tsx
apps/web/tests/browser/brokers.spec.ts
docs/TWF_BW1_SYNTHETIC_BROKER_READ_ONLY_FOUNDATION.md
```

Modified:

```text
README.md
apps/api/src/twf/main.py
apps/api/tests/test_backend_shell.py
apps/web/src/app/globals.css
apps/web/src/components/shell/primary-navigation.tsx
apps/web/tests/browser/auth-test-server.mjs
docs/TWF_DETAILED_ROADMAP.md
docs/TWF_UX_BUCKET_ROADMAP.md
docs/TWF_DOCUMENTATION_INDEX.md
```

The existing OpenAPI path inventory now includes the two broker GETs. Browser setup
adds dedicated disposable broker-flow users per browser/width. The BW-1 feature
left dependency manifests/locks unchanged; the later development-only dependency
follow-up below is separate. Database schema, Dockerfiles, accepted architecture
and DOCX are unchanged.

## Validation evidence

Initial implementation results (superseded by the remediation rerun below):

- Backend: **226 passed** (188 previous + 38 BW-1), using disposable test databases.
  The 38 comprise topology (1), two-adapter scenario matrix (26), normalization and
  aggregation (1), failure isolation (6), misbound/broken adapters (2), clock (1),
  and real-session API/security/OpenAPI (1).
- Frontend: **86 passed across 12 files**, including 12 broker component cases and
  three broker proxy cases.
- Chromium: **54 passed**, six projects at 390, 768, 1024, 1440, 1920 and 2560.
  Broker flows cover both themes, all rooms and five read views, no page errors,
  local overflow and account-navigation bounds. Twenty-four broker overview/position
  screenshots support visual inspection; artifacts remain outside source control.
- Ruff lint and format: passed, 53 Python files formatted. Strict mypy: passed,
  52 source/test/migration files. Python compilation and `pip check`: passed.
- TypeScript, ESLint, frontend Prettier and Next.js production build: passed.
- OpenAPI construction: passed, exactly two broker paths with GET only and typed
  success/error contracts. Compose configuration validation: passed.
- API and web Docker builds: passed (`twf-bw1-api:review`, `twf-bw1-web:review`).
  Disposable container smoke passed: health/ready/status, web login, unauthenticated
  401, topology, HAL 105, unmapped visibility, owner room, protected web pages,
  no-store, POST 405, cross-user 404/error correlation and CORS. Existing auth
  migrations were explicitly applied only to the disposable smoke database;
  no new migration or schema evolution was needed. Containers/network were removed.
- Documentation links/index coverage and `git diff --check`: passed.
- WebKit follow-up, 2026-09-26: **54 passed in 52.9s**, at all six widths, after
  the user installed `libmanette-0.2.so.0` and the test process omitted the inherited
  Snap `GIO_MODULE_DIR` override. Coverage includes authentication, settings, service
  status, shell navigation/overflow, theme persistence/first-paint restoration and
  the complete broker flow in both themes. The local WebKit execution gap is closed;
  this is Playwright WebKit on Linux, not a native macOS/iOS Safari test.

The first follow-up run launched WebKit but all 54 tests failed at HTTP navigation.
An independent local HTTP server containing only an `h1` reproduced the failure,
while a data-URL page worked. Browser diagnostics identified `WPENetworkProcess`
loading Snap core20's incompatible `libpthread.so.0` (`__libc_pthread_init`,
`GLIBC_PRIVATE`). The inherited `GIO_MODULE_DIR` pointed to the VS Code Snap GIO
module cache. Removing only that override for the child process made the isolated
HTTP probe and then the full suite pass. No application, test, system package or
persistent environment configuration change was required for this follow-up.

Reproduce from `apps/web` in this Snap-hosted IDE environment:

```bash
env -u GIO_MODULE_DIR npx playwright test --project='webkit-*' --output=/tmp/twf-bw1-webkit-clean
```

The successful run produced 24 broker screenshots for both themes at six widths;
artifacts remain outside source control. The original missing-library result is
superseded by this follow-up, not reclassified as a TWF compatibility defect.

### TestClient warning follow-up

After the user installed `httpx2` in the API virtual environment, Starlette selected
it automatically. The repository now declares `httpx2>=2.13.1,<3` in the development
extra and pins `httpx2==2.13.1`, `httpcore2==2.13.1` and `truststore==0.10.4` in the
development lock. Existing runtime pins and the application's `httpx` transport
remain unchanged. Explicit non-null session-cookie assertions in two auth tests
accommodate the new client's stricter types without casts or warning suppression.

Follow-up files: `apps/api/pyproject.toml`, `apps/api/requirements-dev.lock`,
`apps/api/tests/test_auth.py`, this record and
[TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md](TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md).
Validation uses `python -m pytest -q -W error` from the repository root: all 226
tests pass with no warnings. Strict mypy, Ruff lint/format and `pip check` also pass.

The existing Playwright `next start`/standalone advisory also remains; the production
Docker image runs the standalone server and passed smoke checks.

## Deferrals and next gate

Deferred in full: real broker SDK/API/auth/credentials/OAuth/vault integration;
instrument master/catalog/search; broker watchlists; New Order, OrderIntent,
preview/submission/cancel/modify; execution safety engine; live order lifecycle;
reconciliation workers; WebSocket/SSE streaming; real quotes; paper trading;
TM/Scanner/TI/LLM business integration; subscriptions/billing; shared accounts and
ACS membership; durable broker schema and production real-adapter configuration.

The injected read interface preserves a future real-adapter extension point,
but BW-1 has no real broker execution path. Shared mode and source-revision fields
now support future read adapters, while commands remain disabled. Later gates still
require verified provider semantics, identity binding, credentials and failure
policies. This work does not assert that those later gates are already implemented.

UX-B2 is advanced by the bounded read-only experience; no UX bucket, TWF-2 or
TWF-6 completion is claimed. Next action: independent BW-1 acceptance review.

Recommendation after bounded remediation: **READY_FOR_BW1_REREVIEW**.


## Bounded remediation after independent review

The independent review held BW-1 for two major findings: fixture-locked common
contracts and cross-browser login-budget interference. The nonblocking overview
observation (holdings value and P&L require entering a room) remains a future UX
enhancement; no overview expansion or BW-2 behavior was introduced.

`BrokerAccount.mode` now uses finite `AccountMode` values `SYNTHETIC`, `SANDBOX`
and `LIVE`; the default remains `SYNTHETIC`. All three runtime fixture accounts
remain synthetic and command capabilities remain false. Frontend room headings,
account navigation, overview cards and overview mode summary derive their labels
from account data. Mixed modes are listed distinctly. Synthetic-only clock copy
is conditional on all accounts being synthetic.

`ObservationMetadata.revision` is required source metadata, not the common schema
version. It accepts 1–128 ASCII characters, starting with an alphanumeric character,
followed by alphanumerics, `.`, `_`, `:`, or `-`. Whitespace, control characters,
markup and oversized/non-string values are rejected. The fixture adapter explicitly
emits `bw1-fixture.v1`; a future source may emit `provider-alpha.snapshot.v2` without
changing shared models. `contract_version` remains `broker.read.v1`. No credential
or transport configuration belongs in either version field.

Contract regressions cover all modes, rejected modes/revisions, alternate revisions,
and a network-free test double with LIVE-shaped account data passing the existing
service read boundary and unified snapshot validation. Component tests verify each
mode in overview cards, navigation and room identity, plus alternate provenance.
These fixtures prove structural compatibility only; no real/sandbox adapter,
authentication, credentials or runtime mode selection was added.

The default Playwright run now starts two disposable API processes and two web
servers: Chromium uses web/API ports 3100/8100; WebKit uses 3101/8101. Each engine
owns a fresh SQLite database and a separate process-local login limiter. Width
projects retain their dedicated settings/broker users. Origins follow each project's
base URL. Servers are never reused and temporary databases are removed on shutdown.
The previous shared API let Chromium consume WebKit's login budget; separate
processes remove that cross-engine interference. No rate override, reset endpoint,
production policy change or minute-long delay was introduced. The accepted limit
remains 60 attempts per peer per minute; its rejection/reset regression still runs.
Each engine remains independently selectable with Playwright's project filter.

Remediation files: `apps/api/src/twf/brokers/contracts.py`,
`apps/api/src/twf/brokers/synthetic.py`, `apps/api/tests/test_brokers.py`,
`apps/web/src/lib/brokers.ts`,
`apps/web/src/components/brokers/broker-workspace.tsx`,
`apps/web/tests/brokers.test.tsx`, `apps/web/playwright.config.ts`,
`apps/web/tests/browser/auth-test-server.mjs`, and browser specs `theme.spec.ts`,
`shell.spec.ts`, `settings.spec.ts`, `services.spec.ts`, plus this record.
Accepted architecture/DOCX, schema, runtime dependencies and login limiter source
are unchanged. Generated `next-env.d.ts` churn is restored after validation.


### Remediation validation results

- Backend: **241 passed** with warnings treated as errors (226 existing plus 15
  contract regressions). Production login-budget rejection/reset, authentication,
  ownership/IDOR, read-only and optional-failure regressions all pass.
- Frontend: **89 passed across 12 files**, including three added mode-rendering cases.
- Default combined browser run: **108 passed in 1.5 minutes**, comprising Chromium
  **54/54** and WebKit **54/54** at 390, 768, 1024, 1440, 1920 and 2560 pixels.
  Command from `apps/web`: `env -u GIO_MODULE_DIR npm run test:e2e`.
  The environment omission is the previously diagnosed Snap host workaround;
  no browser filters, sleeps or policy overrides are needed. Native Safari remains
  outside this Linux validation.
- Ruff lint/format, strict mypy (52 files), Python compilation and `pip check`: pass.
- TypeScript, ESLint, Prettier and production build: pass.
- OpenAPI construction, finite mode enum, bounded revision schema and broker GET-only
  paths: pass. Docker Compose validation: pass.
- API and web Docker builds (`twf-bw1-review-api`, `twf-bw1-review-web`): pass.
  Disposable container smoke passes health/ready/status, web login, anonymous 401,
  two-provider/three-account topology, HAL 105, unmapped visibility, owned room,
  protected pages, no-store, POST 405, cross-user 404/error correlation and CORS.
  Smoke containers/network were removed; no schema change was introduced.
- Documentation link/index checks and `git diff --check`: pass.

The accepted production login limiter and broker architecture Markdown/DOCX have
no remediation diff. README/roadmap milestone hierarchy remains intact; this is
ready for independent rereview, not a freeze or authorization to start BW-2.
