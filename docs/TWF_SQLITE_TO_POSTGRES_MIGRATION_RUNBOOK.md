# SQLite → PostgreSQL Migration Runbook

This is a one-authority cutover, not replication. Review
[TWF_DATABASE_ARCHITECTURE.md](TWF_DATABASE_ARCHITECTURE.md) first. Commands below
run from the repository root unless a `cd` is shown. Substitute actual private
paths. Never use the live database as a destructive migration test target.

## 1. Prepare and stop writers

Record `git status --short`, branch, HEAD, and `git diff --check`. Preserve existing
work. Identify the API's actual working directory and `TWF_DATABASE_URL` without
printing credentials. Identify any other process/tool that can write the database.
Stop the API, reload supervisor, scripts, and all writers. Keep them stopped until
cutover verification completes; do not run SQLite and PostgreSQL authorities together.

Retain the existing credential master key. Do not regenerate it during migration.
Check backup disk space and permissions. Plan downtime and the rollback point.

## 2. Make and verify an immutable SQLite backup

```bash
apps/api/.venv/bin/python -m twf.infrastructure.sqlite_backup \
  --source apps/api/twf.db \
  --directory var/backups/db1/UNIQUE_UTC_TIMESTAMP \
  --writers-stopped
sudo chattr +i var/backups/db1/UNIQUE_UTC_TIMESTAMP/twf-pre-postgres.sqlite \
  var/backups/db1/UNIQUE_UTC_TIMESTAMP/manifest.json
lsattr var/backups/db1/UNIQUE_UTC_TIMESTAMP/*
```

The helper opens the source read-only and uses SQLite's backup API. It verifies
`integrity_check`, `foreign_key_check`, records revision/size/SHA-256 and UTC time,
and creates new files only. On platforms without immutable flags use verified
WORM/object retention or equivalent immutable storage before proceeding. Keep the
original SQLite file too. Do not delete/rewrite it or its only backup.

## 3. Prepare PostgreSQL with split roles

PostgreSQL is the production execution-authority database. Keep three credentials
separate: bootstrap/admin (`TWF_PG_ADMIN_URL`) for role/ownership operations,
`twf_migrator` (`TWF_MIGRATION_DATABASE_URL`) for Alembic/import/restore, and
`twf_app` (`TWF_DATABASE_URL`) for the API. Store each in a private operator secret
source; **never mount the admin or migrator URL into the API service**. The API
container in Compose receives only `TWF_DATABASE_URL`. `TWF_PG_*_PASSWORD` is
needed only when creating a missing role; existing passwords are not rotated.

Stop writers, take a verified PostgreSQL dump before an existing deployment
cutover, and inventory existing ownership/grants. These commands never copy or
rewrite application rows:

```bash
# URLs/passwords are injected privately, not supplied on command lines.
apps/api/.venv/bin/python tools/postgres_roles.py inventory
apps/api/.venv/bin/python tools/postgres_roles.py provision
```

For a **fresh empty** PostgreSQL database (create the database with your bootstrap
administrator first), run `prepare-fresh`, then Alembic as the migrator. A host
migration uses `tools/migrate-postgres.sh` with private runtime and migration URLs.
Compose supports the same operator-only operation via
`docker compose --profile ops run --rm migrate` after provisioning. A blank
migration URL fails; this service is never started by default.

```bash
apps/api/.venv/bin/python tools/postgres_roles.py prepare-fresh
tools/migrate-postgres.sh
# Import verified SQLite data using the migrator URL in this *operator* process.
# Only after import/verification, grant the API its limited runtime DML:
apps/api/.venv/bin/python tools/postgres_roles.py harden
apps/api/.venv/bin/python tools/postgres_roles.py verify
```

