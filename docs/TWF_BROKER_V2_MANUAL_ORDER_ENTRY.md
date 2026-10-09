# Broker V2

Status: **ACCEPTED / FROZEN** — manual trading foundation, 2026-09-28.

The accepted Broker V2 authority, persistence, confirmation, and reconciliation baseline
remains frozen. [Options O1](TWF_OPTIONS_ARCHITECTURE.md) is an **ACTIVE DEVELOPMENT**
instrument-aware extension on that substrate. It adds canonical option identity and
single-leg NFO MARKET/LIMIT support without creating another execution service.
Final Git tag target: `twf-broker-v2` on `main`. Broker V1 remains the accepted
real broker read-only foundation (`aae52e9`, accepted implementation `4ffff9d`).
Final accepted milestone name: **Broker V2**. Earlier implementation/review
working name: **Broker V2.1**. Intermediate evidence below retains its chronology.
Automated validation uses mocked providers; the separate user-driven real smoke
is recorded below without credentials, private account identifiers or real order IDs.

## Scope and approved interaction

The supplied `TWF_Broker_V2_Manual_Order_Entry_Implementation_Prompt_v2.md` and
`ChatGPT Image Sep 28, 2026, 08_51_18 AM.png` are the normative written/visual
references. The compact sequence is Select Instrument → Order Ticket → Preview →
Submission Result → Orders. The existing broker account and function navigation
are retained; this introduces no top-level module.

Orders has **+ New Order**, including the empty view. Executable Instruments rows
have **Buy / Sell**. Both open the same provider-neutral `OrderTicket` dialog,
with the account, exact instrument and side carried through. The ticket uses a
compact blue title, adjacent labeled Buy/Sell controls, conventional field rows,
preview summary and acknowledgement with broker order ID. On mobile the dialog
scrolls within the viewport; underlying tables keep local horizontal scrolling.
Native modal focus containment, Escape, focus restoration, labeled inputs and
explicit Confirm Buy/Sell support keyboard users. Both centralized themes are used.

- **Equity:** select NSE (default), BSE, or Both, then search and select the exact
  exchange-specific row; enter shares. Both can legitimately show the same company
  on NSE and BSE, each with its own broker-native identity.
- **Futures:** select underlying and a real catalog expiry, nearest first; enter lots.
- **Options:** select underlying, listed expiry, CE/PE and a listed strike. A strike
  is valid only for that underlying/expiry/type combination. Enter lots.
- Quantity is calculated as lots × the selected contract's current lot size and
  independently checked by the server. Symbols, expiries and strikes are never
  synthesized. An exchange/reference plus native token is required.
- Initials are the resilient company-logo fallback. Kite supplies no verified
  company-logo URL; no external logo service, tracking request or dependency was added.
- Catalog last prices are not live quotes. The ephemeral LTP overlay described
  below uses exact-contract provider snapshots; unavailable values remain `—`. Limit price × quantity is labeled estimated
  order value (not margin or guaranteed execution value). Available cash is an
  optional bounded read; estimated margin uses Kite POST `/margins/orders` for this
  single order. Both estimates have independent two-second deadlines. Unsupported,
  invalid or unavailable estimates remain `—`; failure does not prevent submission.

The disabled **Exit Plan (optional)** reserves Stop Loss and Take Profit, each
with Price and %. “Managed exits will be enabled with TWF Alerts.” These inputs
are absent from the order request contract. **Broker trigger price** is a separate,
editable field only for native stop-limit (SL) orders; it activates that broker
order and is not a managed exit.

## Instrument selection remediation

Instrument Type is an explicit Equity / Futures / Options radio group in Step 1.
Equity alone shows the NSE / BSE / Both exchange group. Empty equity searches do
not dump the catalog. Equity search matches the trading symbol and provider
company/security name.
It normalizes Unicode width, case, whitespace and punctuation/separators. Common
terminal Ltd/Limited spellings are optional for company-name matching only;
neither the displayed provider name nor execution identity is rewritten.
The server applies the selected class, supported exchange/segment, executable
lot/tick metadata and search term before pagination (30 rows per page). Ranking
is exact symbol → symbol prefix → exact company/name → company/name prefix →
token/word-prefix match → substring. Every query word must match a word prefix in
one field for the token tier (for example `ind rel`); `reliance ind` also matches
`Reliance Industries Limited`. Symbol, exchange and native token break ties
deterministically. This is server-side deterministic matching, with no fuzzy/AI
search or second frontend ranking implementation. Missing names remain absent;
symbol matching still works. Both preserves separate NSE/BSE results.

