# TWF-1.4 — User / Login Foundation

Status: **implemented / fixes applied / pending re-review**. Recommendation: `GO_TWF1_4_REREVIEW`.
Next target after acceptance: **TWF-1.5 Settings Foundation**.

## Accepted baseline and scope

Preflight verified clean `main`, equal to `origin/main` at
`dd0610c18e05ab97ff80ed9aac705d6d5b46ffb8` (TWF-1.3 implementation), with the
accepted TWF-0 architecture tag present. The independent TWF-1.3 review concluded
`ACCEPT_TWF1_3`. Earlier implementation records remain historical; README/index
now identify the current identity target while retaining TWF-1.1A and all prior
milestones. No commit, tag or push was performed.

This implements the bounded first-party authentication option permitted by the
[security architecture](TWF_SECURITY_AUTH_ARCHITECTURE.md),
[data architecture](TWF_DATA_ARCHITECTURE.md), and
[implementation sequence](TWF_DETAILED_ROADMAP.md).

**TWF login is application identity. It grants no broker login, trading permission,
TM authority, risk approval, execution authority, or subscription entitlement.**

## User and credential model

`twf.infrastructure.identity.User` registers with the existing canonical
`twf.infrastructure.database.Base`. Fields: application-generated UUID, unique
normalized username, display name, Argon2id password hash, active flag, and UTC
creation/update timestamps. Identity is suitable for associating future data with
`current_user.id`; no ownership tables or workflows are added yet.

Usernames contain 3–64 ASCII letters/numbers/dot/underscore/hyphen, start with an
alphanumeric character, and normalize by stripping surrounding whitespace and
lowercasing. Email identity/verification is deferred. Display names contain 1–80
characters. Provisioned passwords require 12–128 characters, preserve spaces and
case, and are never stored or returned in plaintext. Hashes use argon2-cffi's
Argon2id defaults (RFC 9106 low-memory profile), independent random salts, and the
library verifier. No custom password cryptography exists.

Unknown users verify against an app-owned dummy hash to avoid an inexpensive
unknown-user path. Unknown users, incorrect passwords, and inactive users receive
the same HTTP 401 message. A valid password never overrides `is_active`.

