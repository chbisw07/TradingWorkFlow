# OE-3 privilege and cursor remediation report

**Later grant hardening:** The final focused review found excess runtime DELETE and Order-event UPDATE privileges after the ownership cutover. The bounded correction and current validation are tracked in [TWF_OE3_FINAL_GRANT_REMEDIATION_REPORT.md](TWF_OE3_FINAL_GRANT_REMEDIATION_REPORT.md). Historical pre-cutover and cutover results below remain unchanged.

**Live cutover addendum (16 October 2026):** The previously blocked PostgreSQL ownership/grant cutover was explicitly approved and completed. The stopped-writer dump, restore and rollback rehearsals, pre/post ownership/grants, direct attacks, runtime DML, API restart, unchanged data, and current PASS scorecard are recorded in [TWF_OE3_LIVE_PRIVILEGE_CUTOVER_REPORT.md](TWF_OE3_LIVE_PRIVILEGE_CUTOVER_REPORT.md). The FAIL scorecard below records the earlier pre-cutover state and is retained as review history. Current status: `READY_FOR_FOCUSED_REREVIEW`; OE-3 is not frozen.

**The sections below are the historical pre-cutover implementation snapshot.**

**Date:** 16 October 2026. **Decision:** implementation validated in disposable PostgreSQL and SQLite, but **NOT READY for focused re-review** while the live PostgreSQL database remains owned by `twf_app`. The automatic approval review rejected the disruptive live ownership cutover. No Queue worker, broker handoff, or OE-4 behavior was added.

## A. Executive verdict

The implementation closes the PostgreSQL ownership bypass when deployed with distinct migrator and runtime roles, and it converts correctly signed malformed Queue cursors to typed `INVALID_CURSOR` HTTP 400. The SQLite claim is explicitly limited to TWF-managed connections inside a trusted process/file boundary. The live PostgreSQL database has **not** been hardened: it still has `twf_app` as database and protected-table owner. This is a deployment blocker, not a failing isolated implementation test.

## B. Preflight

The prior independent review at [TWF_OE3_INDEPENDENT_ADVERSARIAL_REVIEW.md](TWF_OE3_INDEPENDENT_ADVERSARIAL_REVIEW.md) was preserved. Migration 0026 is the live head. Before any live change, read-only inventory found `twf_app` owns the database, all 46 application relations and the Queue trigger function; `public` is owned by `pg_database_owner`, effectively the database owner. The live API uses `twf_app`, with no migrator URL in its environment. The local API and PostgreSQL remained available during implementation.

A 12,061,858-byte preflight custom-format dump was stored at `var/backups/oe3-role-cutover/preflight.dump` with mode 0600 and SHA-256 `acf43e6d772791d80c6a3820bd6caa96796e22b47ad47c21efbbe429788394f7`. `pg_restore --list` succeeded. A full restore into a separate disposable PostgreSQL cluster succeeded at head `0026_oe3_queue_hardening`, with 46 public tables and the Queue audit table readable. This is a snapshot taken while the API was running, **not** the final stopped-writer cutover backup.

## C. Review-finding reproduction

The independent review demonstrated that the then-current app-owned PostgreSQL tables allowed a non-superuser owner to drop the reciprocal Order/Queue FKs and disable the Queue audit trigger, commit incoherence/tampering, then re-enable the trigger. Its SQLite raw-writable-connection probe likewise demonstrated a trigger can be dropped and recreated by a process with direct file/schema control. It also reproduced a correctly signed cursor containing numeric `id: 0` returning HTTP 500 on both backends. Those reproductions were retained rather than altered.

## D. PostgreSQL prior privilege flaw

The live runtime login is not a superuser, but owning the database, protected tables, and trigger function is sufficient to dismantle F1/F2 enforcement. Stronger triggers alone do not fix that authority boundary. Read-only inspection after the rejected cutover confirmed ownership remains unchanged and `twf_app` can still log in.

## E. New role/ownership model

