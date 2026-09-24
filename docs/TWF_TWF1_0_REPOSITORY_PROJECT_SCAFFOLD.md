# TradingWorkFlow — TWF-1.0 Repository / Project Scaffold

## Scope and authority

Bounded implementation record for TWF-1.0, under the accepted TWF-0 baseline.
TWF-1 remains IN_PROGRESS. This target establishes runnable shells, tooling, and
boundaries; it does not close the later TWF-1 targets.

## Git preflight

- Started on `main` with a clean working tree.
- `main` and `origin/main`: `86d4dda54699c5db7bee883ed1b439b23ec17d93`.
- Remote `main` independently confirmed with `git ls-remote`.
- Local and remote `twf-0-architecture-baseline` tag ref:
  `ec93331ee2fb50d3338a97d3bafa7b12c8e25cab`.
- README, engineering standards, technology decision, roadmap, acceptance review,
  documentation index, and deployment architecture reviewed before implementation.
- No AGENTS.md instructions found. No commit, tag, or push performed.

## Repository structure and exact changed-file inventory

Existing architecture files remain unchanged except the README and documentation
index status/navigation updates. Every file below is new unless marked modified.
Existing contents of `docs/` are retained and omitted from this scaffold inventory.

```text
TradingWorkFlow/
├── .dockerignore
├── .editorconfig
├── .gitignore
├── README.md                                      (modified)
├── compose.yaml
├── apps/
│   ├── api/
│   │   ├── .env.example
│   │   ├── pyproject.toml
│   │   ├── requirements.lock
│   │   ├── requirements-dev.lock
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   │   ├── env.py
│   │   │   ├── script.py.mako
│   │   │   └── versions/README.md
│   │   ├── src/twf/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── api/{__init__.py,routes.py}
│   │   │   ├── config/{__init__.py,settings.py}
│   │   │   ├── infrastructure/{__init__.py,database.py}
│   │   │   └── integrations/
│   │   │       ├── __init__.py
│   │   │       ├── scanner/__init__.py
│   │   │       ├── ti/__init__.py
│   │   │       ├── tm/__init__.py
│   │   │       └── llm/__init__.py
│   │   └── tests/test_foundation.py
│   └── web/
│       ├── .npmrc
│       ├── .prettierignore
│       ├── .prettierrc.json
│       ├── package.json
│       ├── package-lock.json
│       ├── tsconfig.json
│       ├── next-env.d.ts
│       ├── next.config.ts
│       ├── eslint.config.mjs
│       ├── vitest.config.ts
│       ├── src/app/{layout.tsx,page.tsx,globals.css}
│       └── tests/{setup.ts,page.test.tsx}
├── deploy/
│   ├── Dockerfile.api
│   └── Dockerfile.web
└── docs/
    ├── TWF_DOCUMENTATION_INDEX.md                  (modified)
    └── TWF_TWF1_0_REPOSITORY_PROJECT_SCAFFOLD.md
```

Brace notation lists separate files, not placeholder directories. `deploy/`
follows the engineering standard. Shared contracts, application/domain packages,
frontend feature/component folders, root tests, and scripts are deferred until
there is code to own. The four explicitly requested integration packages contain
only boundary docstrings. No satellite source is copied into TWF.

## Implementation and tooling

Frontend: Next.js App Router, React, strict TypeScript, metadata/root layout,
responsive light/dark CSS, and a single static foundation page. No remote fonts,
sample assets, charting, component system, authentication, or API fetching.
ESLint uses Next.js flat configurations and Prettier compatibility. Vitest and
React Testing Library verify the root page's accessible headings/status region.
Playwright browser E2E is deferred to later shell/workflow work.

Backend: Python 3.12+, FastAPI application factory with explicitly injected,
immutable Pydantic settings. `GET /health` returns `{"status":"ok"}`.
`GET /api/v1/status` returns `service`, package `version`, `environment`, and
`status`. Responses have Pydantic schemas in OpenAPI. Health is process liveness,
not a claim about database/satellite readiness. API startup performs no database
or external-service operations. Structured request/workflow logging is TWF-1.2.

