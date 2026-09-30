# S2-3A — Generic MCP Provider Connection & Authentication Foundation

> **Current integrated status (2026-09-29):** Durable auth intent and ambiguous-result
> recovery are remediated in S2-3. The [integrated record](TWF_S2_3_TRADINGVIEW_MCP_SCAN_PROVIDER_IMPLEMENTATION.md)
> supersedes the separate re-review gate below. Integrated S2-3 is ACCEPTED /
> FROZEN WITH DEFERRED HARDENING; historical independent reviews remain unchanged.
> Status: **DURABILITY REMEDIATED / INTEGRATED INTO S2-3** — 2026-09-29.
> Implementation evidence only; this document does not independently accept or freeze S2-3A.
> Sprint 2 remains ACTIVE. S2-3A durability work is now part of the integrated S2-3 completion effort. See the
> [S2-3 review](TWF_S2_3_ACCEPTANCE_REVIEW.md) for current status; historical dated
> remediation entries below preserve their original status.

## Preflight and architectural reason

Implementation started on clean `main` at `e22e17ffb2ce492e2a560193a8558c15b7836018`,
which carries `twf-s2-2-internal-scanner-v0`. S2-1 is frozen at
`caadc9d` (`twf-s2-1-discovery-foundation`); Broker V2 is frozen at
`69a643e` (`twf-broker-v2`). No unrelated changes were present.
The previous S2-3 attempt stopped at the authenticated MCP foundation gate:
existing service clients supplied health contracts, while broker OAuth and
credential ownership were broker-specific. That stop was reported in the task
conversation; the starting repository still labelled S2-3 ACTIVE / NEXT.
This record and the updated roadmaps make the missing foundation gate explicit.

Governing architecture remains [S&D](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md),
[configuration](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md),
[service contracts](TWF_SERVICE_CONTRACT_ARCHITECTURE.md),
[service integration](TWF_SERVICE_INTEGRATION_ARCHITECTURE.md),
[security](TWF_SECURITY_AUTH_ARCHITECTURE.md) and [data](TWF_DATA_ARCHITECTURE.md).
There is no change to broker, TI, TM, scanner or trading authority.

## Architecture and scope

```text
Typed deployment Settings → registered ProviderConfig
Authenticated personal settings API → owner/session/expected-generation checks
ConnectionManager → replaceable auth headers + OAuth authorization-code lifecycle
Encrypted token reference → bounded official MCP SDK transport
Raw tool catalog → explicit server-owned ToolPolicy → future business adapter
```

`integrations/mcp` owns provider-neutral configuration, authentication, connection
lifecycle and tool transport. `infrastructure/mcp.py` owns four independent
SQLAlchemy models, including durable operation permits. These are not BrokerAccount records. Existing `Contract`,
`Identifier`, `RequestContext`, `Health`, `SecretReference`, session resolution,
Origin checks, error envelopes and structured logging are reused. Existing TWF-1.6
health-only `ServiceClient` remains unchanged; its DTO is not overloaded with MCP
operations. No new preferences engine or arbitrary settings keys were added.

Stable UUID connection identity carries provider ID, personal owner, display
name, enabled state, generation, configuration fingerprint, auth state, normalized
tools, health, timestamps and an authorized secret reference. Multiple connections
to one or several registered providers are supported. Names confer no authority.
Only USER ownership is implemented, matching the accepted personal settings model.
WORKSPACE/ACCOUNT scopes fail validation; shared membership is not invented.

## Configuration and settings API

Operator registration uses `TWF_MCP_PROVIDERS`, a JSON array parsed by existing
`Settings`. Empty by default; maximum 16 unique provider IDs. Example contains no
credentials and points to a deliberately non-operational example host:

```json
[
  {
    "schema_version": "mcp.connection.v1",
    "provider_id": "example_mcp",
    "display_name": "Example MCP",
    "endpoint": "https://mcp.example/mcp",
    "auth_mode": "NONE",
    "timeout_seconds": 10,
    "max_response_bytes": 262144,
    "max_tools": 64,
    "max_pages": 4,
    "retry_count": 0,
    "refresh_policy": "EXPLICIT",
    "health_policy": "INITIALIZE_AND_LIST_TOOLS"
  }
]
```

OAuth registration additionally requires `oauth.issuer`, `authorization_endpoint`,
`token_endpoint`, `client_id`, `redirect_uri`, optional `revocation_endpoint` and
requested `scopes`. Metadata must be operator-verified against the provider's
issuer documentation. This slice supports explicit metadata and preregistered
public clients; it does not fetch arbitrary discovery URLs or register clients.
API_KEY uses a standard Bearer header only. API keys are submitted once through
`connect`, never placed in `TWF_MCP_PROVIDERS` or preference JSON.

Routes are under `/api/v1/settings/mcp/connections`:

| Method / suffix               | Operation                                                                           |
| ----------------------------- | ----------------------------------------------------------------------------------- |
| POST collection               | Create a disabled personal connection using registered provider ID and display name |
| GET `/{identity}`             | Read owner-scoped status; no network call or hidden commit                          |
| POST `/{identity}/connect`    | Enable NONE or API_KEY; body includes expected `generation`, optional `api_key`     |
| POST `/{identity}/authorize`  | Begin OAuth; expected generation; returns authorization URL and new generation      |
| POST `/{identity}/callback`   | Consume bound `state` and `code` once                                               |
| POST `/{identity}/refresh`    | Explicit provider-dependent refresh; expected generation                            |
| POST `/{identity}/disconnect` | Close admission, drain admitted work, then retire credentials; expected generation  |
| POST `/{identity}/test`       | Initialize MCP and refresh tool discovery only; expected generation                 |
| POST `/{identity}/cleanup`    | Retry previously revoked secret cleanup                                             |

All routes require an active authenticated owner. Writes require the existing
trusted Origin policy. Responses are `no-store`. The API never accepts endpoint
URLs, tool allowlists or arbitrary tool invocations from the browser. Configuration
changes invalidate the stored fingerprint; disconnect and create a newly configured
connection to revalidate rather than silently reuse credentials with another endpoint.
This slice intentionally provides backend contracts, with no provider cards, list
screen or new frontend route.

## OAuth and generation fencing

1. Verify owner, active login, exact connection and expected generation in a short
   transaction. Retire the old reference; increment generation and persist CONNECTING.
2. Generate 256-bit random state and PKCE verifier. Store only the state hash and
   encrypted verifier, bound to owner/session/connection/generation. Attempts expire
   after five minutes. Send S256 challenge and MCP resource audience.
3. Callback requires the same active TWF session, owner, connection and current
   generation. Atomically claim the attempt, clear the verifier ciphertext, and
   commit before provider I/O. Replays and competing callbacks cannot exchange twice.
4. Exchange code outside the transaction, using the exact configured redirect URI,
   client ID, resource audience and PKCE verifier. Reject malformed tokens, non-Bearer
   types and scopes exceeding the configured request.