The only new direct dependency is `argon2-cffi>=25.1,<26`, locked at 25.1.0 with
its bindings/CFFI dependencies. Existing pinned packages were not refreshed.
The [official Argon2 guidance](https://argon2-cffi.readthedocs.io/en/stable/parameters.html)
supports these default parameters. Runtime `pip-audit` found no known vulnerabilities.
No frontend package or external identity provider was added.

## Explicit development provisioning

There is no signup endpoint, default password, automatic seed, or auth-bypass
header. Users are provisioned through an explicit CLI that only accepts
`development` or `test` environments. Production rejects the command before
prompting for a password or opening the database. Existing usernames are never
silently updated; a duplicate fails without changing credentials.

From the repository root, native setup:

```bash
cd apps/api
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
# Configure TWF_DATABASE_URL as needed; default is local SQLite.
.venv/bin/alembic upgrade head
TWF_ENVIRONMENT=development .venv/bin/python -m twf.bootstrap --username trader --display-name "Development Trader"
# Enter and confirm your own password at the hidden prompt.
.venv/bin/uvicorn twf.main:create_app --factory --reload --no-access-log
```

In a second terminal:

```bash
cd apps/web
npm ci
npm run dev
```

Open `http://localhost:3000`. The API's default permitted origin is exactly that
origin. If using another hostname/port (including `127.0.0.1`), configure
`TWF_CORS_ORIGINS` accordingly. There are no committed development credentials.
The browser test harness creates its own disposable database and test-only user,
clears inherited TWF environment settings, and avoids developer dotenv files.

## Sessions and transactions

`AuthSession` stores a SHA-256 digest of an opaque 32-byte random session token,
the user UUID, UTC creation/expiration timestamps, and nullable revocation time.
The raw token is sent only as an HttpOnly cookie. It is not a JWT, contains no
claims, and is never stored in localStorage or the database.

The backend validates token syntax, digest lookup, expiration, revocation, and
current user activation on every `/auth/me` request. It also denies sessions if the
user no longer exists. SQLite timestamps are normalized to UTC during expiration
comparison; PostgreSQL stores timezone-aware timestamps. Default lifetime is eight
hours; `TWF_SESSION_TTL_SECONDS` accepts 60–604800 seconds. No sliding refresh or
silent renewal is introduced. Login rotates/revokes the current session; logout
revokes it and clears the cookie. Replaying a revoked cookie fails.

Credential reads end before password verification and session writes, avoiding
SQLite read-to-write lock upgrades during concurrent logins. Revocation is an
atomic UPDATE. Login/logout explicitly commit their write transactions; the
TWF-1.3 session dependency still closes and rolls back failures. Read-only identity
resolution never commits. Engine disposal and application-only readiness remain
unchanged.

## Cookie, CSRF and origin policy

| Policy | Development/test | Production |
|---|---|---|
| Cookie name | `twf_session` | `__Host-twf_session` |
| HttpOnly | Always | Always |
| Secure | Off for local HTTP | Always on |
| SameSite | Strict | Strict |
| Path / Domain | `/`, no Domain | `/`, no Domain |
| Expiration | Configured Max-Age and server expiry | Same |

Both login and logout require exactly one `Origin` header matching an explicitly
allowed `TWF_CORS_ORIGINS` entry. Missing, `null`, duplicate or untrusted origins
are rejected. Production permits only HTTPS origins and defaults to no permitted
origin. This is the CSRF defense in addition to SameSite Strict; non-browser
clients must supply the configured Origin too. GET `/auth/me` has no mutation.
Future cookie-authenticated write routes must reuse an equivalent origin/CSRF
check; importing the identity dependency alone does not add CSRF protection.

The browser calls same-origin `/api/v1/auth/*` on Next.js. A narrowly allowlisted
server route forwards only login/logout/me to FastAPI, carrying only the recognized
TWF session cookie, Origin and Content-Type. When both session names exist,
`__Host-twf_session` takes precedence, matching server identity resolution; Next.js
production builds also serve development APIs, so NODE_ENV cannot select the name.
Duplicate or malformed selected session cookies fail closed. Unrelated malformed
cookie pairs are ignored and valid session values are preserved without decoding.
The response allowlist preserves Set-Cookie, Retry-After and X-Request-ID.
`TWF_API_ORIGIN` is a server-only runtime
setting (default `http://127.0.0.1:8000`; Compose uses `http://api:8000`). It must be
an HTTP(S) origin without credentials/path/query. The proxy has no database,
password verifier, or identity authority. It has a request-body size check and
bounded upstream timeout. It does not forward arbitrary paths or redirects.

Credentialed cross-origin browser fetches are unnecessary; the accepted API CORS
middleware remains credentials-disabled. CORS origins also provide the explicit
trusted web-origin list for auth POSTs. The proxy returns `Cache-Control: no-store`;
identity fetches and successful auth responses are never cached. Production needs
an HTTPS web endpoint and appropriately protected API/database transport.

## Backend API and replacement seam

| Endpoint | Contract |
|---|---|
| `POST /api/v1/auth/login` | JSON username/password; 200 public identity, 401 generic credentials failure, 403 origin rejection, 429 login budget |
| `POST /api/v1/auth/logout` | 200 `{ "logged_out": true }`; idempotent revocation/cookie deletion; 403 origin rejection |
| `GET /api/v1/auth/me` | 200 `{ id, username, display_name }` or 401 |

Responses are typed and exclude password hashes, token hashes and raw tokens.
Auth 401/403/429 responses reference the canonical `ErrorResponse` in OpenAPI.
Existing request IDs and safe common error envelopes apply. No separate protected
demo endpoint is needed because `/auth/me` exercises backend authorization.
Future routes use the authoritative `get_current_user` dependency. The `twf.auth`
service seam can be replaced with provider-backed authentication while preserving
the current-user contract used by future workflows.

A bounded app-owned login budget allows 60 attempts per socket peer per minute,
with a 1024-peer memory bound and HTTP 429/Retry-After thereafter. It never trusts
arbitrary forwarded client-IP headers. Behind the Next.js proxy, users share the
proxy's budget. This conservative process-local control is not distributed abuse
protection; production hardening must add trusted edge/client rate limiting.

## Frontend flow

The root page moves into `(protected)`, whose server layout resolves `/auth/me`
using the incoming cookie before rendering the shell. Anonymous/expired/revoked
sessions redirect to `/login`. Login redirects already-authenticated users home.
There is no client-only authorization decision and no open redirect parameter.

The login screen uses existing dark/light tokens, visible labels, autocomplete,
keyboard submission, disabled/loading state, and generic credential/network errors.
Current identity appears in the existing top bar with a sign-out button. A small
React context carries the safe identity. Focus/pageshow and a one-minute interval
recheck expiry; 401 redirects to login. Network failure is not treated as proof of
logout. Backend checks remain authoritative between those refreshes.

Logout is confirmed by the backend before navigation. Failure offers a retry and
does not falsely claim that the session was revoked. No profile page or state
management library was introduced. Future APIs must perform their own backend
authorization even when rendered inside the protected layout.

Unknown protected routes retain the shell and existing recovery view. Next.js can
stream the async protected layout before discovering not-found, producing HTTP
200 plus `noindex` and the not-found UI instead of an initial HTTP 404; browser
tests account for both framework response forms and verify the recovery content.

## Migration and Docker

`0002_identity` upgrades `0001_empty_baseline` with only `users` and `auth_sessions`.
Portable UUID, string, boolean and timestamp types use the accepted naming
conventions, unique username constraint, session foreign key and user/expiry
indexes. Alembic explicitly imports identity models to register canonical metadata.
No production `create_all()` or startup migration/provisioning is added.

Downgrading to `0001_empty_baseline` deletes all user/session data. It is tested
only on disposable databases; real deployments require backup and explicit release
approval. Repeated upgrades and metadata drift checks pass on SQLite/PostgreSQL.

Local container setup:

```bash
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m twf.bootstrap --username trader --display-name "Development Trader"
```

Compose's SQLite file is in the API container filesystem; recreation is ephemeral
unless a writable volume is configured. `exec` targets that same filesystem.
Production migration commands use the externally configured PostgreSQL database.
The API starts without creating a database, table or user. Both images continue
to run as non-root users. The web proxy target is runtime-injected in Compose.

## Audit and security limits

Structured events record successful/failed login, verified-but-inactive rejection,
and logout. Success includes the public user UUID and normal request correlation.
No username/password/cookie/token/hash/request body is logged. Full durable audit,
session cleanup jobs, password reset, MFA, verified email, managed IdP provisioning,
multi-device session management and distributed rate limiting remain deferred.
Production user provisioning is deliberately unavailable through the development
CLI. This is a development authentication foundation with secure cookie/session
primitives, not a complete production identity service.

## Validation

### Bounded acceptance corrections

The independent review returned `HOLD_TWF1_4` for cookie over-forwarding, missing
typed auth error schemas, and omitted safe proxy response headers. These three
bounded corrections are applied; acceptance/freeze awaits independent re-review.
No session, password, database, dependency or later milestone functionality changed.

Added 15 proxy boundary cases covering both cookie names, deterministic precedence,
exact values, unrelated/malformed/duplicate cookies, no-cookie forwarding, all three
auth paths, safe headers, Set-Cookie and unchanged status/body. Added five backend
contract cases covering each relevant 401/403/429 runtime envelope and generated
OpenAPI reference. Generic 500 contract checks now cover auth GET/POST operations.

Correction validation: 72 backend tests and 43 frontend tests passed, along with
Ruff lint/format, strict mypy (33 files), compilation, pip check/audit, TypeScript,
ESLint, Prettier, production build, npm audit and npm ls. All 36 Chromium tests
passed across the existing six widths. Rebuilt API/web containers passed actual
login/current-user/logout, cookie set/delete, request-ID propagation and a real
429 response with Retry-After and matching body/header correlation. Repository
whitespace, relative documentation links and credential/logging hygiene checks
passed. Disposable smoke containers and network were removed.

Deferred observations remain unchanged: the body check follows request.text() and
does not enforce a transport-level memory limit; WebKit lacks the host library;
rate limiting remains process-local, with distributed protection deferred.

### Original implementation validation

Validated on 2026-09-25:

- Backend: **67 passing tests**, Ruff lint/format, strict mypy (32 files), Python
  compilation, pip consistency, and runtime vulnerability audit.
- Frontend: **28 passing component tests**, type-check, lint, Prettier, production
  build, npm dependency audit (zero vulnerabilities), and `npm ls --all`.
- Browser: **36 Chromium checks passed** across 390/768/1024/1440/1920/2560,
  including actual backend login, invalid credentials, server-side anonymous
  protection, current user, reload, logout and revoked-cookie replay, plus prior
  shell/theme regressions. Login uses both dark/light themes; mobile rendering was
  inspected. Screenshots/traces stay in ignored Playwright output.
- PostgreSQL 16: baseline-to-identity migration, repeat/check, downgrade/re-upgrade,
  login/me/logout with production cookie flags on a disposable database.
- Docker: both affected images rebuilt; real Chromium login/current-user/logout
  through both containers; explicit migration/provisioning and no startup seeding.
- Repository: whitespace, documentation links, generated-file and credential review.

WebKit remains **unverified**: its browser process fails before opening a page due
to missing host `libmanette-0.2.so.0`, matching the previously documented limitation.
No Chromium result is claimed as Safari certification. The implementation uses
standard cookies/forms/fetch/React patterns, with no browser-specific auth API.
The inherited Starlette/httpx TestClient deprecation and pip-audit hashed-lock
recommendation remain non-blocking. Test Docker containers/networks are removed.

Reproduce backend gates from `apps/api` and frontend gates from `apps/web` using
the repository's existing commands. For Chromium: `npm run test:e2e -- --project='chromium-*'`
after `npm run build`; the harness starts its own API and web servers on 8100/3100.
It does not use the developer's database or provision real accounts.

## Non-goals and next target

No broker login, trading authority, TM approval, subscriptions, roles/teams,
workspace/settings/watchlist models, social login, external IdP, full audit
subsystem, Redis, background jobs, realtime, scanner/TI/TM/LLM integrations or
profile/avatar system. Next is TWF-1.5 Settings Foundation after independent review.
