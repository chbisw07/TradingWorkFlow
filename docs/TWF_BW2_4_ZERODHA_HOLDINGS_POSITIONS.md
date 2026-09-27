# BW-2.4 — Zerodha Holdings / Positions and Broker Room

Status: **IMPLEMENTED / HOLD — existing SQLite authentication cleanup defect**. This bounded slice is uncommitted;
no commit, tag or push is part of this work. BW-2 remains in progress. Real activation
still requires the accepted deployment, approved secret-store and account-binding
gates. Trading remains disabled.

## Authority and preflight

- Branch `main`; clean initial worktree; starting HEAD `3546d7aa661af199e9cfa49a110e5d9df58c3571`.
- BW-2.3 accepted/frozen at `twf-bw2-3-zerodha-catalog-search` on that commit.
  Its implementation record describes the historical acceptance checkpoint; the
  current status pages record the subsequent Git freeze.
- [Broker Workspace Architecture v0.3](TWF_BROKER_WORKSPACE_ARCHITECTURE.md), its
  [review](TWF_BROKER_WORKSPACE_ARCHITECTURE_REVIEW.md) and the
  [BW-2 planning / decision record](TWF_BW2_ONE_REAL_BROKER_READ_ONLY_PLAN.md)
  remain authoritative. This record does not revise their gates.
- [BW-2.1](TWF_BW2_1_SECURE_PROVIDER_ACCOUNT_FOUNDATION.md),
  [BW-2.2](TWF_BW2_2_ZERODHA_AUTH_ACCOUNT_BINDING.md) and
  [BW-2.3](TWF_BW2_3_ZERODHA_NATIVE_CATALOG_SEARCH.md) remain frozen baselines.
- [Data architecture](TWF_DATA_ARCHITECTURE.md),
  [service contracts](TWF_SERVICE_CONTRACT_ARCHITECTURE.md),
  [service integration](TWF_SERVICE_INTEGRATION_ARCHITECTURE.md),
  [security](TWF_SECURITY_AUTH_ARCHITECTURE.md) and
  [engineering standards](TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md) govern the implementation.

## Bounded implementation

Implemented: real Zerodha holdings and positions GET adapters, provider-neutral
normalization, exact catalog enrichment, separately qualified observations,
owner-scoped API, a dashboard derived from those rows and a broker room with
Dashboard, Holdings, Positions and Instruments. Management is at `/brokers/manage`.

Not implemented: real orders or funds reads, watchlist CRUD, drafts, previews,
OrderIntent, placement/cancel/modify, execution safety, TM/Scanner/TI integration,
paper trading, shared accounts or billing. Existing synthetic orders/funds are
unchanged fixtures, not real broker capabilities.

No dependency, schema, migration, observation table, background worker or cache was
added. BW-2.4 chooses **on-demand observations**, not durable portfolio history.

## Official provider mapping

