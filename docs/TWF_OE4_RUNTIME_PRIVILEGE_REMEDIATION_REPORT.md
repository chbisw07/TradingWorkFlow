# OE-4 Runtime Privilege Remediation Report

## A. Executive verdict

**OE4_RUNTIME_PRIVILEGE_REMEDIATION_STATUS = PASS.** The canonical PostgreSQL role policy, live database, fresh database, existing-upgrade database, and restored database now reproduce the same explicit least-privilege model. OE-4 is **READY_FOR_INDEPENDENT_REVIEW**. No commit, tag, push, Queue admission, worker dispatch, or broker submission was performed.

## B. Preflight

Branch `main`; `HEAD == origin/main == f8b61d269be1a6416f9b83cf1a1aa7870e7969db`. The worktree already contained the uncommitted OE-4 implementation. Live PostgreSQL was authoritative, runtime role was `twf_app`, object owner/migrator was `twf_migrator`, and Alembic current/head both resolved to `0028_oe4_dispatch`.

## C. Reproduction

Before remediation, normal Queue policy load returned 500 (`1ba24545178a41a78882920b381b5b94`). Order Preview returned 200 (`b806e91a287045cfbd6c1bcc2e8a7e0`), while Create returned 500 (`d765ca290abf4d1991662db2d6df67fd`).

## D. Exact PostgreSQL errors

`psycopg.errors.InsufficientPrivilege`, SQLSTATE `42501`:

- `permission denied for table twf_queue_dispatch_policies`
- `permission denied for table twf_public_id_counters`

Raw database details remained in server logs and were not returned to the browser.

## E. OE-4 object inventory

Migration 0028 adds five runtime tables, no sequences, four protected trigger functions, their triggers/indexes/constraints, and Queue/Order columns. All tables/functions are owned by `twf_migrator`; `twf_app` owns zero OE-4 objects.

| Object                        | Type     | Owner          | Grants before                   | Required                  | Grants after                          | Runtime path                     | Result |
| ----------------------------- | -------- | -------------- | ------------------------------- | ------------------------- | ------------------------------------- | -------------------------------- | ------ |
| `twf_public_id_counters`      | table    | `twf_migrator` | none                            | SELECT, INSERT, UPDATE    | SELECT, INSERT, UPDATE                | transactional ORD/QID allocation | PASS   |
| `twf_order_public_ids`        | table    | `twf_migrator` | none                            | SELECT, INSERT            | SELECT, INSERT                        | immutable Order alias            | PASS   |
| `twf_queue_dispatch_policies` | table    | `twf_migrator` | none                            | SELECT, INSERT, UPDATE    | SELECT, INSERT, UPDATE                | default read, CAS mode change    | PASS   |
| `twf_queue_policy_events`     | table    | `twf_migrator` | none                            | SELECT, INSERT            | SELECT, INSERT                        | append-only policy audit         | PASS   |
| `twf_dispatch_attempts`       | table    | `twf_migrator` | none                            | SELECT, INSERT, UPDATE    | SELECT, INSERT, UPDATE                | future dispatch lifecycle        | PASS   |
| OE-4 sequences                | sequence | n/a            | n/a                             | none                      | none                                  | allocator is table-backed        | PASS   |
| protected trigger functions   | function | `twf_migrator` | PUBLIC execute before hardening | no direct runtime execute | direct runtime/PUBLIC execute revoked | trigger-only integrity boundary  | PASS   |

## F. Existing role/grant model

The accepted OE-3 split remains: administrator provisions roles, `twf_migrator` owns/migrates, and `twf_app` has only registered runtime DML. DELETE is default-deny with the exact accepted 11-table cleanup allowlist. Audit tables remain SELECT/INSERT only. Runtime has no database/schema CREATE, TEMP, DDL, ownership, role-management, or direct protected-function authority.

## G. Root cause

**ROOT_CAUSE = `tools/postgres_roles.py` had a closed runtime table registry that stopped at the OE-3 schema. Migration 0028 added OE-4 tables without adding their exact DML declarations; therefore `twf_app` lacked SELECT/INSERT/UPDATE on `twf_queue_dispatch_policies` and SELECT/INSERT/UPDATE on `twf_public_id_counters`, breaking policy first-use and post-Preview public-ID allocation. The other OE-4 tables were likewise undeclared and would fail on their runtime paths.**

