# TWF-1.3 — Database Foundation

Status: **implemented, pending independent review**. Recommendation: `GO_TWF1_3_REVIEW`.
Next target after acceptance: **TWF-1.4 User / Login Foundation**.

## Baseline and scope

Resumed preflight verified clean `main`, equal to `origin/main` and accepted tag
`twf-1.2-backend-shell`, at `cfc19a0659974dfa74c5403e490ca34abe9f7ceb`.
The earlier generated frontend change was already resolved; this target did not
restore or edit frontend files. No commit, tag, or push was performed.

This target implements persistence infrastructure under the accepted
[data architecture](TWF_DATA_ARCHITECTURE.md),
[technology decisions](TWF_TECHNOLOGY_DECISION_RECORD.md),
[deployment architecture](TWF_DEPLOYMENT_ARCHITECTURE.md), and
[engineering standards](TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md).
The [TWF-1.2 record](TWF_TWF1_2_BACKEND_SHELL.md) remains historical; its baseline is
now accepted, as reflected in README/index. All earlier milestone history remains.

## Persistence architecture and lifecycle

The existing synchronous SQLAlchemy 2.x style is retained. Future synchronous
use-cases/repositories receive a `Session`; there is no speculative repository or
Unit-of-Work framework. Future async endpoints must keep blocking persistence
work off the event loop, rather than sharing Sessions among concurrent tasks.

`twf.infrastructure.database` owns:

- canonical `Base.metadata`;
- `create_database_engine(settings)`;
- `create_session_factory(engine)`;
- `session_scope(factory)`;
- internal `probe_database(engine)`.

Engine construction is lazy: no connection or schema creation at import,
`create_app`, or lifespan initialization. Lifespan owns one engine and session
factory per app run, clears references and disposes the engine on shutdown.
`create_app(..., engine_factory=...)` supports isolated test infrastructure; the
application owns disposal of the returned engine. Standalone callers/Alembic own
their engines and must dispose them. There is no shared global engine or Session.

`get_db_session` is a synchronous FastAPI yield dependency. It creates one session,
rolls back on exceptions (including cancellation), and always closes. Access
without initialized lifespan fails rather than opening a fallback global session.
No public route currently depends on the database.

## Configuration and security

The existing environment prefix remains `TWF_`: use **`TWF_DATABASE_URL`**.
There is no second unprefixed configuration channel. Environment values override
local `.env`; `.env.example` contains placeholders only. Supported URL forms:

| URL family | Handling |
|---|---|
| `sqlite:///...`, `sqlite+pysqlite:///...` | Normalize to synchronous pysqlite |
| `postgresql://...`, `postgresql+psycopg://...` | Normalize to Psycopg 3 |

Default remains `sqlite+pysqlite:///./twf.db`. PostgreSQL must name a database;
host/password may be supplied through normal PostgreSQL connection configuration,
including Unix sockets. SQLite URL credentials, hosts, ports and query options
are rejected. Async and other drivers are deliberately rejected. Malformed URLs
fail settings validation with a static message. Validation input is hidden in
rendered errors, and the URL remains excluded from Settings repr. Never serialize
Settings or raw structured validation errors to logs; they may contain secrets.

For backward compatibility, SQLite remains accepted in every environment,
including production-mode shell smoke tests. `TWF_ENVIRONMENT=production` does not
automatically select a database: cloud deployments must explicitly inject their
PostgreSQL URL. Invalid production URL configuration fails at settings creation;
unreachable databases are discovered only when used/probed, not by `/ready`.

SQL echo is always OFF (no debug flag needed in this target), SQLAlchemy parameter
rendering is hidden, and the internal probe returns only a boolean. The existing
safe HTTP exception envelope handles database errors without exposing driver
messages, SQL, credentials or parameters. No new database logs or diagnostics
endpoint exists. Operator-run migration errors should be treated as sensitive
operational output, not forwarded to a public response.

## Transactions and sessions

**Reads do not commit. Write use-cases explicitly own commit/rollback boundaries.**

Session configuration is explicit: `autoflush=False`, `autocommit=False`,
`expire_on_commit=False`, `close_resets_only=False`. SQLAlchemy still autobegins a
transaction when needed. Call `flush()` explicitly when a use-case needs database
validation before commit; `commit()` performs its own flush. Retaining loaded
attributes after commit avoids surprise reloads, but callers must explicitly
refresh when fresh database state is needed. Closed sessions cannot be reused.

