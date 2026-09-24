# TWF-1.2 — Backend Shell

Status: **implemented, pending independent review**. Recommendation: `GO_TWF1_2_REVIEW`.
Next target after review: **TWF-1.3 Database Foundation**.

## Baseline and scope

Preflight on resumed work verified clean `main`, equal to `origin/main` at
`74d190e8ed9e5cf22b4c98ee81213a475252e239`. Accepted tags resolve to:

- `twf-1.1-frontend-shell`: `bc7847982162e7c75aea7c39049e19f80c546a17`.
- `twf-1.1a-theme-switching`: `74d190e8ed9e5cf22b4c98ee81213a475252e239`.

The earlier generated frontend-file change was already cleared before this resumed
implementation; no frontend file was restored or modified here. No commit, tag,
or push was performed. The accepted architecture and prior implementation records
remain historical. README/index now identify the accepted theme baseline and the
current backend target without collapsing earlier sub-targets.

TWF is the frontend-facing orchestration gateway. TI owns intelligence, TM owns
authority/risk, and satellite implementations remain outside TWF. This target
establishes transport and cross-cutting foundations only, under the
[service contract architecture](TWF_SERVICE_CONTRACT_ARCHITECTURE.md),
[integration architecture](TWF_SERVICE_INTEGRATION_ARCHITECTURE.md),
[security architecture](TWF_SECURITY_AUTH_ARCHITECTURE.md), and
[deployment architecture](TWF_DEPLOYMENT_ARCHITECTURE.md).

## Application structure and dependency seams

The existing `apps/api/src/twf` package and `create_app(settings=None)` factory
remain. Settings are validated before app construction; a caller can inject an
immutable Settings instance. Each app owns its settings, lifecycle flag, and logger.
No environment, logger-handler, database, or network setup runs at module import.

- `main.py`: factory, metadata, lifespan, middleware/handler registration.
- `api/routes.py`: process probes and a separate router mounted at `/api/v1`.
- `api/dependencies.py`: overridable settings dependency and request-ID accessor.
- `schemas.py`: public Pydantic response contracts.
- `api/errors.py`: safe common error responses.
- `middleware.py`: pure ASGI request context/completion logging and error boundary.
- `observability.py`: per-app JSON logger and task-local correlation context.
- `config/settings.py`: extended existing environment settings.

No fake service registry, adapter interfaces, or future domain routes were added.

## Endpoints and response contracts

| Endpoint | Contract | Meaning |
|---|---|---|
| `GET /health` | `HealthResponse`, 200 | `{"status":"ok"}`; process can answer HTTP |
| `GET /ready` | `ReadinessResponse`, 200/503 | Lifespan initialization completed / not completed |
| `GET /api/v1/status` | `StatusResponse`, 200 | `service`, `version`, `environment`, `api_version`, `status` |
| `GET /api/v1/meta` | `MetadataResponse`, 200 | `service_name`, `service_version`, `api_version`, `environment` |

Status preserves the scaffold's existing `service` and `version` field names;
`api_version` is additive. Metadata separates service identity from API version.
Build/commit metadata is omitted because it is unavailable; runtime Git is not used.

Readiness explicitly returns `checks: "application_initialization_only"`,
`satellite_dependencies_checked: false`, and `database_checked: false`. Its status
is `ready` after startup, otherwise `not_ready` with HTTP 503. It never claims that
TI, TM, Scanner, LLM, Broker, or persistence is available. Shutdown clears the flag.

OpenAPI has a central title, description, and configured service version. `/docs`,
`/redoc`, and `/openapi.json` remain enabled in every environment pending a later
production exposure decision. Shell response models and common 404/405/422/500
error schemas are declared; readiness also declares its 503 response. No API v2.

## Errors, correlation, and middleware order

Application errors have this typed structure:

```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "Internal server error",
    "request_id": "bounded-identifier",
    "details": null
  }
}
```

