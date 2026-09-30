# S2-3A — Focused Independent Re-Review

Date: **2026-09-29**. Decision: **HOLD_S2_3A**.

Starting branch: `main`. Starting HEAD:
`e22e17ffb2ce492e2a560193a8558c15b7836018`.

The [historical HOLD review](TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION_ACCEPTANCE_REVIEW.md)
is preserved. This re-review assesses the four remediations against actual source,
tests, installed SDK/HTTP dependencies and additional synthetic probes. It does
not modify implementation, tests, dependencies or milestone statuses.

## A. Preflight and scope

Branch/HEAD, status, tracked diff/stat/name inventory and recent history were
checked. All implementation/remediation changes remain uncommitted. No unrelated
changes were found. S2-2 remains frozen at `twf-s2-2-internal-scanner-v0` on the
starting HEAD; Broker V2 remains frozen at `twf-broker-v2` / `69a643e`.
README correctly shows S2-3A REMEDIATED / READY FOR RE-REVIEW and S2-3 BLOCKED /
PENDING S2-3A ACCEPTANCE. No Git mutation occurred.

Remediation inventory inspected:

- `integrations/mcp/http.py`, `client.py`, `connection.py`, `oauth.py`;
- `infrastructure/mcp.py` and `alembic/versions/0008_mcp_cleanup_claim.py`;
- `tests/test_mcp_remediation.py`, the migration-head assertions in
  `test_database_foundation.py`, and previous MCP/security/recovery suites;
- README, the [implementation/remediation record](TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION.md),
  documentation index, detailed roadmap and UX bucket roadmap.

Relevant accepted [security](TWF_SECURITY_AUTH_ARCHITECTURE.md),
[service contracts](TWF_SERVICE_CONTRACT_ARCHITECTURE.md),
[service integration](TWF_SERVICE_INTEGRATION_ARCHITECTURE.md),
[configuration/ownership](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md)
and [data](TWF_DATA_ARCHITECTURE.md) boundaries remain governing. No provider-specific
business semantics or unrelated future scope is reopened.

## B. S23A-01 — improved, but not closed

The new check after DNS correctly blocks the tested DNS/disconnect race. Rejected
transports retain a safe typed failure, set `retired`, and refuse subsequent sends.
The original SDK GET-reconnect scenario is covered by the passing new suite.
However, the final authority check is itself asynchronous:

```text
SafeTransport.handle_async_request → await fence()
  → await manager.write(capture)
  → asyncio.to_thread(transaction)
  → check authority, COMMIT, release locks
  → worker result delivered to event loop
  → inner.handle_async_request sends captured Authorization header
```

There is no serialization between the committed authority decision and request
handoff. A disconnect can complete in that gap. The remaining checks after
`await fence()` inspect only this transport's local retired flag and deadline;
disconnect does not independently set that flag on the old transport.

### Deterministic independent reproduction

Temporary script: `/tmp/s23a-rereview/deep_probes.py`.

1. Establish an API-key connection and start a normal manager tool-discovery call.
2. Instrument `manager.transaction` in the review process only. Run the original
   transaction completely, including commit; at the transport's authority capture,
   pause its worker thread using `threading.Event` before returning the result.
3. On the event loop, fully complete disconnect through the unmodified manager.
4. Release the worker thread and record every actual authenticated call received
   by the inner synthetic HTTP transport.

This models delayed delivery of a completed worker result, without changing the
transaction's checks or its return value. The barrier is after the authority read
and before the inner transport is called; it is not delaying a request already
handed off to that transport. No sleeps orchestrate the race.

| Database      | Authenticated dispatches starting after disconnect | Method            | Final caller result |
| ------------- | -------------------------------------------------- | ----------------- | ------------------- |
| SQLite        | **1**                                              | POST (initialize) | STALE_GENERATION    |
| PostgreSQL 16 | **1**                                              | POST (initialize) | STALE_GENERATION    |

Both outcomes reproduced again in a second run. Final stale-result rejection is
working, but it does not undo the credential transmission. All credentials and
responses in these probes are synthetic; no external network is used.

**S23A-01 remains HIGH / MUST FIX BEFORE S2-3.** Establish an enforceable dispatch
linearization/serialization boundary with authority revocation. Merely adding
another asynchronous read leaves the same class of gap. Regression proof must
pause after the final DB authority transaction has released its locks, not only
before DNS completes. Preserve normal semantics for requests actually handed off
before revocation.

## C. S23A-02 — closed for the reviewed lifecycle