The TWF canonical asset class remains **EQUITY** (the existing selection API wire
value is `asset=equity`); broker-native `kind=EQ` is separate metadata. Equity
cards show the symbol, provider name when present and `NSE · Equity` or
`BSE · Equity`. Native tokens are hidden from normal contract cards, but reference,
symbol, exchange, token and segment/type metadata remain intact in capability and
order payloads. The compact dialog, Buy/Sell, preview and disabled Exit Plan are
preserved. The later bounded quote overlay below adds ephemeral reference prices.

Futures uses matching catalog underlyings, then valid non-expired catalog expiries
sorted nearest first, and returns contracts only after both are selected. Options
requires underlying → expiry → CE/PE → a listed strike for that combination before
returning an executable row. The equity exchange filter does not apply to NFO
contracts. Changing a parent filter resets dependent filters and pagination;
obsolete search responses and errors cannot replace a newer selection. Selection
passes the exact reference and native token to the existing capability, preview
and confirmation flow. Submission, idempotency and reconciliation are unchanged.

**Provider classification limit:** EQ with segment matching NSE/BSE is the
strongest classification available in this catalog; Kite can also label bonds,
debentures and other cash-market instruments EQ. Metadata can exclude derivatives,
indices, unsupported segments and distinctly typed debt, but cannot guarantee a
perfect stock-versus-debt distinction. TWF does not infer equity from symbol
patterns or advertise a strict stocks-only guarantee. See the [Kite catalog
schema](https://kite.trade/docs/connect/v3/market-data-and-instruments/) and
[Kite's classification explanation](https://kite.trade/forum/discussion/comment/31309/).
Authoritative stock/debt classification is a separate future enhancement, with no
new external dependency in this remediation. The user explicitly accepted this
bounded limitation as non-blocking for Broker V2.

Previous class-scoping remediation validation: **310 backend tests**, **92 frontend unit tests**, and
**6 Chromium Broker V2 journeys** passed. Each browser journey covers Equity,
Futures and Options in both themes at one of 390 / 768 / 1024 / 1440 / 1920 /
2560 pixels, including exchange switching by keyboard, ranked results, exact
BSE identity through the proxy, dependent strikes, preview and synthetic order
reconciliation. Screenshots confirmed the compact selector across these layouts.
Ruff lint/format, strict mypy, TypeScript, ESLint, Prettier, production build,
OpenAPI construction and `git diff --check` passed. SQLite integration tests and
a disposable PostgreSQL 16 migration/selection/exact-identity preview smoke passed.
All provider calls used synthetic transport; no real orders were placed. No new
schema, dependency or execution-path change was required for this remediation.

Equity relevance refinement validation: **353 backend tests**, **94 frontend
unit tests**, and **6 Chromium Broker V2 journeys** passed. The journeys exercised
both themes at 390 / 768 / 1024 / 1440 / 1920 / 2560 pixels, including symbol,
long-name and normalized queries through the real proxy, simplified card labels,
hidden tokens and exact BSE identity passed to the ticket. Focused tests cover all
six rank tiers, token-prefix matching, missing-name fallback and unchanged exchange
scope. Ruff lint/format, strict mypy, TypeScript, ESLint, Prettier, production
build, OpenAPI construction and `git diff --check` passed. Rendered screenshots
were inspected across the responsive sizes. Order execution paths and derivative
selection logic are unchanged. No live orders, new dependencies or Git writes
were performed.

## Ephemeral LTP overlay

The browser POSTs exact reference/native-token pairs to
`/api/v1/brokers/accounts/{account_id}/order-entry/quotes`. The authenticated,
owner-scoped, same-origin endpoint accepts 1–30 identities, resolves each against
the current broker catalog and returns only reference, native token, nullable
price and a batch `received_at` timestamp. This is TWF receipt time, not the time
of the last exchange trade. Quote records never enter catalog records or any application database (the
chosen order Price still persists in the normal OrderIntent), and quote reads do not advance portfolio freshness.
Connection generation is checked again after the provider response.

A small provider-neutral `QuoteAdapter` boundary is implemented by Zerodha using
batched [Kite LTP](https://kite.trade/docs/connect/v3/market-quotes/#retrieving-ltp-quotes)
requests (`i=exchange:tradingsymbol`). Returned native tokens must match the
selected catalog identity. Futures and options use the exact contract/premium,
never the underlying spot instrument. Missing or nonpositive/nonfinite values
remain unknown. Provider errors are sanitized; credentials stay server-side.
The existing HTTPX timeouts and body limits remain, with a separate total quote
work deadline of at most three seconds including catalog resolution, streaming
and parsing (or the configured broker deadline if shorter).

One serial polling loop runs approximately every two seconds for intersecting
result cards (IntersectionObserver within the dialog) or the selected ticket
instrument. It never polls the whole catalog or offscreen rows. Changing search,
class, visible rows, route or account replaces/ends the scope; closing/unmounting
aborts fetches and clears refresh, request-deadline and freshness timers. The
browser aborts a request after four seconds; slow responses never create overlap.
If IntersectionObserver is unavailable, cards remain unknown instead of polling
an unbounded fallback. Preview/result stages do not poll.

Kite documents [one quote request per second](https://kite.trade/docs/connect/v3/exceptions/#api-rate-limit).
The adapter admits at most one batch per API key every 1.05 seconds, bounds the
in-memory admission map to 1024 entries, and applies a ten-second cooldown after
a provider 429. Requests rejected by this gate return a safe unavailable response;
there are no hidden provider retries or growing wait queues. This admission gate
is process-local: deployments must route each API key's quote traffic to one API
process; independent replicas or other applications sharing a key do not share
this gate. Cross-replica rate coordination is outside this bounded enhancement.

A quote is copyable for five seconds after receipt. Missing, stale, failed or
invalid responses show `—`, never zero; Set Price is disabled. Prices not exactly
aligned to the instrument tick are shown as reference only, with copying disabled
and a prompt to enter a tick-aligned price. Exact decimal arithmetic checks tick
alignment; no arbitrary rounding is applied.

A price-bearing ticket initializes Price once from the fresh launch-card snapshot,
or from the first valid quote that arrives if no snapshot exists and the user has
not edited Price. Later LTP refreshes update only the reference display. Explicit
**Set Price** copies the current fresh, tick-valid LTP; manual edits (including
clearing Price) always prevent delayed automatic initialization. Preview and
submission retain that frozen chosen Price. Existing approximate value and margin
calculations continue using the chosen Price. SL Trigger Price is never initialized
from LTP, and the managed Exit Plan remains disabled.

Equity and futures retain the accepted LIMIT/SL behavior. Options O1 adds MARKET
alongside LIMIT for single-leg CE/PE orders. An option MARKET ticket displays the
exact-contract LTP only as an optional reference and indicative-value input; it does
not create a Price field or send the LTP as a limit price. The provider payload uses
MARKET with price zero according to the existing Zerodha adapter convention.

Manual quote smoke after review: connect Zerodha, search a contract, compare LTP
with Kite, watch the reference refresh, open Buy/Sell, verify launch Price stays
fixed, then verify Set Price and a manual edit. No real order is necessary. All
automated quote and order tests use synthetic broker transport.

## Capability and deployment

Broker V2 keeps its bounded regular-order subset, with Options O1 enabling MARKET
only for single-leg CE/PE:

| Instrument             | Products  | MARKET validity | LIMIT validity | SL validity | Quantity                |
| ---------------------- | --------- | --------------- | -------------- | ----------- | ----------------------- |
| NSE/BSE EQ, lot size 1 | CNC, MIS  | —               | DAY, IOC       | DAY         | Integer shares          |
| NFO FUT                | NRML, MIS | —               | DAY, IOC       | DAY         | Integer lots × lot size |
| NFO CE/PE              | NRML, MIS | DAY, IOC        | DAY, IOC       | —           | Integer lots × lot size |

LIMIT requires a positive tick-aligned price; SL also requires a positive aligned
trigger. Buy limit ≥ trigger; sell limit ≤ trigger. Option MARKET carries no user
price. The generic UI consumes backend product/type/validity/quantity and broker
capability rules. Unsupported segments, expired contracts, missing tick/lot metadata,
unknown identities, invalid products, and unsupported order types fail closed. The
catalog uses V1's bounded daily cache (up to 24 hours); expiry is checked in
Asia/Kolkata on each resolution, and metadata changes invalidate a preview. Broker
RMS, exchange state, freeze limits and account permissions remain final authorities.
Preview does not guarantee acceptance. SL-M, MTF, AMO, autoslice, icebergs and other
varieties are outside this supported subset.

Run migrations explicitly; application startup never auto-migrates:

```bash
cd apps/api
.venv/bin/alembic upgrade head
```

The additive `0006_order_intents` creates `broker_order_intents`; it does not rewrite
V1 accounts or encrypted secrets. SQLite and PostgreSQL use the same model and
transaction policy. Downgrade drops this new ledger and is **only** appropriate
for disposable validation databases, never as a production recovery strategy.

`TWF_BROKER_MANUAL_TRADING_ENABLED=false` is the default. After independent
acceptance, an operator can set it to `true` in the API environment and restart
all API instances (Compose forwards the same variable). This does not connect an
account or place an order. It exposes manual capability only to authenticated
owners of connected accounts. User action is still required to preview and
confirm each order. Do not use this toggle as cancellation of an in-flight order.
The credential master key and accepted V1 secure setup remain unchanged.

A connected enabled room displays **MANUAL TRADING ENABLED** with its actual
snapshot freshness; instrument metadata remains explicitly a daily list.
Disabled/disconnected rooms show TRADING DISABLED. This never implies automated
trading or realtime streaming. Portfolio freshness remains separate from the
quote overlay.

### Zerodha order permission and IP whitelist

The TWF manual-trading switch enables the local workflow; broker authorization
is separate. Zerodha requires a public static IP for API order placement from
1 April 2026. Portfolio/order-book reads and market data can still work when the
order-placement IP requirement is unmet. See
[Zerodha's static-IP setup instructions](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/static-ip).

In the Kite Connect developer account, open **Profile > IP Whitelist**, register
the API server's actual public static outbound IP, then **Update**. This is not
the browser's address, `localhost`, a private LAN IP or the callback URL. Verify
the address before saving: Zerodha limits modifications to one per calendar week.
The outgoing address family must match too; allowing IPv4 does not cover requests
that actually leave over IPv6. See the
[Kite explanation of outgoing IPv4/IPv6](https://kite.trade/forum/discussion/15966/i-have-updated-my-static-ip-yet-trades-are-not-being-accepted).
If the server lacks a stable public IP, arrange a static egress address with the
ISP or hosting provider before relying on API order placement.

TWF recognizes explicit provider messages for missing IP configuration, a
disallowed outgoing IP and a user not enabled for the Kite app. It displays only
fixed safe instructions, never the raw provider body, IP or credentials. Other
permission errors remain explicitly unidentified and direct the operator to
check both the whitelist and app/account access. If both are correct, use
Zerodha support to investigate the remaining permission denial. A generic
permission rejection by itself does not establish an IP mismatch.

Restart the API after deploying the diagnostic change. Existing rejected
receipts retain their original safe message; their discarded provider details
cannot be reconstructed. No old intent is resubmitted. Once broker configuration
is corrected, any new order still requires a new user preview and confirmation.

## Durable authority and submission safety

A preview stores immutable normalized terms, instrument metadata, user, account,
provider identity, current session and account generation, plus explicit
`source=BROKER_WORKSPACE` and `execution_authority=MANUAL_USER`. Previews expire
in five minutes. Client-controlled authority fields and managed-exit fields are
rejected. All routes enforce authentication/ownership; mutations additionally
require the accepted exact Origin. Responses are no-store.

The confirmation payload cannot replace preview terms. Before claiming, the
server resolves the catalog again and checks connection, session, generation,
expiry, products, order types, validity, positive quantities, lots and tick sizes.
An account/intent lock claims PREVIEWED → SUBMITTING and commits **before** the
provider call. PostgreSQL row locks serialize contenders; SQLite uses the existing
bounded write-reservation/retry policy. Contention fails with a safe conflict,
never an unbounded retry or a raw lock error. Duplicate confirmation observes the
original intent and never calls placement again.

| State              | Meaning                                                                                      |
| ------------------ | -------------------------------------------------------------------------------------------- |
| PREVIEWED          | Validated immutable terms; nothing submitted                                                 |
| SUBMITTING         | Durable attempt claimed; dispatch may have happened                                          |
| SUBMITTED          | Provider acknowledged an order ID, or broker book recovered it; not proof of execution       |
| BROKER_REJECTED    | Explicit well-formed provider rejection with an allowlisted safe explanation                 |
| SUBMISSION_UNKNOWN | Timeout, lost/invalid response or other non-definitive outcome; never automatically resubmit |

Zerodha placement uses POST `/orders/regular` with explicitly mapped form fields
and an alphanumeric 20-character correlation tag. There are no HTTP retries,
redirects or environment proxies. HTTPX connect/read/write/pool limits remain,
inside the configured total wall-clock deadline, covering streaming, size limits
and parsing. Response bodies are bounded. Only recognized explicit provider
rejections become BROKER_REJECTED; other failures become unknown. Raw provider
messages, credentials and exception text are never reflected. The ledger stores
no credential material.

An interrupted process or failed result-save leaves the committed SUBMITTING
record, preventing another dispatch. After the dispatch deadline plus five
seconds, a broker-book check can mark an unmatched lingering claim unknown.
Disconnect after dispatch does not undo a live broker order; its acknowledgement
is recorded even if the original session/connection is later revoked. Reconnect
the same bound broker identity to recover it.

This is **at-most-one TWF dispatch per intent**, not exactly-once broker execution.
A separately created intent is a new human order; TWF cannot infer whether similar
terms are an intentional second order. There is no scheduler or retry worker.

## Broker truth and recovery

The result shows Order Submitted only with an acknowledged/recovered broker ID,
and states that execution is not guaranteed. Unknown results explicitly instruct
checking Orders/refresh before placing another order; the result does not offer
Place Another Order until a definitive outcome is known.

Orders itself remains the provider order book. All/Open/Completed/Cancelled/Rejected
filters operate on provider states. Recent manual submissions are a separate
receipt list (latest 50 attempted intents), persisted across browser reloads.
Each receipt can be reopened and explicitly refreshed. The ID lookup API also
supports direct recovery of an older known intent.

`MODIFY VALIDATION PENDING` is an active/Open broker state: visible in All and
Open, hidden in Completed, Cancelled and Rejected. This is a frontend filtering
correction only; the raw broker status remains preserved.

Reconciliation reads GET `/orders`. A known broker ID is authoritative, including
later changes made directly in Kite. Without an ID, recovery requires exactly one
matching correlation tag **and** exchange/symbol, side, product, type, quantity,
price, trigger and validity in the original account. Duplicate matches remain
unknown. Absence never means “safe to resubmit”: Kite's order book is transient
for the trading day, so next-day absence cannot disprove acceptance. When broker
history cannot resolve uncertainty, the user must inspect Kite/support rather
than blindly retry. Local original terms remain immutable even if Kite is later
modified; the provider status is displayed separately.

## API boundary

All paths below are relative to `/api/v1/brokers/accounts/{account_id}/order-entry`.
The existing web proxy allowlist forwards only these explicit routes.

| Method | Path                             | Purpose                                                   |
| ------ | -------------------------------- | --------------------------------------------------------- |
| GET    | `/capabilities`                  | Account enablement, optionally exact-contract rules       |
| GET    | `/choices`                       | Catalog-derived dependent choices and 30-row result pages |
| POST   | `/quotes`                        | Ephemeral exact-identity LTP batch; no quote persistence  |
| POST   | `/preview`                       | Validate and persist immutable manual intent              |
| GET    | `/intents`                       | Latest 50 attempted intents for this owner/account        |
| GET    | `/intents/{intent_id}`           | Read an owned receipt                                     |
| POST   | `/intents/{intent_id}/confirm`   | Claim once and submit; duplicate returns original state   |
| POST   | `/intents/{intent_id}/reconcile` | Read broker truth; never place/resubmit                   |

No managed SL/TP, Alerts, trailing, bracket strategy, multi-leg/basket orders,
modify/cancel actions, Scanner/TI/TM/agent execution, routing/failover or second
provider was added. V1 reads, holdings settled+T1+MTF semantics, encrypted
credentials and auth lifecycle remain the regression baseline.

## Provider references

Official Kite documentation checked for this implementation:
[orders](https://kite.trade/docs/connect/v3/orders/),
[instrument catalog](https://kite.trade/docs/connect/v3/market-quotes/), and
[margin estimates](https://kite.trade/docs/connect/v3/margins/).
The order-placement acknowledgement is distinct from execution; the tag is a
correlation aid, not a broker idempotency guarantee.

## Validation evidence

Validation is performed with disposable SQLite/PostgreSQL databases and a mocked
HTTP transport. The test provider cannot send an external request. Automated
browser journeys use generated test users and a disposable credential master
key; they never read the developer database or `.env`.

### Final acceptance and controlled real smoke

Broker V2 was accepted following substantial review, controlled real Zerodha
smoke, post-smoke acceptance, the Open Orders filter fix and closed-position P&L
remediation. The user selected an instrument in TWF, observed live LTP, used the
order ticket and Preview, and confirmed once. A controlled real Zerodha order
was successfully acknowledged and returned a real broker order ID. TWF displayed
“Order Submitted” with the qualification that broker acknowledgement does not
guarantee execution. This evidence is user-observed, separate from automated tests.

An earlier submission was rejected while Zerodha's static-IP configuration was
incorrect. TWF showed rejection, preserved truthful failure state, did not show
false success and did not automatically resubmit. Subsequent permission
diagnostics are sanitized and advisory: known missing-whitelist, outgoing-IP and
app/account cases receive fixed guidance; unidentified denials remain uncertain.
No actual public IP, credentials or private broker identifiers are recorded here.

Accepted read-model corrections are detailed in the [Broker V1 read-model
record](TWF_BROKER_V1_VERTICAL_SLICE.md): holdings combine settled,
T1 and MTF quantities conservatively while preserving provider P&L and unknowns.
For positions with known net quantity zero, remaining provider total P&L is
realized and unrealized is zero. Consistent open/partial splits are preserved;
unknown values remain `—`. Neither order-history aggregation nor quote-based P&L
recalculation was added.

Latest accepted validation after the P&L remediation, superseding earlier counts
for the same suites: **394 backend tests**, **113 frontend tests**, and **12
Chromium broker journeys** passed. The journeys cover both themes at 390, 768,
1024, 1440, 1920 and 2560 pixels. Ruff lint/format, strict mypy, Python compilation,
pip check, TypeScript, ESLint, Prettier, production build, OpenAPI and
`git diff --check` passed. Post-smoke acceptance also verified focused broker/quote
coverage, SQLite/PostgreSQL migrations and runtime, duplicate-confirmation races
on both databases, API/web Docker builds, Compose/container smoke and documentation
targets. Final freeze validation on 2026-09-28 repeated the **394-test backend**,
**166-test focused broker**, **113-test frontend** and **12-journey Chromium** runs:
all passed. Static checks, production build, OpenAPI, SQLite/PostgreSQL 16 migration
round trips and runtime/concurrency checks, Compose validation, API/web Docker
builds, container/proxy smoke, documentation links and secret-pattern review also
passed. All automated provider traffic remained synthetic; no further real order
was placed for the freeze.

### Known non-blocking limitations

- Safari/WebKit remains unverified in this environment: local HTTP navigation
  fails even against an independent plain-HTML control server. This is an
  environment/runtime limitation, not a Broker V2 defect or proof of compatibility.
- Quote admission is process-local, acceptable for the current single-process/local
  deployment. Multi-process, horizontal scaling and cloud deployment require renewed
  rate-coordination design and validation.
- Exit Plan Stop Loss/Take Profit controls remain visible but disabled; managed
  exits belong to future TWF Alerts. Native broker SL is separately supported.
- Kite may classify bonds/debentures as native `EQ`. TWF's canonical `EQUITY`
  filter cannot promise perfect stock-versus-debt classification from that metadata.

### Historical implementation validation

LTP overlay validation on 2026-09-28:

- Backend full suite: **368 passed**, including **15** focused quote tests for
  exact identity, sanitization, missing/invalid values, ownership, Origin,
  request bounds, rate admission, cooldown, streaming deadline and connection
  generation changes. Existing order and read regressions remain passing.
- Frontend full suite: **107 passed**, including **13** focused quote tests for
  launch snapshots, delayed initialization, manual edits, explicit Set Price,
  exact tick alignment, stale expiry, failure handling, visible-card scoping,
  serial polling and cleanup. Mocked MARKET capability remains reference-only;
  actual backend capabilities continue to support LIMIT/SL only.
- Chromium: **6 Broker V2 journeys passed** at 390, 768, 1024, 1440, 1920 and
  2560 pixels. Each exercises both themes and Equity/Futures/Options, including
  changing LTP with frozen Price, Set Price, preserved manual edits and the
  existing preview/confirmation/reconciliation flow. Rendered ticket screenshots
  were inspected across all six widths.
- Ruff lint/format, strict mypy, Python compilation, pip check, TypeScript,
  ESLint, Prettier, OpenAPI bounded quote schema and `git diff --check` passed.
  Production web build and API/web Docker image builds passed.
- Disposable SQLite/container migration and PostgreSQL 16 migration/selection/
  preview/quote smoke passed. Compose validation, container health/readiness/
  status, quote forwarding through the web proxy and existing synthetic
  confirmation/idempotency/reconciliation/read smoke passed. Temporary
  containers and test databases were removed.
- Quotes and order submissions used synthetic provider fixtures only. No real
  orders were placed, no dependencies were added and no Git writes were made.

Original manual-order implementation validation on 2026-09-28:

- Backend: **303 passed** (258-test accepted baseline + 45 order regressions).
  Coverage includes Buy/Sell mappings across all three asset classes; catalog-only
  dependencies; invalid/missing terms and authority fields; IDOR/Origin/session
  binding; expiry and metadata changes; repeated six-way SQLite confirmation
  races; slow streaming total deadlines; explicit rejection; lost responses;
  unknown/absent/duplicate-tag reconciliation; crashed claims; external Kite
  modification; and independently failing optional cash/margin estimates.
- Frontend: **89 passed** (84 baseline + 5 focused tests), including immutable
  preview terms, lot calculation, trigger/exit separation, disabled exits,
  in-flight double-click protection, uncertainty recovery and executable rows.
- Chromium: **60 journeys passed**, including all six widths (390, 768, 1024,
  1440, 1920, 2560), dark/light Equity/Futures/Options flows, both launch points,
  preview/result, receipt recovery after reload, Escape/focus restoration, local
  table scrolling and no body overflow. All accepted V1 browser journeys passed.
- Ruff lint/format, strict mypy, Python compilation, pip check, TypeScript,
  ESLint, Prettier and production build passed. No dependencies were added.
- OpenAPI construction and closed order-input schema verified. Disposable SQLite
  upgrade/repeat-upgrade/downgrade/re-upgrade and metadata comparison passed.
- Disposable PostgreSQL 16: migration round trips/metadata comparison, six
  repeated six-way confirmation races across Equity/Futures/Options, lost-response
  reconciliation and all six V1 reads passed.
- Compose validation, API/web image builds, explicit container migration,
  `/health`, `/ready`, `/api/v1/status`, authenticated same-origin proxy, capability,
  optional estimates, mocked placement, duplicate confirmation, reconciliation,
  receipt lookup and V1 reads/disconnect passed. Containers and their disposable
  test data were removed; no developer database was used.
- Rendered ticket/preview/result screenshots were compared with the supplied
  wireframe. Compact proportions, blue header, side controls, contract metadata,
  required preview, acknowledgement and the disabled Exit Plan are preserved.
- WebKit can launch and render `setContent`, but both V1 and V2 journeys fail at
  HTTP `/login` navigation with `WebKit encountered an internal error`. A separate
  Node HTTP server serving only a plain HTML heading reproduced the same error
  in desktop and mobile contexts. This is independent host/runtime evidence,
  not evidence of Safari compatibility. Safari/WebKit execution remains unverified;
  no Chromium-specific API or CSS dependency was intentionally introduced.

At the historical implementation checkpoint above, automated placement used only
`httpx.MockTransport`; real-order smoke had not yet occurred and review was still
pending. Final acceptance and controlled real smoke supersede that earlier status
without rewriting its evidence.
