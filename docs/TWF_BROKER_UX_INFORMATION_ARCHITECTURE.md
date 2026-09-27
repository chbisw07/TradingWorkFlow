# Broker Workspace — Information Architecture

Status: **Implemented / pending user UX review**. This is a presentation correction
on top of the uncommitted BW-2.4 worktree, not a new broker capability or an
acceptance/freeze decision. [Broker Workspace architecture v0.3](TWF_BROKER_WORKSPACE_ARCHITECTURE.md)
remains authoritative. The [BW-2.4 record](TWF_BW2_4_ZERODHA_HOLDINGS_POSITIONS.md)
retains its authentication concurrency blocker and HOLD status.

## Navigation and daily work

The global sidebar remains the home for cross-broker modules. Unavailable modules
retain “Later” treatment. The compact status strip is unchanged.

Within Brokers, the primary selector is **Overview · Zerodha · Manage Brokers**.
Real accounts take priority. Setup and technical diagnostics are separate from the
daily workspace. No unsupported provider looks configurable.

| Route | Purpose |
| --- | --- |
| `/brokers` | Real broker connection summary and next action; no synthetic totals |
| `/brokers/zerodha` | Opens the sole connected account directly; otherwise shows account selection or a clear configuration path |
| `/brokers/zerodha/{account_id}/dashboard` | Compact account KPIs and holdings/positions status |
| `/brokers/zerodha/{account_id}/holdings` | Holdings table |
| `/brokers/zerodha/{account_id}/positions` | Net positions table; day activity on demand |
| `/brokers/zerodha/{account_id}/instruments` | Free-text and structured instrument search |
| `/brokers/manage` | Compact provider-card grid with connection details behind Manage |
| `/brokers/development` | Synthetic overview and qualified analytical totals |
| `/brokers/{account_id}/{view}` | Preserved synthetic account routes; legacy `instruments` route still opens the real instrument room |

A broker room has one compact identity/connection header, explicit **Live data ·
Read only · Trading disabled** labels, and conventional function links:
**Dashboard · Holdings · Positions · Instruments**. Disconnected or expired accounts
have a configuration/reconnection path. Unknown values remain **—**, never an
invented zero. Status uses words, not color alone.

Holdings and positions use compact tables, with unambiguous derivative identity
when available. Additional quantities, source timestamps and native IDs are on-demand
details. Instruments uses a table with text search and Underlying, Segment, Expiry,
Strike and CE/PE/FUT filters; less common filters are behind “More filters.” Search
version pinning, refresh, Next/Previous, account isolation and null semantics are
preserved.

## Setup and development

Manage Brokers presents responsive provider cards. Zerodha cards show the account,
connection state, read-only capability and a Manage disclosure. Credential editing,
connection, disconnection and cleanup retain the existing safeguards inside that
disclosure. Fyers and Angel One say “Coming later” and have no actions. Adding a
Zerodha account remains explicit; it is not mixed into daily holdings/positions.

**Development / Synthetic** is a collapsed secondary disclosure. Expanding it
loads links to the existing Alpha/Beta accounts and their synthetic overview.
Normal Overview does not fetch or display synthetic observations. Existing synthetic
holdings, positions, orders, funds, provenance and qualified aggregates remain
available in this separate area.

## Workspace and responsive behavior

The global sidebar stays compact. The main broker workspace uses the remaining
width, including ultrawide displays, without a permanent right-hand status column.
“Workspace details” opens a modal inspector for service troubleshooting; instrument
and dataset details stay beside their tables. The inspector supports keyboard entry,
Escape dismissal and focus restoration, and becomes a drawer on mobile. The broker
console starts collapsed; its existing contents remain accessible.

- Desktop: horizontal broker selector and function navigation; three provider-card
  columns and compact KPI row.
- Tablet: two provider-card columns, compact global navigation and flexible tables.
- Mobile: broker dropdown, one provider-card column, two-column KPIs and filters,
  scrollable function navigation and table-local horizontal scrolling.
- Both themes use the existing centralized tokens. Focus outlines, native controls,
  labeled regions, table headers and non-color status text remain available.

## Future locations, not implemented features

Broker-specific operational work belongs in its broker room. Cross-broker analytical
work belongs in the corresponding global TWF module. A future broker Watchlist will
hold exact executable native instruments; it is distinct from a global analytical
watchlist. Future Orders reserves **Drafts · Working · Completed · All**. Orders,
Funds and Watchlist tabs remain hidden for real brokers until implemented. No new
adapter, trading, order, watchlist, Scanner, TI, TM or alert capability is introduced.

## Validation and boundaries

Backend sources, tests, migrations, dependencies and API contracts are preserved from
the pre-UX BW-2.4 worktree. Browser journeys exercise the real connection flow using
isolated test providers, not a live Zerodha account. The documented pre-existing
SQLite authentication-cleanup race remains outside this frontend task; serial browser
validation does not establish that the race has been fixed.

Validation on 2026-09-27: 121 frontend unit tests and 437 backend tests passed.
The full Chromium/WebKit suite passed 120 checks; after the final tablet/layout and
setup-control refinements, all 24 affected broker journeys passed again. Both runs
used one worker to isolate UX validation from the known authentication cleanup race.
All six widths (390, 768, 1024, 1440, 1920, 2560) and both themes were covered.
The local review gallery at `apps/web/test-results/ux-final/review.html` contains
144 captures of the six target screens. These generated artifacts are Git/Docker
ignored. Mobile, tablet, desktop and ultrawide screenshots were visually reviewed.

TypeScript, ESLint, Prettier, production build, both Docker builds, disposable
container smoke, Compose validation, documentation links/index and `git diff --check`
passed. All 84 backend source/test/configuration files matched the pre-UX snapshot;
the OpenAPI SHA-256 remained
`4c45251f2f3a75b2e64c16889c1b12635e334ba9050b47762005719d25c898d3`.
No new regression was found; the previously documented BW-2.2 cleanup concurrency
defect remains unresolved. The UX is ready for user review, while BW-2.4 remains
on hold. No commit, tag or push was performed.