Checked 2026-09-27 against current official Kite documentation:
[portfolio](https://kite.trade/docs/connect/v3/portfolio/),
[authentication](https://kite.trade/docs/connect/v3/user/) and
[exceptions / rate limits](https://kite.trade/docs/connect/v3/exceptions/).
No live provider call is used in default validation.

| Provider behavior | TWF behavior |
| --- | --- |
| `GET /portfolio/holdings` | `holdings.rows`; no order or funds operation |
| `GET /portfolio/positions`, `data.net` | Current `positions.rows`, including zero-quantity rows when returned |
| Positions `data.day` | Separate `activity_rows`; never added to net positions or dashboard totals |
| `X-Kite-Version: 3`, `Authorization: token api_key:access_token` | Backend-only headers; credential material never enters public responses or frontend DTOs |
| `instrument_token`, `tradingsymbol`, `exchange` | Native ID string, symbol and exchange retained exactly |
| `product` | Preserved string; known CNC/MIS/NRML/CO/BO/MTF classification; unfamiliar values stay visible and flagged |
| `quantity` | Strict signed integer, serialized as Decimal; holdings cannot be negative, short positions can |
| `average_price`, `last_price`, `close_price`, `pnl` | Nullable decimal observations, retaining supplied zero; no missing-to-zero coercion |
| Holdings `used_quantity`, `t1_quantity`, `realised_quantity`, `authorised_quantity` | Used, unsettled, settled and authorised quantities kept separately |
| Holdings `collateral_quantity`, `collateral_type`, `mtf.quantity`, `mtf.value` | Collateral and financed quantities/value retained; no margin or tradability inference |
| Holdings `day_change`, `day_change_percentage` | Nullable provider-supplied day change and percentage |
| Positions `overnight_quantity`, `buy_quantity`, `sell_quantity`, `buy_price`, `sell_price`, `multiplier` | Separate overnight, buy/sell quantities and averages, and multiplier |
| Positions `realised`, `unrealised` | Nullable realized/unrealized P&L; official documentation describes these as intraday returns |
| Missing per-row source time | `source_as_of = null`; retrieval time is never presented as a market timestamp |

Holdings `current_value` is reported quantity × supplied last price when both are
available. P&L is provider-supplied; its percentage is P&L / (quantity × average
price) × 100 only for a positive, known cost basis. Available quantity is the
arithmetic difference quantity − used quantity only when used is known and in
range. It is **not** a guarantee of sellable quantity, settlement, collateral
release or trading permission. Unsettled quantity is not silently added to quantity.

The official holdings prose still refers to T+2 while separately exposing T1 and
realised quantities. TWF preserves those fields rather than assuming current
settlement policy or inventing a combined quantity. Position net/day payloads overlap
by design. Their distinction is retained, and no independent P&L calculation assumes
that provider intraday realized/unrealized components must equal total position P&L.
Unknown optional values and unknown products do not make valid native rows disappear.

## Contract and authorization boundary

`twf.brokers.portfolio_contracts` supplies the additive, provider-neutral
`broker.native-read.v1` response. The frozen `broker.read.v1` synthetic contract is
unchanged; it cannot truthfully represent nullable native derivative observations.
Only `zerodha_portfolio.py` understands provider JSON keys and response DTOs.

`GET /api/v1/broker-portfolio/accounts/{account_id}` returns both separately
qualified datasets and their summary in one typed response. This keeps dashboard
math and rows together. The route requires the authenticated user, ownership and
`broker.read` on the selected account. Cross-owner access returns canonical 404;
denied permission 403; missing session 401. Unsupported methods are 405. Public
errors contain neither provider bodies nor credentials. API and Next BFF responses
are `Cache-Control: no-store`. The BFF permits only the exact account GET path,
rejects queries/arbitrary destinations, forwards the selected session cookie and
safe correlation ID, and refuses redirects.

Before **each** provider call the service validates the persisted account binding,
configuration and connection generation; verifies active secret ownership/purpose/
generation/expiry; resolves via the accepted secret-store boundary; and rechecks
authority. It rechecks the lease after each call and after enrichment before returning.
A disconnect/rebind detected mid-read produces canonical 409 and discards the
entire result; the second call is not started after a first-call fence failure.
An already in-flight HTTP request cannot be recalled, but its late result cannot
be accepted under a changed generation. No token or observation is retained by a
new backend cache, and the accepted generation/CAS implementation is unchanged.

## Bounds, failures and truthfulness

- Fixed HTTPS provider destinations; GET only; redirects and environment proxy
  inheritance disabled; no retries.
- Each dataset has HTTPX connect/read/write/pool timeouts of 5 seconds and an
  independent 8-second total deadline covering transport, slow streaming, byte
  limits, parsing and normalization. The calls are sequential, for at most two
  provider budgets; the BFF permits 25 seconds for them and application overhead.
- At most 4 MiB of raw response and 10,000 rows across net/day. Unexpected compression
  is rejected to avoid unbounded decompression. Parsing is bounded and checked
  before/after JSON decoding and through normalization; synchronous parsing cannot
  be preempted mid-operation, but no result past its deadline is accepted.
- Typed failures: authentication required/expired, timeout, rate limit, unavailable,
  invalid response, oversized response and partial response. Stale binding is a
  canonical HTTP conflict rather than an accepted observation.
- Malformed top-level shapes reject the dataset. Invalid/duplicate rows are counted,
  valid rows retained as PARTIAL/DEGRADED, and affected totals withheld. Monetary
  values are finite, bounded to magnitude 1e18 and 12 fractional places; extreme
  exponents cannot overflow derived arithmetic or silently underflow to zero. Empty COMPLETE
  is distinct from MISSING; all-invalid PARTIAL is not a successful empty read.
- Failure of one dataset does not replace the other with fabricated rows or disable
  `/ready`. Provider HTTP errors are never reflected verbatim or unnecessarily logged.
- `attempted_at` records a read attempt; `received_at` exists only for a successful
  normalized response. Each dataset carries provider/account/source, generation,
  health, completeness, rejected/total row counts and retrieval freshness policy.
- Holdings retrieval freshness is 60 seconds; positions 15 seconds. The UI ages these
  states locally without polling and labels prices as observations, not streaming
  quotes. Source freshness remains unknown when the provider supplies no source time.
- There is no stale fallback cache. Refresh clears the displayed response and a
  failed refresh does not keep old rows as current. Tabs share the loaded response
  while the room remains mounted; navigation/remount may request a new observation.
- Counts and totals derive exclusively from those normalized rows. Partial/missing
  datasets withhold counts and totals. Any missing contributing value withholds that
  total. A complete empty dataset may truthfully total zero. Open positions count
  nonzero net quantities; day activity does not contribute.

## Exact catalog enrichment

The service loads one published immutable catalog snapshot for the owned account,
then matches **native token + exchange + symbol**. It uses bounded batches of 400
native IDs rather than loading an entire instrument master per row. Token reuse
with a changed symbol cannot silently attach a different instrument.

A match adds catalog version, catalog fingerprint, instrument fingerprint, optional
canonical ID, name, expiry, strike, CE/PE/FUT kind, lot size, tick size, exchange and
segment. Stale catalog matches are marked STALE. Missing catalog metadata or a failed
exact match leaves the original observation visible as UNAVAILABLE/UNMAPPED, with
nullable derivative terms; no symbol parser guesses identity. Enrichment supplies
no trading authority. There is no canonical position netting across real accounts.

## Broker room UX

- `/brokers` prioritizes the real Zerodha entry; synthetic accounts and aggregates
  remain under Development / Synthetic. No Personal Rooms label remains in the UI.
- `/brokers/zerodha` is a useful selection/connection landing even with no account.
  An owned account opens `/brokers/zerodha/{account_id}/dashboard`.
- Four active function links: Dashboard, Holdings, Positions and Instruments.
  Orders/Funds are explicitly Later, not action links. Existing instrument-search
  links remain compatible and BW-2.3 version-pinned pagination is preserved.
- `/brokers/manage` houses existing add/configure/connect/disconnect controls.
  Connection/reauth state and a management/reconnect path remain visible in the room.
  Direct Instruments entry reads only account context, without triggering portfolio calls.
- LIVE DATA · READ ONLY and TRADING DISABLED are explicit. The operational area uses
  the available workspace width; the optional shell context panel is hidden only
  on real room/management routes. Two stale shell labels now point to account rooms
  and state Trading disabled, instead of falsely claiming no broker connection/live
  data. The global shell layout is otherwise unchanged.
- Tables retain density on large screens and scroll locally on small screens;
  navigation wraps. Semantic headings, captions, column headers, focusable scroll
  regions and signed P&L preserve keyboard and non-color meaning in both themes.
  Catalog IDs/generation/technical read details are behind disclosure controls.
- Empty, unavailable, partial, stale and reauthentication states have distinct copy.
  Missing numbers render `—`, never a fabricated zero. Derivative terms use exact
  catalog metadata and remain visible next to the native symbol when available.

## Requirement and test mapping

| Requirement | Artifact | Evidence |
| --- | --- | --- |
| Provider mapping, decimals, nulls, partial data, finite reads | `apps/api/src/twf/brokers/zerodha_portfolio.py` | `apps/api/tests/test_portfolio.py`: normalization, status failures, malformed/oversized data, slow chunks, parsing deadline |
| Native contract, identity and summary | `apps/api/src/twf/brokers/portfolio_contracts.py`, `apps/api/src/twf/portfolio.py` | Net/day separation, summary consistency, catalog fingerprints, stale catalog/token mismatch, missing fields |
| Owner/read permission and generation safety | `apps/api/src/twf/api/portfolio.py`, `apps/api/src/twf/portfolio.py` | 401/403/404/405, expired/stale token, disconnect during read, failure isolation; frozen auth suites |
| Room information architecture and state UX | `apps/web/src/components/brokers/real-broker-room.tsx`, broker routes/styles | `portfolio.test.tsx`, existing broker/auth/catalog tests |
| Narrow web API boundary | `apps/web/src/app/api/v1/broker-portfolio/[...path]/route.ts` | `portfolio-proxy.test.tsx`: exact path, cookie isolation, query rejection, sanitized failures |
| Responsive real/synthetic workflows | `apps/web/tests/browser/broker-auth.spec.ts`, `brokers.spec.ts` | Deterministic local adapters, both themes, Chromium/WebKit, six standard widths |

## Validation

Validation completed on 2026-09-27. All provider responses were deterministic
fixtures. No developer/production database, real credential, provider authentication
or live portfolio was exercised.

| Check | Result |
| --- | --- |
| Repository backend suite | 437 passed |
| Focused BW-2.4 portfolio suite, SQLite | 50 passed |
| Same portfolio suite, disposable PostgreSQL 16 | 50 passed |
| Frontend unit suite | 117 passed in 16 files |
| Combined Chromium + WebKit, both themes, 390/768/1024/1440/1920/2560 | 120 passed before the final direct-Instruments context addition |
| Affected broker journeys after that addition, both engines/six widths | 11 passed, 1 failed before any portfolio call: existing auth finalizer returned 500 |
| Repeated finalizer concurrency probe on current worktree | 9 failed / 11 passed; unexpected 500 under SQLite contention |
| Same probe against a separate `git archive HEAD` in `/tmp` | 12 failed / 8 passed; confirms frozen-baseline defect |
| Ruff lint/format, strict mypy, Python compilation, pip check | Passed |
| TypeScript, ESLint, Prettier, production web build | Passed |
| OpenAPI, Compose, API and web Docker builds | Passed |
| Isolated API/web container smoke | Health/ready/status, login, BFF, owned native read, default auth gate, no-store, 401/404/405, CORS and room routes passed |
| Documentation link/index and whitespace review | Passed; 38 Markdown files, 276 local links/anchors, 48 indexed documents |

The first combined browser run exposed a test navigation race on WebKit: a forced
navigation followed the Return to Brokers click before it completed. The test now
waits for the overview and follows Manage Brokers normally; the subsequent full
120-test run passed. This is distinct from the later reproducible API failure.

Manual screenshot inspection covered all six widths across Chromium/WebKit and
both themes. Navigation wraps, tables contain their own overflow and the real room
uses the main workspace. The host's Snap-injected GTK/GIO variables were unset for
WebKit runs, as in earlier accepted validation. No browser checks were skipped.

### Bounded blocker: authentication cleanup after binding

**MAJOR_FIX / HOLD_BW2_4:** concurrent finalizations for two independently owned
accounts on SQLite can return HTTP 500 in the existing
`BrokerAuth.finalize()` → `cleanup()` path. Sanitized instrumentation identified
`SQLITE_BUSY` at `apps/api/src/twf/broker_auth.py:446`, invoked after the binding
commit at line 781 via cleanup at line 791. Thus a binding can have committed before
its response reports failure. This is not a provider portfolio timeout or a WebKit
compatibility failure.

The API auth handler, auth service and database engine policy are unchanged by
BW-2.4. A separate archive of frozen `3546d7a`, loaded through `PYTHONPATH` with the
same isolated fixtures, reproduced the error. The ordinary backend suite passes
because it does not cover this distinct post-bind cleanup race. A green earlier
browser run does not resolve that evidence.

The bounded next action is to review/remediate contention handling for post-bind
secret-cleanup bookkeeping: preserve the authoritative binding result, keep cleanup
retryable and generation-safe, avoid raw 500s, and add repeated regression coverage.
This accepted authentication boundary was not rewritten inside the read-only slice.
No holding/position scope expansion or new database state is needed. The requested
exception for a discovered concurrency issue now applies; do not advance BW-2.4
until this issue has a bounded fix and focused validation.

Reproduction used two users, two accounts, independent browser sessions, sequential
setup/callbacks and simultaneous finalization. Each of twenty cases used a fresh
SQLite database. To reproduce, save the following as a temporary test file and run
from the repository root with
`PYTHONPATH=apps/api/src:apps/api/tests apps/api/.venv/bin/pytest -p conftest /tmp/test_finalize_race.py -q`:

```python
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from test_broker_auth import (
    HEADERS, account, configure, initiate, receive, login,
    browser as browser, database as database,
)


@pytest.mark.parametrize("iteration", range(20))
def test_finalize_race(browser, iteration):
    clients = [TestClient(browser.app), TestClient(browser.app)]
    try:
        for client, name in zip(clients, ("alice", "bob")):
            login(client, name)
            owned = account(client, name)
            configure(client, owned)
            receive(client, initiate(client, owned))
        barrier = Barrier(2)

        def finalize(client):
            barrier.wait(timeout=10)
            return client.post(
                "/api/v1/broker-auth/finalize", headers=HEADERS
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(finalize, clients))
        assert all(code in (200, 409) for code in statuses), statuses
    finally:
        for client in clients:
            client.close()
```

`conftest` enforces disposable SQLite/environment isolation; the provider and secret
store are test doubles. Unexpected 500 is the failure under investigation; safe
conflict is permitted by this probe.

No schema changed, so a new migration or observation concurrency subsystem is not
needed. Existing schema migration/setup is exercised by the isolated suites and
container smoke. Production provider activation and permission/entitlement checks
remain deployment responsibilities; this validation is not a claim of a live account
smoke. This implementation does not add a distributed rate limiter or automatic
refresh/retry that would bypass existing provider limits.

The slice uses the requested exhaustive implementation validation. The discovered
concurrency defect requires the bounded authentication follow-up above. The broader
BW-2 end-to-end read-only review remains later; BW-2, TWF-2 and UX-B2 are not completed
by this slice. Recommendation: **HOLD_BW2_4**.
