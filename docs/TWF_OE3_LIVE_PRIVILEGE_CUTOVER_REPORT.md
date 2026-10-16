# OE-3 live PostgreSQL privilege cutover

**Cutover:** 16 October 2026, approximately 00:27–00:36 IST. **Decision:** `OE3_LIVE_CUTOVER_STATUS = PASS`; `OE3_READY_FOR_FOCUSED_REREVIEW = YES`. This is remediation, not OE-3 acceptance or freeze.

## A. Executive live-cutover verdict

The approved cutover moved the live PostgreSQL database, schema, relation, sequence, and function ownership from `twf_app` to `twf_migrator`. The API restarted as `twf_app`; PostgreSQL remains primary; all 46 application-table fingerprints matched; SQLite files were unchanged. No broker order or OE-4 behavior was added.

## B. Preflight

Branch `main`, HEAD `fd7c391dd4f711b7a3dfaae31b8a6755c0ee3094`; existing uncommitted remediation was preserved and `git diff --check` passed. Container `twf-db1-postgres-1` ran PostgreSQL 16.13, database `twf`, timezone `Etc/UTC`, Alembic head `0026_oe3_queue_hardening`. API reloader PID `2419809` served `/health` and `/ready`; readiness reported PostgreSQL/ready/checked. Both roles existed, `twf_app` had no elevated role flags, and backup/restore tools and disk space were available.

## C. Writer shutdown

The API reloader and worker were stopped. `twf_app` was set `NOLOGIN`, its one idle session was terminated, and the session count reached zero before backup. No other application writer/test process was active. PostgreSQL stayed running. Runtime login was restored only after atomic hardening and verification; the API remained stopped through direct role probes.

## D. Pre-cutover backup

Stopped-writer custom-format dump: `var/backups/oe3-role-cutover/final-stopped-writers-20261015T185746Z.dump`, 12,061,858 bytes, mode 0400, SHA-256 `de5678ce498864818732eaf3a43497fdc694daeaa17bd9419ee3d193922f7edf`. It was created from authoritative `twf` as bootstrap role `twf` at source HEAD above. Dump, TOC, checksum, owner inventories, fingerprints, and restore/startup evidence remain private under `var/backups/oe3-role-cutover/`; the earlier `preflight.dump` was retained.

## E. Restore verification

The dump restored with `pg_restore --exit-on-error --no-owner --no-acl` into a fresh, socket-only PostgreSQL cluster at head 0026. All 46 table counts and UTC-normalized, C-collation-sorted row-content digests matched source. Canonical fingerprint SHA-256: `bfb4e0f1c40ffd6b6bfc39f45c8de3e3f3c06084a3b15a3cbf8cfb0043f2bd12`. An initial aggregate comparison used server-default locale ordering and reported a false digest difference; per-row hashes matched, and the corrected fixed-order comparison matched every table *before* live ownership changed. The restored copy then passed split-role `harden`/`verify`, rollback-only app DML, and DDL denial.

## F. Pre-cutover ownership/grants

Before cutover, `twf_app` owned `twf`, protected Order/Preview/Queue tables, their sequences, and `twf_queue_event_immutable()`; `public` was owned by `pg_database_owner`, effectively the database owner. Relation ACLs were default/null. Exact pre-cutover role/owner/ACL/constraint/trigger inventory: `var/backups/oe3-role-cutover/live-before-ownership.txt`.

## G. Ownership transfer

The existing `tools/postgres_roles.py harden` procedure ran once under bootstrap authority at exact head 0026 and committed ownership and ACL changes in one transaction; independent `verify` passed. `twf_migrator` now owns database `twf`, schema `public`, all application relations/sequences, and the Queue audit function. `twf_app` owns none. Post-cutover inventory: `var/backups/oe3-role-cutover/live-after-ownership.txt`.

## H. Runtime grants

