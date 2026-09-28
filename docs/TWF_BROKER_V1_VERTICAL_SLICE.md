# Broker V1 — complete read-only vertical slice

Status: **ACCEPTED / FROZEN**, integrated into `main` at `aae52e9`
(accepted implementation `4ffff9d`). The following sections record the accepted
read-only V1 boundary and its implementation history. Earlier work remains on
`archive/broker-work-before-simplification`.

[Broker V2](TWF_BROKER_V2_MANUAL_ORDER_ENTRY.md) is the accepted/frozen manual
trading foundation (`twf-broker-v2`), extending Orders and Instruments. Its opt-in execution
capability and order-intent ledger do not alter V1 holdings valuation, credentials
or connection lifecycle. References below to no trading describe the frozen V1 scope.

The user-authorized Broker V1 desktop v2 prompt and supplied six-panel wireframe
are the delivery scope for this rebuild. The accepted TWF-0/TWF-1 history remains
intact. This is one implementation record, not a new sequence of micro-milestones.

## Workflow and routes

`Brokers → Manage Brokers → Setup Zerodha → official broker login → verified
account tab → Overview / Holdings / Positions / Orders / Funds / Instruments`.

- `/brokers`: Overview and Manage Brokers, plus operational bound account tabs.
- `/brokers/manage`: provider cards and search; only Zerodha exposes Setup.
- `/brokers/manage/my`: saved connections, Open, Manage, Reconnect, Disconnect.
- `/brokers/setup/zerodha`: name, API key and API secret only.
- `/brokers/setup/zerodha/{account_id}`: replace configuration for an owned
  connection; saved secrets are never returned. The original identity remains bound.
- `/brokers/callback`: public landing page clears callback query parameters before
  making a same-origin authenticated POST. This preserves the accepted Strict
  session cookie while supporting a cross-site return from Kite. The response has
  no-store/no-referrer headers; Next development request logs exclude this URL.
  Any external reverse proxy must likewise omit callback query strings.
- `/brokers/accounts/{account_id}/{view}`: six read-only views above.

The existing dark default and light toggle remain. Broker pages use compact cards,
forms, horizontal tabs and locally scrollable tables. They omit unrelated context,
console and fixed shell connection labels. There is no synthetic broker product
UI, third navigation layer, watchlist editor or trading control.

## Backend and durable boundary

All endpoints are under `/api/v1/brokers` and require a valid TWF user session.
All mutations also require an exact allowed Origin.

| Method | Relative route              | Result                                                                |
| ------ | --------------------------- | --------------------------------------------------------------------- |
| GET    | `/providers`                | Supported/coming-later provider catalog                               |
| GET    | `/setup`                    | Callback URL, storage availability and safe setup message; no secrets |
| GET    | `/accounts`                 | Owned normalized connection state                                     |
| POST   | `/accounts`                 | Create/update owned encrypted configuration                           |
| POST   | `/accounts/{id}/connect`    | One-time, session-bound official login URL                            |
| POST   | `/callback`                 | Consume attempt, exchange token, verify profile, bind identity        |
| POST   | `/accounts/{id}/disconnect` | Destroy local access token and invalidate in-flight work              |
| GET    | `/accounts/{id}/{view}`     | Typed normalized snapshot; search query for Instruments               |

`BrokerAdapter` is a small read-only protocol. `ZerodhaAdapter` owns all Kite URLs,
headers, DTO parsing and normalization. The frontend uses TWF contracts exclusively.
No new satellite dependencies, trading endpoints or provider SDK are introduced.

Alembic `0004_broker_v1` adds only `broker_accounts`, `broker_secrets` and
`broker_attempts`. There is no portfolio-history persistence. Accounts have UUID
identity independent of their display names; ownership is checked for every
operation. A verified provider identity cannot be replaced on a bound connection.
Different provider accounts can coexist; duplicate bindings within the same TWF
user/provider are rejected by a database unique constraint.

## Encrypted database credentials