## H. Canonical grant-policy fix

`tools/postgres_roles.py` now explicitly registers all 51 runtime tables, defines per-table SELECT/INSERT/UPDATE/DELETE sets, declares zero runtime sequences, registers all protected functions, and refuses unknown future objects. Static and live-role tests fail if schema objects and the registry diverge. There is no `GRANT ALL`, ownership transfer, broad default grant, or DELETE expansion.

## I. Live backup

Writers were stopped and runtime login disabled. Backup: `var/backups/oe4-runtime-privileges/20261016T151208Z/twf-live-before.dump`; 12,163,348 bytes; SHA-256 `cebf265abde1ea3d9a2af110379cbe8396eb6d278a7885cd7143d528564dcd90`; mode 0400. Its isolated restore matched all 51 table fingerprints and accepted the canonical hardening/verification procedure.

## J. Live grant application

The canonical `harden` operation applied the source policy transactionally; `verify` passes the exact table/sequence/function registries, grants, 11-table DELETE allowlist, append-only restrictions, ownership, OE-3 constraints/triggers, and DDL denials. The grant application changed no business row.

During browser validation, an earlier fixture process inherited the live migration URL and inserted test users; the fingerprint audit detected this. The API was stopped, the verified backup was restored, all 51 fingerprints matched exactly, the browser harness was fixed to bind both runtime and migration URLs to its disposable database, and canonical hardening was reapplied. The final live database has the original single user plus only the explicitly verified OE-4 test records.

## K. Order creation verification

Final live Preview returned 200 (`055b43a1df874814a5e0ceb366c0226e`) and Create returned 200 (`38a0a60a74674736a9ca420f56bbec46`). Order `c144ee51-fe4b-48af-b2b4-88c19805bb30` was created as READY/MANUAL with public ID `ORD-20261016221849-001`. It was not admitted to Queue.

## L. Queue policy verification

Final policy load returned 200 (`de4ba136dfe34e73b3df6b1a32d47be9`). MANUAL→AUTO (`2a7cb8361f8a4f5f8042d5c455784917`) and AUTO→MANUAL (`3f1ef5d93a294f258d404610f3dfe263`) both returned 200 and appended policy audit events. The final mode is MANUAL.

## M. Execution interlock verification

Every policy response reported `execution_enabled=false`. Existing Queue rows/events were byte-stable, dispatch-attempt count stayed zero, and broker-intent count stayed ten. Broker submission calls were zero. The validation-only API process was stopped immediately afterward.

## N. Security regression

Rollback-only live probes under `twf_app` were denied with SQLSTATE 42501 for Order/Queue/broker-intent DELETE, Order/Queue-event UPDATE/DELETE, ALTER TABLE, trigger/function/table DROP, CREATE TABLE, owner change, and CREATE ROLE. Protected functions cannot be invoked directly. OE-3 boundaries remain intact.

## O. Fresh DB validation

A disposable fresh PostgreSQL database migrated to 0028, received the canonical policy, passed the exact grant verifier, and ran normal Order/policy API operations as `twf_app`.

## P. Existing DB validation

A disposable existing-head database received the corrected policy without row changes; OE-4 paths began working and the prior restrictions remained enforced.

## Q. Restore validation

The stopped-writer dump was restored into an empty disposable database. All table counts/content fingerprints matched, harden/verify passed, `twf_app` remained non-owner, and normal Order/policy paths passed.

## R. Frozen-system regressions

OE-1 lifecycle/trust authority, OE-2 Preview/Create binding, OE-3 coherence/audit/pagination/idempotent replay, and DB-1 PostgreSQL-primary/fail-closed behavior remained unchanged. Test isolation was strengthened so both runtime and migration URLs always target the same disposable backend.

## S. Backend/frontend/browser gates