For an **already split PostgreSQL deployment at 0026**, do not rerun
`prepare-fresh` or import data. Stop the API/all writers and disable runtime
login; verify a fresh `pg_dump` and an isolated restore. Before 0027, the
bootstrap administrator must verify `twf_migrator` has database CONNECT/CREATE
and schema USAGE/CREATE: prior ownership transfer may have left an inherited ACL
that names the new owner but withholds CONNECT. If missing, grant those rights to
the migrator under bootstrap authority while writers remain stopped. Upgrade to
head `0027_oe3_order_event_audit` with the migrator, then run `inventory`,
`harden`, and `verify` under the bootstrap/admin URL. Re-enable runtime login
only after the exact grant matrix and direct DML probes pass. A still-app-owned
0026 deployment needs a separately rehearsed owner-transition procedure before
this 0027 path; do not give migration credentials to the API to work around it.
`harden` transfers database, schema, tables, sequences, and trigger functions to
`twf_migrator`, explicitly grants the migrator database/schema rights that old ACLs
may have withheld, and applies runtime grants in one PostgreSQL transaction. It does
not recreate tables or touch rows/IDs. Check the app-role DDL-denial probes and
normal Preview → READY → Queue/Hold/Release paths before restarting the API.
If a step fails, its transaction rolls back; retain the dump and keep writers
stopped while diagnosing. An operator must reapply/verify grants after future
migrations add tables, because this cutover deliberately avoids broad default DML
grants. Database role names default to `twf_migrator`/`twf_app` and may be set via
`TWF_PG_MIGRATOR_ROLE`/`TWF_PG_APP_ROLE`; schema defaults to `public`.

The runtime role has CONNECT, schema USAGE, and needed table DML. DELETE is
default-denied for current and future tables; only the explicit 11-table
`REQUIRED_DELETE_TABLES` cleanup allowlist in `tools/postgres_roles.py` receives
DELETE. TWF Order and Queue audit events have SELECT/INSERT only, and
`alembic_version` has SELECT only. Migration 0027 adds PostgreSQL and SQLite
Order-event UPDATE/DELETE guards; the runtime role cannot alter their PostgreSQL
trigger or function. Verify exact grants after every migration before API restart. It owns no
protected object or database and cannot CREATE in the schema/database. The
migrator owns schema objects and runs Alembic. The bootstrap/admin role creates
roles/databases and performs the ownership transfer; it is never an API login.
No automatic SQLite failover or dual-write is added. A PostgreSQL URL for a native
API uses `127.0.0.1:55432`; Compose API/migration containers use `postgres:5432`.

## 4. Inventory, import, verify

In the isolated operator import process, set `TWF_DATABASE_URL` to the **migrator**
URL for the destination; never run the importer with API credentials. Reports are
private and ignored because they contain owner IDs and row fingerprints. Use a new
report path each time; the importer refuses to overwrite reports.

```bash
mkdir -p var/db1
apps/api/.venv/bin/python -m twf.infrastructure.sqlite_migration \
  --source var/backups/db1/UNIQUE_UTC_TIMESTAMP/twf-pre-postgres.sqlite \
  --manifest var/backups/db1/UNIQUE_UTC_TIMESTAMP/manifest.json \
  --dry-run --report var/db1/dry-run.json
apps/api/.venv/bin/python -m twf.infrastructure.sqlite_migration \
  --source var/backups/db1/UNIQUE_UTC_TIMESTAMP/twf-pre-postgres.sqlite \
  --manifest var/backups/db1/UNIQUE_UTC_TIMESTAMP/manifest.json \
  --report var/db1/import-verification.json
```

Require `IMPORTED_AND_VERIFIED`, equal counts and content hashes for **every**
table, no FK/unique anomalies, and no numeric/date/timestamp/JSON mismatch. Empty
critical tables are explicitly recorded as empty; representative test fixtures
exercise their data types and lifecycle records. Do not fabricate real records to
make an inventory look complete. Review first/last keys, owner counts, null counts,
and sequence restart records in the report.