`tools/postgres_roles.py` establishes a bootstrap administrator, `twf_migrator` database/schema/object owner, and limited `twf_app` runtime login. Runtime receives CONNECT, schema USAGE, required table DML and sequence access; Queue audit receives SELECT/INSERT only, and `alembic_version` SELECT only. Runtime has no database/schema CREATE or TEMP privilege, owns no application object, and must not be a member of the migrator, bootstrap, or any elevated role. The Queue audit function remains invoker-security; PUBLIC/runtime direct EXECUTE is revoked. It has no unqualified object lookup. Runtime connections cannot alter/drop the F1 constraints or F2 trigger/function, while normal Queue DML still works.

The `twf_migrator` role was provisioned on the live cluster, with its generated credential in an ignored, mode-0600 local operator file `.env.oe3-migrator`. No live database/schema/table/function ownership or runtime grant was changed. In production, operator credentials need separate secret custody; the local same-user development host is not a process-isolation guarantee.

## F. Role migration/bootstrap implementation

The operator CLI supports inventory, provision, empty-schema preparation, harden and verify. Hardening requires exact Alembic head 0026, transfers all application relation/function and database/schema ownership, revokes broad runtime/PUBLIC rights, applies narrow grants, then verifies in one PostgreSQL transaction. It copies no business row. `tools/migrate-postgres.sh` requires a distinct migration URL and migrator login; Compose exposes an opt-in `ops` migration service while the API receives only its runtime URL. Fresh bootstrap and legacy app-owned schema cutover were both tested in disposable real-role databases. No schema migration 0027 was required; 0025 and 0026 were not edited.

## G. PostgreSQL DDL-bypass attacks

After disposable cutover, direct runtime attempts to drop each F1 FK, disable/drop the F2 trigger, drop its function/table/index, change table/schema/function ownership, create a table/role/database, `SET ROLE` migrator/bootstrap, grant itself migrator, or reassign ownership were denied (permission SQLSTATE 42501). The operator verifier also rejects inherited membership in any elevated role. These attacks **remain possible against the unchanged live app-owned schema** until the approved cutover is performed.

## H. PostgreSQL normal DML regression

A real `twf_app` login on both fresh and converted disposable PostgreSQL databases completed login, broker account fixture binding, OE-2 Preview/Create to READY, Queue admission and idempotent replay, Hold, Release, list, and three audit events. A restored database retained audit rows and continued to deny runtime DDL. No live broker order was placed.

## I. F1/F2 revalidation

Under the separated runtime role, direct split-state Order/Entry insert/update transactions failed at COMMIT, while valid admission worked. Direct Queue event UPDATE/DELETE were rejected; the protected trigger cannot be disabled by runtime DDL. Existing 0026 hardening tests and all backend suites passed. These guarantees are demonstrated for the separated disposable role model, not yet for the live app-owned database.

## J. SQLite trust-boundary decision

SQLite fallback protects normal TWF-managed connections with foreign keys and installed triggers. It has no PostgreSQL-equivalent role/ownership defense against arbitrary writable file access or an independent raw connection with schema control. The database file and parent directory must be restricted to a trusted service account; same-user file permissions do not stop a hostile same-user process. SQLite is an explicit fallback/recovery/developer mode, not an adversarially equivalent execution authority.

## K. SQLite managed-connection validation

The complete SQLite suite passed (1,473 passed, 75 backend-specific skips), including managed F1 commit rejection, F2 event mutation rejection, F3 pagination, and typed invalid-cursor handling. The independent review's raw writable bypass is retained as a documented out-of-boundary counterexample, not misreported as impossible.

## L. Cursor root cause

The old decoder verified HMAC and scope but passed an arbitrary JSON `id` to `UUID(...)`. `UUID(0)` raised `AttributeError` outside the translated exception set; an authenticated user could sign this malformed payload with their session-derived key and obtain HTTP 500.

## M. Cursor validation implementation

The decoder now requires an exact JSON object/key set, integer version 1, matching owner/filter, string timestamp and UUID fields, an aware parseable timestamp normalized to UTC, and a parseable UUID before querying. It bounds token length and maps malformed signature/base64/JSON/semantic conversion errors to `INVALID_CURSOR` HTTP 400. Valid keyset ordering, owner isolation, and live-list behavior are unchanged. The Queue UI refreshes the newest page on typed invalid cursor, shows a short notice, and does not render raw backend detail.

## N. Cursor adversarial results