HTTP exceptions preserve their status, use `HTTP_<status>` and a standard HTTP
phrase, and retain protocol headers Allow, Retry-After, and WWW-Authenticate.
Arbitrary exception detail is never echoed. Request validation returns 422 with
`INVALID_REQUEST`; Pydantic raw input, field context, and exception text are omitted.
Unexpected exceptions return 500 with `INTERNAL_ERROR` and are logged by class
name only. `details` is deliberately null in this shell; later typed domain errors
can extend it under their own contracts. No response includes a traceback or secret.

`X-Request-ID` accepts one header, trims outer whitespace, and requires
`[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. Absent, duplicate, invalid, or oversized values
are replaced with a UUID4 hex identifier. The value is correlation metadata, not
identity, trust, or authorization. Callers must not place secrets in identifiers.
The effective ID is returned in the response, available through request state and
`get_request_id`, and held in a ContextVar for logging. Tokens are reset in finally;
concurrent-request isolation is tested.

Inbound application middleware order:

```text
Starlette ServerErrorMiddleware (framework outer fallback)
  → RequestContextMiddleware (assign ID; wrap response; log completion)
  → CORSMiddleware
  → ErrorBoundaryMiddleware (unexpected application exceptions)
  → Starlette ExceptionMiddleware (HTTP/validation handlers)
  → routing / dependencies / endpoint
```

The inner error boundary converts application failures before the framework's
outer fallback can bypass CORS and request-ID response handling. Tests prove
headers survive ordinary, handled-error, and unexpected-error responses, and that
preflight requests also receive IDs. Starlette's CORS preflight responses remain
its native protocol responses (200 or plain-text 400), not application envelopes.
Probe readiness failures retain the typed readiness contract.

After HTTP response start, an exception cannot replace the response; it propagates.
No streaming/background response work exists in this shell. Future streaming
targets must define their own mid-stream failure behavior. Lifespan exceptions
also propagate rather than being mislabeled as request errors.

## Logging and security baseline

Standard-library logging emits JSON to stdout with UTC timestamp, level, service,
environment, event, and request ID. Lifecycle events are `application_started`
and `application_stopped`; request events include `request_completed` and
`request_failed`. Completion includes method, route template (or `unmatched`),
status, and duration in milliseconds. Failures include exception class, not its
message, locals, or stack text.

An explicit formatter allowlist excludes arbitrary record extras. Current logging
calls contain static event names; no body, raw URL, query, arbitrary header,
credential, or settings dump is logged. The logger is app-owned, so constructing
multiple apps neither stacks global handlers nor changes another app's level.
INFO lifecycle/completion events are intentionally filtered when a higher level
is configured; failure events are ERROR.

Use `--no-access-log` for Uvicorn to avoid duplicate raw path/query logs. The API
Docker command and README native commands now include it. Existing Uvicorn server
startup messages are still server-owned text, while TWF application logs are JSON.
Other hosting servers/proxies must configure their own access-log redaction.

This is not authentication or production hardening. No auth, users, sessions,
authorization, rate limiting, broker credentials, or provider keys are introduced.
Safe messages and debug-disabled behavior apply in all environments.

## Configuration and CORS

Existing Pydantic settings keep the `TWF_` prefix, optional local `.env`,
environment-over-dotenv precedence, and immutable settings. Do not deploy dotenv
files as secrets in the image; the existing Docker exclusions remain.

| Variable | Default / policy |
|---|---|
| `TWF_ENVIRONMENT` | `development`; accepts development, test, production |
| `TWF_SERVICE_NAME` | `twf-api`; bounded safe identifier |
| `TWF_SERVICE_VERSION` | Installed package version (`0.1.0`); bounded version text |
| `TWF_API_VERSION` | `v1`; other versions rejected for this target |
| `TWF_API_PREFIX` | `/api/v1`; other namespaces rejected for this target |
| `TWF_LOG_LEVEL` | DEBUG in development, INFO in test/production; explicit uppercase override |
| `TWF_CORS_ORIGINS` | JSON array; development defaults to `http://localhost:3000`; test/production empty |
| `TWF_DATABASE_URL` | Existing scaffold setting, repr-hidden; unused by this shell |