Persistence: SQLAlchemy 2.x empty declarative metadata, engine factory, session
factory, and Alembic online/offline environments and revision template. Callers
own session transactions and engine disposal. No `create_all`, model, repository
protocol, application table, or business revision exists. The migration smoke
test permits only Alembic's own version table. The first business schema and
portable repository behavior belong to TWF-1.3.

Dependencies: npm lockfile and pip-compile runtime/development lockfiles pin the
resolved environment. Python development locks constrain runtime versions to
`requirements.lock`. Generated lockfiles and Next.js's type reference file are
intentional source-controlled artifacts; environments, caches, build output,
database files, and local dotenv files are ignored. Build tooling is not a
production dependency.

Docker: non-root API and standalone Next.js runtime images; Compose binds ports
to loopback, sets API development mode, and probes API liveness. The web image
uses a production build for a repeatable local smoke baseline. Native commands
provide hot reload. No persistent DB volume is needed while the API performs no
database work; add persistence with TWF-1.3 before storing real state. Containers
are a local foundation, not a hardened production deployment.

## Configuration

Run API commands from `apps/api`. Optional `.env` is loaded from that directory;
environment variables take precedence. `cp .env.example .env` is optional.

| Variable | Default | Meaning |
|---|---|---|
| `TWF_ENVIRONMENT` | `development` | Validated `development`, `test`, or `production` |
| `TWF_DATABASE_URL` | `sqlite+pysqlite:///./twf.db` | SQLAlchemy URL; relative to API working directory |

Tests inject test settings and use memory/temporary databases. Production mode is
a validated environment label, not an authentication or production-readiness
switch. The database URL is excluded from settings repr and API responses.
Future secrets remain server-side; no secrets are supplied here. Frontend runtime
mode uses Next.js's standard `NODE_ENV`; no custom browser environment is needed.

## Developer commands

Backend, from the repository root:

```bash
cd apps/api
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/uvicorn twf.main:create_app --factory --reload
```

Backend checks, from `apps/api`:

```bash
.venv/bin/python -m compileall -q src tests alembic
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/python -m pip check
.venv/bin/alembic heads
.venv/bin/alembic upgrade head
.venv/bin/alembic check
```

`alembic heads` is intentionally empty. Migration commands may create the ignored
local SQLite file. Tests instead run upgrade/check/downgrade on a temporary file.
To regenerate dependency locks intentionally (Python 3.12, from `apps/api`):

```bash
.venv/bin/python -m pip install pip-tools==7.6.1
.venv/bin/pip-compile --strip-extras --no-emit-index-url --output-file=requirements.lock pyproject.toml
.venv/bin/pip-compile --extra=dev --strip-extras --no-emit-index-url --constraint=requirements.lock --output-file=requirements-dev.lock pyproject.toml
```

Frontend, from repository root (Node.js 20.19+ / 22.13+ / 24+; Docker uses Node.js 22):

```bash
cd apps/web
npm ci
npm run dev
```

Frontend checks and production start, from `apps/web`:

```bash
npm run type-check
npm run lint
npm test
npm run format:check
npm run build
npm start
```

Containers and repository checks, from repository root:

```bash
docker compose config --quiet
docker compose up --build
# In a second terminal:
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/api/v1/status
curl --fail http://localhost:3000/
docker compose down
git diff --check
```

## Validation evidence

Validated on 2026-09-24 with Python 3.12.3, Node.js 20.20.2, npm 10.8.2,
and Docker 29.8.1. All acceptance checks passed.