The exact numeric-ID reproduction, invalid signature, bad but validly signed timestamp/UUID, wrong version, missing fields, wrong types, wrong filter, cross-owner token, oversized token, and 180 generated malformed payloads all returned typed 400, never 500. The PostgreSQL final focused gate passed 10 tests including the new real-role and cursor suites; the SQLite focused gate passed 7 with one PostgreSQL-only skip.

## O. Pagination regression

Existing 125- and 500-entry traversal tests passed on both backends, including tied timestamps, insert-between-pages, filtered state changes, owner isolation and terminal cursor behavior. Observed duplicates: 0; omissions: 0. The operator view remains newest-first; execution FIFO semantics remain unchanged. The browser test covers older-page loading, return to newest, filtering, and invalid-cursor recovery.

## P. Backup/restore role validation

Disposable role tests used `pg_dump -Fc --no-owner --no-acl`, `pg_restore --no-owner --no-acl` into a fresh database, then `harden`/`verify`; restored Queue history was readable and runtime DDL denial remained. The live preflight dump also restored independently. A **final** backup after stopping live writers and a live role-cutover verification are pending approval.

## Q. DB-1/OE-1/OE-2 regression

Full PostgreSQL rerun: **1,547 passed, 1 SQLite-specific skip, 4 warnings** in 697.19 seconds. The first full attempt had 1,546 passed/1 skipped/1 failure: unchanged `test_disconnect_refresh_matrix[sqlite-OLD_CLEANUP_PENDING]` timed out under full-suite MCP load, then passed in isolation (2.20 seconds); no MCP code or timeout was changed. Full SQLite: **1,473 passed, 75 backend-specific skips, 4 warnings** in 498.42 seconds. Frozen OE-1/OE-2 and DB-1 focused/concurrency paths remain green within those gates. No automatic SQLite failover or dual-write was introduced.

## R. Frontend/browser gates

Frontend unit suite: 33 files, 296 tests passed. TypeScript, ESLint, Prettier, and production build passed after fixing a callback type and formatting the changed files. PostgreSQL-backed Chromium Queue flows at 390 and 1440 pixels: 4 passed. PostgreSQL-backed Trade/Positions, OE-2, and retained Broker fixture flows at those widths: 6 passed. The first two browser attempts failed only because a new test scoped its alert selector inside the table section, then matched Next.js's separate route announcer; the corrected selector passed. No live broker order was sent.

## S. Static gates

Ruff, Ruff format check (237 files), compileall, pip check, changed-file mypy (4 files), and `git diff --check` passed. Repository mypy over `src tests` reports 15 pre-existing errors in three unchanged tests (`test_derivative_templates.py`, `test_option_chain.py`, `test_derivative_relative_volume.py`); changed files have no mypy errors. Running mypy over `.` additionally encounters duplicate generated `build/lib/twf` modules, so the source/test invocation is the meaningful repository-wide comparison.

## T. Exact files changed

Runtime: `apps/api/src/twf/queue/service.py`, `apps/web/src/components/orders/queue-workspace.tsx`, `compose.yaml`, `tools/postgres_roles.py`, `tools/migrate-postgres.sh`. Tests: `apps/api/tests/test_postgres_privilege_boundary.py`, `apps/api/tests/test_twf_queue_cursor_security.py`, `apps/web/tests/queue-pagination.test.tsx`, `apps/web/tests/browser/twf-queue.spec.ts`. Documentation: `README.md`, `apps/api/.env.example`, `docs/TWF_DATABASE_ARCHITECTURE.md`, `docs/TWF_QUEUE_OE3_ARCHITECTURE.md`, `docs/TWF_SQLITE_TO_POSTGRES_MIGRATION_RUNBOOK.md`, and this report. The pre-existing untracked independent review was preserved.

## U. Known limitations

The live PostgreSQL role cutover remains undone. The automatic approval review rejected the requested action because it would pause/terminate live application sessions and persistently change database ownership/grants without explicit approval of that concrete disruption. `twf_migrator` is provisioned, but `twf_app` is still live database/protected-object owner. The preflight dump is not the required final stopped-writer backup. Local native development processes share a filesystem user; production must keep admin/migration secrets out of the API runtime. SQLite arbitrary writable access is outside its security guarantee. The unrelated repository mypy debt and first full-suite MCP timing observation remain carry-forward items.

## V. Required scorecard