Explicit `[]` disables allowed origins even in development. CORS rejects wildcard,
non-HTTP(S), credential-bearing, path/query/fragment-bearing, and malformed-port
origins. Credentials are always disabled; GET is the only allowed cross-origin
method. Content-Type and X-Request-ID are permitted headers; X-Request-ID is
exposed to browsers. CORS is browser transport policy, not authentication.
For cloud deployment configure explicit HTTPS frontend origins.

No dependency or lockfile change was needed. Database/Alembic code and the
accepted frontend remain untouched.

## Tests and validation

Validation on 2026-09-24:

| Check | Result |
|---|---|
| `.venv/bin/pytest -q` | 32 passed, including existing empty database/migration tests |
| `.venv/bin/ruff check .` | Pass |
| `.venv/bin/ruff format --check .` | Pass, 22 files |
| `.venv/bin/mypy` | Pass, 21 source files |
| Python compilation | Pass |
| `.venv/bin/python -m pip check` | No broken requirements |
| FastAPI/OpenAPI construction | Pass, four typed shell endpoints and error schemas |
| `docker compose config --quiet` | Pass |
| Clean API Docker build (`--no-cache`) | Pass, `twf-api:twf1-2-review` |
| Production container endpoint smoke | 200 on health, ready, status, meta, OpenAPI |
| Container error/CORS/request-ID smoke | Safe 404 envelope, matching IDs, configured origin header |
| Container log inspection | JSON completion records, no probe query-string leakage |
| `git diff --check`, local documentation links, secret-pattern review | Pass |

New tests exercise lifecycle/readiness, exact contracts, injected settings,
environment configuration, invalid CORS origins, generated/normalized/duplicate
IDs, HTTP/validation/unexpected errors, protocol headers, preflight acceptance and
rejection, CORS on errors, 20 concurrent requests and context reset, safe structured
logs, log-level selection, and OpenAPI. Unsafe exercise routes exist only in test
apps. Tests isolate configuration from developer dotenv and inherited settings.

The existing Starlette/httpx TestClient deprecation warning remains non-blocking;
dependencies were not changed to silence it. No frontend validation was necessary
because no frontend or shared runtime configuration changed. No fresh vulnerability
audit was run; dependency versions are unchanged from the accepted baseline.

Reproduce from `apps/api` with the commands above. Native run:

```bash
.venv/bin/uvicorn twf.main:create_app --factory --reload --no-access-log
```

Container smoke used a temporary non-root production-mode container bound to
`127.0.0.1:38000`, with a configured HTTPS CORS origin. It was stopped and removed
after smoke tests; existing user services were not touched. Compose's existing
healthcheck remains a liveness probe; deployment readiness can use `/ready`.
Runtime host/port can be overridden by the container command/Uvicorn CLI; no app
logic embeds a bind address, TLS endpoint, Git dependency, or runtime state path.
Reverse-proxy HTTPS, remote endpoints, and later PostgreSQL remain deployment
choices without changes to shell semantics.

## Exact changed files

- `apps/api/.env.example`
- `apps/api/src/twf/main.py`
- `apps/api/src/twf/config/settings.py`
- `apps/api/src/twf/api/routes.py`
- `apps/api/src/twf/api/dependencies.py`
- `apps/api/src/twf/api/errors.py`
- `apps/api/src/twf/schemas.py`
- `apps/api/src/twf/middleware.py`
- `apps/api/src/twf/observability.py`
- `apps/api/tests/test_foundation.py`
- `apps/api/tests/test_backend_shell.py`
- `deploy/Dockerfile.api`
- `README.md`
- `docs/TWF_DOCUMENTATION_INDEX.md`
- `docs/TWF_TWF1_2_BACKEND_SHELL.md`

## Non-goals

No trading workflows, scanner/TI/TM/LLM/broker integrations or health checks,
database business models/repositories, authentication, user profiles, orders,
positions, realtime/WebSocket/SSE, workers, queues, Redis, billing, subscriptions,
Kubernetes, cloud-provider infrastructure, or frontend redesign. TWF does not
acquire satellite authority. Stop at independent TWF-1.2 review before TWF-1.3.
