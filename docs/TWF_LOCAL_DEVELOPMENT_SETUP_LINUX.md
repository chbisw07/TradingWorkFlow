# TradingWorkFlow — Ubuntu/Linux Local Development Setup

## 1. Purpose

This guide covers local development setup for TradingWorkFlow (TWF) on
Ubuntu/Linux. It documents the current TWF-1 application scaffold: a Next.js web
app, a FastAPI backend, an empty SQLAlchemy/Alembic persistence foundation, and a
Docker Compose smoke environment.

Run commands from the repository root unless a section changes directories.

## 2. Supported and verified environment

Repository-defined requirements:

| Tool           | Project requirement                                              |
| -------------- | ---------------------------------------------------------------- |
| Python         | 3.12 or later                                                    |
| Node.js        | `^20.19.0`, `^22.13.0`, or 24 and later                          |
| npm            | Required; no separate minimum is declared                        |
| Docker         | Required only for the container workflow; no minimum is declared |
| Docker Compose | Compose v2 CLI syntax: `docker compose`                          |
| Git            | Required; no minimum is declared                                 |

The following versions form an example workstation on which the complete
TWF-1.0 validation passed. They are verified examples, not additional minimums:

```text
Python 3.12.3
Node.js 20.20.2
npm 10.8.2
Docker 29.8.1
Docker Compose 5.5.1
Git 2.43.0
```

## 3. Verify prerequisites

```bash
python3 --version
node --version
npm --version
docker --version
docker compose version
git --version
```

Python and Node.js are required for native development. Docker and Docker Compose
are optional when only native servers are used. If a command is missing, install
the tool using your organization's standard Ubuntu package or version-management
process, then rerun these checks. Confirm that Python and Node.js satisfy the
repository requirements above.

## 4. Clone and inspect the repository

The configured upstream uses GitHub SSH:

```bash
git clone git@github.com:chbisw07/TradingWorkFlow.git
cd TradingWorkFlow
git status
git pull
```

The SSH clone command requires a GitHub account with access to the repository and
an SSH key configured for that account. A clean checkout on `main` should report
no modified or untracked files.

## 5. Backend setup