On failure, the import transaction rolls back. Diagnose the reported table/key;
do not skip rows or silently deduplicate. Rerun against an empty destination after
fixing the cause. After a successful import, use `--verify-only` to recheck instead
of importing again. It performs no writes and uses a consistent read-only snapshot.
Keep all writers stopped while comparing to the pre-cutover source. If writing the
report fails after the import commits, the importer reports that ambiguity: use
`--verify-only` with a fresh writable report path. A filesystem report and a database
transaction cannot be committed atomically.

### NUMERIC certification and refusal (DB1-R1 remediation)

An import never uses SQLite's ordinary REAL-to-TEXT CAST as evidence of exact
numeric fidelity. INTEGER/TEXT storage is parsed exactly; REAL storage must map
uniquely to one decimal at the matching declared precision/scale. The candidate
must round-trip to the stored REAL and its adjacent scale values must not.
The importer refuses ambiguous REAL values, extra scale, precision overflow,
non-finite/unsupported storage and differing or unbounded numeric declarations.
An existing SQLite integrity failure is refused before row certification.

Example: `NUMERIC(20,5)` holding the review value `12345678901.12345` is preserved
exactly. The same binary storage under `NUMERIC(20,6)` may be ambiguous and is
refused; it must never become a rounded value certified as exact. Trailing zeros
can normalize only when the numeric value is unchanged and fits the declaration.

`NumericMigrationFailure` identifies table, column, primary key, declared type,
and a sanitized reason, without printing the numeric value. For example:
`precision_probe column amount key ["array",[2]] declared NUMERIC(10, 2): REAL has
no unique lossless decimal at declared scale; import refused`.
Any such failure rolls back **all** imported rows and emits no successful import
status. A verify-only mismatch likewise cannot produce `VERIFIED_READ_ONLY`.

Keep the immutable backup intact. Investigate the original authoritative source,
its declared scale and storage; establish an exact value from trustworthy source
records or correct the source/schema through a separately reviewed data repair.
Make a new verified immutable snapshot of that corrected working copy before
retrying an empty destination. Never edit the retained backup, silently round,
skip a row, or force a lossy migration. There is no `--force-lossy` mode.

After cutover, the old snapshot cannot certify newer writes. Compare a fresh
PostgreSQL dump to its restore, and separately account for added/updated records
when checking original migrated rows. Do not relabel a content mismatch as a
successful snapshot verification. Keep any expected differences explicit.

## 5. Validate before cutover

```bash
tools/test-postgres.sh -q
# Contains the focused OE suites, 50 Preview races, 55 Queue races, Hold/Release,
# rollback, migration, exact-value, no-fallback, and schema/head checks.
cd apps/api
.venv/bin/python -m pytest --db-backend=sqlite -q
cd ../..
cd apps/web
npm run test -- --maxWorkers=2
npm run build
cd ../..
tools/test-postgres.sh --browser \
  tests/browser/twf-orders.spec.ts tests/browser/twf-queue.spec.ts \
  tests/browser/trade-workspace.spec.ts tests/browser/broker-orders.spec.ts \
  tests/browser/watchlists.spec.ts tests/browser/scanner-watchlist-unification.spec.ts \
  --project=chromium-390 --project=chromium-1440
```

The launcher needs PostgreSQL server tools. It creates its own socket-only cluster;
it never uses the destination or developer DB. Plain pytest without a disposable
PostgreSQL URL fails; SQLite testing requires the explicit backend option.

## 6. Take and rehearse a PostgreSQL backup

Use a protected, non-command-line secret source (service file/`.pgpass`/secret
injection). `pg_dump -Fc --no-owner --no-acl` preserves data and schema without
binding the artifact to local role names. Restore into a **separate empty**
database owned by `twf_migrator` using `pg_restore --exit-on-error --no-owner
--no-acl` authenticated as that migrator; provision roles first, then run
`tools/postgres_roles.py harden` and `verify` against the restored database.
Verify `twf_migrator` owns the database/schema/tables/functions, `twf_app` can
perform normal DML, and its DDL bypass attempts receive permission denied.
Compare all table counts/content, FKs, IDs and sensitive business values to the
source; do not treat a successful restore command alone as proof of fidelity.