| Check | Exact command / probe | Result |
|---|---|---|
| Python compilation | `.venv/bin/python -m compileall -q src tests alembic` | PASS |
| Backend behavior | `.venv/bin/pytest` | PASS, 8 tests |
| Python lint | `.venv/bin/ruff check .` | PASS |
| Python formatting | `.venv/bin/ruff format --check .` | PASS, 16 files |
| Python types | `.venv/bin/mypy` | PASS, 15 source files |
| Python dependencies | `.venv/bin/python -m pip check` | PASS |
| API packaging | `.venv/bin/python -m pip wheel --no-deps --wheel-dir /tmp/twf-scaffold-wheels .` | PASS |
| Migration lifecycle | pytest temporary SQLite upgrade head / check / downgrade base | PASS, no business tables |
| Clean web install | `npm ci --no-audit --no-fund` | PASS, 447 packages; complete lockfile |
| Frontend types | `npm run type-check` | PASS |
| Frontend lint | `npm run lint` | PASS, zero lint warnings |
| Page rendering | `npm test` | PASS, 1 component test |
| Production web build | `npm run build` | PASS, root page statically prerendered |
| Web formatting | `npm run format:check` | PASS |
| Web dependency scan | `npm audit --audit-level=low` | PASS, zero reported vulnerabilities |
| API runtime dependency scan | `apps/api/.venv/bin/pip-audit -r apps/api/requirements.lock --no-deps --disable-pip` (root) | PASS, no known vulnerabilities |
| Compose syntax | `docker compose config --quiet` | PASS |
| Container builds | `docker compose build api`; `docker compose build web` | PASS |
| Container startup | `docker compose up -d --wait --no-build` | PASS |
| HTTP container smoke | `/`, `/health`, `/api/v1/status` | HTTP 200; expected page text and JSON verified |
| Documentation links | Local Markdown links in all 3 updated/new documentation files | PASS |
| Repository hygiene | Git-visible file inventory, generated-file exclusions, obvious credential patterns | PASS |
| Whitespace | `git diff --check` plus new-file whitespace inspection | PASS |

The 8 backend tests cover both routes/imports, each of the 3 supported environment
values, rejection of an invalid environment, app-instance setting isolation,
session/engine behavior with empty metadata, and the empty migration lifecycle.
The web component test verifies page headings and the named status region.
HTTP smoke checks exercised the built non-root container runtimes. Test containers
were stopped and removed after validation; downloaded dependencies/build caches
remain locally ignored.

Non-blocking tool notices: Starlette warns that its `httpx` TestClient compatibility
path is deprecated; the tests pass. ESLint 9.39.5 is deprecated upstream but is
retained because the Next.js React/accessibility plugins currently declare support
through ESLint 9; ESLint 10 would violate their peer dependencies. jsdom's transitive
`whatwg-encoding` dependency also emits a deprecation notice. Reassess these with
future dependency refreshes. pip-audit recommends hashed lockfiles; these files
pin versions without hashes. The API audit covers runtime dependencies; it is not
a full production security review.

Initial npm installation stalled and left an incomplete transitive type entry.
The final lockfile was regenerated from the manifest in an empty temporary
directory, and both clean native installation and Docker builds passed without
the damaged-lockfile warning. The sandbox failed to initialize, so shell work
used approved escalation; this did not require changes to repository settings.

## Non-goals and next target

No login, users, business models, settings persistence, service clients, synthetic
or live adapters, broker access, LLM SDKs, websocket/SSE infrastructure, trader
workspace, charts, UI library, billing, Redis, PostgreSQL service, reverse proxy,
ingress, or Kubernetes. Existing accepted architecture is preserved.

Next target: **TWF-1.1 Frontend Shell** — bounded layout/navigation and
loading/error states under the accepted UX architecture. Full backend logging,
database models/migrations, authentication, settings, and service-client
foundations retain their later target gates.

## Reference checks

Current framework conventions checked against the official
[Next.js installation guide](https://nextjs.org/docs/app/getting-started/installation),
[Next.js ESLint guide](https://nextjs.org/docs/app/api-reference/config/eslint), and
[Pydantic settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

## Final status

```text
TWF1_0_REPOSITORY_STRUCTURE_IMPLEMENTED = YES
TWF1_0_FRONTEND_SHELL_IMPLEMENTED = YES
TWF1_0_BACKEND_SHELL_IMPLEMENTED = YES
TWF1_0_CONFIG_FOUNDATION_IMPLEMENTED = YES
TWF1_0_DB_SCAFFOLD_IMPLEMENTED = YES
TWF1_0_QUALITY_TOOLING_IMPLEMENTED = YES
TWF1_0_DOCUMENTATION_UPDATED = YES
READY_FOR_TWF1_1 = YES
```

Recommendation: **GO_TWF1_1**.