| Gate                                     | Result                                                 |
| ---------------------------------------- | ------------------------------------------------------ |
| Full PostgreSQL backend                  | 1,578 passed, 1 skipped, 4 warnings; 798.69s           |
| Full SQLite backend                      | 1,504 passed, 75 skipped, 4 warnings; 482.91s          |
| Static/fresh/upgrade/restore role policy | 3 passed; 10.12s                                       |
| Frontend unit                            | 296 passed, 33 files                                   |
| PostgreSQL Chromium                      | 12 passed; 390/1024/1440                               |
| TypeScript / ESLint / Prettier / build   | PASS                                                   |
| Ruff / format / compileall / pip check   | PASS; 245 Python files formatted                       |
| Changed-file mypy                        | PASS; 31 source files                                  |
| Repository mypy                          | PRE_EXISTING_UNRELATED: 15 errors in 3 unchanged tests |
| git diff --check                         | PASS                                                   |

## T. Exact files changed by this remediation

- `tools/postgres_roles.py`
- `apps/api/tests/test_postgres_role_policy_static.py`
- `apps/api/tests/test_postgres_privilege_boundary.py`
- `apps/api/tests/conftest.py`
- `apps/api/tests/test_database_db1.py`
- `apps/api/tests/test_database_foundation.py`
- `apps/api/tests/test_foundation.py`
- `apps/web/tests/browser/auth-test-server.mjs`
- `docs/TWF_OE4_RUNTIME_PRIVILEGE_REMEDIATION_REPORT.md`
- `docs/TWF_OE4_IMPLEMENTATION_REPORT.md`
- `docs/TWF_DATABASE_ARCHITECTURE.md`
- `docs/TWF_SQLITE_TO_POSTGRES_MIGRATION_RUNBOOK.md`
- `docs/TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md`

Private ignored evidence is under `var/oe4-privilege-remediation/` and `var/backups/oe4-runtime-privileges/`.

## U. Documentation

The implementation report now links this remediation, while database architecture, role/bootstrap, restore, and local setup documentation state the explicit registry/reapply/verify requirement for every migration.

## V. Scorecard

```text
OE4_RUNTIME_PRIVILEGE_REMEDIATION_STATUS = PASS

ROOT_CAUSE_IDENTIFIED = PASS
EXACT_FAILING_OBJECTS_IDENTIFIED = PASS
MIGRATION_HEAD_CURRENT = PASS

CANONICAL_ROLE_POLICY_UPDATED = PASS
NO_GRANT_ALL = PASS
NO_OWNERSHIP_TRANSFER = PASS
DELETE_DEFAULT_DENY_PRESERVED = PASS

OE4_TABLE_GRANTS_CORRECT = PASS
OE4_SEQUENCE_GRANTS_CORRECT = PASS
OE4_FUNCTION_GRANTS_CORRECT = PASS

LIVE_BACKUP_CREATED = PASS
LIVE_POLICY_APPLIED = PASS
LIVE_DATA_PRESERVED = PASS

TWF_ORDER_CREATE_LIVE = PASS
QUEUE_POLICY_LOAD_LIVE = PASS
MANUAL_AUTO_UI_ENABLED = PASS
MODE_CHANGE_SAFE_WITH_EXECUTION_OFF = PASS

EXECUTION_CAPABILITY_REMAINS_OFF = PASS
NO_LIVE_BROKER_ORDER = PASS

FRESH_DB_GRANT_MODEL = PASS
EXISTING_DB_GRANT_UPGRADE = PASS
RESTORE_GRANT_MODEL = PASS

OE3_SECURITY_INTACT = PASS
OE2_FROZEN_INTACT = PASS
OE1_FROZEN_INTACT = PASS
DB1_FROZEN_INTACT = PASS

FULL_BACKEND_POSTGRES = PASS
FULL_BACKEND_SQLITE = PASS
OE4_FOCUSED = PASS
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
BUILD = PASS
GIT_DIFF_CHECK = PASS

OE4_READY_FOR_INDEPENDENT_REVIEW = YES
```

## W. Final status

**OE4_RUNTIME_PRIVILEGE_REMEDIATION_STATUS = PASS**  
**OE4_READY_FOR_INDEPENDENT_REVIEW = YES**