Old refresh credentials now remain revoked cleanup obligations. Receipt of a
replacement token creates a durable pending secret reference; promotion reuses
that row and rechecks owner/session/generation. Missing/deleted pending rows or
stale generations cannot promote. Disconnect removes local authority first.

The seven-phase matrix passed independently on SQLite and PostgreSQL:
BEFORE_PROVIDER_CALL, PROVIDER_CALL_IN_FLIGHT, TOKEN_RETURNED, PENDING_STORED,
PROMOTION_PENDING, PROMOTED and OLD_CLEANUP_PENDING. Revocation failure leaves
known material pending; a recreated manager can subsequently resolve it. The
previous failed-refresh/disconnect reproduction now makes two remote revocation
calls for the known original token bundle and ends disconnected with no pending
record after successful cleanup.

No new stale promotion or loss of known persisted credentials was reproduced.
The existing documented limits around a total database outage or a remote token
never received by TWF remain limits of the bounded implementation, rather than
being represented as distributed atomicity with an OAuth server.

## D. S23A-03 — closed with the documented conservative policy

The owner/provider group protects active and pending authoritative connections.
This prevents old-generation cleanup from revoking token values retained by a
new generation without pretending that different token strings imply different
provider grants. Pending references remain discoverable and unusable locally.

The revocation-enforcing fixture confirms that cleanup of an old generation does
not break the newer generation. Additional independent probes created two
connections for one owner/provider: disconnect and cleanup of the first remained
pending while the second was active; disconnecting the last authority then allowed
both cleanup obligations to resolve. Owner predicates remain explicit; no raw
token matching or cross-owner sharing policy is introduced.

Five event-driven rounds on **each database** additionally proved:

- the first cleanup attempt holds its claim while remote revocation is paused;
- a second cleanup attempt does not issue a duplicate concurrent revoke;
- authentication on the same connection and a new connection to the same provider
  is rejected with STALE_GENERATION during that claim;
- releasing the barrier resolves cleanup, and another cleanup does no further work.

Temporary script: `/tmp/s23a-rereview/cleanup_probes.py`. Both database runs passed.

The tradeoff remains delayed cleanup while any authoritative connection in that
owner/provider group exists. Explicit cleanup after the last authority disappears
works. Remote revocation is retryable/idempotent; the implementation does not claim
network-wide exactly-once delivery across process failures or separate batches.
This does not reopen provider-specific grant semantics as a prerequisite.

## E–F. Migration 0008 and database concurrency

`0008_mcp_cleanup_claim` correctly follows `0007_mcp_connections`. It adds a nullable
`cleanup_until` timestamp to existing connection rows. No credential data is
rewritten or deleted during upgrade. Existing owner/provider connection identity
and owner locking govern the claim; this migration adds no new ownership key.
No additional uniqueness constraint is required for the single claim field.
Downgrade removes that field and is structurally valid on both tested databases.

Independent checks:

- SQLite: create populated 0007 schema with a connection generation and opaque
  ciphertext marker, upgrade/repeat/check, downgrade to 0007, re-upgrade/check.
  Existing generation/ciphertext are preserved and the new claim defaults to NULL.
- PostgreSQL 16: prior migration to head, repeated upgrade, downgrade/re-upgrade,
  metadata check; a later populated round trip preserves all remaining secret
  records (two at that checkpoint) and initializes claims to NULL.
- The repository remediation suite independently passed **30 cases**, including
  the SQLite cases plus 12 PostgreSQL lifecycle cases.
- The independent five-round competing-cleanup/new-auth probe passed on both
  databases. The dispatch completion-gap probe nevertheless failed on both.

All database work used disposable local databases. No upgrade of the user's normal
application database was performed. The PostgreSQL container was removed afterward.

Migration and cleanup/auth claim serialization pass. Overall persistence/concurrency
acceptance fails because the authority decision and outbound dispatch are still
not serialized; it is not a failure of migration 0008 or replacement-token promotion.

## G. S23A-04 — partial improvement, but not closed

The previous slow remote DELETE response case and immediate close-error case now
pass. SDK automatic termination is disabled, and normal explicit termination runs
inside the operation budget. The new suite correctly exercises cancellable response
stream teardown. It does not exercise the installed HTTP pool's shielded close.