For the 16 October 2026 OE-3 live role cutover, the retained stopped-writer
custom-format dump includes original owner/ACL metadata. A separate disposable
restore _without_ `--no-owner --no-acl`, into a database initially owned by
`twf_app` after provisioning the source roles, reproduced the pre-cutover owners
and all 46 application-table content fingerprints. This is a rehearsed metadata
rollback artifact, not permission to restore stale data over newer writes. See
[TWF_OE3_LIVE_PRIVILEGE_CUTOVER_REPORT.md](TWF_OE3_LIVE_PRIVILEGE_CUTOVER_REPORT.md).

Restrict dump permissions (`umask 077`), encrypt/store off-host, retain the
credential master key separately, and rehearse restoration regularly. A stale
SQLite snapshot is not a current PostgreSQL backup.

## 7. Cut over exactly once

Only after import, focused/full gates, and restore verification pass:

1. Keep SQLite writers stopped. Reconfirm the source/backup checksum.
2. Save the old private runtime configuration securely (it includes secrets).
3. Replace only `TWF_DATABASE_URL` in the runtime environment/private `apps/api/.env`
   with the verified PostgreSQL application URL. Retain all other configuration.
4. Start the API with the normal command. Startup must pass connection/head checks.
5. Check `/ready`: `database_backend=PostgreSQL`, `database_status=ready`,
   `database_checked=true`. Never accept SQLite fallback as an unnoticed success.
6. Verify login/session, Watchlists, Scanner history/catalog, Trade Orders/Queue,
   Positions and Broker reads. Use the isolated synthetic-provider browser gate
   for new Equity/Futures/Option Order, Preview, Queue/Hold/Release writes; never
   submit a live broker order merely to test the migration.
7. Confirm new isolated PostgreSQL writes persist and the retained SQLite file is
   unchanged. Retain the immutable backup and reports.

API startup never runs migrations or switches backends. If PostgreSQL is down,
startup fails closed; an already running API's `/ready` becomes 503. `/health`
is liveness, not persistence readiness.

## 8. Rollback and explicit SQLite fallback

**Before cutover / before PostgreSQL accepts writes:** if migration/validation fails,
leave PostgreSQL non-authoritative and restart the original SQLite configuration
only as an explicit operator decision. No import rollback touches the SQLite source.

**After PostgreSQL accepts writes:** stop all writers; preserve a fresh PostgreSQL
dump and logs; repair or restore PostgreSQL from a verified recovery point. Do not
point the API at the old SQLite file: it is stale. Reconcile all newer state before
any explicit fallback decision. Restoring config alone loses new data.

For a deliberate lightweight or reconciled recovery environment, set an explicit
`TWF_DATABASE_URL=sqlite+pysqlite:///ABSOLUTE/PATH/fallback.db`, run Alembic on that
chosen working copy, then start the API. `/ready` reports `SQLite fallback`. Never
open the immutable backup for writes. No automated PostgreSQL → SQLite exporter,
replication, or reverse synchronization is implemented.

Version: DB-1, 2026-10-15. Review status belongs to the implementation report;
this runbook does not freeze OE-3 or authorize an OE-4 worker.

### OE-4 and future object registration

The role tool uses an exact schema registry. Migration 0028 adds five registered tables and zero sequences. A migration that adds any runtime table, sequence, or protected function must declare it and its minimum operations in `tools/postgres_roles.py`; otherwise `harden`/`verify` refuses the schema. Never repair this with an ad-hoc live GRANT. Stop writers, take and restore-verify a dump, apply the canonical policy, verify exact ownership/grants and rollback-only denial probes, then restart the API. The OE-4 live procedure and evidence are recorded in [TWF_OE4_RUNTIME_PRIVILEGE_REMEDIATION_REPORT.md](TWF_OE4_RUNTIME_PRIVILEGE_REMEDIATION_REPORT.md).