The bounded credential remediation retains the existing standard
[Fernet authenticated-encryption format](https://cryptography.io/en/latest/fernet/)
from `cryptography`: AES-128-CBC plus HMAC-SHA256, using a URL-safe base64-encoded
32-byte master key. This is the prompt's permitted existing authenticated primitive;
it is not AES-256-GCM. `CredentialCipher` handles bytes; `EncryptedSecretStore`
handles the provider-neutral credential bundle. No dependency was added.

`broker_accounts.secret_id` owns a generic `broker_secrets` record. The encrypted
JSON bundle contains credential keys (`api_key`, `api_secret`, `access_token`), with
no provider-specific database columns. The standard token persists its format
version, encryption timestamp, fresh random 128-bit IV, ciphertext and authentication
tag together; TWF does not extract or separately manage IVs. The library generates
a fresh CSPRNG IV on every encryption. `algorithm=fernet-v1`, `created_at` and
`updated_at` are stored alongside the token. No master key is stored in the DB.

New Alembic migration `0005_credential_metadata` adds those metadata columns to
`0004_broker_v1` without rewriting ciphertext, accounts or foreign keys. Existing
rows receive migration-time lifecycle timestamps because the old schema did not
track them. New ORM writes use UTC timestamps and update `updated_at` on replacement.
A constant epoch default supports SQLite's additive column rules without rebuilding
a referenced table; raw SQL writers must supply real timestamps. A metadata-only
downgrade/re-upgrade preserves the ciphertext and account data.

Set **`TWF_CREDENTIAL_MASTER_KEY`** outside the database and restart the API. It is
validated before credential use; it is never generated on startup. The legacy
`TWF_BROKER_SECRET_KEY` remains supported when the new setting is absent, preserving
existing Broker V1 credentials. If both are set, the new setting is authoritative:
there is no fallback on an invalid or wrong key. When renaming the setting, keep
its exact existing value. Do not generate a replacement key for an existing DB.

Missing/invalid keys return a safe 503 for credential operations; `/setup` returns
`storage_available=false` and an actionable `storage_message`, which disables the
Connect button. Other application functions remain available. A valid key enables
setup in development, test and production. Production deployments must inject the
same stable key into all API instances using their environment/secret manager.
This is encrypted DB storage, not a managed vault or a key-rotation implementation.

Setup/replacement encrypts before persistence and never echoes saved secrets.
Credentials are decrypted only in server memory for broker operations. Wrong keys,
modified tokens or unknown algorithms fail closed before connect can create an
authentication attempt. Replace credentials through the owned setup form or restore
the correct key; no plaintext fallback exists. Replacement clears the old access
token and invalidates earlier generations. Account responses, logs and audit/change
records contain no secret values. The public API key appears only in the official
Kite login URL as required; API secrets and access tokens never enter browser URLs.

## Authentication, concurrency and freshness

- Login attempts use random state, hashed at rest, bound to the exact TWF session,
  owner, account and generation; they expire after five minutes and are consumed
  once before provider I/O. Cancelled, replayed, stale and wrong-session callbacks
  are safely rejected.
- SHA-256 token exchange is followed by a separate `/user/profile` verification.
  Token-response identity, profile identity, broker and API key must match.
- HTTPX connect/read/write/pool timeouts remain. A separate configurable total
  deadline (default 20 seconds) covers a complete exchange plus profile check or
  complete read, including streamed byte limits and off-thread JSON/CSV parsing.
  There is no retry loop around provider requests. Failures use typed sanitized
  envelopes; partial authentication never binds an account.
- No database transaction spans a provider call. PostgreSQL uses row locks and
  conditional generation updates. SQLite reserves writes before read snapshots,
  with a 200 ms busy timeout and at most three attempts. Losing callbacks return
  a safe conflict. If rejection bookkeeping is also blocked, sanitized logging
  preserves the original rejection rather than producing a database exception.
- Configure, connect and disconnect advance generations. Final callbacks and
  reads recheck session, ownership and generation before accepting results.
- Disconnect is **local TWF disconnect**: the access token is erased and further
  reads are disabled immediately. It does not claim to revoke Kite's remote API
  session or sign out of Kite web/mobile. Users can revoke separately in Kite;
  remote logout is deliberately not called with credential-bearing query URLs.
- Token expiry is bounded locally at the next day's 06:00 Asia/Kolkata. Provider
  401/403 also marks reauthentication required. There is no automated refresh or
  unsupported website-login automation.
- Mounted rooms consume account state every 15 seconds, on window focus, and on
  cross-tab disconnect notification. In-page mutations update immediately. Newer
  account generations/timestamps override older read responses. Local read errors
  or failed account checks suppress LIVE. Snapshots become STALE after 30 seconds;
  reauth/disconnect always takes precedence over retained rows.
- Instrument lists are daily reference data, labelled accordingly, never live
  quotes. A process-local 24-hour catalog cache has bounded download/row counts,
  serialized refresh, exact native identity joins and deterministic pagination.
  Cached searches still verify the current provider session. Restarts fetch again;
  this V1 cache is not a distributed catalog service.

## Normalized reads

All missing values remain null and render as `—`; zero is not a fallback.

- Holdings: normalized ownership = `quantity + t1_quantity + mtf.quantity`.
  Settled and T1 shares use the provider average together; collateral/pledged,
  authorised, realised, opening and used quantities are not added again. Each
  ownership component must be present, finite, nonnegative and integral; missing
  or invalid components make total quantity/value/cost-derived fields unknown.
  An explicit zero MTF quantity establishes no MTF; an absent MTF object does not.
- Market value = known total quantity × last price. Missing last price means
  unknown value, not zero. Provider P&L is retained unchanged, never synthesized.
  With zero MTF, cost = (settled + T1) × average and P&L % = provider P&L / cost ×
  100 only for known, nonzero cost and known P&L. Missing last price alone does
  not invalidate a known cost/provider-P&L percentage; zero cost yields null %.
- Nonzero MTF quantity participates in ownership and market value. The published
  contract exposes separate MTF average/value fields but does not establish a
  combined cost or the top-level P&L's MTF coverage unambiguously. Therefore the
  combined average, cost basis and P&L % remain unknown; displayed P&L is only
  the provider-reported figure, not a claimed recomputation across MTF components.
- Overview sums the same normalized holding values; any unknown row makes the
  aggregate unknown rather than a partial sum. Empty holdings total zero. The
  existing nullable response shape and UI em dash rendering are unchanged.

These semantics follow the [Kite holdings contract](https://kite.trade/docs/connect/v3/portfolio/#holdings)
and [Zerodha's quantity clarification](https://kite.trade/forum/discussion/comment/50543/)
(checked 2026-09-28). The MTF cost/P&L ambiguity is handled conservatively above.

- Positions: net positions, product, quantity, average, LTP, realised/unrealised
  and total P&L. Day and net positions are not summed together.
  The existing `realized`, `unrealized`, `pnl` fields retain provider snapshot
  amounts for open/partially closed positions when their split is consistent.
  Kite's legacy split can put closed P&L under `unrealised`: when net quantity
  is explicitly zero, TWF classifies known provider `pnl` as realized and sets
  unrealized to zero. Total P&L is never replaced by `m2m` (day P&L), recalculated
  from orders, or refreshed using separate quotes. If total is missing, it stays
  unknown; closed realized P&L is retained only if the supplied unrealized value
  is explicitly zero. Missing/invalid amounts remain null (`—`); missing quantity
  does not establish closure. A split contradicting known total is unknown rather
  than corrected by inventing amounts. When all three amounts are known, realized
  plus unrealized equals total. Overview counts open positions, not position P&L.
  See the [Kite positions contract](https://kite.trade/docs/connect/v3/portfolio/#positions)
  and [Zerodha's legacy-field clarification](https://kite.trade/forum/discussion/13535/realised-field-update)
  (checked 2026-09-28).
- Orders: today's broker order book, time (IST), instrument, side, quantity,
  type, price and status. Raw status messages and private provider fields are dropped.
- Funds: equity/commodity segments, enabled state, raw available cash, utilised
  debits, net available margin and collateral. Missing segments are not fabricated.
- Overview: enabled-segment cash, known holdings value, nonzero net position count
  and nonterminal order count. Incomplete inputs remain unknown.
- Instruments: exchange + symbol + provider reference plus native token. Structured
  expiry, strike, kind, segment, lot size and provider-supplied underlying/name are
  retained. No derivative identity is guessed from a display string; unavailable
  fields stay null. Unmapped portfolio instruments remain visible. Query filters:
  `q`, `underlying`, `expiry`, `strike`, `kind`, `page`, `limit` (maximum 100).

## Official provider references checked

Checked 2026-09-27 against official Kite Connect v3 documentation:
[login, profile, margins and logout](https://kite.trade/docs/connect/v3/user/),
[holdings and positions](https://kite.trade/docs/connect/v3/portfolio/),
[order book](https://kite.trade/docs/connect/v3/orders/), and
[instrument CSV](https://kite.trade/docs/connect/v3/market-quotes/).
The official flow requires a registered redirect URL, short-lived request token,
server-side checksum exchange and next-day token expiry. No TOTP, password or PIN
is collected by TWF. The instrument dump is generated daily, with tokens potentially
reused after expiry; joins therefore also require exchange and symbol.

## Exact local setup and real smoke

For a first Broker V1 installation, use a **fresh database for this rebuild**; an ignored database from the archived
branch may have a later, incompatible Alembic revision. Do not reset or delete that
database. The commands below use `broker-v1.db` and a separate ignored environment
file, leaving existing `.env` and existing database files intact.

For an existing Broker V1 database, keep its database URL and key. Load its current
environment and run `.venv/bin/alembic upgrade head`; do not recreate accounts or
keys. No user credential files or databases were inspected by this remediation.

From `apps/api`, install dependencies and create the local environment once:

```bash
.venv/bin/pip install -r requirements-dev.lock
umask 077
.venv/bin/python - <<'PY'
from pathlib import Path
from cryptography.fernet import Fernet
path = Path('.env.broker-v1')
with path.open('x') as output:
    output.write('TWF_ENVIRONMENT=development\n')
    output.write('TWF_DATABASE_URL=sqlite+pysqlite:///./broker-v1.db\n')
    output.write("TWF_CORS_ORIGINS='[\"http://localhost:3000\"]'\n")
    output.write('TWF_BROKER_CALLBACK_URL=http://localhost:3000/brokers/callback\n')
    output.write('TWF_CREDENTIAL_MASTER_KEY=' + Fernet.generate_key().decode() + '\n')
path.chmod(0o600)
PY
```

The exclusive create deliberately refuses to replace an existing key. Keep this
file private; losing/changing its key makes saved
credentials unreadable. Back up the key separately from the database, under restricted
access. Do not paste it or broker credentials into chat. For an existing setup with
no credential key yet, follow the [local guide](TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md#broker-v1-credential-master-key)
to create a dedicated ignored key file once.

Load that environment, migrate, create a TWF login (once), then start the API:

```bash
set -a
source .env.broker-v1
set +a
.venv/bin/alembic upgrade head
.venv/bin/python -m twf.bootstrap --username trader --display-name Trader
.venv/bin/uvicorn twf.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

The bootstrap command prompts for a password locally. Reuse the created user on
subsequent starts. In another terminal, from `apps/web`:

```bash
npm ci
npm run build
TWF_API_ORIGIN=http://127.0.0.1:8000 npm run start
```

Open **http://localhost:3000** (use this exact origin, not the LAN IP).

1. In the Zerodha developer console, set the Kite app's redirect URL to exactly
   **`http://localhost:3000/brokers/callback`**. If the app requires HTTPS, use a
   controlled HTTPS origin and update both `TWF_BROKER_CALLBACK_URL` and
   `TWF_CORS_ORIGINS`; open TWF on that same origin. No automated tunnel is created.
2. Sign in to TWF with the local user.
3. Brokers → Manage Brokers → Zerodha → Setup.
4. Enter connection name, API key and API secret **only in TWF**.
5. Click Connect Broker and complete the official Zerodha login.
6. Confirm the verified Zerodha account tab appears automatically.
7. Open Overview, Holdings, Positions, Orders and Funds; compare against Kite.
   Empty broker data is valid; missing fields must show `—`.
8. Open Instruments, search `HAL`, then try a derivative filter if needed.
9. Disconnect; confirm the operational tab disappears, any retained data is
   labelled NOT CONNECTED and further refresh is disabled.
10. My Brokers → Reconnect; authenticate the same broker identity again.

A valid app/account and the provider-side redirect setting are user-controlled
prerequisites. Automated tests never use real Zerodha credentials. Successful
mocked journeys do not assert successful real-account access or data entitlements.

## Validation and changed-file inventory

Initial Broker V1 validation on 2026-09-27, before the credential remediation:

| Check                                                             | Result                                                                                                                                                                                          |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Full backend suite                                                | 218 passed, including 30 focused Broker V1 tests                                                                                                                                                |
| Ruff lint / format                                                | Passed                                                                                                                                                                                          |
| Strict mypy                                                       | Passed; 56 source/test/migration files                                                                                                                                                          |
| Python compilation / pip check                                    | Passed                                                                                                                                                                                          |
| OpenAPI construction                                              | Passed, including broker contracts                                                                                                                                                              |
| SQLite upgrade / repeat / downgrade / re-upgrade / metadata check | Passed on disposable databases                                                                                                                                                                  |
| PostgreSQL 16 migration and runtime smoke                         | Passed; three four-way callback races each had exactly one success, then all six read views passed                                                                                              |
| Full frontend suite                                               | 77 passed in 11 files                                                                                                                                                                           |
| TypeScript / ESLint / Prettier / production build                 | Passed                                                                                                                                                                                          |
| Chromium full suite                                               | 54 passed across 390, 768, 1024, 1440, 1920 and 2560 widths                                                                                                                                     |
| Mocked broker browser journey                                     | Passed at all six widths, both themes, using the real TWF API with a fake Kite transport                                                                                                        |
| WebKit                                                            | Not verified: isolated broker journey fails on navigation with an internal WebKit error; same failure independently reproduced on a plain local HTML server, while Chromium passes that control |
| Compose / API Docker build / Web Docker build                     | Passed                                                                                                                                                                                          |
| Container smoke                                                   | Passed: explicit migration, health/ready/status, login, web proxy, protected broker pages, encrypted setup, connect URL, local disconnect and safe read rejection                               |
| Development callback privacy smoke                                | Passed: temporary token absent from actual Next dev logs; no-referrer header present (Next dev overrides Cache-Control to no-cache; production no-store is browser-tested)                      |
| Git whitespace / local documentation links                        | Passed                                                                                                                                                                                          |
| Real Zerodha smoke                                                | Requires user credentials and provider-side app configuration; not run                                                                                                                          |

The initial combined browser run also exhausted the fixture server's production
login budget after the Chromium projects; WebKit was rerun on a fresh server to
separate this from its host/runtime error. No rate-limit weakening was introduced.
Run browser families separately when checking the existing full suite on one peer:
`npx playwright test --project='chromium-*'` and
`npx playwright test --project='webkit-*'`. Chromium success is not Safari evidence.

Source inspection found no Chromium-only browser APIs in the new client workflow.
Responsive CSS uses grid/flex and local overflow; browser state uses standard
fetch, AbortController, storage notifications and focus events. Proxy timeout APIs
run server-side. Safari rendering and callback behavior remain residual uncertainty.

No generated screenshots, traces, databases or credentials are committed; browser
artifacts are ignored and excluded from Docker contexts. Production only adds
`cryptography`; the development lock now explicitly includes the installed `httpx2`
TestClient dependency. No frontend dependency was added.

### Encrypted credential remediation validation (2026-09-27)

- Focused credential and Broker V1 regressions: **49 passed** (19 new credential
  cases plus the existing 30 broker cases).
- Full backend suite: **237 passed**, no pytest warnings. Ruff lint/format, strict
  mypy (58 files), Python compilation and `pip check` passed.
- Full frontend unit suite: **78 passed** in 11 files. TypeScript, ESLint, Prettier
  and production build passed.
- Chromium broker setup/connect/read/disconnect journey: **6 passed**, at 390,
  768, 1024, 1440, 1920 and 2560, both themes. Uses real TWF routes/persistence with
  dummy credentials and fake Kite responses. The prior full 54-test browser run
  is historical; this bounded remediation reran the relevant six broker journeys.
- SQLite: full migration roundtrip, repeat upgrade, schema comparison and populated
  metadata downgrade/re-upgrade passed, preserving ciphertext/account identity.
- Disposable PostgreSQL 16: the same metadata preservation and encrypted replacement
  checks passed, plus three four-way callback races (one winner each) and six reads.
- OpenAPI construction and the safe setup response schema passed. Compose validation,
  API/web image builds and container smoke passed (migration, health, ready, status,
  login, setup metadata, encrypted save, connect URL, local disconnect, safe rejection).
- Git whitespace and local documentation-link checks passed. No new dependency,
  real provider request, user credential read, commit, tag or push was performed.

The standard token format and legacy key alias preserve existing ciphertext. The
new metadata migration adds only algorithm/version and lifecycle timestamps; it
does not rewrite migration `0004_broker_v1`. Auth, ownership, callback replay,
provider deadline, disconnect and stale-generation regressions remain covered.

WebKit was not rerun for this bounded change; its previously documented host/runtime
limitation remains. A real Zerodha smoke still requires the user's app/account,
callback configuration and stable external key. Automated success is not evidence
of real provider login. Recommendation: **READY_FOR_REAL_ZERODHA_SMOKE** after local
key configuration, migration and restart; independent acceptance remains pending.

Exactly 16 files were changed by this remediation, relative to the existing dirty
Broker V1 worktree:

```text
apps/api/.env.example
apps/api/alembic/versions/0005_credential_metadata.py
apps/api/src/twf/api/brokers.py
apps/api/src/twf/brokers/secrets.py
apps/api/src/twf/brokers/service.py
apps/api/src/twf/config/settings.py
apps/api/src/twf/infrastructure/broker.py
apps/api/tests/test_broker_v1.py
apps/api/tests/test_credential_storage.py
apps/api/tests/test_database_foundation.py
apps/web/src/components/brokers/broker-workspace.tsx
apps/web/tests/brokers.test.tsx
apps/web/tests/browser/auth-test-server.mjs
compose.yaml
docs/TWF_BROKER_V1_VERTICAL_SLICE.md
docs/TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md
```

### Exact changed files (complete Broker V1 worktree)

```text
.gitignore
README.md
apps/api/.env.example
apps/api/alembic/env.py
apps/api/alembic/versions/0004_broker_v1.py
apps/api/alembic/versions/0005_credential_metadata.py
apps/api/pyproject.toml
apps/api/requirements-dev.lock
apps/api/requirements.lock
apps/api/src/twf/api/brokers.py
apps/api/src/twf/brokers/__init__.py
apps/api/src/twf/brokers/contracts.py
apps/api/src/twf/brokers/secrets.py
apps/api/src/twf/brokers/service.py
apps/api/src/twf/brokers/zerodha.py
apps/api/src/twf/config/settings.py
apps/api/src/twf/infrastructure/broker.py
apps/api/src/twf/main.py
apps/api/tests/broker_provider_fixture.py
apps/api/tests/test_auth.py
apps/api/tests/test_backend_shell.py
apps/api/tests/test_broker_v1.py
apps/api/tests/test_credential_storage.py
apps/api/tests/test_database_foundation.py
apps/api/tests/test_foundation.py
apps/web/next.config.ts
apps/web/src/app/(protected)/brokers/[[...path]]/page.tsx
apps/web/src/app/api/v1/brokers/[...path]/route.ts
apps/web/src/app/brokers/callback/page.tsx
apps/web/src/app/globals.css
apps/web/src/components/brokers/broker-callback.tsx
apps/web/src/components/brokers/broker-workspace.tsx
apps/web/src/components/shell/app-shell.tsx
apps/web/src/components/shell/primary-navigation.tsx
apps/web/src/components/shell/top-bar.tsx
apps/web/src/lib/brokers.ts
apps/web/src/styles/brokers.css
apps/web/src/styles/tokens.css
apps/web/tests/brokers.test.tsx
apps/web/tests/browser/auth-test-server.mjs
apps/web/tests/browser/brokers.spec.ts
apps/web/tests/browser/service_fixture_api.py
compose.yaml
docs/TWF_BROKER_V1_VERTICAL_SLICE.md
docs/TWF_DETAILED_ROADMAP.md
docs/TWF_DOCUMENTATION_INDEX.md
docs/TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md
```
