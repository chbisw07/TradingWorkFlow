# Broker Workspace — Information Architecture

Status: **Broker UX bounded remediation implemented / pending independent UX rereview**.
This is a product UX correction on top of the BW-2.4 implementation, not a new
broker capability or an acceptance/freeze decision.
[Broker Workspace architecture v0.3](TWF_BROKER_WORKSPACE_ARCHITECTURE.md) remains
authoritative. The [BW-2.4 record](TWF_BW2_4_ZERODHA_HOLDINGS_POSITIONS.md) retains
its authentication concurrency blocker and HOLD status.

## Navigation and daily work

The rule is simple, obvious, compact and professional. The global sidebar remains
Home, Brokers, Watchlists, Scanner, Candidates, Positions, Orders, Alerts, History
and Settings. Individual accounts never enter that sidebar. Future modules retain
“Later” treatment. The compact status strip links to Connections; no extra strip is added.

Without a connected real account, the primary broker selector contains only
**Overview · Manage Brokers**. Overview says “No broker connected yet. Connect a
broker to start using TWF.” and offers Manage Brokers. It does not fetch synthetic
observations or present an empty provider workspace as a connection.

After successful configuration and verified binding, each connected account gets
its own tab: `Overview | Zerodha · Primary | Zerodha · Algo | Manage Brokers`
(each provider/name pair is one tab). Tabs require an enabled, configured,
bound account in `CONNECTED` state **and an implemented operational room with a
valid route**. Provider manifests declare room support independently from setup
support and connection state. A shared resolver governs both rendered routes and
operational links. Only Zerodha currently has a real room. Unsupported-room accounts
remain visible in My Brokers with an explicit unavailable reason, without Open links
or operational tabs; this does not invent Fyers support. Tabs disappear after disconnect/removal. The
shared broker layout refreshes owner-scoped connection state on entry, mutation
and window focus. Unavailable account refresh clears old tabs instead of leaving
stale connection claims. Previously bound expired accounts also appear on Overview with a reconnect link,
while their operational tab stays hidden until verification succeeds again.
They remain discoverable in My Brokers.

| Route | Purpose |
| --- | --- |
| `/brokers` | Connected accounts, reconnect links for expired bound accounts, or a clear empty-state action |
| `/brokers/zerodha` | Preserved legacy entry to the same account overview |
| `/brokers/zerodha/{account_id}/dashboard` | Account **Overview**: compact KPIs and holdings/positions status; existing URL preserved |
| `/brokers/zerodha/{account_id}/holdings` | Holdings table |
| `/brokers/zerodha/{account_id}/positions` | Net positions table; day activity on demand |
| `/brokers/zerodha/{account_id}/instruments` | Free-text and structured instrument search |
| `/brokers/manage` | **All Brokers**: searchable provider catalog |
| `/brokers/manage/my` | **My Brokers**: searchable saved connections/accounts |
| `/brokers/manage/setup/zerodha` | Shared manifest-driven setup form for a new connection |
| `/brokers/manage/accounts/{account_id}` | Manage that account, replace credentials, connect/reconnect or disconnect |
| `/brokers/development` | Preserved synthetic overview, discoverable only in development/test |
| `/brokers/{account_id}/{view}` | Preserved synthetic routes; legacy `instruments` route still opens real instrument search |

There are two levels: **which account**, then **which function**. The connected
workspace has one compact provider/account identity, connection state, a truthful
read-status headline, **Trading disabled**, and **Overview · Holdings · Positions ·
Instruments**. There is no extra user-facing “room” navigation concept. Unimplemented
real Orders, Funds and Watchlist tabs are hidden. Unknown values remain **—**, never
an invented zero. Status uses words as well as color.

The room headline gives authentication state precedence: **Reauth required**,
**Not connected**, or **Connecting**. **Live data · Read only** requires a connected
account and complete, available, fresh observations with valid receipt timestamps
for the displayed dataset (both datasets on Overview). Partial/missing or unhealthy
reads show **Read only · Degraded**, all-unavailable reads show **Read only ·
Unavailable**, and elapsed freshness windows or explicit stale metadata show
**Read only · Stale data**. The existing clock ages the headline without a new
request. Loading and failed refreshes cannot retain a live claim. Instruments shows
**Read only · Reference data**, without triggering portfolio reads or inferring
read health from authentication. The callback completion screen also makes no live
read claim. Trading remains disabled in every state.