5. Recheck owner, active session, configuration fingerprint and generation before
   attaching encrypted tokens. Late tokens cannot attach to a replacement generation.
   Captured late tokens enter the revoked cleanup queue instead.

Callback is an authenticated **same-origin POST conduit**, not a provider-facing
GET redirect endpoint. Existing SameSite=Strict cookies remain unchanged. A future
frontend landing page must receive code/state, scrub them from the URL immediately,
apply no-referrer/no-store policy and submit them from the same origin. That page
and real browser OAuth acceptance are deferred. No access/refresh token reaches
the browser. No real provider authorization was attempted in this task.

SQLite obtains a bounded writer reservation before reading the claim; lock contention
has three attempts, 200 ms busy timeout each and 25/50 ms backoff, then a sanitized
STALE_GENERATION result. PostgreSQL locks the active session/user/connection rows.
External calls never run within the write transaction. Session revocation and
owner deactivation are rechecked before attachment and tool dispatch/result acceptance.

## Encryption, refresh and cleanup

Generic token records reuse the accepted `CredentialCipher` and deployment-managed
`TWF_CREDENTIAL_MASTER_KEY`; there is no second encryption algorithm or key system.
Encrypted payloads include reference ID, connection, owner, provider and generation.
Those bindings and logical revocation are checked on every use. Ordinary status
contains only the existing `SecretReference` shape and expiry metadata.

Refresh requires a current, non-revoked reference and a returned refresh token.
It logically retires the previous binding and claims a new generation before I/O;
replacement is persisted as a cleanup-pending reference before promotion under
the same final checks. Old material remains a durable cleanup obligation, including
failed refresh and disconnect. Provider revocation is deferred while this owner has
any active/pending connection to the provider, protecting retained token values. There are no silent refresh loops or automatic authentication retries.

Disconnect first durably closes admission and enters DISCONNECTING. It preserves
the generation and secret binding while admitted operations drain. Only proven
drain allows clearing the active reference/tools, advancing generation and entering
DISCONNECTED. An unresolved worker or failed local close keeps DISCONNECTING and
requires recovery; expiry alone never proves drain. Revocation, when
configured, attempts both refresh and access tokens. Failures retain encrypted,
logically revoked rows and expose `cleanup_pending=true` for explicit retry.
Cleanup processes at most 16 records within one provider time budget, only after
active/pending owner/provider authority has disappeared. A durable expiring cleanup
claim fences new authorization during remote revocation. Changed issuer
configuration or an unavailable encryption key leaves cleanup pending instead of
sending credentials to a changed destination. Restart preserves reference and
cleanup state; network sessions are recreated per operation.

A remote server can issue a token while its response is lost or the process crashes.
TWF cannot revoke a token it never received. Such tokens never become usable locally;
provider expiry/revocation policy remains necessary. A total database outage can
also prevent saving an orphan cleanup record; sanitized PENDING logging records the
failure, but durable cleanup is not claimed in that case. Key rotation, production
vault operations, retention and administrative recovery remain separate gates.

## MCP session, budgets and authority

Official `mcp==2.2.0` implements Streamable HTTP and SDK session lifecycle. A new
owned session initializes, lists tools and optionally invokes one allowed tool.
Its resources remain owned until local close; caller timeout does not await shielded
teardown past the public deadline. The offline fixture negotiates protocol 2025-11-25.
Unsupported initialize versions yield CONTRACT_MISMATCH; this is not a claim to
support every SDK protocol, transport or optional capability.

Configured timeout is 0.05–30 seconds, with HTTP connect/read/write/pool limits
and a total caller deadline covering admission, streaming, size checks, parsing,
normal remote session termination and successful unwind;
token parsing also checks elapsed wall time before attachment. Transport permits
only exact configured HTTPS URLs on port 443. Credentials, query strings, fragments,
redirects, proxy inheritance, private/reserved DNS answers and compressed responses
are rejected. DNS is resolved before connecting to a pinned public address, retaining
TLS SNI and Host. Local tests inject an in-memory transport without opening sockets;
this is not permission for arbitrary private-network endpoints in production.

Default aggregate body budget is 256 KiB (hard maximum 1 MiB), headers 16 KiB,
24 HTTP requests per transport, at most 8 discovery pages/128 tools. TWF does not
retry business calls. The SDK can open/reconnect its protocol GET stream; every
request now passes the dispatch fence and request/time budgets. This is not a
product streaming subscription. No stdio subprocess or client sampling capability
is introduced. Cancellation retires dispatch; local teardown remains owned until completion or
an explicitly unresolved close failure.
Provider errors are normalized; raw SDK/OAuth exceptions and payloads do not escape.

Tool metadata is untrusted. Exact server-owned names must appear in `ToolPolicy`;
discovery and remote read-only hints never grant authority. Unknown well-formed
tools and optional protocol metadata are tolerated. Arguments are limited to 16 KiB
and validated against discovered object schemas. Schemas are limited to 16 KiB and
12 levels; remote/recursive references and regex keywords are rejected. This
intentionally bounded JSON Schema subset may need reviewed extension for a future
provider. Business semantic validation and domain capability mapping belong to S2-3.

## Health, failures and logging

Health test only initializes and lists tools. AVAILABLE means the last check
succeeded, not current market data or business authorization. Initial/disconnected
health is UNKNOWN; expired/stalled auth is REAUTH_REQUIRED/DEGRADED; failures and
changed provider registration produce unavailable status. Last success and errors
remain distinguishable from current auth state. `/ready` stays application-only.

Stable failures distinguish not configured, auth/reauth required, authentication
and authorization failures, service unavailable, timeout, rate limited, missing or
disallowed tools, invalid arguments, schema/contract mismatch, stale generation,
revoked credentials, closed connection and secret-store unavailable. Existing TWF
wire names such as `SERVICE_UNAVAILABLE`, `INVALID_RESPONSE` and
`AUTHENTICATION_FAILED` are reused. Numeric Retry-After is bounded to 3600 seconds;
it never triggers automatic retries.

Structured metadata logs carry connection ID, generation, operation, outcome and
request correlation. SDK/HTTP debug payload logging is suppressed at composition.
No tokens, authorization headers, cookies, verifier, raw provider responses or URLs
are deliberately logged. This is operational correlation, not a new durable audit
ledger. Tests check token absence and owner boundaries. Public error envelopes use
the accepted request ID and safe message.

## Persistence and dependencies

Alembic `0007_mcp_connections`, after `0006_order_intents`, creates
`mcp_connections`, `mcp_secrets`, `mcp_oauth_attempts` with UUID ownership and foreign
keys. Follow-up `0008_mcp_cleanup_claim` adds the nullable cleanup lease to existing
0007 databases without deleting credentials. `0009_mcp_operation_permits` adds the
operation ledger without rewriting connection or secret rows. Follow-up
`0010_mcp_provider_outcome` adds nullable provider-result evidence without changing
existing outcomes or credential records. Its downgrade refuses outstanding permits
or REAUTH_DRAINING connections. Production startup does not migrate.
Apply `alembic upgrade head` explicitly
from `apps/api` with the intended database configured. Downgrade deletes these MCP
records and requires disconnect/revocation beforehand; it is not a token revoke tool.

