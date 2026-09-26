# BW-2.2 — Zerodha Authentication and Account Binding

## Status and authority

**ACTIVE / PENDING INDEPENDENT REVIEW — 2026-09-26**

Preflight: clean `main` at `b139d356761a519b06d3a82545fbdfbce3d032d8`, tagged
`twf-bw2-1-secure-provider-account-foundation`. The preceding independent review
accepted BW-2.1. That Git evidence supersedes the historical pending-review wording
in its implementation record. BW-1 remains frozen at
`twf-bw1-synthetic-broker-readonly`. No commit, tag or push is part of this slice.

[Broker Workspace v0.3](TWF_BROKER_WORKSPACE_ARCHITECTURE.md), the
[BW-2 v0.2 plan](TWF_BW2_ONE_REAL_BROKER_READ_ONLY_PLAN.md), and the accepted
[BW-2.1 foundation](TWF_BW2_1_SECURE_PROVIDER_ACCOUNT_FOUNDATION.md) govern this work.
Existing TWF and UX milestone identities are unchanged.

Authentication transport and setup UX are implemented. **Real activation remains
fail-closed by default:** no managed vault was selected or installed for this
implementation. The deployment must inject an approved `SecretStore`, explicitly
enable authentication and configure its registered callback. Tests use clearly
isolated fake stores/providers; they do not supply a production store or prove live
Kite app permissions. No real credential or provider call was used in validation.

## Bounded scope and artifacts

| Requirement                       | Implementation                                                               | Evidence                                                                       |
| --------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Configuration and permissions     | `twf.api.broker_auth`, `twf.broker_auth`                                     | Origin, owner, operation-policy, revision and generation tests                 |
| Fixed provider boundary           | `twf.brokers.zerodha_auth`                                                   | Mocked official-shaped token/profile responses, failures and response bounds   |
| Single-use session-bound callback | `BrokerAuthAttempt`; clean callback and finalize routes                      | Replay, wrong session, expiry, concurrent workers, cross-site browser flow     |
| Verified immutable binding        | Finalize CAS and existing provider/environment/account uniqueness constraint | Profile mismatch, duplicate binding, rebind denial, mid-flight disconnect      |
| Generation-validated secret use   | `BrokerAuth.resolve`; scoped lifecycle metadata                              | Stale lease, pending/active scope, disconnect and expiry tests                 |
| Revocation and retry              | `BrokerSecretLifecycle`; bounded cleanup action                              | Failed deletion, retained physical value, denied resolution and later deletion |
| Additive persistence              | Alembic `0005_broker_auth`                                                   | SQLite/PostgreSQL upgrade, repeat, metadata, downgrade/re-upgrade              |
| Brokers UX                        | `real-brokers.tsx`, clean completion page, dedicated proxy                   | Configuration secret clearing; both themes and six browser widths              |
| Frozen synthetic experience       | Existing `broker.read.v1` and synthetic service unchanged                    | Backend, frontend and combined Chromium/WebKit regression suites               |

## Configure to bind

1. An authenticated owner creates a personal Zerodha account through the existing
   account API. The Brokers page provides an account label and credential form.
2. An origin-checked configure POST requires `broker.configure` and expected
   configuration revision/generation. The non-secret app identifier is durable;
   the API secret goes to the store and only its opaque reference is persisted.
   Saving increments configuration revision, invalidates prior attempts/active
   token, and requires fresh authentication. The secret is never returned.
3. Connect requires `broker.connect`, enabled/complete configuration, a usable
   approved store and `TWF_ZERODHA_AUTH_ENABLED=true`. A five-minute single-use
   attempt binds a random state hash to the initiating TWF session hash, owner,
   account, provider, environment, revision and generation. Return targets are
   deployment constants; the request cannot supply one.
4. The fixed Kite login URL carries only app key and opaque correlation through
   `redirect_params`. The dedicated API callback accepts the provider-mandated
   one-use `request_token`. It claims the attempt atomically, verifies the original
   session is still active, resolves the current configuration secret and exchanges
   the token server-side. No normal Strict cookie is required on this cross-site
   request, and callback state alone cannot activate an account.
5. The returned access token is a pending vault value scoped to that attempt and
   target generation. A short-lived HttpOnly correlation cookie is set. The API
   immediately sends a no-store, no-referrer 303 to `/broker-auth/complete` with no
   query. No token goes into cookies, localStorage, sessionStorage or page props.
6. The loaded clean page makes an origin-checked POST with the ordinary Strict
   TWF session cookie and the correlation cookie. The session must exactly match
   the initiator. Finalization claims the attempt once, resolves the pending token,
   fetches only `/user/profile`, and verifies broker, app and subject identity.
7. The database CAS atomically advances generation, binds the verified provider
   account ID, activates current-generation token/configuration references and
   writes the audit event. Profile identity must match exchange identity and any
   previous binding. Rebinding the same TWF UUID to another provider identity is
   rejected; duplicate verified bindings return a safe conflict. `bound_at` and
   last authentication success are retained. Read health remains `UNKNOWN`.