Normal scope exit closes and rolls back unfinished transactions; it never commits.
Exception exit explicitly rolls back before close. A use-case that catches an
integrity failure and continues must itself roll back before using that session
again. No hidden commits or distributed transactions are introduced.

## SQLite and PostgreSQL

File SQLite uses SQLAlchemy's default file pool. Infrastructure alone configures
`check_same_thread=False` for FastAPI worker-thread use and Python 3.12+
`autocommit=False` for normal transaction behavior, including DDL. A connection
hook enables foreign keys outside a transaction. No domain code uses PRAGMAs.

In-memory SQLite uses `StaticPool` so sequential operations across worker threads
see one database per engine. This is intended for isolated, sequential tests;
concurrent transactions must use separate sessions with file SQLite or PostgreSQL,
not one shared in-memory connection. Tests mainly use disposable temporary files.

PostgreSQL uses Psycopg and SQLAlchemy's normal dialect pool. Both dialects use
pool pre-ping; no premature pool-size tuning was introduced. PostgreSQL connection
options such as TLS/connection timeout can be supplied through its URL query.
Credentials stay in externally injected configuration. No domain path or cloud
provider is embedded in the persistence design.

**PostgreSQL architecture compatible: YES. Runtime verified: YES.**
A disposable PostgreSQL 16 container used the already available image, a dynamic
loopback-only port, and randomly generated ephemeral credentials. It passed upgrade,
repeat upgrade, schema check, current/history, downgrade/re-upgrade, SELECT 1,
explicit commit and rollback checks. Only Alembic's version table remained after
test-only proof objects were removed. The engine and container were cleaned up.
This verifies foundation mechanics, not future domain schemas or production load.

## Metadata and migrations

`Base.metadata` remains empty. Naming conventions cover primary keys, foreign
keys, indexes, unique constraints and named check constraints. Composite names use
the first column: future schema authors must explicitly name constraints where
that would collide. Check constraints must have explicit descriptive names.
Future typed model modules should inherit this Base and be imported into the
canonical metadata registration path before Alembic configures its context.

Alembic's existing online/offline entry point continues to use Settings and this
canonical metadata; no URL or secret is placed in `alembic.ini` and no URL is passed
through ConfigParser interpolation. Online mode uses the same engine factory and
disposes it in finally. Offline PostgreSQL SQL generation is tested without a server.

`0001_empty_baseline` is the first revision. Upgrade/downgrade intentionally contain
no business DDL. Alembic creates only `alembic_version`; existing history contained
no revisions, so none was deleted or rewritten. Test proof tables use a separate
DeclarativeBase and never pollute canonical production metadata.

**Production migrations are explicit deployment/release operations. FastAPI
startup must not blindly auto-migrate production databases.** No runtime
`Base.metadata.create_all()` exists. Test-only schema setup uses separate metadata.

From `apps/api`, after setting the intended `TWF_DATABASE_URL`:

```bash
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/alembic history
.venv/bin/alembic check
```

Only on a disposable test database: `alembic downgrade base`, followed by
`alembic upgrade head`. Future destructive revisions require their own downgrade
policy and deployment review. This empty baseline does not migrate SQLite data
to PostgreSQL; future schema/data migrations retain their acceptance gates.

## Probe and readiness

`probe_database(engine)` runs SELECT 1 using a short-lived connection context,
closes/returns that connection to the pool, and returns false for SQLAlchemy errors
without logging exception content. It does not inspect or mutate schema. Connection
and statement timeouts follow driver/deployment settings; this helper is not a
bounded HTTP health endpoint. Opening a configured SQLite file can create that
empty file as part of SQLite connection behavior.

`/ready` remains exactly the TWF-1.2 application-initialization contract, with
`database_checked: false` and `satellite_dependencies_checked: false`. An unavailable
database does not change it. Database-dependent readiness needs a future explicit
decision.

## Future model conventions

Use SQLAlchemy 2.x `Mapped[]`/`mapped_column`, explicit nullability, foreign keys,
indexes and portable identifiers (prefer application-generated UUID semantics).
Use UTC timestamp semantics; PostgreSQL timezone-aware types and application-side
normalization must be explicit. Do not assume SQLite preserves timezone offsets
like PostgreSQL. Avoid mutable JSON defaults. Prefer a portable string/check-based
enum policy unless a later decision justifies native enums. Future financial values
need explicit decimal precision/scale, never float coercion. None of these future
domain models or custom financial types is implemented here.

