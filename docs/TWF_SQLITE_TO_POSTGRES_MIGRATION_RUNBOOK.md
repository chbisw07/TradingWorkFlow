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

## 3. Prepare PostgreSQL

Create a private root `.env` (0600, ignored) with `TWF_POSTGRES_PASSWORD` for the
bootstrap role and `TWF_DATABASE_URL` for the intended application connection.
Use `compose.yaml` with `docker compose up -d postgres` (or `--env-file` for a
separate private deployment file). The service uses a persistent named volume and
loopback port 55432. Do not use `docker compose down -v` on authoritative data.

Provision a non-superuser application role and database ownership using your
administrator's secure connection. The migration/application role must own its
schema objects and have access to sequences. It does not need superuser, role
creation, or database creation. For an existing managed PostgreSQL service, use its
approved TLS and secret configuration instead of the local Compose service.

For a new local Compose database with the example bootstrap/database name `twf`:

```bash
docker compose exec postgres psql -U twf -d twf
```

In that interactive psql session (the password prompt is hidden):

```sql
CREATE ROLE twf_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
\password twf_app
ALTER DATABASE twf OWNER TO twf_app;
\q
```

Use the new application role in the private runtime URL. Do not recreate an
existing role or change ownership on an unrelated database.

Supply `TWF_DATABASE_URL` through the environment without placing a password in
shell history (for example, a hidden `read -rs` prompt followed by `export`). Native
API: `postgresql+psycopg://...@127.0.0.1:55432/twf`; container API: host `postgres`,
port `5432`. These are different connection contexts.

```bash
cd apps/api
.venv/bin/alembic upgrade head
.venv/bin/alembic current
cd ../..
```

Use a **fresh empty destination**. Do not downgrade or erase a populated runtime DB.
The expected head is `0025_twf_queue`. Run upgrade/downgrade tests only in the
isolated test cluster described below.

## 4. Inventory, import, verify

Set `TWF_DATABASE_URL` to the destination in the current environment. Reports are
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

For Compose, keep passwords off argv and restrict output file permissions:

```bash
umask 077
docker compose exec -T postgres pg_dump -U twf_app -Fc twf \
  > var/backups/db1/postgres-before-cutover.dump
# Create a separate empty restore database owned by the application role:
docker compose exec -T postgres createdb -U twf -O twf_app twf_restore_check
docker compose exec -T postgres pg_restore --exit-on-error \
  -U twf_app -d twf_restore_check < var/backups/db1/postgres-before-cutover.dump
```

Adapt role/database names to your provisioning. With non-container PostgreSQL use
`pg_dump`/`pg_restore` and a protected `.pgpass`, service file, or secret injection;
SQLAlchemy's `+psycopg` URL is not a libpq command URL. Point the importer at the
restore database and use `--verify-only` against the immutable SQLite backup.
Require equal counts/content. Keep the dump and verification report. Remove only
the specifically named disposable restore DB after verification if desired.

For ongoing operation, back up PostgreSQL at a frequency appropriate to the loss
window and test restoration regularly. Local manual dumps alone are not HA/PITR;
production needs managed backup/retention/off-host protection and key custody.

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