`twf_app` now has database CONNECT, schema USAGE, SELECT/INSERT/UPDATE/DELETE on 44 of 46 ordinary tables, sequence USAGE/SELECT, Queue-event SELECT/INSERT only, and `alembic_version` SELECT only. It has no database/schema CREATE or TEMP, direct audit-function EXECUTE, protected-object ownership, or migrator/admin/elevated-role membership. Its LOGIN is enabled for normal API use. The API process has no admin/migrator URL/password variables. The current tested procedure grants DELETE to those 44 tables as a broad compatibility matrix; a narrower per-table DELETE review remains a focused-review item, and was not improvised during this live cutover. New migrations require an operator grant/verification pass before API restart.

## I. DDL-bypass attacks

With the actual `twf_app` login, ALTER on Order/Queue tables, DROP F1 constraint, DISABLE/DROP F2 trigger, ALTER/DROP its function, ALTER OWNER, CREATE in `public`, SET ROLE migrator, CREATE ROLE, and CREATE DATABASE all returned SQLSTATE 42501. Search path is `"$user", public`; runtime cannot CREATE in the searched schema/database or create temporary objects. Mutating DDL probes used rollback-only transactions.

## J. F1/F2 direct attacks

Synthetic live-role, rollback-only cases for READY Order plus Entry, QUEUED Order without Entry, mismatched binding, owner mismatch, and deletion of a bound Entry each failed with SQLSTATE 23503. Queue-event UPDATE/DELETE and bulk forms returned 42501. Post-restart probes repeated F1 unbound-QUEUED rejection and F1/F2 DDL and audit mutation denial. The 0026 constraints and audit trigger stayed enabled.

## K. Normal runtime DML

The live runtime role performed synthetic Preview INSERT/UPDATE/read, valid bound Order/Queue admission, Queue event INSERT/history read, and Hold/Release state updates in a forced-rollback transaction; no test business row persisted. The focused isolated PostgreSQL gate covered service-level admission/replay, Hold/Release, history, F1/F2, cursor handling, and DB1-R2 concurrency: **106 passed**. No live broker submission occurred.

## L. Data preservation

All 46 table counts and content fingerprints matched before cutover, after ownership transfer, after rollback-only probes, and after API restart. Live Order, Queue Entry, Queue event, and manual Preview counts remained zero. Ownership/ACL metadata and the temporary `NOLOGIN` maintenance gate were the only live DB changes; LOGIN was restored.

## M. API restart

The API restarted under its normal runtime configuration (reloader PID `3142612`), without admin/migrator secrets. `/health` returned 200; `/ready` returned 200 with `database_backend=PostgreSQL`, `database_status=ready`, and `database_checked=true`.

## N. Runtime role verification

Post-restart PostgreSQL activity showed an idle `twf_app` application session, the database owner remained `twf_migrator`, and head remained 0026. A direct runtime-URL connection returned `current_user=twf_app`. Post-restart F1/F2/DDL probes remained denied.

## O. Module/UI smoke

The live web server returned HTTP 200 for Watchlists, Scanners, Trade, Orders, Positions, and Brokers route loads. Unauthenticated protected API reads returned 401/403 as expected, not a database/server error. The focused API suite exercised authenticated Order/Queue paths on isolated PostgreSQL; the earlier PostgreSQL-backed browser gate covered Trade/Positions, Queue, OE-2, and Broker fixture flows. No live broker order was used as a smoke test.

## P. Backup/restore role model

The disposable restored DB passed `harden`/`verify` with distinct `twf_migrator`/`twf_app` roles. The restored app role could perform rollback-only synthetic Order/Queue/event DML but could not disable the trigger. Recovery into a fresh target requires role provisioning, restore, then `harden`/`verify` before runtime access; the runbook also retains the metadata-preserving recovery option.

## Q. SQLite preservation