The recommended setup installs the committed development lockfile, then installs
the local API package in editable mode without resolving dependencies a second
time:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
```

Run backend commands from `apps/api` with this virtual environment active. The
editable install makes `twf` importable while source edits take effect without a
reinstall.

## 6. Backend validation

From `apps/api`, with `.venv` active:

```bash
python -m compileall -q src tests alembic
pytest
ruff check .
ruff format --check .
mypy
python -m pip check
alembic heads
alembic check
```

`alembic heads` is intentionally empty because the scaffold has no business
schema. `alembic check` may create the ignored development SQLite file when it
connects to the default database URL.

## 7. Run the backend

From `apps/api`, with `.venv` active:

```bash
uvicorn twf.main:create_app --factory --reload
```

The `--factory` flag is required because `twf.main` exports `create_app`, not a
module-level FastAPI application. The development server uses port 8000:

- Health: <http://localhost:8000/health>
- Status: <http://localhost:8000/api/v1/status>
- OpenAPI UI: <http://localhost:8000/docs>

Stop the server with `Ctrl+C`.

## 8. Frontend setup

In a separate terminal from the repository root:

```bash
cd apps/web
npm ci
```

Use `npm ci` for normal setup because it installs exactly from the committed
`package-lock.json`, removes a stale dependency tree before installation, and
fails when the manifest and lockfile disagree. Use `npm install` only while
intentionally changing dependencies and the lockfile.

## 9. Frontend validation

From `apps/web`:

```bash
npm run type-check
npm run lint
npm test
npm run format:check
npm run build
```

These commands generate ignored `.next` and TypeScript cache output. Next.js also
maintains the tracked `next-env.d.ts`; run the full sequence through `npm run
build`, then inspect `git status` rather than committing an incidental generated
path change.

## 10. Run the frontend

From `apps/web`:

```bash
npm run dev
```

Open <http://localhost:3000>. Stop the server with `Ctrl+C`.

For a local production-build check after `npm run build`, use `npm start`.

## 11. Run frontend and backend together

After one-time setup, use two terminals opened at the repository root.

Terminal 1 — backend/API:

```bash
cd apps/api
source .venv/bin/activate
uvicorn twf.main:create_app --factory --reload
```

Terminal 2 — frontend/web:

```bash
cd apps/web
npm run dev
```

The current scaffold does not yet fetch API data from the web page. Running both
servers proves the local application boundaries and prepares the normal workflow
for later TWF-1 targets.

## 12. Docker workflow

From the repository root:

```bash
docker compose config --quiet
docker compose up --build
```

Verify the running environment in a second terminal:

```bash
curl --fail http://localhost:3000/
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/api/v1/status
```

The Compose ports are bound to loopback at `127.0.0.1:3000` and
`127.0.0.1:8000`. Stop and remove the containers and project network with:

```bash
docker compose down
```

Use the native development servers for fast edit-refresh work. Use Docker for a
repeatable environment-parity or integration smoke check. A Docker rebuild is not
required for every small source or documentation edit.

## 13. Environment files

The backend has an optional example file. From `apps/api`:

```bash
cp .env.example .env
```

The committed defaults are:

```text
TWF_ENVIRONMENT=development
TWF_DATABASE_URL=sqlite+pysqlite:///./twf.db
```

Environment variables override values loaded from `apps/api/.env`. The current
frontend has no application-specific environment file. Never commit `.env` files
or secrets; the root `.gitignore` excludes local dotenv files while allowing
`.env.example` documentation.

## 14. VS Code workflow

Open the repository root in VS Code so both applications and the shared
documentation remain visible. Select this backend interpreter after setup:

```text
apps/api/.venv/bin/python
```

Useful optional extensions are Python, Pylance, Ruff, ESLint, Prettier, and
Docker. Match formatter and lint behavior to the repository commands rather than
relying only on editor diagnostics. Keep frontend and backend development servers
in separate integrated terminals.

## 15. Git hygiene

Check repository state before and after work:

```bash
git status
```

The root `.gitignore` covers local artifacts including:

```text
.venv/
node_modules/
.next/
.env and .env.* (except .env.example)
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
build/
dist/
coverage/
*.tsbuildinfo
*.db and *.sqlite*
```

Do not force-add these files. Investigate any unexpected Git-visible generated
file before committing.

## 16. Recommended daily startup

Terminal 1 — backend/API:

```bash
cd apps/api
source .venv/bin/activate
uvicorn twf.main:create_app --factory --reload
```

Terminal 2 — frontend/web:

```bash
cd apps/web
npm run dev
```

Then open <http://localhost:3000> and use the API health/status URLs when checking
the backend.

## 17. Recommended daily shutdown

1. Stop each native development server with `Ctrl+C`.
2. In the backend terminal, leave the virtual environment and inspect Git state:

   ```bash
   deactivate
   cd ../..
   git status
   ```

3. If Docker was used, run this from the repository root:

   ```bash
   docker compose down
   git status
   ```

## 18. Fresh validation before a commit

Run the following practical sequence. A Docker rebuild is appropriate when
container or dependency behavior changed, but is optional for ordinary small
frontend or documentation changes.

Backend, from `apps/api` with `.venv` active:

```bash
python -m compileall -q src tests alembic
pytest
ruff check .
ruff format --check .
mypy
python -m pip check
alembic check
```

Frontend, from `apps/web`:

```bash
npm run type-check
npm run lint
npm test
npm run format:check
npm run build
```

Repository hygiene, from the repository root:

```bash
git diff --check
git status
```

Review every changed file before committing.

## 19. Troubleshooting

### Optional Sharp/WASM packages reported as extraneous

A fresh `npm ci` currently installs `@img/sharp-wasm32` and `@emnapi/runtime`,
while `npm ls --all` may label them extraneous. This is a known, non-blocking
lockfile-hygiene notice: type checks, tests, builds, Docker builds, and dependency
audits pass. Do not edit `package-lock.json` manually; resolve it during a bounded
dependency-maintenance change.

### Backend TestClient deprecation notice

Backend tests may emit a Starlette notice that its current `httpx` TestClient path
is deprecated. The tests pass. Treat the notice as non-blocking until the
compatible test-client migration is taken as a dependency-maintenance change.

### Frontend dependency deprecation notices

Installation may report that ESLint 9.39.5 or jsdom's transitive
`whatwg-encoding` package is deprecated. ESLint 9 is retained because the current
Next.js React/accessibility lint plugins declare support through ESLint 9. These
notices are non-blocking and should be revisited through a compatible dependency
refresh.

### Next.js updates `next-env.d.ts`

`next typegen` and Next.js development/build modes may switch generated imports
in the tracked `next-env.d.ts` between `.next/dev/types` and `.next/types`. Run
the complete validation sequence through `npm run build` before the final
`git status`. Do not hand-edit or commit an unexplained generated path change.

### Port already in use

Check which process or container owns the local ports:

```bash
ss -ltnp | grep -E ':3000|:8000'
docker compose ps
```

Stop the previous development process with `Ctrl+C`, or run
`docker compose down` if the Compose environment owns the ports.

### Virtual environment is not active

If `uvicorn`, `pytest`, `ruff`, or `mypy` is unavailable, return to `apps/api` and
activate the environment:

```bash
source .venv/bin/activate
```

If `.venv` does not exist, repeat the backend setup steps.

### Stale frontend dependencies

From `apps/web`, restore the committed dependency tree with:

```bash
npm ci
```

### Docker containers are still running

From the repository root:

```bash
docker compose ps
docker compose down
```

### Missing backend `.env`

The `.env` file is optional because typed development defaults exist. If local
overrides are expected, create it from the example while in `apps/api`:

```bash
cp .env.example .env
```

## 20. Security notes

- Do not place production secrets in this guide, committed files, or shell
  history.
- Never commit `.env` or credentials.
- The current scaffold requires no broker credentials or LLM provider keys.
- Keep local development services loopback-bound where the supplied Compose file
  does so.
- Treat future service credentials as server-side configuration; never expose
  them to frontend bundles.

## 21. Current limitations

The current scaffold does not yet include:

- real login;
- scanner integration;
- TradingIntelligence integration;
- TradeMonitor integration;
- an LLM provider integration;
- broker integration; or
- production PostgreSQL deployment.

These capabilities remain assigned to later gated targets.
