# TWF Database Architecture — DB-1

Status: DB-1 was accepted/frozen in
[TWF_DB1_FINAL_ACCEPTANCE_REVIEW.md](TWF_DB1_FINAL_ACCEPTANCE_REVIEW.md).
OE-3 privilege/cursor remediation is separate and pending focused re-review;
OE-4 worker execution and Broker handoff remain unimplemented.

## Authority and configuration

**PostgreSQL is the primary authoritative runtime database. SQLite is an explicit
fallback, recovery snapshot, or lightweight local mode.** There is no automatic
failover, dual-write, replication, or synchronization between these databases.
A PostgreSQL outage must not create or write a SQLite database.

The existing canonical setting is `TWF_DATABASE_URL`, loaded through typed Settings
and the existing private `apps/api/.env`/deployment environment convention. A
missing URL fails with an actionable error. A PostgreSQL URL uses synchronous
`postgresql+psycopg`; `postgresql://` is normalized to that driver. An explicit
`sqlite+pysqlite:///...` URL deliberately selects SQLite fallback. No unprefixed
`DATABASE_URL` alias or second configuration system is introduced.

Credentials belong in private environment files or a secret manager, never source,
logs, command-line arguments, or reports. Existing encrypted broker/provider data
is copied unchanged; retain the original credential master key separately.
Remote deployments can use driver URL parameters such as `sslmode=verify-full` and
`sslrootcert`. Local socket/loopback validation does not establish production TLS.

## Engine, transactions, and startup

The existing synchronous SQLAlchemy/psycopg stack remains. PostgreSQL uses a pool
of 5, overflow of 5, pool timeout 10 seconds, connection timeout 5 seconds,
`pool_pre_ping`, SQL echo disabled, and hidden parameters. Bounded settings expose
pool size, overflow, and connection timeout. Each new PostgreSQL connection sets
its session timezone to UTC; it must not inherit the host's local timezone.

READ COMMITTED plus existing conditional writes, uniqueness, and explicit
transactions preserve the current CAS design. OE-1 state/event transactions stay
unchanged. OE-2's conditional Preview claim, OE-1 savepoints, readiness, and linkage
share one outer transaction. OE-3 admission creates its Queue Entry, transitions
READY → QUEUED, and appends both histories together. Existing SQLite BUSY/LOCKED
retries remain dialect-specific; they are not used as PostgreSQL retry policy.
No generalized retry loop or SERIALIZABLE isolation is added. DB1-R2 admission
replay reads the existing Queue Entry and its linked Order in one joined statement,
with `populate_existing` to refresh stale ORM objects. Authentication and Order
ownership are checked first. The same coherent read is used after bounded admission
contention. Missing/mismatched ownership or impossible Order state still fails;
no invariant exception is swallowed. Hold/Release and the admission write transaction
are unchanged.

Engine construction is lazy. API lifespan verifies a connection and the exact
supported Alembic head (`0027_oe3_order_event_audit`) before marking initialization complete.
Failure disposes the engine and prevents startup. A graph consistency test ensures
that the supported head tracks Alembic. Operators run migrations explicitly;
startup never mutates schema. `/health` remains process liveness. `/ready` probes
persistence and head compatibility and returns 503 on failure, with only safe
backend/status fields. Satellite/broker readiness is a separate concern.

Both backends must be migrated before startup. SQLite keeps its explicit
transactions, foreign-key enforcement, and memory-connection behavior. It does
not acquire PostgreSQL row-lock semantics or become a high-concurrency replica.

## Schema and migration fidelity

Alembic remains the sole application schema path. DB-1 does not rewrite historical
migration IDs or alter Order/Queue lifecycle constraints. PostgreSQL's existing
128-character Alembic version column accommodates the published long revision IDs.
Live tests exercise upgrade from zero, downgrade to base and back, recent critical
migrations, and metadata/schema agreement.

The offline importer is `python -m twf.infrastructure.sqlite_migration`. It requires
an explicit verified read-only SQLite snapshot, matching backup size/SHA-256,
matching source/destination head and full table/column sets, and an empty migrated
PostgreSQL destination. It copies in reflected FK dependency order without disabling
constraints. A single transaction locks the destination tables, copies every row,
checks every table's count/content hash/null counts/owner counts, rechecks FKs,
and resets any integer sequences transactionally. Any row/verification failure
rolls back the import; no deduplication, omission, or partial acceptance occurs.

