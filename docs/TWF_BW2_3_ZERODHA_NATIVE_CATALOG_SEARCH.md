# BW-2.3 — Zerodha Native Catalog / Instrument Search

## Status and authority

**ACCEPTED / FREEZE PENDING — 2026-09-27**

Focused independent rereview decision: `ACCEPT_BW2_3`. The pagination hold is
resolved; no remaining blocker, major or minor finding was identified.
`READY_TO_FREEZE_BW2_3 = YES` and `READY_FOR_NEXT_BW2_SLICE = YES`.
Acceptance covers this bounded catalog/search slice; the BW-2 workstream remains
in progress. The BW-2.3 commit and freeze tag are pending.

Implementation preflight: clean `main`, HEAD `58ed806bfc845ee18a14484df0837f57dc85bd80`, tag
`twf-bw2-2-zerodha-auth-account-binding`. BW-2.2 is accepted/frozen; that Git
freeze supersedes historical pending-review text in its implementation record.
BW-2.1, BW-1 and the TWF-0/TWF-1 baselines remain accepted. No commit, tag or push
is included here.

Governing sources: [Broker Workspace v0.3](TWF_BROKER_WORKSPACE_ARCHITECTURE.md),
[architecture review](TWF_BROKER_WORKSPACE_ARCHITECTURE_REVIEW.md),
[BW-2 plan](TWF_BW2_ONE_REAL_BROKER_READ_ONLY_PLAN.md),
[BW-2.1](TWF_BW2_1_SECURE_PROVIDER_ACCOUNT_FOUNDATION.md),
[BW-2.2](TWF_BW2_2_ZERODHA_AUTH_ACCOUNT_BINDING.md), and accepted
[data](TWF_DATA_ARCHITECTURE.md), [contracts](TWF_SERVICE_CONTRACT_ARCHITECTURE.md),
[integration](TWF_SERVICE_INTEGRATION_ARCHITECTURE.md),
[security](TWF_SECURITY_AUTH_ARCHITECTURE.md) and
[engineering](TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md) standards.

## Provider evidence and ambiguities