The mounted room reconciles its read snapshot with the shared `BrokerSession`
account state. A newer account refresh overrides older room authentication claims;
account UUID/provider matching and `connection_generation` prevent another account
or an old-generation read from restoring Connected/Live. Session response receipt
and read start are ordered with a browser monotonic clock. A read started after the
last session refresh may still discover expired authentication for that same
generation; a subsequent session refresh takes precedence. Instruments consumes
the same session context instead of retaining a separate authentication copy.

Focus refresh updates the room headline, connection text and management/reconnect
link while it remains mounted, even when its operational tab disappears. Existing
observations remain visible with **Showing last available snapshot** after disconnect,
reauthentication or a generation change. Their receipt times, unavailable values
and original data remain intact; they are never described as Live. Reconnecting
with a different generation requires a matching fresh read before Live can return.
A failed/missing account refresh cannot fall back to an old Connected claim. Current
account read-health degradation also withdraws Live without a new portfolio request.

Holdings and positions use compact tables with unambiguous derivative identity
when available. Additional quantities, source timestamps and native IDs remain
on-demand details. Instruments keeps free-text search and Underlying, Segment,
Expiry, Strike and CE/PE/FUT filters, with less common filters behind More filters.
Version pinning, refresh, Next/Previous, isolation and null semantics are preserved.

## Manage Brokers and setup

All Brokers uses a compact three-column desktop/two-column tablet/one-column mobile
grid. Zerodha remains visible when connected and can add another connection.
Angel One, Fyers and Dhan say Coming later and have no setup action. Broker search
filters the catalog; My Brokers searches both provider and connection name.

My Brokers is account-oriented. Connected accounts offer Open and Manage; expired
accounts offer Reconnect. Incomplete saved setups remain visible for recovery.
Credentials are entered on a standalone shared setup page, not in nested card
forms. Connection creation, configuration, callback binding, disconnect and pending
cleanup continue through the accepted APIs and server permission flags.

The [Generic Broker Setup and Adapter Architecture](TWF_GENERIC_BROKER_SETUP_AND_ADAPTER_ARCHITECTURE.md)
describes provider manifests, field kinds, credential lifecycles, the test-only
second-provider proof, and the existing backend adapter/SecretStore boundary.
No generic UI field automatically gains a persistence path or provider API support.

## Development fixtures

A collapsed **Development / Synthetic** disclosure is rendered only when the server
runtime is explicitly `TWF_ENVIRONMENT=development` or `test`, or when no such value
is supplied during `next dev`. Production and unknown environments hide it; a normal
production Next build defaults to hidden. A declared `TWF_ENVIRONMENT=production`
always hides it. Browser fixtures explicitly declare test environment even though
they exercise a production Next build. This is a server decision, not a client toggle.

Expanding the disclosure loads the existing Alpha/Beta fixture links. Synthetic
holdings, positions, orders, funds, provenance and qualified aggregates retain their
routes and tests. Discovery gating does not change backend synthetic authorization
or make those routes a new security boundary.

## Responsive layout and accessibility

The main broker workspace owns the available width, including ultrawide displays.
Workspace details opens an on-demand modal inspector, with keyboard activation,
Escape dismissal and focus restoration. It becomes a drawer on mobile. The console
starts collapsed. Setup itself has a bounded readable width; tables use the workspace.
On broker pages at compact widths (including 390 and 768px), the status strip is one
locally scrollable row. All five fields remain available by touch and keyboard; the
focusable strip has a visible focus outline and does not overflow the body.

The wide no-broker state uses a concise, left-aligned onboarding block, a readable
heading and a filled **Manage Brokers** action with a minimum 44px target. It adds
no giant decorative card, fictitious metrics or filler. The surrounding workspace
continues to use the available width.