The [official Python SDK](https://github.com/modelcontextprotocol/python-sdk) is MIT.
Its required HTTPX2 is already used by the test baseline and is promoted to runtime;
existing HTTPX broker paths are unchanged. JSON Schema validation uses MIT
`jsonschema`; dev-only typing uses `types-jsonschema`. Locked transitive additions
include MIT `mcp-types`, `attrs`, `referencing`, `rpds-py`, `PyJWT`, and JSON Schema
specifications, Apache-2.0 OpenTelemetry API and python-multipart, and BSD-3-Clause
sse-starlette. No agent framework is introduced. JWT/server dependencies arrive via
the SDK; TWF does not add JWT login, MCP server hosting or telemetry export.
Existing package pins were preserved. Primary protocol references:
[MCP authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization),
[transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).

Dependency audit **is not clean**: pip-audit reports seven entries (four distinct
advisory IDs) for the unchanged baseline `cryptography==47.0.0`: PYSEC-2026-3552,
PYSEC-2026-3553, PYSEC-2026-3554 and GHSA-537c-gmf6-5ccf. None were reported for added
packages. Reported fixed versions span 48.0.1–50.0.0, outside the existing `<48`
policy. The [upstream wheel advisory](https://github.com/pyca/cryptography/security/advisories/GHSA-537c-gmf6-5ccf)
and [PKCS#7 advisory](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5)
were checked. TWF uses Fernet, not PKCS#7 or cryptography's X.509 verifier; that does
not certify the entire dependency safe. Resolve the baseline dependency policy and
revalidate before production acceptance; no broad crypto upgrade is hidden here.

## Original implementation validation evidence

Historical implementation evidence; the remediation results below supersede counts
and close the four blockers for independent re-review, not self-acceptance.

- Full backend pytest: **775 passed in 98.16 seconds**, including **53 new MCP tests**
  and all 722 existing regression tests. No warnings were reported.
- New offline suites: `test_mcp_connections.py`, `test_mcp_security.py`,
  `test_mcp_recovery.py`, with `mcp_support.py` exercising the actual SDK.
- Covers no-auth/API key/OAuth, PKCE/state, expiry/refresh, restart, same-session
  binding, replay, five four-way SQLite callback races, encrypted references,
  swapped references, disconnect during exchange/discovery, cancellation, cleanup
  failure/retry, safe destinations, schema/byte/page/time limits, protocol drift,
  owner isolation, Origin/session API boundary and no public invocation route.
- SQLite upgrade/repeat/downgrade/re-upgrade and Alembic metadata checks pass.
- Disposable PostgreSQL 16 migration/repeat/downgrade/re-upgrade/check pass.
  Five independent four-way callback races each produce one success; subsequent
  discovery/refresh/disconnect leave no active or pending secret. Provider I/O uses
  the synthetic transport only; no developer database or broker was contacted.
- Ruff and format check pass (106 Python files); strict mypy passes (105 checked
  source files). Compilation/import and pip check pass. OpenAPI builds with 39 paths
  and 63 component schemas.
- Offline sdist/wheel build succeeds in a temporary environment with repository-
  compatible setuptools; the existing API venv has setuptools 84 outside `<83`.
- No frontend code changed; frontend build/browser runs are not applicable.
- Prettier passes for all five changed Markdown files; 152 local Markdown targets
  resolve. `git diff --check` passes.

## Exact change inventory

New source/migration files:

- `apps/api/src/twf/integrations/mcp/__init__.py`
- `apps/api/src/twf/integrations/mcp/contracts.py`
- `apps/api/src/twf/integrations/mcp/http.py`
- `apps/api/src/twf/integrations/mcp/oauth.py`
- `apps/api/src/twf/integrations/mcp/client.py`
- `apps/api/src/twf/integrations/mcp/connection.py`
- `apps/api/src/twf/infrastructure/mcp.py`
- `apps/api/src/twf/api/mcp.py`
- `apps/api/alembic/versions/0007_mcp_connections.py`

Modified source/configuration files:

- `apps/api/src/twf/config/settings.py`
- `apps/api/src/twf/main.py`
- `apps/api/src/twf/observability.py`
- `apps/api/alembic/env.py`
- `apps/api/pyproject.toml`
- `apps/api/requirements.lock`
- `apps/api/requirements-dev.lock`

New test files: `apps/api/tests/mcp_support.py`, `test_mcp_connections.py`,
`test_mcp_security.py`, `test_mcp_recovery.py` in that directory.
Existing `test_backend_shell.py`, `test_database_foundation.py` and
`test_foundation.py` retain exact inventories, extended for nine new routes,
three tables and migration head 0007.

Documentation: this new record, `README.md`, `docs/TWF_DOCUMENTATION_INDEX.md`,
`docs/TWF_DETAILED_ROADMAP.md`, `docs/TWF_UX_BUCKET_ROADMAP.md`. No normative
architecture or DOCX companion is modified. No commit, tag, push or branch operation.

## Limitations, deviations and review gate

Architecture deviations: **NONE**. Backend-only configuration and personal ownership
are the bounded paths explicitly permitted by the prompt and accepted architecture.
The workspace-isolation proof is rejection of unsupported workspace scope, not an
implemented cross-workspace sharing system.

Deferred: real provider registration/authorization acceptance; browser callback
landing UX; dynamic metadata/client registration; confidential-client/device grants;
shared ownership; background refresh/cleanup workers; administrative connection lists,
quotas and retention; distributed rate/cost budgets; richer schemas/transports;
production vault/key rotation; business tool mapping; all TradingView scanning,
Tapetide, S&D candidate logic and full settings UX. Existing broker authority,
manual orders, S2-1/S2-2, login and personal preferences remain unchanged.

Review must independently assess OAuth/transport boundaries, the known baseline
audit findings and real-provider compatibility before allowing S2-3. Implementation
completion does not imply acceptance, production readiness or authorization to
contact a real provider.

## Acceptance evidence

```ini
GENERIC_MCP_PROVIDER_CONFIG_IMPLEMENTED = YES
OWNER_SCOPED_CONNECTION_IDENTITY = YES
AUTH_STRATEGY_ABSTRACTION_IMPLEMENTED = YES
NO_AUTH_SUPPORTED = YES
OAUTH21_FOUNDATION_IMPLEMENTED = YES
API_KEY_AUTH_CONTRACT = YES
OAUTH_STATE_VALIDATION = YES
PKCE_IMPLEMENTED = YES
CALLBACK_OWNER_BINDING = YES
GENERATION_FENCING = YES
STALE_CALLBACK_REJECTED = YES
SECURE_TOKEN_REFERENCE_STORAGE = YES
RAW_TOKEN_NOT_IN_SETTINGS = YES
RAW_TOKEN_NOT_LOGGED = YES
TOKEN_REFRESH_SUPPORTED = PROVIDER_DEPENDENT
REVOCATION_DISCONNECT_IMPLEMENTED = YES
CLEANUP_PENDING_HANDLED = YES
MCP_TRANSPORT_IMPLEMENTED = YES
MCP_SESSION_LIFECYCLE = YES
TOOL_DISCOVERY_IMPLEMENTED = YES
TOOL_INVOCATION_IMPLEMENTED = YES
TOOL_ALLOWLIST_SUPPORTED = YES
DISCOVERY_DOES_NOT_IMPLY_AUTHORITY = YES
HEALTH_MODEL_IMPLEMENTED = YES
TYPED_FAILURES_IMPLEMENTED = YES
SYNTHETIC_MCP_PROVIDER = YES
SYNTHETIC_OAUTH_FLOW_PROVEN = YES
OWNER_ISOLATION_PROVEN = YES
GENERATION_FENCING_PROVEN = YES
SETTINGS_INTEGRATION = YES
SERVICE_CLIENT_REUSE = YES
BROKER_V2_REGRESSION_FREE = YES
S2_1_S2_2_REGRESSION_FREE = YES
TESTS_PASS = YES
READY_FOR_S2_3A_REVIEW = YES
```

These values refer to the bounded implementation and offline evidence above.
Dependency audit findings and deferred real-provider/browser acceptance remain
explicit review inputs, not silently waived checks.

## Historical first remediation — S23A-01 through S23A-04 — 2026-09-29

The following first-attempt evidence is historical. The independent
[focused re-review](TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION_REREVIEW.md)
kept S23A-01-R1 and S23A-04-R1 open. Its dispatch and teardown conclusions supersede
the first-attempt PASS claims below. The final remediation and explicitly approved
architecture decision are recorded in the next section.

Preflight remained `main` at `e22e17ffb2ce492e2a560193a8558c15b7836018`, with
only the uncommitted S2-3A implementation and historical
[HOLD review](TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION_ACCEPTANCE_REVIEW.md).
That review is preserved unchanged. Status is **REMEDIATED / READY FOR RE-REVIEW**;
S2-3 remains **BLOCKED / PENDING S2-3A ACCEPTANCE**. Architecture deviations: **NONE**.

### Dispatch authority and session retirement — S23A-01

`SafeTransport` checks authority after DNS and request preparation, immediately
before handing the request to the HTTP transport. The manager reloads the owner,
active login, configuration fingerprint, generation, enabled state and encrypted
reference binding. The same gate covers SDK initialization, GET/reconnect, list,
call and normal DELETE requests. OAuth exchange/refresh and cleanup receive their
own scoped dispatch fences via a context variable; no mutable global credential
state is used. Timeout is checked again after the fence.

Generation supersession makes old sessions logically non-dispatchable through the
DB fence even across manager instances. On rejection the transport records the
safe typed failure and retires; future sends cannot reach its inner transport.
That stored failure survives SDK background-error normalization. Local close is
idempotent. Requests already handed to the transport before revocation cannot be
unsent; their stale results still cannot attach. No automatic tool replay is added.

### Refresh receipt, promotion and cleanup — S23A-02

The explicit transition is:

```text
ACTIVE A → retire A with cleanup obligation → CONNECTING G+1
         → provider refresh → persist B as revoked/cleanup-pending
         → locked owner/session/generation check → promote that same B reference
```

Promotion changes the pending reference in place, avoiding a second copy of B for
promotion. Disconnect clears active authority and advances generation first.
A remains tracked even if provider refresh fails or the process loses the in-memory
transition. B, once received and durably stored, is either promoted under the
current generation or retained only for cleanup. Cleanup deleting a pending B
after disconnect cannot cause stale promotion: promotion requires the row to
still exist and the authoritative generation to match. No database transaction
spans provider I/O. As before, a total database outage or an unreceived remote
token has explicit recovery limitations; this change does not claim distributed
atomicity with the provider.

### Conservative credential ownership protection — S23A-03

Generation age alone no longer permits remote revocation. Existing stable secret
reference UUIDs remain encrypted and generation-bound. Because generic providers
may reuse token values or relate different token values to the same grant, cleanup
protects the entire **owner/provider authority group**: if any connection in that
group is CONNECTED or CONNECTING and enabled, revoked references remain pending.
This deliberately protects a superset of potentially shared material and does not
infer provider grant identity from plaintext comparison. The tradeoff is delayed
cleanup for obsolete credentials until all such authoritative connections are
disconnected or require reauthentication. Pending cleanup never grants local use.

A short DB transaction, serialized by the existing owner lock / SQLite writer
reservation, claims cleanup. `cleanup_until` prevents new authentication authority
in that owner/provider group during the bounded remote revoke attempt. The claim
expires after the provider budget plus one second for bookkeeping, permitting
restart recovery. Cleanup dispatch also checks its claim. Completion deletes only
the captured resolved reference IDs; errors retain obligations, and local storage
failures release the claim separately where possible. Retry remains explicit.
Within one batch, transient SHA-256 token fingerprints prevent duplicate revoke
calls for identical values; fingerprints and raw values are neither stored nor
logged. No new encryption algorithm, key system or credential-sharing feature is
introduced.

### Deadline and error precedence — S23A-04

The official SDK runs within AnyIO's level-cancellation deadline. Its unbudgeted
`terminate_on_close` DELETE is disabled. Normal explicit DELETE is inside the same
operation budget and authority fence; it occurs once. On timeout all owned local
SDK/HTTP contexts unwind under cancellation, without detached or untracked tasks.
No new background-worker architecture is introduced.

Deadline expiry is reported as **TIMEOUT**, including when local close also raises.
A previously recorded dispatch-authority failure remains the authoritative safe
failure when the SDK wraps it. Secondary teardown errors cannot turn an expired
operation into SERVICE_UNAVAILABLE. Connection health records the typed failure
as unavailable/degraded evidence; successful normal close retains normal results.
There is no attempt to continue remote DELETE after the deadline or after authority
revocation. Remote MCP session termination is therefore best effort on abnormal
exit; provider-side expiry remains necessary. All local session tasks/transports
are closed, rather than keeping a worker alive to retry remote session deletion.
Encrypted token revocation obligations are separate and remain explicitly pending.

### Regression evidence and exact remediation inventory

New `tests/test_mcp_remediation.py` adds 18 default cases, with 12 lifecycle cases
also executable against an explicitly supplied disposable local PostgreSQL URL.
The fixture refuses nonlocal/non-test database names and does not use the
application database URL. Event barriers cover dispatch after DNS, SDK GET
reconnect, logout/supersession, seven refresh phases, pending/active retained-token
protection, cleanup claims and retry through a recreated manager. A fixture that
honors revocation proves the active generation remains usable. Deadline tests
block response teardown on an event, use an 80 ms budget and a 250 ms upper bound,
and verify cancellation, TIMEOUT precedence over local close errors and normal /
idempotent closure. No race is orchestrated with sleep.

Source modified in this remediation:

- `apps/api/src/twf/integrations/mcp/http.py`
- `apps/api/src/twf/integrations/mcp/client.py`
- `apps/api/src/twf/integrations/mcp/connection.py`
- `apps/api/src/twf/integrations/mcp/oauth.py`
- `apps/api/src/twf/infrastructure/mcp.py`

Created migration: `apps/api/alembic/versions/0008_mcp_cleanup_claim.py`.
Created tests: `apps/api/tests/test_mcp_remediation.py`.
Updated tests: `apps/api/tests/test_database_foundation.py` (expected migration head
only; prior security assertions are retained).
Documentation: this record, README, detailed roadmap, UX bucket roadmap and
documentation index. No frontend, broker, S2-1/S2-2 runtime, dependency locks or
historical acceptance review changed.

Deferred S23A-05 remains the remote-session closure error-fidelity follow-up.
S23A-06 remains **NONBLOCKING_WITH_EVIDENCE**, with four known cryptography advisories;
the dependency audit is not represented as clean and no dependency was upgraded.
No real MCP provider, broker call, Git mutation or acceptance/freeze action is part
of this remediation.

### Remediation validation results

- Full backend suite: **793 passed in 134.90 seconds**, no warnings; all 775 prior
  cases retained and 18 new cases added.
- SQLite/PostgreSQL remediation matrix: **30 passed** (18 default cases plus
  12 PostgreSQL lifecycle cases). Five additional four-way PostgreSQL callback
  races and five two-way refresh races each produced exactly one success and safe
  stale losers; restart, discovery and disconnect passed.
- PostgreSQL 16: clean upgrade, repeated upgrade, 0008 downgrade to 0007,
  re-upgrade and metadata check passed. SQLite full migration/lifecycle/concurrency
  checks passed in the full suite. Only disposable databases were used.
- Ruff lint/format passed: 108 Python files formatted. Strict mypy passed:
  107 checked files. Compilation/imports and OpenAPI construction passed:
  39 paths / 63 schemas. `pip check` passed.
- Offline sdist/wheel build passed with repository-compatible temporary build
  tooling. Runtime dependencies and lock files are unchanged by remediation.
- Prettier passed for five changed Markdown files; 153 local links resolve;
  `git diff --check` passed. Frontend is unchanged.

```ini
S23A_01_DISPATCH_BOUNDARY_FENCING = PASS
S23A_01_STALE_SESSION_RETIRED = PASS
S23A_01_NO_AUTH_DISPATCH_AFTER_STALE = PASS
S23A_02_REFRESH_CLEANUP_OBLIGATION_PRESERVED = PASS
S23A_02_DISCONNECT_DURING_REFRESH_SAFE = PASS
S23A_02_NO_STALE_TOKEN_PROMOTION = PASS
S23A_03_ACTIVE_CREDENTIAL_REFERENCE_PROTECTED = PASS
S23A_03_SHARED_CREDENTIAL_NOT_REVOKED = PASS
S23A_03_DEFERRED_CLEANUP_RETRIES = PASS
S23A_04_CALLER_TIMEOUT_BOUNDED = PASS
S23A_04_TIMEOUT_ERROR_PRESERVED = PASS
S23A_04_SLOW_TEARDOWN_DETACHED_OR_BOUNDED = PASS
S23A_04_CLEANUP_FAILURE_DOES_NOT_MASK_TIMEOUT = PASS
GENERATION_FENCING_REGRESSION_FREE = PASS
OWNER_ISOLATION_REGRESSION_FREE = PASS
OAUTH_PKCE_REGRESSION_FREE = PASS
SECRET_STORAGE_REGRESSION_FREE = PASS
TOOL_ALLOWLIST_REGRESSION_FREE = PASS
S2_1_S2_2_REGRESSION_FREE = PASS
BROKER_V2_REGRESSION_FREE = PASS
TESTS_PASS = PASS
READY_FOR_S2_3A_REREVIEW = YES
```

This is implementation/remediation evidence, not independent acceptance. The
historical HOLD review remains unchanged and S2-3 is not authorized by this record.

## Final focused remediation — approved permits and draining disconnect

Status remains **REMEDIATED / READY FOR RE-REVIEW**. S2-3 remains
**BLOCKED / PENDING S2-3A ACCEPTANCE**. Neither historical review is modified.

### Approved architecture decision

The user explicitly rejected a database lock spanning provider I/O and approved
durable generation-bound operation permits, draining disconnect, and hard public
deadlines. This supersedes the previous requirement to cancel every physically
unsent request immediately on disconnect request. Previously admitted operations
may finish during DISCONNECTING; no authenticated application request may start
after **completed** disconnect. An admission commit is the permission boundary,
not a claim that network bytes have already been transmitted.

No database transaction or lock spans DNS, HTTP, streaming or local pool close.
Admission, state transitions and completion use short transactions with the same
SQLite writer reservation / PostgreSQL owner/session/connection locking order.
There is no provider-specific code, distributed worker framework or dependency change.

### Durable admission and drain — S23A-01-R1

`mcp_operations` binds each permit to its UUID, connection, owner, generation,
login session hash, worker UUID, operation kind, creation/deadline timestamps,
outcome, cleanup state and completion timestamp. The UUID also identifies the
owned local operation/task and its transports. Remote session IDs remain local
and are not exposed or logged. Maximum eight outstanding permits per connection;
maximum 128 owned invocation tasks per manager, with fail-closed admission.

Secret resolution occurs inside atomic admission. An unresolved or expired
outstanding permit blocks new admission. Each outbound request still rechecks
owner/login, permit identity, generation, provider fingerprint and deadline after
DNS. Reconnect, reauthorization and refresh cannot supersede a generation while
its operations remain outstanding.

```text
CONNECTED / CONNECTING
  -> atomically disable new admission -> DISCONNECTING (same generation)
  -> admitted operations finish, including local unwind
  -> owning worker records COMPLETE
  -> last completion retires the secret and advances generation -> DISCONNECTED
```

Disconnect observes drain for up to 50 ms within its invocation budget, then
returns a truthful DISCONNECTING view if necessary. Status adds `operations_pending`
and `recovery_required`. A subsequent status read can observe automatic completion
by the last finishing owner; retrying disconnect while still draining is safe.
Provider token revocation is separate cleanup work, not an authenticated tool call;
it may remain pending after local disconnect. No business call is retried.

A worker-completion gap after either admission commit or the final authority-check
commit no longer permits a false completed disconnect: the durable permit remains
visible to every worker. Tests deliberately allow the admitted request to reach
the synthetic transport while DISCONNECTING, then assert no authenticated
application dispatch after DISCONNECTED. Late discovery/authentication results
cannot promote while disconnect is draining.

### End-to-end deadline and teardown — S23A-04-R1

The public caller waits on an owned invocation task and an independent deadline
signal; it does not await a cancellation-shielded HTTP pool close past that deadline.
The deadline starts at invocation entry, including admission and result bookkeeping.
Before the provider is identified, the smallest registered budget bounds lookup;
once identified, its configured absolute deadline still starts at invocation entry.
Connect/read/write/pool timeouts and byte/page/tool budgets remain in force.

Expiration retires the operation and cancels its AnyIO scope. Every transport
checks that retirement immediately before handoff, so an expired invocation cannot
start another authenticated request. The caller receives TIMEOUT, even if work
completed but successful unwind exceeded the deadline. An explicit final check
before returning success covers completed tasks as well as errors. Late success
or a secondary teardown error cannot replace the caller's TIMEOUT.

`Operations` keeps strong, named task ownership until SDK contexts, HTTP contexts,
and final bookkeeping finish. Database workers are also awaited by that owner
before permit completion, even when the caller has already timed out. Shutdown
retires owned operations and attempts a bounded drain before engine disposal.
This is local resource ownership, not a generic background-job service.

Durable permit state is RUNNING during provider work, then FINALIZING during
local outcome persistence. After expiry, status reports
recovery required; a disconnect marks the outstanding permit UNRESOLVED. Successful
late unwind may mark it COMPLETE but never changes the invocation's TIMEOUT result.
A failed local close remains UNRESOLVED with FAILED_RETRYABLE diagnostics. An absent
worker cannot complete another worker's permit. Restart or lease expiry never
silently deletes these records, advances generation, or assumes sockets stopped.

**Recovery limitation:** unknown worker liveness or failed local close requires
operator investigation and proof of worker/socket termination before any future
repair can resolve the permit. This slice provides truthful fail-closed recovery
state, not an automatic administrative override or a claim that failed close
succeeded. Ordinary encrypted-token revocation failures still use the existing
explicit cleanup retry route. No request is replayed to recover a permit.

Remote revocation also has a durable operation permit. The owner/provider cleanup
lease still serializes claims, and outstanding revocation permits protect that
owner/provider group even after lease expiry while shielded teardown continues.
Thus timeout does not reopen authorization against an unresolved revocation.
S23A-02 token receipt/promotion obligations and S23A-03 conservative shared-grant
protection remain in force.

### Final remediation inventory

Source modified in this final remediation:

- `apps/api/src/twf/api/mcp.py`
- `apps/api/src/twf/integrations/mcp/connection.py`
- `apps/api/src/twf/integrations/mcp/contracts.py`
- `apps/api/src/twf/integrations/mcp/client.py`
- `apps/api/src/twf/integrations/mcp/http.py`
- `apps/api/src/twf/infrastructure/mcp.py`
- `apps/api/src/twf/main.py`

New source: `apps/api/src/twf/integrations/mcp/lifecycle.py`.
New migration: `apps/api/alembic/versions/0009_mcp_operation_permits.py`.
Migration downgrade refuses outstanding permits; stop application workers before
migration changes. No developer database is migrated during validation.

New tests: `apps/api/tests/test_mcp_permits.py`. Updated tests:
`test_mcp_remediation.py`, `test_mcp_recovery.py`, `test_mcp_security.py`,
`test_database_foundation.py`, `test_foundation.py`. Changes to prior tests reflect
the approved drain/owned-teardown semantics; the refresh phase matrix, cleanup
protection, token secrecy, owner checks and permit/transport counts remain asserted.

Documentation modified: this file only. Historical review records, dependencies,
frontend, Broker V2 and Scan & Discover business implementation are unchanged.
Cryptography advisory disposition remains **NONBLOCKING_WITH_EVIDENCE**; the audit
is not clean and no dependency upgrade is included.

### Final validation

- Full backend pytest: **813 passed in 114.60 seconds**, no warnings. This
  includes all prior 793 cases plus 20 new permit/deadline cases. Broker V2,
  S2-1/S2-2, settings, service clients and auth/security regressions pass.
- SQLite/PostgreSQL focused matrix: **62 passed in 22.16 seconds**. Five rounds
  per database at each of two committed-worker barriers (admission and final
  authority check); separate OS-process drain/admission tests on both databases;
  retained seven-phase refresh and shared-credential cleanup tests.
- Actual HTTPcore shielded-pool reproducer: **80–81 ms caller latency** for an
  80 ms budget in all four scenarios (successful body, timed-out body, delayed
  close error, timeout plus delayed close error). Every result is TIMEOUT;
  local tasks remain owned at return and subsequently drain. Unit regressions
  assert a 150 ms upper bound with event-controlled teardown and late-result
  quarantine, including delayed DB-worker and final public-status lookup cases.
- Migration 0009 on disposable SQLite/PostgreSQL 16: upgrade, repeat upgrade,
  refusal to downgrade with an unresolved permit, safe downgrade/re-upgrade,
  preservation of connection generation and encrypted-record sentinel, and
  Alembic metadata check all pass. The disposable PostgreSQL container was removed.
- Ruff lint and format pass (111 Python files). Strict mypy passes (110 checked
  files). Compilation/imports, `pip check`, and offline sdist/wheel build pass.
  OpenAPI remains 39 paths / 63 schemas; DISCONNECTING and both recovery fields
  are present in the generated contract.
- Prettier, local Markdown link checks and `git diff --check` pass. The changed-file
  hash comparison matches this remediation inventory; dependency files and the
  historical acceptance review match the prior review snapshot. Neither historical
  review was edited. No frontend/browser rerun is claimed for this backend-only change.

The following legacy scorecard names are evaluated under the explicitly approved
**admission/draining** contract. In particular, “after disconnect” means after
DISCONNECTED, not after the initial request enters DISCONNECTING. The old physical
send-versus-immediate-revocation invariant is superseded, not silently claimed.

```ini
S23A_01_FINAL_DISPATCH_SERIALIZED = PASS
S23A_01_WORKER_COMPLETION_GAP_BLOCKED = PASS
S23A_01_NO_AUTH_POST_AFTER_DISCONNECT = PASS
S23A_01_SQLITE_RACE_PASS = PASS
S23A_01_POSTGRES_RACE_PASS = PASS

S23A_04_FINAL_DEADLINE_CHECK = PASS
S23A_04_SUCCESS_AFTER_DEADLINE_BLOCKED = PASS
S23A_04_SHIELDED_CLOSE_BOUNDED = PASS
S23A_04_DEFERRED_TEARDOWN_TRACKED = PASS
S23A_04_TIMEOUT_ERROR_PRESERVED = PASS

S23A_02_REGRESSION_FREE = PASS
S23A_03_REGRESSION_FREE = PASS
OWNER_ISOLATION_REGRESSION_FREE = PASS
OAUTH_PKCE_REGRESSION_FREE = PASS
SECRET_STORAGE_REGRESSION_FREE = PASS
TOOL_ALLOWLIST_REGRESSION_FREE = PASS
S2_1_S2_2_REGRESSION_FREE = PASS
BROKER_V2_REGRESSION_FREE = PASS
TESTS_PASS = PASS

ARCHITECTURE_CHANGE_TO_ALLOW_DB_LOCK_ACROSS_PROVIDER_IO = NO
DURABLE_OPERATION_PERMIT_AND_DRAINING_DISCONNECT = IMPLEMENTED
HARD_END_TO_END_TIMEOUT_SEMANTICS = IMPLEMENTED
READY_FOR_S2_3A_REREVIEW = YES
```

This records implementation evidence only. Independent re-review is still required;
S2-3 remains blocked and no acceptance, freeze, commit, tag or push is performed.

## Corrected final focused remediation — auth draining and durable outcomes

Status: **REMEDIATED / READY FOR RE-REVIEW**. S2-3 remains **BLOCKED / PENDING
S2-3A ACCEPTANCE**. This section records the corrected remediation; earlier
validation sections describe their respective earlier implementation checkpoints.
Neither historical HOLD/re-review document is changed.

### Auth-failure admission and retirement

HTTP 401 / authentication failure now uses the existing permit drain:

```text
CONNECTED G1
  -> atomically close admission, set REAUTH_DRAINING G1
  -> retain G1 credential authority for already-admitted permits
  -> drain admitted work and quarantine late provider success
  -> last resolved permit retires G1 authority and advances generation
  -> REAUTH_REQUIRED
```

Invalidation BEGIN and FINAL invalidation are different boundaries. A permit
admitted before BEGIN may still physically send under G1 while draining; the
corrected architecture expressly permits that. New admission receives a typed
REAUTH_REQUIRED rejection. Reconnect/refresh cannot replace the draining
credential. Already-admitted operations remain subject to the existing owner,
session, configuration, permit and deadline checks. No new last-moment check is
claimed to eliminate the transport handoff gap.

The auth-failure transaction marks pending permits with negative auth outcomes,
using the original authentication error for the detecting operation and
REAUTH_REQUIRED for its peers. G1's secret and generation remain intact until
all admitted work resolves. Late provider success cannot clear this state,
restore healthy authority, or replace those outcomes. FINAL invalidation retires
the secret and advances generation. Old-generation admission/dispatch is then
rejected. Remote token revocation remains a separate bounded cleanup obligation.

Expired/lost-worker permits and failed local close remain outstanding; expiry is
not evidence that sending stopped. REAUTH_DRAINING therefore remains visible with
`operations_pending` / `recovery_required`. Recreated managers preserve the fence.
Existing operator investigation requirements still apply; this slice does not
add an administrative force-complete endpoint. Shared-grant cleanup also protects
REAUTH_DRAINING connections.

### Provider evidence and final-outcome arbitration

`MCPOperation.provider_outcome` is bounded diagnostic evidence, not an authority
grant. For example, provider_outcome=SUCCESS with outcome=TIMEOUT or
REAUTH_REQUIRED is valid. No raw response, token or additional secret is stored.

Finalization has two short local transactions after provider/SDK contexts unwind:

1. Persist provider evidence and FINALIZING. This preparation does not decide
   SUCCESS. A lost worker at this stage remains visible and blocks drain.
2. Under the same durable owner/session/connection/permit locking order, arbitrate
   immediately at the SQLAlchemy session commit boundary, record the outcome and
   cleanup state, and settle any connection drain.

Arbitration is explicit rather than a numeric severity ranking:

- The first caller timeout/cancellation signal is final for that invocation and
  is retained as TIMEOUT/CANCELLED during owned persistence reconciliation.
- Without such a caller decision, the first database-serialized negative permit
  outcome is retained. Auth invalidation writes this guard in the transaction
  that closes admission; replayed completion cannot change it to SUCCESS.
- A SUCCESS candidate must still pass deadline and connection-generation/draining
  checks at finalization. A reached deadline becomes TIMEOUT; auth drain becomes
  REAUTH_REQUIRED; explicit disconnect/supersession becomes STALE_GENERATION.
- A completion write failure never returns SUCCESS. The closest existing typed
  storage failure, SECRET_STORE_UNAVAILABLE, is reused with sanitized diagnostics.

Public timeout does not wait for a stalled commit or shielded unwind. If commit
execution or result delivery crosses that caller boundary, the owned task checks
again and persists the negative caller decision before relinquishing ownership.
A caller cancellation after task completion similarly schedules a named, tracked
negative-only reconciliation. Commit delivery is not treated as an atomic
transaction with the HTTP caller: database bookkeeping can remain pending after
that caller has received its final negative result. No success audit is emitted
while this reconciliation remains pending.

Once a negative outcome is durable, subsequent completion uses the locked permit
record as its guard, even without the original in-memory terminal marker. Provider
evidence may be retained; it cannot promote the negative outcome to SUCCESS.

### Success, failure and audit sequencing

The success path is provider result, local finalization, successful commit, final
caller deadline check, then SUCCEEDED audit and caller return without another
async suspension. SUCCESS is never returned when completion persistence fails.
The audit is the existing sanitized operational log, not a new transactional
outbox or exactly-once delivery guarantee. Process failure can omit a success log;
this implementation does not claim atomic delivery of database state and logs.

A failed completion is reported as a typed storage failure, or the already-final
caller TIMEOUT/CANCELLED. Best-effort recovery persistence retains provider evidence,
marks the permit UNRESOLVED / FAILED_RETRYABLE and records unavailable health.
If that persistence is also unavailable, the previous durable RUNNING/FINALIZING
record remains and sanitized `permit_completion / UNRESOLVED` logging records the
failure. An ambiguous commit acknowledgment requires investigation; a database
outage is not represented as proof of a clean result. Existing unresolved permits
block drain/admission across restart; no remote request is replayed as recovery.

No normal SUCCEEDED audit is emitted for timeout, cancellation, auth invalidation
or completion persistence failure. Late task exceptions are consumed by the
existing operation owner. No database transaction or authority lock spans
provider I/O, DNS, response streaming or transport teardown.

### Focused change and test inventory

Changed in this corrected remediation:

- `apps/api/src/twf/integrations/mcp/connection.py`: auth drain, durable outcome
  arbitration, persistence failure handling, and deferred success audit.
- `apps/api/src/twf/integrations/mcp/lifecycle.py`: caller terminal decision,
  tracked reconciliation, and post-commit audit delivery.
- `apps/api/src/twf/integrations/mcp/contracts.py`: REAUTH_DRAINING and CANCELLED.
- `apps/api/src/twf/infrastructure/mcp.py`: separate provider-outcome evidence.
- `apps/api/alembic/versions/0010_mcp_provider_outcome.py`: new additive migration
  and guarded downgrade; explicitly run `alembic upgrade head` before deployment.
- `apps/api/tests/test_mcp_finalization.py`: 33 default cases, also all executed
  against disposable PostgreSQL 16 (66 cases across the two databases).
- `apps/api/tests/test_database_foundation.py`: expected migration head only.
- This implementation document.

Auth tests pause after a committed authority check before real synthetic transport
send, inside provider I/O, and after provider success before finalization. Each is
repeated three times per database. A second manager receives a real synthetic
HTTP 401; tests observe the admission fence, generation/reference retention,
negative durable outcomes, no success audit and zero old-generation sends after
FINAL invalidation. A separate matrix covers multiple admitted operations and a
lost worker during auth drain. The mock transport also acquires the same authority
locks through a different session during network work, detecting a DB lock held
across that boundary.

Finalization tests pause at preparation commit, decision commit, and committed
result delivery for TIMEOUT/CANCELLED, repeated three times per database. Both databases
use a 400 ms invocation budget so the actual SDK reaches the intended commit
barrier even under suite load. Each enforces at most 120 ms scheduler tolerance.
Existing actual HTTPcore shielded-teardown tests retain the 80 ms budget / 150 ms
caller bound. All races use events/barriers rather than scheduler sleeps.
Persistence tests force transactional write/commit failure at both finalization
stages, including failure of the recovery write. Success audit tests independently
read the committed record from another session. Late replay tests clear the local
terminal marker to verify the durable negative guard itself.

### Corrected remediation validation

- Full backend suite: **846 passed in 127.84 seconds**, no warnings. All 813
  previous cases remain; 33 focused cases were added. Existing rate-limit retry
  metadata is preserved when finalization retains the original typed failure.
- Final SQLite/PostgreSQL 16 matrix: **128 passed in 39.28 seconds**: 66 corrected
  finalization/auth cases plus 62 existing permit/refresh/cleanup cases. This final
  run uses the stabilized 400 ms finalization budget; the existing 80 ms pool-close
  and public-deadline cases remain unchanged and passing.
- Migration 0010: SQLite and PostgreSQL upgrade from 0009, repeated upgrade,
  0010/0009/0010 round trip, existing connection/credential/outcome preservation,
  unresolved-permit and REAUTH_DRAINING downgrade refusal, and Alembic metadata
  checks passed. Only disposable databases were used.
- Ruff lint and formatting: **113 files**; strict mypy: **112 files**; Python
  compilation/imports, OpenAPI (**39 paths / 63 schemas**, including the new
  state/outcome), `pip check`, and offline sdist/wheel build passed.
- Prettier: five current-status/implementation Markdown files checked; **154 local
  link targets** resolve; `git diff --check` passed. No frontend validation is
  claimed for this backend-only remediation.
- The preflight hash comparison identifies exactly the eight files listed above.
  Dependency manifests/locks, README/roadmaps, historical reviews, Broker V2 and
  S2-1/S2-2 source remain unchanged by this corrected remediation. HEAD remains
  `e22e17ffb2ce492e2a560193a8558c15b7836018` on `main`; no Git history/ref mutation.

S23A-02 and S23A-03 remain closed without redesign. S23A-04 bounded public deadlines
and owned teardown are preserved. S23A-05 remains **LOW / SAFE TO DEFER**.
S23A-06 remains **NONBLOCKING_WITH_EVIDENCE**; the cryptography audit is **not clean**.
Dependency manifests and locks are unchanged by this remediation. Architecture
deviations: **NONE**. No frontend, broker, S2-1/S2-2 implementation, roadmap status,
historical review or Git history is changed. No real provider or broker is called.

```ini
S23A_AUTH_FAILURE_USES_DRAINING = PASS
S23A_AUTH_FAILURE_CLOSES_NEW_ADMISSION = PASS
S23A_AUTH_FAILURE_EXISTING_PERMITS_DRAIN = PASS
S23A_AUTH_FAILURE_LATE_SUCCESS_NOT_PROMOTED = PASS
S23A_AUTH_FAILURE_FINAL_RETIREMENT_AFTER_DRAIN = PASS
S23A_NO_AUTH_DISPATCH_AFTER_FINAL_INVALIDATION = PASS
S23A_AUTH_FAILURE_SQLITE_RACE = PASS
S23A_AUTH_FAILURE_POSTGRES_RACE = PASS

S23A_FINAL_OUTCOME_MONOTONIC = PASS
S23A_TIMEOUT_DURABLE_OUTCOME_TRUTHFUL = PASS
S23A_CANCELLATION_DURABLE_OUTCOME_TRUTHFUL = PASS
S23A_AUTH_INVALIDATION_DURABLE_OUTCOME_TRUTHFUL = PASS
S23A_LATE_SUCCESS_CANNOT_OVERWRITE_TERMINAL = PASS

S23A_SUCCESS_AUDIT_AFTER_DURABLE_COMMIT = PASS
S23A_NO_SUCCESS_AUDIT_ON_TIMEOUT = PASS
S23A_NO_SUCCESS_AUDIT_ON_CANCEL = PASS
S23A_NO_SUCCESS_AUDIT_ON_AUTH_INVALIDATION = PASS

S23A_COMPLETION_PERSISTENCE_FAILURE_TYPED = PASS
S23A_COMPLETION_PERSISTENCE_FAILURE_NOT_SUCCESS = PASS
S23A_UNRESOLVED_PERMIT_RECOVERABLE = PASS
NO_DB_LOCK_ACROSS_PROVIDER_IO = PASS

S23A_02_REGRESSION_FREE = PASS
S23A_03_REGRESSION_FREE = PASS
S23A_04_REGRESSION_FREE = PASS
OWNER_ISOLATION_REGRESSION_FREE = PASS
OAUTH_PKCE_REGRESSION_FREE = PASS
SECRET_STORAGE_REGRESSION_FREE = PASS
TOOL_ALLOWLIST_REGRESSION_FREE = PASS
S2_1_S2_2_REGRESSION_FREE = PASS
BROKER_V2_REGRESSION_FREE = PASS
TESTS_PASS = PASS
READY_FOR_S2_3A_REREVIEW = YES
```

This is remediation evidence only. Independent acceptance is still required;
S2-3 remains blocked. No new freeze tag or implementation authorization is implied.

## Integrated S2-3 durability closure — 2026-09-29

Migration 0011 adds `auth_invalidation_pending` and `reconciliation_required`.
A durable auth intent precedes the normal fence write; its loss/failure cannot
silently reopen admission after that intent commits. A committed SUCCESS candidate
retains a reconciliation obligation until the owned post-return delivery receipt.
The callback may not clear that marker before the public timeout/cancellation
boundary. Success audit follows confirmed delivery bookkeeping.

Owner-scoped POST `connections/{identity}/recover` uses only durable local state.
Known negative outcomes stay negative. Expired ambiguous/lost work becomes
UNRESOLVED, preserving provider evidence without guessing a lost caller result or
replaying any provider request. Lease expiry is not completion proof. Auth drain,
generation retention/retirement, hard deadlines and no DB transaction across I/O
remain unchanged. Status projects pending auth invalidation as disabled
REAUTH_DRAINING. No raw credentials are added to these marker columns.

Actual spawned-process loss, real commit/lost acknowledgment, cancellation/timeout,
receipt failure, restart and second-worker rejection are covered on SQLite and
PostgreSQL 16. Migration downgrade guards preserve outstanding recovery obligations.
For exact final counts, limits, operator recovery and current integrated acceptance,
see the [S2-3 record](TWF_S2_3_TRADINGVIEW_MCP_SCAN_PROVIDER_IMPLEMENTATION.md) and
[review](TWF_S2_3_ACCEPTANCE_REVIEW.md). The prior three independent review files are
byte-identical; this appendix does not rewrite their findings or create a freeze.