## Tests, dependencies and Docker

The complete suite has **48 passing tests**, including all 32 prior backend tests.
Autouse test setup clears inherited TWF configuration, changes to a temporary
working directory to avoid developer dotenv, and supplies an isolated database.
The backend shell fixture uses isolated memory SQLite. Tests cover URL validation,
lazy startup and disposal, cross-thread sequential memory access, independent
sessions, explicit commit, normal-exit rollback, failure rollback, permanent close,
foreign-key/unique failures, FastAPI cleanup and safe database error responses,
probe failures, unchanged readiness, deterministic migration lifecycle, canonical
metadata, and offline PostgreSQL SQL generation.

Exactly one driver was added: `psycopg[binary]>=3.3,<4`, resolved to `psycopg` and
its binary distribution at **3.3.6** in both lockfiles. The binary extra packages
libpq for the existing slim container without another OS build toolchain. Existing
pinned versions were preserved. No second ORM, async stack or pooling framework.
Driver packaging follows the [official Psycopg installation guide](https://www.psycopg.org/psycopg3/docs/basic/install.html).
SQLite transaction handling follows [SQLAlchemy's dialect guidance](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html).

Compose now permits `TWF_DATABASE_URL` environment override while retaining the
writable `/app/twf.db` development default. SQLite data in the default container is
ephemeral; durable local use needs an appropriately writable mounted location.
The existing Dockerfile already includes Alembic and runs as a non-root user.
No credentials are baked into the image. Example explicit container migration:

```bash
docker compose run --rm api alembic upgrade head
# For an already running local SQLite container (same filesystem):
docker compose exec api alembic upgrade head
```

One-off SQLite containers do not share their writable filesystem with an existing
API container; use an explicit volume or `exec` when that persistence is intended.
Production uses the externally injected PostgreSQL URL for the separate release
migration command and the API.

Validation on 2026-09-24:

| Check | Result |
|---|---|
| `pytest -q` | 48 passed |
| `ruff check .`; `ruff format --check .` | Pass |
| Strict `mypy` | Pass, 24 source files |
| `python -m compileall -q src tests alembic` | Pass |
| `python -m pip check` | No broken requirements |
| `pip-audit -r requirements.lock --no-deps --disable-pip` | No known vulnerabilities |
| SQLite migrations, repeat/check, downgrade/re-upgrade | Pass, disposable test databases |
| PostgreSQL 16 runtime migrations and transaction smoke | Pass |
| Docker Compose configuration | Pass |
| Clean `docker build --no-cache -f deploy/Dockerfile.api -t twf-api:twf1-3-review .` | Pass |
| Container health/ready/status and non-root writable SQLite | Pass |
| Explicit in-container Alembic upgrade/repeat/check/downgrade/re-upgrade | Pass |
| Documentation links, secret-pattern review, `git diff --check` | Pass |

The existing Starlette/httpx TestClient deprecation notice remains. pip-audit also
recommends hashed locks; current repository locks pin versions without hashes.
Frontend tests were not run because frontend/shared runtime files did not change.
Disposable smoke containers were removed; local build images/caches remain.

## Exact changed files

- `apps/api/.env.example`
- `apps/api/alembic/versions/README.md`
- `apps/api/alembic/versions/0001_empty_baseline.py`
- `apps/api/pyproject.toml`
- `apps/api/requirements.lock`
- `apps/api/requirements-dev.lock`
- `apps/api/src/twf/config/settings.py`
- `apps/api/src/twf/infrastructure/database.py`
- `apps/api/src/twf/api/dependencies.py`
- `apps/api/src/twf/main.py`
- `apps/api/tests/conftest.py`
- `apps/api/tests/test_backend_shell.py`
- `apps/api/tests/test_database_foundation.py`
- `compose.yaml`
- `README.md`
- `docs/TWF_DOCUMENTATION_INDEX.md`
- `docs/TWF_TWF1_3_DATABASE_FOUNDATION.md`

## Non-goals

No production business tables, users/accounts, authentication/authorization,
workspaces/watchlists, scanner/TI/TM/LLM/broker integrations or persistence,
orders/positions/trades, alerts/history, subscriptions/billing, domain repositories,
Redis/caching, background jobs, realtime, CQRS/event sourcing, analytics warehouse,
Kubernetes, cloud-specific infrastructure, or frontend changes. Existing satellite
ownership and public shell response contracts are preserved.
