# TradingWorkFlow (TWF) — TWF-1.5 Settings Foundation

## Status and authority

Implemented on 2026-09-25; **pending independent acceptance review**. No acceptance,
freeze, commit or tag is asserted by this record.

Preflight: branch `main`, starting commit
`a11c8c14d75ab91d5917f69ffc0d401ffcf27de5`, clean working tree. The configuration
reconciliation was already committed; there were no unrelated uncommitted changes.

Governing scope: [configuration architecture v0.6, section 34](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md#34-twf-15-minimum-foundation-guidance),
the [configuration review](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md), accepted
[TWF-1.4 authentication](TWF_TWF1_4_USER_LOGIN_FOUNDATION.md),
[TWF-1.3 database foundation](TWF_TWF1_3_DATABASE_FOUNDATION.md), and the
[UX bucket plan](TWF_UX_BUCKET_ROADMAP.md). This record describes the bounded delivery;
it does not replace the normative architecture.

## Section 34 implementation contract

The finite contract and implementation/test matrix were declared before coding.

| Requirement | Delivered boundary | Evidence |
|---|---|---|
| Typed descriptors | Two keys below; class, schema version, legal scope, HOT mutability, permission and capability identity | Catalog, malformed value, unknown key and forbidden scope tests |
| User ownership | Accepted authenticated user UUID; USER writes only; read-only PLATFORM defaults | Anonymous, cross-user, forged ownership and CSRF tests |
| Effective resolution | Typed overrides resolved centrally against defaults; per-key USER/PLATFORM source | Default, partial override, reset and round-trip tests |
| Non-secret personal profiles | Named, validated, revisioned preference snapshots; explicit apply and detach | Create/edit/apply, stale revisions, reset and deactivation tests |
| Capability/entitlement boundary | Injectable policy protocol with two explicit foundation grants; unknown capabilities denied | Denied policy preserves stored data; unknown capability denied |
| Secret-reference contract | UUID reference, ownership kind and owner UUID; extra fields forbidden | Raw secret field rejected; no credential endpoint or persistence |
| Setup and change metadata | Protected Settings page, clear feedback, metadata-only change rows in mutation transaction | Component, browser, rollback and correlation tests |
| Concurrency and migrations | Compare-and-swap revisions from first write; forward Alembic migration | Competing writers, stale saves, SQLite and PostgreSQL checks |

### Finite settings

| Key | Class | Values | Default | Scope | Capability |
|---|---|---|---|---|---|
| `density` | PRESENTATION | `comfortable`, `compact` | `comfortable` | USER | `foundation.appearance` |
| `default_horizon` | USER_WORKFLOW | `5d`, `15d` | `5d` | USER | `foundation.workflow_preferences` |

Both are schema version 1, HOT, with `settings:own` authority. Density changes only
the Settings surface's spacing. It is not a global workspace layout setting.
The horizon is a safe stored preference reserved for future analysis; it starts no
analysis, service call or trading operation.

An omitted key inherits the PLATFORM default. Explicit null, wrong types, unknown
keys and unsupported scope values are rejected. The values object replaces the
current set of overrides; it is not a patch or arbitrary key/value store.
`{}` resets both values to inherited defaults. Effective values and source labels
are returned separately from stored overrides.

### Theme and identity transitions

Theme remains the accepted **device-local** TWF-1.1A preference. It is not a key in
the user preference/profile schema and is not copied into a user's saved settings.
The existing pre-paint bootstrap, dark default, local-storage fallback, hydration
behavior and top-bar toggle are unchanged.

Logout and user switching preserve that browser/device appearance, as before.
The next user receives their own authenticated settings from the API; the previous
user's device theme is never represented as the next user's saved preference.
The UI explicitly explains this distinction. A future user-owned theme feature
requires its own fallback/migration/restoration design.

## Implementation layers

- `settings_contracts.py`: strict typed inputs, response/descriptor models, scope/class/
  mutability vocabulary, secret-reference contract and capability-policy interface.
- `preferences.py`: authorization, effective resolution, profile operations, revision
  checks, explicit transaction ownership and metadata audit.
- `infrastructure/preferences.py`: SQLAlchemy 2.x models using canonical metadata.
- `api/preferences.py`: thin typed routes using the accepted session/auth/origin
  dependencies and common error envelope.
- Frontend Settings page/component/styles: bounded personal settings/profile UX within
  the accepted shell. The server proxy forwards only permitted routes, the selected
  session cookie and original Origin/content type; it does not manufacture authority.

The capability policy is a finite foundation implementation, not a billing engine.
Both implemented capabilities are required for this small combined settings/profile
surface. A later entitlement adapter may replace the policy without deleting stored
configuration. Unknown capabilities fail closed. No commercial plan names exist.

## Persistence, transactions and migration

Forward migration `0003_preferences` follows `0002_identity`; accepted migration
history is unchanged. It adds exactly:

- `user_preferences`: user FK/primary key, typed override JSON, revision/schema version,
  applied profile ID/revision and update time.
- `preference_profiles`: UUID, owning user FK, bounded name, typed preference JSON,
  revision/schema version and update time.
- `preference_changes`: actor/owner user, target, action, resulting revision,
  request ID and timestamp. No values, credentials or request bodies are copied here.

Schema uses portable UUID/JSON/string/integer/date-time columns. No SQLite-specific
application branch, new driver, dependency, startup connection or automatic migration
was introduced. Apply migrations explicitly using the accepted deployment process:

```bash
cd apps/api
.venv/bin/alembic upgrade head
```

Reads do not create preference rows. Revision 0 denotes no saved preferences;
the first successful mutation creates revision 1. Subsequent writes condition on the
expected revision. A stale or competing first write returns 409 rather than
overwriting another change. Profile edits likewise require the current revision.

Profile apply requires both the expected settings revision and profile revision.
A conditional profile update holds its revision stable while the settings snapshot
and audit row commit atomically. Editing a saved profile never silently changes an
already applied snapshot. The response distinguishes saved and applied revisions.
Deactivation detaches the profile and retains effective preference overrides.
Reset clears overrides and the profile binding but retains saved profiles.

Authentication/read snapshots end before mutation transactions. Settings use cases
commit explicitly; the accepted request dependency rolls back failed transactions
and always closes sessions. No transaction contains a network or provider call.
The metadata audit commits or rolls back with the mutation. Readiness remains
application-only. Downgrade to `0002_identity` removes settings data/tables while
preserving identity; use downgrade only deliberately on disposable/test databases.

## API contract

All routes below are relative to `/api/v1/settings`, authenticated and no-store
on successful reads/responses. Mutations additionally require the accepted trusted
Origin check. Ownership comes from the server session, never an input user ID.

| Method | Path | Behavior |
|---|---|---|
| GET | `/definitions` | Finite descriptor catalog |
| GET | `/values` | Overrides, effective values, sources and applied revision |
| PUT | `/values` | Validate and apply replacement overrides with expected revision |
| POST | `/reset` | Restore defaults with expected revision |
| POST | `/deactivate` | Detach applied profile, retaining overrides |
| GET | `/profiles` | Current user's saved profiles |
| POST | `/profiles` | Validate/create named profile; 201; does not apply |
| PUT | `/profiles/{profile_id}` | Validate/edit owned profile at expected revision |
| POST | `/profiles/{profile_id}/apply` | Apply validated snapshot with both revisions |

Examples of request bodies:

```json
{"revision":0,"scope":"USER","values":{"density":"compact","default_horizon":"15d"}}
```

```json
{"name":"Research desk","scope":"USER","values":{"density":"compact"}}
```

```json
{"revision":1,"profile_revision":1,"scope":"USER"}
```

Unknown/foreign profiles return 404; missing authentication returns 401; denied policy
or Origin returns 403; revision conflicts return 409; invalid contracts return 422.
Backend errors reuse the safe request-ID-correlated envelope. Proxy transport failures
return a safe 503; unsupported proxy routes return 404 and oversized bodies return 413.
The proxy forwards backend request IDs and disables caching. No raw exception detail
is displayed in the Settings UI.

## Frontend behavior

The existing Settings navigation item now opens protected `/settings`. Sections group
personal preferences, preference profiles and an honest unavailable integration area.
Save/apply, cancel, reset, profile create/edit/apply and deactivate have distinct actions.
A profile is saved as VALIDATED; only explicit apply changes current preferences.
HOT application completes in the database transaction; no reconnect is simulated.

Native labels, fieldsets, headings, buttons/selects, visible token-based focus,
44px controls, status announcements and error alerts support keyboard/screen-reader
use. Failed loads offer reload; pending writes disable conflicting controls;
401/403 errors communicate session/permission unavailability without claiming success.
An empty profile list is explained. Changing a draft does not change stored settings.

Both themes reuse centralized tokens. Mobile stacks controls and actions; tablet
retains the shell's compact rail; desktop restores full navigation and side context;
large screens constrain form width. The surface advances UX-B1 only.

## Validation evidence

Executed against this implementation:

| Check | Result |
|---|---|
| Backend pytest | **86 passed**; includes 14 settings cases and accepted regression suite |
| Ruff lint / format | Passed; 40 files formatted |
| Strict mypy | Passed; 39 source files |
| Python compilation / pip check | Passed; no broken requirements |
| Frontend unit/component/proxy tests | **53 passed** across 7 files |
| ESLint / Prettier / TypeScript | Passed |
| Next.js production build | Passed |
| Chromium full suite | **42 passed** across 390, 768, 1024, 1440, 1920 and 2560 |
| Settings-only Chromium rerun | **6 passed**; same six cases, not additional unique coverage |
| Rendered Settings | Dark/light inspected at all six widths; no horizontal overflow |
| SQLite migration regression | Upgrade/repeat/downgrade/re-upgrade and metadata checks passed |
| Disposable PostgreSQL 16 | Populated identity upgrade, repeat upgrade, Alembic drift check, authenticated profile apply, stale write/reset, identity-preserving downgrade and re-upgrade passed |
| Docker Compose configuration | Passed |
| API and web images | Both built successfully; final API rebuild passed |
| Isolated container smoke | Non-root API, no startup database creation, explicit migration, health/ready/status, real web login, settings save/reload, rejected missing Origin with correlated error, logout passed |
| Git whitespace / local documentation links | Passed |

Regression coverage includes omitted defaults, persistence, safe validation errors,
foreign ownership, CSRF, unknown scopes/capabilities, raw-secret field rejection,
profile stale edits/apply, failed-commit atomic rollback, and two concurrent writers
competing for both the first and a subsequent settings revision. Test users/databases
are isolated; browser projects have distinct settings users.

The optional WebKit-1440 rerun could not launch: the host lacks
`libmanette-0.2.so.0` (MiniBrowser exit 127, before any application navigation).
This is a host dependency limitation, not a passing Safari test or new application
defect. Safari/WebKit runtime compatibility remains unverified. New browser-side
code uses ordinary React forms/fetch and existing theme tokens; server-only
`AbortSignal.timeout` is not a browser requirement. No Chromium-only UI API was added.

The backend test run emitted the existing Starlette/httpx deprecation warning.
No dependency was changed to suppress it. Initial smoke harness attempts used an
incorrect build path and PostgreSQL's temporary initialization socket; correcting
the harness and waiting for TCP readiness produced the passing checks above.

## Exact changed-file inventory

Created:

```text
apps/api/alembic/versions/0003_preferences.py
apps/api/src/twf/settings_contracts.py
apps/api/src/twf/preferences.py
apps/api/src/twf/infrastructure/preferences.py
apps/api/src/twf/api/preferences.py
apps/api/tests/test_preferences.py
apps/web/src/app/(protected)/settings/page.tsx
apps/web/src/app/api/v1/settings/[...path]/route.ts
apps/web/src/components/settings/settings-center.tsx
apps/web/src/styles/settings.css
apps/web/tests/settings.test.tsx
apps/web/tests/settings-proxy.test.tsx
apps/web/tests/browser/settings.spec.ts
docs/TWF_TWF1_5_SETTINGS_FOUNDATION.md
```

Modified:

```text
README.md
apps/api/alembic/env.py
apps/api/src/twf/main.py
apps/api/tests/test_backend_shell.py
apps/api/tests/test_database_foundation.py
apps/api/tests/test_foundation.py
apps/web/src/app/globals.css
apps/web/src/components/shell/primary-navigation.tsx
apps/web/tests/browser/auth-test-server.mjs
apps/web/tests/browser/shell.spec.ts
apps/web/tests/shell.test.tsx
docs/TWF_DETAILED_ROADMAP.md
docs/TWF_DOCUMENTATION_INDEX.md
docs/TWF_UX_BUCKET_ROADMAP.md
```

Existing test changes register the new routes/tables and enabled Settings navigation;
browser fixtures add isolated settings users. Dependency manifests/locks, auth/session
implementation, theme bootstrap/tokens, deployment definitions and normative
configuration architecture are unchanged. Generated browser artifacts remain ignored.

## Explicit deferrals

ACCOUNT/WORKSPACE/WORKFLOW ownership/persistence, full APS/ACS administration and
roles, billing/subscription lifecycle, full entitlement management, support access,
service principals, production vaults, credential entry, provider profiles and live
connection tests, real WARM reconnect/rebind, COLD deployment controls, arbitrary
plugins, profile import/export/schema migration UI, history/rollback UI, advanced
policy precedence, user-owned theme synchronization, live trading integrations and
UX-B2/B3 remain deferred. No role fixtures or tenant memberships were invented.
The minimal change table is not a full audit subsystem.

## Delivery assessment

```ini
APS_ACS_BOUNDARY_PRESERVED = YES
AUTHORITY_BACKEND_ENFORCED = YES
CAPABILITY_EXTENSION_PATH_PRESERVED = YES
HOT_WARM_COLD_MODEL_PRESERVED = YES
SETTING_CLASS_MODEL_PRESERVED = YES
SCOPE_MODEL_PRESERVED = YES
EFFECTIVE_CONFIG_BOUNDARY_PRESERVED = YES
SECRETS_NOT_STORED_AS_ORDINARY_SETTINGS = YES
SUBSCRIPTION_NOT_HARDCODED = YES
TWF1_4_AUTH_PRESERVED = YES
DB_PORTABILITY_PRESERVED = YES
UX_B1_ALIGNMENT = YES
UX_B2_B3_NOT_PREMATURELY_IMPLEMENTED = YES
TWF1_5_SCOPE_COMPLETE = YES
TWF1_5_TESTS_PASS = YES
TWF1_5_DOCUMENTATION_UPDATED = YES
READY_FOR_INDEPENDENT_REVIEW = YES
```

`TWF1_5_TESTS_PASS` covers the required executed backend/frontend/Chromium checks;
it does not assert WebKit execution. Recommendation: **READY_FOR_TWF1_5_REVIEW**.
Independent acceptance and Git freeze remain the owner's next gate.