- Desktop: horizontal account and function navigation, three provider columns.
- Tablet: compact global navigation, two provider columns, local horizontal scrolling.
- Mobile: account dropdown, one provider column, two-column KPIs/filters, scrollable
  function navigation and table-local scrolling without horizontal body overflow.
- Dark and light modes use the existing centralized theme tokens. Labeled controls,
  visible keyboard focus, native form constraints, current-page semantics, table
  headers and non-color-only statuses remain in place.

## Future locations, not new features

Broker Watchlists will contain exact executable broker-native instruments and remain
distinct from global analytical watchlists. Future broker Orders reserves **Drafts ·
Working · Completed · All**. No real orders/funds, watchlist, trading, Scanner, TI, TM,
alert, streaming, new provider or backend framework is introduced.

## Validation and known boundary

The previous UX checkpoint passed 121 frontend tests, 437 backend tests and 120
Chromium/WebKit checks. This simplicity revision adds acceptance coverage for account
navigation and the generic setup lifecycle.

The known SQLite post-bind cleanup contention defect remains tracked in BW-2.4.
Browser checks use one worker to isolate UX testing; this does not prove that the
concurrent authentication defect is fixed or authorize a BW freeze.


Validation completed on 2026-09-27:

| Check | Result |
| --- | --- |
| Frontend unit suite | 135 tests passed across 18 files |
| Backend regression suite | 437 tests passed |
| Chromium and WebKit | Full final suite: 120 passed, one worker; 390, 768, 1024, 1440, 1920 and 2560px; both themes |
| TypeScript, ESLint, Prettier | Passed |
| Production web build | Passed |
| Ruff lint/format, strict mypy, Python compilation | Passed |
| OpenAPI | Unchanged from starting checkpoint |
| API and web Docker builds | Passed; API built without layer cache |
| Disposable container smoke | Health/readiness/status, login, ownership, CORS, read-only gates, BFF paths and protected pages passed |
| Production UX smoke | Fixture discovery hidden after hydration; empty account navigation and keyboard/focus setup checks passed |
| Documentation and Git whitespace | Local links/index and `git diff --check` passed |

The final local gallery at `apps/web/test-results/broker-v2/review.html` contains
192 captures: eight target screens × six widths × two engines × two themes.
Mobile, tablet, desktop and ultrawide captures were visually reviewed. The eight
screens are empty Overview, All Brokers, My Brokers, Setup Zerodha, connected
Overview, Holdings, Positions and Instruments. Generated captures remain ignored
by Git and excluded from Docker context. All provider responses use isolated test
fixtures; no live broker access was performed.

An early run overlapped a local rebuild and was discarded. A separate intermittent
WebKit error was traced to the test's hard navigation immediately after login,
which cancelled Next.js route prefetches. The journey now clicks the visible Brokers
navigation link, matching actual user interaction. No page-error assertion was
removed or filtered; the final stable-build full suite passed.

All 88 checked backend/shared/deployment files match the starting checkpoint;
dependencies and migrations are unchanged. OpenAPI SHA-256 remains
`4c45251f2f3a75b2e64c16889c1b12635e334ba9050b47762005719d25c898d3`.
The UX baseline is ready for user review; BW-2.4 remains on hold for its separately
tracked authentication defect. No commit, tag or push was performed.


## Bounded remediation validation

This revision addresses operational-route eligibility, truthful room headlines,
compact mobile context, and the no-broker primary action. It does not mark the UX
baseline accepted or change BW-2.4 HOLD. The SQLite post-bind cleanup race remains
separately tracked and unchanged. Backend, BFF, SecretStore, ownership checks,
provider adapters, catalog/search and portfolio semantics are outside this change.

Targeted tests cover two supported accounts, unsupported-room providers retained
in management without operational links, every supported room function route,
healthy/degraded/stale/expired/disconnected/connecting/unavailable states, read aging,
failed refresh, and reference-only Instruments. Browser journeys capture both themes
and assert compact status-strip height, keyboard scrolling, no body overflow, and
the visible primary empty-state action. Validation results follow below.


Bounded remediation validation completed on 2026-09-27:

| Check | Result |
| --- | --- |
| Targeted broker UX tests | 50 passed across four files |
| Full frontend unit suite | 151 passed across 18 files |
| Backend regression suite | 437 passed |
| Chromium | 60 passed; one worker; all six widths and both themes |
| WebKit | Not verified in this run: a minimal local HTTP page outside TWF also fails with a WebKit internal navigation error |
| TypeScript, ESLint, Prettier, production web build | Passed |
| OpenAPI | Unchanged; SHA-256 remains `4c45251f2f3a75b2e64c16889c1b12635e334ba9050b47762005719d25c898d3` |
| API/web Docker builds and Compose validation | Passed |
| Disposable container smoke | Health/readiness/status, login, ownership, CORS, error correlation, auth gates, BFF, catalog and read-only portfolio checks passed |
| Production UX smoke | Fixture discovery hidden; empty state, compact strip, no body overflow, keyboard setup and focus passed |
| Preservation | All 94 checked backend/BFF/shared/dependency/deployment files match this task's starting checkpoint |
| Documentation and whitespace | 286 local link targets resolve, UX index entry exists, and `git diff --check` passes |

The local screenshot gallery is `/tmp/twf-broker-ux-remediation/review.html`:
156 broker journey captures plus 13 production captures. It includes all six widths
in both themes, healthy/degraded/stale/reauth/disconnected/unavailable headlines,
management and setup, and the wide no-broker state. Representative mobile, tablet,
desktop and ultrawide screens were visually inspected. Screenshots and disposable
smoke fixtures remain outside the repository; no live broker access was performed.

The earlier WebKit success above belongs to the prior simplicity checkpoint, not
this remediation. The isolated runtime failure prevents a new Safari/WebKit claim;
Chromium success does not resolve that uncertainty. No browser error assertions were
suppressed. The UX baseline remains **pending independent rereview**, and the known
SQLite authentication race remains unchanged, unconcealed and outside this work.
No backend fix or BW-2.4 acceptance is implied. No commit, tag or push was performed.


## Live-status reconciliation remediation

Status: **Implemented / pending independent UX rereview**. This frontend-only
correction addresses the focused review's remaining mounted-room status finding.
It does not accept the UX baseline or change the separately tracked SQLite post-bind
cleanup race or BW-2.4 HOLD. Backend APIs, auth, SecretStore, ownership, generation
fencing, provider adapters and holdings/positions/catalog semantics are unchanged.

Regression coverage keeps a healthy room mounted while focus refresh changes the
account to disconnected, reauth-required, connecting or degraded. It checks retained
observations, account isolation, newer-session/older-read precedence, and reconnection
with a new generation. Browser scenarios repeat disconnect and reauth transitions
at all six widths, both themes, without navigation/reload or real broker calls.


Final validation for this remediation (2026-09-27):

| Check | Result |
| --- | --- |
| Frontend full suite | 162 passed across 19 files |
| Focused mounted-room reconciliation suite | 11 passed |
| Backend regression suite | 437 passed |
| Targeted Chromium real/synthetic broker journeys | 12 passed; 390/768/1024/1440/1920/2560px and both themes |
| TypeScript / ESLint / Prettier / production build | Passed |
| API/web Docker builds / Compose / disposable container smoke | Passed |
| OpenAPI | Unchanged; same SHA-256 recorded above |
| Backend/BFF/shared/dependencies/deployment | 96 checked files unchanged from this task's starting checkpoint |
| Documentation links/index / `git diff --check` | Passed; 286 local link targets resolve |
| WebKit | Minimal non-TWF HTTP page still fails with an internal navigation error; application compatibility remains unverified |

Account `read_health=UNKNOWN` is the existing foundation default, not an observation
failure. Fresh portfolio metadata decides read quality in that case; explicit session
DEGRADED/UNAVAILABLE withdraws Live. A first browser run exposed and corrected this
distinction; the final result above uses the corrected build.

Final screenshots are available in `/tmp/twf-live-status/review.html`, including
mounted disconnect/reauth with retained observations in both themes. Source changes
are limited to session/status reconciliation, the room, associated tests and this
record. No backend or SQLite-race repair, acceptance/freeze, commit, tag or push is
included. The Broker UX baseline remains **pending independent rereview**.