```text
OE3_REMEDIATION_STATUS = FAIL

PG_MIGRATOR_ROLE_SEPARATE = PASS
PG_RUNTIME_ROLE_SEPARATE = PASS
PG_RUNTIME_NOT_SCHEMA_OWNER = FAIL
PG_RUNTIME_NOT_TABLE_OWNER = FAIL
PG_RUNTIME_NOT_FUNCTION_OWNER = FAIL

PG_RUNTIME_ALTER_TABLE_BLOCKED = FAIL
PG_RUNTIME_DROP_CONSTRAINT_BLOCKED = FAIL
PG_RUNTIME_DISABLE_TRIGGER_BLOCKED = FAIL
PG_RUNTIME_DROP_TRIGGER_BLOCKED = FAIL
PG_RUNTIME_ALTER_FUNCTION_BLOCKED = FAIL
PG_RUNTIME_ROLE_ESCALATION_BLOCKED = PASS
PG_RUNTIME_CREATE_ROLE_BLOCKED = PASS
PG_RUNTIME_CREATE_DB_BLOCKED = PASS
PG_SEARCH_PATH_SAFE = FAIL

PG_NORMAL_RUNTIME_DML = PASS
PG_F1_INVARIANT_ENFORCED = FAIL
PG_F2_IMMUTABILITY_ENFORCED = FAIL

PG_FRESH_BOOTSTRAP = PASS
PG_EXISTING_DB_ROLE_MIGRATION = PASS
PG_DUMP_RESTORE_ROLE_MODEL = PASS

SQLITE_POLICY_DOCUMENTED = PASS
SQLITE_TRUST_BOUNDARY_EXPLICIT = PASS
SQLITE_MANAGED_F1 = PASS
SQLITE_MANAGED_F2 = PASS
SQLITE_MANAGED_F3 = PASS
SQLITE_NO_FALSE_SECURITY_CLAIM = PASS

CURSOR_REVIEW_REPRODUCED = PASS
CURSOR_SEMANTIC_VALIDATION = PASS
CURSOR_INVALID_SIGNATURE_4XX = PASS
CURSOR_VALID_SIGNATURE_INVALID_CONTENT_4XX = PASS
CURSOR_UNKNOWN_VERSION_4XX = PASS
CURSOR_FILTER_BINDING = PASS
CURSOR_OWNER_ISOLATION = PASS
CURSOR_FUZZ_NO_500 = PASS

F3_125_TRAVERSAL = PASS
F3_500_TRAVERSAL = PASS
F3_DUPLICATES = 0
F3_OMISSIONS = 0

MIGRATION_0025_UNCHANGED = PASS
MIGRATION_0026_UNCHANGED_OR_JUSTIFIED = PASS
MIGRATION_0027_CREATED_IF_REQUIRED = NOT_REQUIRED

DB1_FROZEN_INTACT = PASS
OE1_FROZEN_INTACT = PASS
OE2_FROZEN_INTACT = PASS
OE4_NOT_IMPLEMENTED = PASS

FULL_BACKEND_POSTGRES = PASS
FULL_BACKEND_SQLITE = PASS
FRONTEND = PASS
BROWSER_POSTGRES = PASS

CHANGED_FILE_MYPY = PASS
REPO_MYPY = PRE_EXISTING_UNRELATED
RUFF = PASS
FORMAT = PASS
COMPILE = PASS
PIP_CHECK = PASS
TYPESCRIPT = PASS
ESLINT = PASS
PRETTIER = PASS
GIT_DIFF_CHECK = PASS

OE3_READY_FOR_FOCUSED_REREVIEW = NO
```

The PostgreSQL boundary fields are scored against **the actual live database**, not the passing disposable model; this is why the aggregate status is FAIL.

## W. Final status

**NOT_READY.** A concrete live cutover is prepared but blocked pending explicit approval: pause `twf_app` logins and terminate existing app sessions; create and verify a stopped-writer custom-format dump; run the already tested atomic `harden`/`verify`; restore runtime login; verify critical row counts, `/ready`, normal runtime DML, and denial of runtime DDL. If any step fails, retain the dump and keep the old ownership transaction intact or follow the documented restore procedure. After that operation, rerun live role inventory and update this scorecard before independent focused re-review. No commit, tag, push, or OE-4 start was performed.