The official [Kite instrument documentation](https://kite.trade/docs/connect/v3/market-quotes/#instruments),
checked 2026-09-27, documents authenticated `GET https://api.kite.trade/instruments`,
a daily gzip CSV, and token reuse after derivative expiry. Its example supplies
`X-Kite-Version: 3` and `Authorization: token api_key:access_token`. Daily
`last_price` is not a live quote and is deliberately excluded here.

The documented source has no snapshot checksum, authoritative row count, or
per-row generation timestamp. `source_at` stays null and `source_freshness` stays
`UNKNOWN`. A successfully received, fully validated document means `COMPLETE` for
that document, not proof of the provider's entire market universe. HTTP truncation,
invalid rows and malformed CSV fail the refresh; a well-formed upstream omission
cannot be detected without an authoritative manifest. Names can be absent,
particularly for derivatives. No underlying is guessed from a symbol.

## Requirement to artifact to test

| Requirement                                | Artifact                                                                   | Evidence                                                                                                   |
| ------------------------------------------ | -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Fixed provider acquisition and translation | `twf.brokers.zerodha_catalog`                                              | Auth headers, identity/gzip decoding, status errors, slow stream and bounds tests                          |
| Provider-neutral identity                  | `twf.brokers.catalog_contracts`                                            | Equity, FUT, CE, PE, optional fields, unknown type/segment and unmapped rows                               |
| Atomic version publication                 | `twf.catalog`, `twf.infrastructure.catalog`, Alembic `0006_native_catalog` | Idempotency, token reuse/history, transaction rollback and concurrent refresh fencing on SQLite/PostgreSQL |
| Owned typed search                         | `twf.api.catalog`                                                          | Every filter, bounds, Origin, ownership/IDOR, permissions and historical version isolation                 |
| Room search UI                             | `instrument-search.tsx`, dedicated catalog proxy                           | Frontend identity/state/filter/proxy tests; Chromium/WebKit search workflow                                |
| Freshness and failed refresh               | Catalog pointer and status contract                                        | Daily grace boundary, prior version retention, typed failure and partial-row counts                        |
| Frozen behavior                            | Existing auth/synthetic services                                           | Full backend/frontend/browser regressions                                                                  |

## Acquisition, publication and history

Refresh is an explicit owner action. Search never fetches a provider response.
There is no startup download, scheduler or automatic retry. Production activation
still requires the approved secret store, enabled BW-2.2 deployment, verified
connection, app rights and operational quota controls specified by the BW-2 plan.
Default validation injects provider/store doubles and makes no real Kite call.

```text
Owner requests refresh
  -> broker.read + broker.configure + Origin checks
  -> generation/revision fence and two-minute per-account refresh claim
  -> commit request audit, end transaction
  -> generation-validated active secret resolution
  -> bounded fetch -> decode -> validate -> normalize -> fingerprint
  -> recheck generation/revision and refresh claim
  -> insert immutable version and rows; switch active pointer in one transaction
  -> commit success/activation audit
```

The auth service validates secret ownership, provider, environment, current
reference and generation before secret use. HTTP runs without an open database
transaction. Disconnect/configuration changes during fetch prevent publication.
A second worker receives a safe conflict while the claim is live. A process crash
leaves the old catalog active; after the finite claim expires, status reports a
failed/stale acquisition and a new manual refresh can reclaim it. The claim ID
fences a late worker after reclamation.

Catalogs are account-scoped in this slice. This duplicates a provider-wide master
across accounts but prevents accidental cross-owner sharing, keeps refresh
permissions/audits unambiguous, and avoids a new global cache/quota service.
Production shared-app quota coordination remains a deployment prerequisite, as in
the accepted BW-2 plan; this does not claim to implement a cross-replica app budget.

`catalog_snapshots` stores immutable UUID version, provider/account, SHA-256 content
fingerprint, receipt/source timestamps and row count. `catalog_instruments` stores
versioned rows with UUID identities, native identity and search indexes.
`catalog_pointers` stores the active version, refresh claim, last verified time,
last failure and attempt counts. Alembic owns schema evolution; startup does not
migrate. No accepted migration is rewritten.

Sorted normalized row fingerprints define the snapshot fingerprint. CSV order and
ignored last-price changes do not create new versions. Identical content reuses its
version and updates last verification time. New content creates a new version;
old rows are retained. The same native token can therefore refer to different
contracts in different versions without overwriting history. Requests may pin a
historical version; a foreign account's version returns 404.

All row batches (500 rows each), the pointer, and successful audit events commit
atomically. Validation or persistence failure preserves the old active version.
Failed refresh metadata is recorded separately after rollback. A continuing DB
outage can prevent that write; the finite refresh claim then supplies recovery and
stale-state detection. Refresh audits contain metadata only: requested, succeeded,
failed, and version activated.

## Native identity and parsing

| Provider field                              | Provider-neutral durable/API field         |
| ------------------------------------------- | ------------------------------------------ |
| `instrument_token`                          | `native_id`                                |
| `exchange_token`                            | `exchange_id` (nullable)                   |
| `tradingsymbol`                             | `symbol`                                   |
| `name`                                      | `name` (nullable)                          |
| `exchange`, `segment`, `instrument_type`    | Same market concepts, bounded strings      |
| `expiry`, `strike`, `lot_size`, `tick_size` | Typed date, Decimal, integer and Decimal   |
| CE / PE / FUT                               | `derivative_kind` when explicitly supplied |

Each row also has a fingerprint, snapshot version, and nullable `canonical_id`.
Canonical mapping is optional and no mapping/netting is invented. Native identity
is always retained; a naked symbol is never treated as an immutable global ID.
Unknown bounded segment/type labels remain searchable with no invented derivative
semantics. There is no provider DTO/CSV column object in shared UI contracts or SQL.

Required headers/fields, token syntax, length limits, dates and numeric precision
are validated. Blank optional values remain null; invalid numerics never become
zero. Options require strike and expiry; futures require expiry. Lot and tick must
be positive; unsupported precision or malformed values reject the refresh. Duplicate
native tokens or exchange/symbol keys reject publication, including exact duplicate
rows. Rejected and accepted row counts are retained for partial attempts. No partial
snapshot replaces a good catalog.

Limits are explicit adapter constants: **30-second total deadline**, separate
five-second HTTPX connect/read/write/pool timeouts, **16 MiB wire**, **64 MiB decoded**,
and **250,000 rows**. Gzip expansion is bounded before accumulation. Redirects and
environment proxies are disabled. The total deadline includes streaming, decoding,
CSV parsing, normalization and fingerprinting. Synchronous bounded parsing cannot
be preempted; checks reject an overrun before publication. Cancellation closes the
HTTP stream/client. Event-loop teardown does not wait for an already-running OS DNS
resolver; a cancelled resolution cannot resume the HTTP operation. No request is
retried automatically. Limits need real master/app evidence before live activation.

## Search and UX

`GET /api/v1/broker-catalog/accounts/{account_id}/instruments` returns
`broker.catalog.v1`, catalog metadata and native rows. Filters: `text`, `exchange`,
`segment`, `instrument_type`, `expiry`, `strike`, `derivative_kind`, `name`, `symbol`,
and typed UUID snapshot `version`. Result `limit` is 1–100, offset 0–10,000, text
fields at most 128 characters. LIKE metacharacters are escaped. Sorting is stable:
exchange, segment, symbol, native ID. `matched` and pagination are explicit.

The first page (`offset=0`, also the default) may omit `version`; the server
resolves the active snapshot and returns it in `catalog.version`. Continuations
(`offset>0`) require `version`, otherwise the canonical validation envelope returns
422. Malformed UUIDs also return 422. Nonexistent or foreign-account versions return
404 without falling back to the active catalog. Existing owner/provider checks
apply before snapshot access.

Instrument Search retains the first resolved version for the active search. Next,
Previous (including offset zero) and refresh-triggered reloads send that exact
version. Publishing B while a search is pinned to A does not change its results;
retained inactive snapshots remain searchable. Submitting a new query or filter
clears the version and offset so the next first page may resolve B. Changing the
account remounts the search session and clears filters, offset and version. This
slice supports Zerodha only; provider scope follows the owned account.

The pagination regression publishes A, reuses token 3 for a different contract in
B, traverses every A page and returns to its first page. Exact ordered identities
remain A, with no missing/duplicate rows or B identity leakage; a new search returns
B's distinct row identity/fingerprint. Browser fixtures likewise reuse 30 tokens
across PAGEA/PAGEB instruments and verify 25+5 A results after B is published,
Previous returning the identical first page, and a new query/filter adopting B.
No live Zerodha call is used.

`POST /api/v1/broker-catalog/accounts/{account_id}/refresh` additionally requires
Origin and `broker.configure`. Both operations enforce login, owner and
`broker.read`. No-store responses contain no secrets or database/provider error
text. The dedicated web proxy only permits these routes and allowlisted query
parameters; it forwards the TWF session and Origin, with a finite 45-second upstream
budget.

Real broker cards link to `/brokers/{account_id}/instruments`. Instrument Search
supports text plus the structured name → segment → expiry → strike → CE/PE/FUT
sequence. It shows exchange-qualified symbols, names, native IDs, contract fields,
lot/tick, provider, catalog version and timestamps. Blank derivative names are
explained; users can search by symbol. Mobile uses compact cards and two-column
filters, desktop uses three-column filters, and large screens use two result
columns. Existing centralized theme tokens supply both themes. Labels remain
**LIVE DATA · READ ONLY** and **TRADING DISABLED**; synthetic rooms remain secondary
on the Brokers overview and their contracts are unchanged.

## Freshness and failure behavior

Acquisition freshness follows the plan's daily 08:30 Asia/Kolkata target with a
**two-hour grace window**. At 10:30 a successful acquisition at or after that day's
08:30 is required; before that cutoff the preceding day's target applies. This
uses daily publication, not a market calendar or generic service-health TTL.
Provider/source freshness remains unknown and catalog data is never a live price.

`FRESH`: current acquisition; `STALE`: prior catalog past the policy cutoff or a
failed latest refresh; `UNKNOWN`: connected account with no acquisition yet;
`UNAVAILABLE`: no published catalog and acquisition/auth unavailable. Active
completeness and last-attempt completeness are separate. A failed partial attempt
can report `PARTIAL` while retained active data remains `COMPLETE`.

Failures are typed: timeout, unavailable, auth required, rate limited, invalid,
partial, empty, oversized and stale connection. No success/binding state is created
by catalog fetching. Cached owned data remains searchable after auth expiry, with
a reauthentication message and disabled refresh until reconnection.

## Scope and validation

Catalog acquisition/search are implemented. **Portfolio reads, watchlists, order
draft/preview, trading, TM, Scanner and TI remain deferred.** No new dependency,
real portfolio endpoint or command path was added. Readiness remains application-only.

Validation uses injected CSV/auth/store fixtures and disposable databases only.

| Gate                                              | Result                                                                                                                                                                   |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Full backend suite                                | 387 passed; includes all 52 catalog cases and frozen baseline regressions                                                                                                |
| Focused pagination regressions                    | 5 passed; continuation validation, ownership isolation, historical traversal and token reuse |
| PostgreSQL 16 catalog suite                       | 52 passed in isolated schemas                                                                                                                                            |
| Frontend unit/component suite                     | 102 passed in 14 files; 8 catalog-specific cases                                                                                                                         |
| Ruff lint / format                                | Passed; 73 Python files formatted                                                                                                                                        |
| Strict mypy                                       | Passed; 72 source files                                                                                                                                                  |
| Python compilation / pip check                    | Passed                                                                                                                                                                   |
| TypeScript / ESLint / Prettier / production build | Passed                                                                                                                                                                   |
| SQLite + PostgreSQL migrations                    | Upgrade from accepted 0005, repeat head, metadata drift check, downgrade to 0005, re-upgrade; existing user/account preserved                                            |
| API + web Docker builds                           | Passed                                                                                                                                                                   |
| Container smoke                                   | Health/ready/status, explicit migration, login, catalog proxy/page/OpenAPI, auth-required/no-store, Origin, 401/404 ownership, existing broker-room/CORS behavior passed |
| Compose configuration                             | Passed                                                                                                                                                                   |

Final browser run: **120 passed** (60 Chromium, 60 WebKit).
Targeted mobile pagination/auth journeys: **2 passed** (one per engine).
Documentation validation: 37 Markdown files, 259 local links/anchors, 78 tables,
15 Mermaid fences and 47 indexed documents passed; `git diff --check` passed.

Browser validation covers Chromium and WebKit at 390, 768, 1024, 1440, 1920 and
2560 pixels, both themes, the existing synthetic workspace and the new
HAL → NFO-OPT → expiry → strike → CE/PE workflow, plus version-pinned
pagination across a refresh and token reuse. The local Snap-based IDE injects
GIO/GTK library paths that can crash WebKit's network process with a
`libpthread.so.0: undefined symbol: __libc_pthread_init` loader error. This was
independently reproduced against a plain local HTML server. Removing those inherited
overrides for the validation process restores WebKit; no application/browser
compatibility patch or system environment change was made. Reproduce with:

```sh
cd apps/web
env -u GIO_MODULE_DIR -u GTK_PATH -u GTK_EXE_PREFIX \
  -u GTK_IM_MODULE_FILE -u GDK_PIXBUF_MODULE_FILE -u GDK_PIXBUF_MODULEDIR \
  -u LD_LIBRARY_PATH npm run test:e2e
```

Live Zerodha acquisition is not certified by these fixture checks. Before live
activation, confirm app entitlements, approved secret storage, shared-app quota
coordination and the chosen response/deadline limits against actual master sizes.
BW-2.3 is accepted following focused independent rereview. Git freeze is pending;
no new freeze tag or real-broker activation is claimed.