`--dry-run` inventories and checks without writing. `--verify-only` compares an
already imported/restored destination using a read-only repeatable-read transaction.
The default mode refuses a populated destination, including after a successful
import. To restart after failure, fix the issue and use the still-empty destination.
The tool does not change runtime configuration or stop applications on your behalf.

Fidelity rules:

- UUIDs preserve identity; opaque text and all PK/FK links are preserved. No new
  Order, Preview, Queue, owner, or history IDs are generated during import.
- NUMERIC extraction is storage-aware and refuses uncertifiable values (DB1-R1).
  Source and destination must declare the same explicit `NUMERIC(p,s)` or
  `DECIMAL(p,s)`, with nonnegative scale no greater than precision. INTEGER storage
  is read as exact integer text; TEXT is parsed directly as Decimal; NULL stays
  NULL. Neither extraction nor verification converts these values through a
  Python float. Finite values must fit the declared precision and scale exactly.
- For SQLite REAL storage, high-detail SQLite formatting proposes a Decimal at
  the declared scale; formatting alone is **not** authoritative. Independent SQL
  comparisons against the stored REAL require that candidate to round-trip and
  both adjacent scale values to differ. No match means excess scale/unrepresentable
  storage; an adjacent match means ambiguity at this scale. Either condition
  raises `NumericMigrationFailure` and rolls back the entire import. This accepts
  only a uniquely reconstructible declared-scale decimal, not an arbitrary rounded
  spelling of the binary value. INTEGER storage never uses REAL formatting.
- Source inventory uses certified values; destination verification independently
  reads PostgreSQL Decimal values and checks exact representability before hashing.
  There is no lossy override. Invalid source integrity, unsupported storage/types,
  non-finite values, declaration mismatch and precision/scale overflow are refused.
  Trailing zeros may normalize only without changing numeric value. Decimal strings
  in business JSON remain strings. Precision lost before SQLite storage cannot be
  recovered or claimed as preserved.
- Expiry is an exchange-calendar date. DATE and JSON expiry strings are copied
  without timezone conversion.
- Naive SQLite DateTime values are interpreted as UTC, matching existing TWF
  persistence conventions. Aware values are normalized to UTC instants.
- JSON is copied as raw JSON through PostgreSQL's JSON parser. Verification uses
  semantic sorted content with decimal parsing for arbitrary JSON numbers, so
  object ordering is irrelevant, arrays remain ordered, and SQL NULL remains
  distinct from JSON null. Encrypted strings remain byte-for-byte text.
- Current application PKs use UUID/text, so there are no production sequences to
  reset. A live synthetic SERIAL fixture verifies next-ID behavior after import.

## Deployment and test modes

`compose.yaml` provides a persistent PostgreSQL 16 service, loopback port 55432,
a named volume, healthcheck, and an API dependency on database health. Credentials
are required via private env. Native API URLs use `127.0.0.1:55432`; a container API
must use `postgres:5432`. Migrations must be run before the API starts. Use a
separate non-superuser schema owner (`twf_migrator`) and limited application
role (`twf_app`). Bootstrap/admin and migrator credentials must not be available
to the running API.

The primary test gate is `tools/test-postgres.sh -q`. It creates a disposable
PostgreSQL cluster using installed PostgreSQL server binaries (`pg_config --bindir`,
or `TWF_PG_BINDIR`). The cluster accepts only a private Unix socket inside a 0700
temporary directory, has no TCP listener, and is stopped/deleted on exit. Tests use
a separate random schema each; deployment dotenv/settings are never inherited.
Plain pytest defaults to PostgreSQL and fails clearly without the isolated test
URL. Explicit fallback compatibility uses `--db-backend=sqlite`.

