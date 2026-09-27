# Generic Broker Setup and Adapter Architecture

Status: **Implemented / pending user UX review**. This is the Broker UX simplicity
baseline, not a new broker capability or BW acceptance decision. The accepted
[Broker Workspace architecture v0.3](TWF_BROKER_WORKSPACE_ARCHITECTURE.md),
[secure account foundation](TWF_BW2_1_SECURE_PROVIDER_ACCOUNT_FOUNDATION.md) and
existing backend contracts remain authoritative. See the
[UX information architecture](TWF_BROKER_UX_INFORMATION_ARCHITECTURE.md) for navigation.

## Provider catalog and account identity

`brokerProviders` in `apps/web/src/lib/broker-setup.ts` is presentation metadata.
A `BrokerProviderManifest` declares provider ID, display name, support state, auth
strategy, credential fields and capabilities. Zerodha is the only supported real
provider. Angel One, Fyers and Dhan are catalog entries marked “Coming later,” with
no setup action or live adapter. Connected Zerodha remains visible in All Brokers.

A provider is not an account. My Brokers lists owner-scoped connection records,
including incomplete saved setups that need recovery. Operational tabs use the
account UUID and label, for example **Zerodha · Primary** and **Zerodha · Algo**.
A tab requires an enabled, configured account, verified provider account ID,
`bound_at`, and `CONNECTED` authentication state. Disconnect removes it after the
server response; focus refresh also reconciles expiry/removal. A failed refresh
clears stale tabs. This is presentation, not an authorization boundary: all server
ownership checks and generation fences still apply.

## One setup form

`BrokerSetupForm` renders provider-neutral fields, sorted by manifest order, on one
consistent standalone page. Connection name is common metadata. Each credential
field declares `key`, `label`, `kind`, `required`, `secret`, `lifecycle`, optional
placeholder/validation, and order. Supported kinds are TEXT, CLIENT_ID, API_KEY,
API_SECRET, TOKEN, TOTP_CODE, TOTP_SECRET, PIN and PASSWORD.

Zerodha displays only API key and API secret. The user saves configuration, registers
the displayed callback URL with their broker app if needed, then connects through
the existing browser redirect/callback strategy. The UI offers no invented “Test
connection” API. Existing accounts support credential replacement, connection,
disconnection and retrying pending credential cleanup according to the backend's
`can_*` flags. Unsupported actions are absent; unavailable reasons are visible.
Connection names are editable when creating an account; this task adds no rename API.

The shared form only collects ephemeral inputs. The supported setup controller
explicitly maps Zerodha's two fields into the accepted configuration contract with
`expected_revision` and `expected_generation`. It does not send arbitrary manifest
fields to storage. Account creation precedes configuration, so an interrupted save
can leave an incomplete account visible in My Brokers for recovery.

## Lifecycle and secrecy

| Lifecycle | Meaning | Current safeguards |
| --- | --- | --- |
| ONE_TIME_INPUT | Use for one authentication attempt only | TOTP codes require this lifecycle; no current production persistence path accepts them |
| SESSION_ONLY | Use only for a supported session-generation flow | Representable for future adapters and the test fixture; no production PIN/password/token session flow is added |
| PERSISTENT_SECRET | Configuration surviving an authentication attempt | Only the accepted Zerodha API key/secret contract is wired; reusable PINs/passwords/TOTP seeds with this declaration fail closed |

The persistence lifecycle does not override `secret`: the existing Zerodha app key
is a non-secret identifier, while API secret storage remains in the approved
SecretStore. No secret is added to a relational model, audit, returned payload or
log. Owner/account/provider scoping and generation fencing remain unchanged.

Inputs are uncontrolled and never copied into React state, localStorage, cookies,
URLs or analytics. All credential inputs are cleared before awaiting submission,
both on success and failure. The transient submission object is emptied on completion;
only in-flight request handling retains the necessary values. Secret kinds are masked
even if a manifest omits its secret flag. Errors are sanitized and never echo provider
exceptions or credentials. No raw saved values are loaded into edit forms.

The test-only Fixture Provider uses Client ID, API key, session-only PIN and one-time
TOTP with the same component. Tests cover rendering, validation, immediate clearing,
failure, double submission and invalid persistent lifecycle rejection. This fixture
is absent from the production manifest catalog. This proves form extensibility,
not support for another provider's authentication API.

## Existing common adapter boundary

The browser calls only the same-origin TWF BFF. Credential configuration and auth
state stay in the backend broker service and approved SecretStore. The only external
browser navigation is the approved provider login URL; the client verifies its origin
and path before navigating. Provider HTTP APIs are never called from the frontend.

Existing capability-oriented contracts separate authentication/profile verification,
catalog/search, and native portfolio reads. Zerodha implementations own provider
syntax, deadlines, parsing and errors behind those contracts. This task introduces
no giant base class or replacement backend framework. Capability metadata can express
profile, catalog, search, holdings, positions, orders, funds, streaming and commands;
capability support grants neither authorization nor entitlement. The backend remains
the authority and trading remains disabled.

A future provider adds a presentation manifest plus an explicitly supported, reviewed
backend adapter/configuration mapping. The generic form needs no provider-specific
layout, but new credential lifecycles or callback destinations must be deliberately
implemented and validated; adding a manifest alone does not activate a provider.

Future order intent translation belongs behind a common broker command contract:
side, exact native instrument, quantity, order type, price, product and validity map
to provider syntax in an adapter. No command, holdings/positions arithmetic change,
orders/funds read, watchlist, streaming, broker integration or entitlement is added here.

## Scope and known defect

The pre-existing SQLite post-bind cleanup race remains tracked in the
[BW-2.4 record](TWF_BW2_4_ZERODHA_HOLDINGS_POSITIONS.md). Binding may commit before
cleanup encounters contention. This UX task does not repair that race or change
BW-2.4 HOLD. Backend source, tests, migrations, dependencies and OpenAPI are preserved.