`apps/api/twf.db`, `var/db1/remediation/type-inspection.sqlite`, and `var/backups/db1/20261015T065401Z/twf-pre-postgres.sqlite` had matching SHA-256 values before and after cutover. No reverse sync, dual-write, or PostgreSQL-to-SQLite auto-failover was enabled. SQLite remains explicit fallback only.

## R. Rollback readiness

The final dump was also restored into a *second* disposable DB with its original owners/ACLs (without `--no-owner --no-acl`). Database, Order table, and audit-function owners were `twf_app`, head remained 0026, and all 46 content digests matched. This rehearsed the pre-cutover recovery artifact without rolling back healthy live PostgreSQL. For a future failure, stop writers and reconcile newer PostgreSQL writes before restore; never grant `twf_app` broad authority merely to start the API. Private pre/post inventories and restore evidence remain retained.

## S. Exact live DB changes

`twf_app` LOGIN was temporarily disabled and restored. Database/schema/application table/view/sequence/function ownership moved to `twf_migrator`; broad runtime/PUBLIC rights were revoked and the narrow runtime grant matrix applied. Business rows, IDs, expiry dates, timestamps, JSON, Queue state, migration history, and SQLite data did not change. No 0027 migration was created or run.

## T. Exact source/config changes

This cutover turn changed documentation status/evidence only. Runtime source, domain semantics, migration files, and private API configuration were not modified. Existing uncommitted OE-3 remediation remains uncommitted. No commit, tag, or push occurred.

## U. Required live role scorecard

```text
OE3_LIVE_CUTOVER_STATUS = PASS
WRITERS_STOPPED = PASS
PRE_CUTOVER_BACKUP_CREATED = PASS
PRE_CUTOVER_BACKUP_RESTORE_VERIFIED = PASS
PRE_CUTOVER_DATA_FINGERPRINT_RECORDED = PASS
TWF_MIGRATOR_EXISTS = PASS
TWF_APP_EXISTS = PASS
TWF_APP_NOT_SCHEMA_OWNER = PASS
TWF_APP_NOT_PROTECTED_TABLE_OWNER = PASS
TWF_APP_NOT_TRIGGER_FUNCTION_OWNER = PASS
TWF_MIGRATOR_OWNS_PROTECTED_OBJECTS = PASS
TWF_APP_ALTER_TABLE_BLOCKED = PASS
TWF_APP_DROP_CONSTRAINT_BLOCKED = PASS
TWF_APP_DISABLE_TRIGGER_BLOCKED = PASS
TWF_APP_DROP_TRIGGER_BLOCKED = PASS
TWF_APP_ALTER_FUNCTION_BLOCKED = PASS
TWF_APP_SET_ROLE_MIGRATOR_BLOCKED = PASS
TWF_APP_CREATE_ROLE_BLOCKED = PASS
TWF_APP_CREATE_DB_BLOCKED = PASS
F1_LIVE_RUNTIME_ROLE_ENFORCED = PASS
F2_LIVE_RUNTIME_ROLE_ENFORCED = PASS
NORMAL_RUNTIME_DML = PASS
QUEUE_ADMISSION = PASS
QUEUE_REPLAY = PASS
HOLD_RELEASE = PASS
QUEUE_HISTORY_READ = PASS
POST_CUTOVER_DATA_MATCH = PASS
API_RESTARTED_AS_TWF_APP = PASS
HEALTH_READY = PASS
POSTGRES_PRIMARY_RETAINED = PASS
SQLITE_UNTOUCHED = PASS
NO_AUTO_FAILOVER = PASS
RESTORE_ROLE_MODEL_VERIFIED = PASS
ROLLBACK_PATH_VERIFIED = PASS
OE4_NOT_IMPLEMENTED = PASS
OE3_READY_FOR_FOCUSED_REREVIEW = YES
```

## V. Final status

`READY_FOR_FOCUSED_REREVIEW`. The prior independent FAIL review remains historical evidence. OE-3 is not accepted or frozen by this cutover; no OE-4 worker, Broker V2 handoff, scheduling, or execution retry was added.