Generic persistence tests, including OE-1/OE-2/OE-3, run on PostgreSQL. Tests of
SQLite memory/PRAGMA/legacy syntax remain explicit SQLite probes; the SQLite-only
BEGIN IMMEDIATE test is skipped in PostgreSQL mode and run in fallback mode.
Browser smoke uses `tools/test-postgres.sh --browser ...`; provider/order transports
remain synthetic, but persistence and concurrency use live PostgreSQL. No live
broker order is needed to validate the database migration.

## Backup, cutover, and recovery

Follow the [migration runbook](TWF_SQLITE_TO_POSTGRES_MIGRATION_RUNBOOK.md).
Stop all writers before backup/import and retain the original source. The backup
helper creates a new snapshot, verifies integrity/FKs, records size/hash/time, and
marks files read-only. Apply filesystem immutable flags or WORM retention before
migration. A file permission alone is not immutable storage.

Once PostgreSQL is authoritative, take PostgreSQL `pg_dump` backups and rehearse
`pg_restore` into an isolated database. Backups contain sensitive data and need
restricted permissions, encrypted/off-host storage, retention, and separate master
key custody. The current local setup is not HA, PITR, or an off-host backup service.
A PostgreSQL → SQLite snapshot exporter is **DEFERRED**. The pre-cutover SQLite
snapshot does not receive later writes.

Before cutover failure, keep the original SQLite authority. After PostgreSQL has
accepted any new write, stop writes and repair/restore PostgreSQL; do not switch
casually to stale SQLite. Any fallback requires an explicit reconciled recovery
point and operator decision. Copying `.env` back is not data reconciliation.


## OE-3 PostgreSQL privilege boundary and SQLite trust scope (16 October 2026)

PostgreSQL remains the production execution-authority database. The live role model
uses a bootstrap administrator, a separate `twf_migrator` schema/database owner,
and a limited `twf_app` runtime login. The approved live ownership cutover completed
on 16 October 2026; its evidence is in [the live cutover report](TWF_OE3_LIVE_PRIVILEGE_CUTOVER_REPORT.md). Alembic and data restore run under migration
authority; the API receives only its runtime URL. `twf_app` has CONNECT, schema
USAGE, required table DML and sequence usage. Runtime DELETE is default-denied,
with an explicit 11-table cleanup allowlist; TWF Order and Queue audit events
have SELECT/INSERT only, while `alembic_version` has SELECT only. Migration 0027
adds database-level Order-event UPDATE/DELETE guards on PostgreSQL and SQLite. It owns no application schema, table,
sequence, trigger function, or database, cannot CREATE in the searched schema or
database, and is not a member of the migration/admin roles. The 0026 deferred constraints and audit trigger resist direct
DML **and** runtime-role DDL removal. The audit function is not SECURITY DEFINER and contains no
unqualified object lookup; direct EXECUTE is revoked from PUBLIC/runtime.
New migrations require an operator grant/verification pass before API restart.
See [the role cutover runbook](TWF_SQLITE_TO_POSTGRES_MIGRATION_RUNBOOK.md).

SQLite has **no equivalent hostile-direct-SQL role boundary**. In explicit
fallback/recovery/developer mode, TWF-managed connections enable `foreign_keys=ON`
and migration-installed triggers enforce Order/Queue coherence and append-only
Queue events for normal application DML; keyset pagination remains owner-bound.
A process with arbitrary writable access to the database file or a separate raw
connection can disable foreign keys, drop triggers, or edit bytes. This is outside
the supported adversarial guarantee. Keep the database and containing directory
private to a trusted service account (for example mode 0600/0700), and never
interpret same-user file permissions as protection against a hostile process.
SQLite is not an adversarially equivalent production execution authority.

## Carry-forward boundaries

OE-3's cross-table coherence, Queue event immutability, and pagination were not
part of DB-1 acceptance. The later 0026 and role/cursor remediation, including the live role cutover, are ready for
focused OE-3 re-review; OE-3 is not frozen. Existing service transaction atomicity is validated
independently of the runtime-role direct-SQL boundary.
PostgreSQL `FOR UPDATE` and `SKIP LOCKED` are verified capabilities for later OE-4,
not an implemented worker, risk check, scheduler, or execution path.

Version: DB-1, 2026-10-15. This policy supersedes historical SQLite-default and
PostgreSQL-offline-only statements without rewriting their historical evidence.