The installed `httpcore2` implementation uses `AsyncShieldCancellation` in
`AsyncConnectionPool._close_connections`, including calls from `aclose`. TWF awaits
that pool close via its HTTPX context while returning from inside `anyio.fail_after`.
Cancellation therefore does not bound all teardown. Moreover, elapsed-time checking
in `SDKClient.execute` is only in the exception path; successful shielded unwind can
return a successful result after its deadline.

### Independent teardown reproduction

The synthetic HTTP transport returns normal MCP fixture responses. Its local close
uses the **actual installed `httpcore2.AsyncConnectionPool.aclose`**, populated with
one synthetic connection whose close releases after a 320 ms event-loop timer. This
exercises real library cancellation shielding, not a replacement timeout algorithm.
No network socket/provider is involved. The test separately covers completed work,
an operation that waits until timeout, and a delayed local close exception.

Configured deadline: **80 ms**. Repeated manager-path measurements:

| Scenario                                         | Caller elapsed | Caller result | Stored health |
| ------------------------------------------------ | -------------- | ------------- | ------------- |
| MCP work succeeds, pool close delayed            | **357–368 ms** | **SUCCESS**   | AVAILABLE     |
| MCP operation times out, pool close delayed      | **409–410 ms** | TIMEOUT       | UNAVAILABLE   |
| MCP work succeeds, delayed pool close raises     | **356–367 ms** | TIMEOUT       | UNAVAILABLE   |
| MCP operation times out and delayed close raises | **410 ms**     | TIMEOUT       | UNAVAILABLE   |

Scripts/results: `/tmp/s23a-rereview/slow_pool_close.py`, `deep_probes.py` and
`deep-results-repeat.jsonl`. Teardown completed by caller return in these probes;
no unowned background task or post-return credential dispatch was observed.
The problem is that the caller must wait for shielded teardown, and normal work
can be reported successful after the deadline.

**S23A-04 remains HIGH / MUST FIX BEFORE S2-3.** Bound or explicitly own/control
shielded local HTTP-pool cleanup without extending the caller deadline. Check
elapsed time on successful unwind as well as exceptions. Preserve TIMEOUT over
secondary close errors. Add a regression using the actual pool shielding behavior;
a cancellable synthetic response body alone is insufficient proof.

Error precedence for an actual operation timeout plus close failure passes. The
broader caller-deadline and controlled-slow-teardown acceptance gates fail.

## H. Original security properties and test quality

The full **793-test** suite passed independently, including existing OAuth state /
PKCE, callback ownership/session binding, encrypted reference checks, redaction,
allowlist/discovery separation, restart and prior Broker/S2-1/S2-2 regressions.
An additional wrong-verifier probe rejected the callback without token attachment;
DEBUG-enabled MCP/HTTP logging and TWF structured records contained none of the
synthetic token/verifier/state/code sentinels.

The 18 new cases use real synchronization and meaningful assertions, including
actual authenticated dispatch counts. Their gaps are specific: DNS barriers occur
before the last authority read, and the close fixtures do not reproduce real
HTTPcore shielded local cleanup. Thus the suite is useful but is not yet sufficient
to close the two remaining blockers. Passing counts do not override the independent
counterexamples.

S23A-05 remains LOW / SAFE TO DEFER: remote session closure error fidelity is not
made unsafe by these changes. No fix is required for that item in this re-review.

## I. Dependency audit revalidation

The independent runtime-lock audit again reports **seven records / four distinct
advisories** for unchanged `cryptography==47.0.0`. The audit is **not clean**. Both
lock files are unchanged from the reviewed remediation snapshot. Added remediation
code does not introduce cryptography X.509 verification, RSA/PKCS#7 decryption, or
ASN.1 decoding paths. Its transient SHA-256 fingerprints use standard-library
hashlib. Credential storage still uses the existing Fernet cipher.

Primary advisories were reopened and compared against actual usage:

| Advisory                                                                                                             | Vulnerable function / fixed release                               | Current path assessment                                                    |
| -------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- | -------------------------------------------------------------------------- |
| [GHSA-m2h6-j472-rp4c / CVE-2026-69248](https://github.com/pyca/cryptography/security/advisories/GHSA-m2h6-j472-rp4c) | Cryptography X.509 DNS name-constraint verification; fixed 49.0.0 | Verifier unused by this MCP path; NOT_APPLICABLE to this path.             |
| [GHSA-jwv3-5hgf-82ww / CVE-2026-69249](https://github.com/pyca/cryptography/security/advisories/GHSA-jwv3-5hgf-82ww) | Cryptography X.509 path-building denial of service; fixed 49.0.0  | Verifier unused; NOT_APPLICABLE to this path.                              |
| [GHSA-g6cj-pr64-35w5 / CVE-2026-69247](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5) | RSA PKCS#7 envelope-decryption oracle; fixed 50.0.0               | No PKCS#7 decryption; Fernet is not this API; NOT_APPLICABLE to this path. |
| [GHSA-537c-gmf6-5ccf / CVE-2026-34180](https://github.com/pyca/cryptography/security/advisories/GHSA-537c-gmf6-5ccf) | Vulnerable ASN.1 decoder in bundled OpenSSL; fixed wheel 48.0.1   | No qualifying ASN.1 input path; NOT_APPLICABLE to this MCP path.           |

Runtime linkage independently remains cryptography/OpenSSL 4.0.0 and Python
`ssl`/OpenSSL 3.0.13. These are separate libraries; a wheel upgrade is not a system
TLS upgrade. The historical review details the advisory prerequisites, affected
versions and bounded upgrade recommendation. This assessment is based on current
code reachability, not merely on the prior decision or dependency age.

**CRYPTOGRAPHY_ADVISORIES_STATUS = NONBLOCKING_WITH_EVIDENCE**. Retain the bounded
baseline upgrade follow-up and reassess if crypto usage changes. No dependency
modification was made by the reviewer.

## J. Required scorecard

```ini
S23A_01_DISPATCH_BOUNDARY_FENCING = FAIL
S23A_01_PRE_DISPATCH_RACE_BLOCKED = FAIL
S23A_01_STALE_SESSION_RETIRED = FAIL
S23A_01_NO_AUTH_DISPATCH_AFTER_STALE = FAIL

S23A_02_REFRESH_CLEANUP_OBLIGATION_PRESERVED = PASS
S23A_02_DISCONNECT_DURING_REFRESH_SAFE = PASS
S23A_02_NO_STALE_TOKEN_PROMOTION = PASS

S23A_03_ACTIVE_CREDENTIAL_REFERENCE_PROTECTED = PASS
S23A_03_SHARED_CREDENTIAL_NOT_REVOKED = PASS
S23A_03_DEFERRED_CLEANUP_RETRIES = PASS
S23A_03_PROVIDER_CLEANUP_CLAIM = PASS

MCP_CLEANUP_CLAIM_MIGRATION = PASS
MCP_MIGRATION_UPGRADE_SQLITE = PASS
MCP_MIGRATION_UPGRADE_POSTGRES = PASS
MCP_CLEANUP_AUTH_SERIALIZATION = PASS

S23A_04_CALLER_TIMEOUT_BOUNDED = FAIL
S23A_04_TIMEOUT_ERROR_PRESERVED = PASS
S23A_04_SLOW_TEARDOWN_CONTROLLED = FAIL
TIMEOUT_SESSION_AUTHORITY_RETIRED = PASS

MCP_PERSISTENCE_CONCURRENCY = FAIL

OWNER_SCOPED_CONNECTION_IDENTITY = PASS
OAUTH_STATE_PKCE = PASS
CALLBACK_OWNER_BINDING = PASS
SECURE_TOKEN_STORAGE = PASS
MCP_SECRET_REDACTION = PASS
TOOL_ALLOWLIST = PASS
DISCOVERY_AUTHORITY_SEPARATION = PASS
MCP_RESTART_RECOVERY = PASS

S23A_05_STILL_NONBLOCKING = PASS
CRYPTOGRAPHY_ADVISORIES_STATUS = NONBLOCKING_WITH_EVIDENCE

S2_3A_REMEDIATION_TEST_QUALITY = FAIL
REGRESSION_FREE = PASS
S2_3A_DOCUMENTATION_ACCURATE = FAIL
```

Retired transports reject subsequent use once their local fence detects retirement;
the retirement FAIL reflects the uncovered supersession-to-detection gap. Restart
PASS concerns durable local authority/cleanup recovery. Regression PASS refers to
existing automated behavior, not acceptance of the two remaining new defects.

## K. Findings

| ID         | Severity | Timing               | Area/File                                                                                      | Finding                                                                                                                                                                                              | Required Action                                                                                                                                                                                    |
| ---------- | -------- | -------------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S23A-01-R1 | HIGH     | MUST FIX BEFORE S2-3 | `integrations/mcp/http.py:85`, `connection.py:123`, `connection.py:763`                        | Final authority transaction commits/releases locks before async dispatch resumes. A completed disconnect can be followed by an authenticated POST from that old generation on SQLite and PostgreSQL. | Serialize the final dispatch handoff with revocation/supersession; add the worker-completion-gap regression with authenticated dispatch count zero. Preserve already-dispatched request semantics. |
| S23A-04-R1 | HIGH     | MUST FIX BEFORE S2-3 | `integrations/mcp/client.py:94`, `client.py:167`, `http.py:128`; installed HTTPcore pool close | Actual pool cleanup shields cancellation. An 80 ms manager call takes 357–410 ms; successful work can return SUCCESS after the deadline.                                                             | Control/bound shielded local close, enforce the deadline on successful unwind, preserve timeout precedence, and test the real pool-close shield.                                                   |
| S23A-05    | LOW      | SAFE TO DEFER        | `integrations/mcp/http.py`                                                                     | Remote session-close error fidelity remains deferred.                                                                                                                                                | Retain a follow-up; does not independently block this review.                                                                                                                                      |
| S23A-06    | NOTE     | SAFE TO DEFER        | Dependency locks / cryptography baseline                                                       | Audit remains nonclean, with no reachable vulnerable crypto functionality found in the MCP path.                                                                                                     | Preserve evidence and the bounded dependency-maintenance follow-up.                                                                                                                                |

S23A-02 and S23A-03 are closed by this focused review. No unrelated future-scope or
cosmetic finding is used to hold acceptance. The implementation document's absolute
stale-dispatch and total-deadline claims need correction with the eventual fixes.
Its milestone status, migration requirement and deferred advisory disclosure are
otherwise appropriately explicit.

## L. Validation results

| Validation                          | Independent result                                                                                                                |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Full backend pytest                 | **793 passed in 134.24 seconds**, no warnings.                                                                                    |
| SQLite/PostgreSQL remediation suite | **30 passed in 7.51 seconds**.                                                                                                    |
| Additional concurrency              | Five cleanup/two-worker/new-auth rounds per database passed; worker-completion dispatch gap failed twice on both databases.       |
| Migration checks                    | SQLite populated 0007 → 0008 and PostgreSQL 16 upgrade/repeat/downgrade/re-upgrade/check passed; ciphertext/generation preserved. |
| Ruff lint / formatting              | PASS; 108 files formatted.                                                                                                        |
| Strict mypy                         | PASS; 107 checked files.                                                                                                          |
| Compilation/import / OpenAPI        | PASS; 39 paths, 63 component schemas.                                                                                             |
| Dependency consistency              | `pip check` PASS.                                                                                                                 |
| Security audit                      | Seven records / four advisories; NONBLOCKING_WITH_EVIDENCE, not clean.                                                            |
| Offline package build               | PASS, sdist and wheel, repository-compatible temporary build tooling.                                                             |
| Documentation / links / whitespace  | PASS after record creation: formatting, 160 local targets, blocked status terminology and `git diff --check`.                     |
| Frontend / external services        | Frontend untouched; no real MCP provider or broker calls.                                                                         |

Temporary scripts, synthetic output, audit JSON and build artifacts are under
`/tmp/s23a-rereview*`. The final SHA-256 comparison confirms every pre-existing repository file,
including the historical HOLD report, is unchanged; only this record was added. Runtime proof is offline except for the isolated PostgreSQL container;
public dependency-advisory lookup is not a provider integration call.

## M–R. Reviewer changes and decision

Created exactly:

`docs/TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION_REREVIEW.md`

Existing files modified by reviewer: **NONE**.
Runtime source changed by reviewer: **NO**.
Historical HOLD review changed: **NO**.
No commit, tag, push, merge, rebase, cherry-pick, reset or status promotion occurred.

**HOLD_S2_3A**.

Can a real authenticated MCP provider now use this foundation without stale
credential dispatch or caller-deadline violations? **Not yet.** Cleanup preservation
and active-credential protection now pass, but S23A-01 and S23A-04 remain open through
the independently reproduced cases above. This calls for focused correction and
another re-review, not a provider-specific authentication redesign.

S2-3 remains **BLOCKED / PENDING S2-3A ACCEPTANCE**. No TradingView integration or
other provider/business work is authorized by this report. No Tapetide, Market /
event Intelligence, LLM, TI, TM, LOB, broker execution from S&D, autonomous trading
or production ML authorization is implied.

Recommended Git action: do not freeze/tag S2-3A as accepted now. After the two
remaining blockers are fixed and independently pass review, the user may authorize
committing implementation/remediation plus review documentation and optionally an
S2-3A freeze tag. No Git action is performed here.