The adapter follows the current official [Kite user contract](https://kite.trade/docs/connect/v3/user/)
for checksum exchange, authorization headers and profile verification, and maps
[documented errors](https://kite.trade/docs/connect/v3/exceptions/) to bounded safe
failures. Destinations are fixed HTTPS endpoints, redirects and environment proxies
are disabled, HTTPX connect/read/write/pool timeouts remain five seconds, and a
separate **five-second total monotonic deadline applies to each token-exchange or
profile request**. Async I/O inside the synchronous adapter boundary lets that
deadline cancel header/body waits and close the stream without leaving background
request workers. Event-loop cleanup does not wait for a cancelled OS DNS resolver
worker; that worker may finish in the background, but its result cannot continue
the provider request. The deadline covers streaming, size checks, JSON parsing and model
validation. Synchronous parsing of the at-most-64-KiB body cannot be preempted by
the event loop; explicit checks reject any parsing overrun before its result can
be used. Total or HTTPX phase timeouts become the typed `PROVIDER_TIMEOUT` failure.
Failed attempts are rejected, pending tokens are logically revoked for cleanup,
and no identity, generation increment or active token is committed. Authentication
has no automatic retries. Provider DTOs and
raw error bodies never reach application responses or persisted domain fields.

## Secret lifecycle and races

Every store reference has owner/account/provider/environment/generation plus
purpose/context. Configuration references match the persisted current generation
and credential revision. Pending references target N+1 and match one live attempt;
active references match N and the current connection's active reference.
`BrokerAuth.resolve` reloads authoritative state before and after vault access.
Each provider result is checked again, then activated only by a generation/revision
CAS. A disconnect or configuration change during provider I/O discards the result.
There is no database transaction across provider HTTP calls. An already dispatched
request cannot be recalled; its result cannot reactivate a revoked connection.

Concurrent callback/finalization claims still use database compare-and-set; only
one worker may consume each attempt. PostgreSQL behavior is unchanged. Recognized
SQLite BUSY/LOCKED failures at the claim become safe conflicts. A losing request
writes rejection audit through a separate single `INSERT ... SELECT`, avoiding a
SQLite read-to-write upgrade race. That write uses the existing finite SQLite busy
timeout (five seconds) with no application retry loop. If contention still prevents
the audit, the transaction rolls back and emits only
`broker_callback_rejection_audit_contended`; rejection is preserved, not HTTP 500.
No provider call is replayed. Other database errors are not misclassified as SQLite
contention. The callback keeps its clean 303 response; failed finalization returns
the canonical safe error envelope.

Staged references have a durable lifecycle row and ten-minute expiry. Supersession,
disconnect, failed promotion and expired attempts mark references `REVOKED` before
physical deletion. Revoked values cannot be resolved through the application even
if the underlying store still contains them. Each cleanup action attempts at most
ten deletions. Failure leaves a durable pending row and a constant redacted warning;
retry is safe through the owner-scoped cleanup endpoint/UI or subsequent lifecycle
actions. Vault access denial also stays pending: it is not evidence of physical
deletion. Approved stores should provide idempotent deletion with a positive result
for confirmed prior deletion; ambiguous failures remain pending. Completed deletion is audited. No worker framework was introduced.

There is no distributed transaction between vault and SQL. If storing a candidate
succeeds but writing its lifecycle row fails, the service attempts compensating
deletion and fails closed. A production vault's operational recovery must cover a
simultaneous SQL/deletion outage or process death in this narrow staging window;
this slice does not claim guaranteed physical erasure under those failures. The
accepted BW-2.1 store was process-local and no production token store existed.

Disconnect requires its own permission and expected generation. It advances the
fence, clears the active token and pending attempts, and audits local disconnection.
Configuration is re-scoped for reconnect when the vault is available. If vault
access fails, local disconnection still commits; credentials must then be entered
again. Cleanup failures never restore authentication.

TWF does **not** call provider-side logout. The UI explicitly says that the Zerodha
session may remain valid until expiry or logout at Zerodha. Invalid token responses
produce `REAUTH_REQUIRED`. Time-expired connections display reauthentication and
cannot resolve an active token; a new Connect action materializes the revocation.
Authentication state, configured/enabled flags, revision, generation and read health
remain separate.

## Deployment and callback routing

The following settings are server-only:

- `TWF_ZERODHA_AUTH_ENABLED`: defaults to `false`.
- `TWF_ZERODHA_WEB_ORIGIN`: exact origin of the TWF web application.
- `TWF_ZERODHA_CALLBACK_URL`: fixed `/api/v1/broker-auth/callback` on the same host
  and scheme. Different development ports are supported. Enabled production auth
  requires HTTPS.

Register that exact callback in the Kite developer console. Route this callback
**directly to FastAPI**, without rendering it through Next.js. In production,
configure the edge route to omit query strings from access logs, tracing and
analytics; retain the supplied `--no-access-log` Uvicorn setting. The callback sends
`Cache-Control: no-store`, `Referrer-Policy: no-referrer` and a restrictive CSP.
The clean web page has no-referrer, no-store and frame-denial headers. The ordinary
web auth proxy never accepts or forwards a callback query.

No managed vault provider or dependency was selected implicitly. Production
composition must supply an approved store implementing immutable scope checks and
operational recovery. Merely setting the environment flag does not enable Connect
with the memory/default-unavailable stores. Deployment acceptance must also verify
Kite app rights, proxy log suppression, and the shared app quota policy required by
the BW-2 plan before real activation. No multi-replica quota service was added here.

The configure form represents the user's explicitly supplied app credentials for
that personal connection. It cannot expose or overwrite a platform-managed app
secret. This follows the supplied BW-2.2 owner-scoped configure requirement; shared
platform app administration remains outside this slice.

## API and UX

The additive `/api/v1/broker-auth` surface provides account connection status,
configure, connect, callback, finalize, disconnect and cleanup. Mutation routes
require Origin/CSRF checks. The narrow cross-site callback is the only exception;
its state/session checks and subsequent authenticated finalization replace no
ordinary authorization check. API responses and audits omit all secret values and
references. The UI clears its password input immediately after submission.

Brokers now places **Real brokers / Zerodha** ahead of **Development / Synthetic**.
Each connection shows configuration and auth state, verified identity when present,
**LIVE DATA · READ ONLY**, and **TRADING DISABLED**. Disabled Connect explains the
missing prerequisite. Alpha A1/A2 and Beta B1 retain their rooms, observations,
qualified aggregates and provenance. There is no real portfolio dataset to merge
into the synthetic overview.

No real holdings, positions, orders, funds, instruments/catalog/search, watchlists,
order intent/preview/placement/cancellation, streaming, TM, Scanner, TI, billing,
paper trading or shared broker-account functionality was added. `/ready` retains
application-only semantics. No dependency or accepted migration was changed.

## Validation before bounded remediation

- Full backend: **310 passed**, including **38 BW-2.2 tests** and all BW-1/BW-2.1 regressions.
- Disposable PostgreSQL 16: **69 passed** across BW-2.2 (38) and BW-2.1 (31).
- Ruff lint/format, strict mypy (65 source files), Python compilation and `pip check`: passed.
- Frontend: **94 tests in 13 files passed**; TypeScript, ESLint, Prettier and production build passed.
- Combined Chromium/WebKit: **120 passed** at 390, 768, 1024, 1440, 1920 and 2560 pixels. Both themes, real cross-site navigation with the Strict TWF cookie absent on callback, clean finalization, disconnect, reauth and synthetic regression were exercised. New auth projects use separate disposable API processes to preserve the existing login rate limit. Screenshots at mobile, desktop and ultrawide sizes were visually inspected.
- SQLite and PostgreSQL: 0004 baseline data preserved across upgrade to 0005, repeat upgrade, metadata drift check, downgrade and re-upgrade.
- API/web Docker builds, explicit migration in the API container, health/ready/status, OpenAPI, web login, broker ownership/regression, default Connect gate, clean callback/page headers and CORS smoke: passed.
- Compose validation, documentation links/index/structure checks and `git diff --check`: passed. Changed-file secret-pattern review found no real credentials. Redaction tests inspect responses, audit records, database content and application JSON logs.

Provider HTTP responses and the approved vault are deterministic test doubles. No live Kite account, managed production vault, edge logging configuration or shared operational quota was validated. These remain deployment acceptance prerequisites. No real portfolio reads or trading were enabled.

This implementation remains pending independent review, not accepted/frozen.

## Bounded review remediation

The independent review held BW-2.2 for the missing total provider deadline, an
intermittent SQLite rejection-audit race, and stale UX roadmap status text. This
remediation changes only those concerns and their tests/documentation. BW-2.1 is
ACCEPTED / FROZEN; BW-2.2 stays ACTIVE / PENDING REVIEW. No freeze or real activation
is implied by passing tests.

Remediation validation:

- Full backend: **335 passed**, including **63 BW-2.2 tests**.
- Disposable PostgreSQL 16: **94 passed** across BW-2.2 (63) and BW-2.1 (31).
- Callback and finalization races each run eight times per database backend,
  asserting exactly one success and one safe conflict, with no duplicate provider
  exchange/profile call.
- Slow-chunk streams time out and close for both exchange and profile. Additional
  checks cover blocked headers, cancelled resolver work, parsing overruns, typed
  HTTPX timeouts, and rejection without partial binding or usable pending tokens.
- Forced SQLite claim and rejection-audit contention preserve safe responses and
  sanitized logging without retrying provider calls.
- Ruff lint/format, strict mypy (65 source files), Python compilation and `pip check`:
  passed. Changed Markdown passes Prettier; documentation links/structure and
  `git diff --check` pass.
- Rebuilt API image and disposable container smoke passed: explicit migration,
  health/readiness/status, login, ownership/error envelopes, default Connect gate,
  clean callback/landing headers and CORS. The unchanged web image was reused.
- Frontend and browser suites were not rerun for this backend/documentation-only
  remediation; their prior evidence is recorded above. No live Kite calls were made.
