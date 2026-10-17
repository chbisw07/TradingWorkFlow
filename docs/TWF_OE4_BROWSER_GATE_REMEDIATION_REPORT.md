# TWF OE-4 Browser Gate Remediation Report

Date: 17 October 2026  
Scope: WebKit environment repair, current-UX browser assertion reconciliation, browser fixture isolation, and focused OE-4 safety regression  
Decision: **PASS — ready for an independent final focused re-review**

## A. Executive verdict

The browser acceptance blocker recorded by the OE-4 independent adversarial review is remediated. The exact PostgreSQL-backed acceptance command, `tools/test-postgres.sh --browser`, now completes with **427 passed, 17 narrowly scoped applicability skips, and 0 failed** across Chromium and WebKit at 390, 768, 1024, 1440, 1920, and 2560 pixels.

The original WebKit failure was environmental and occurred before application interaction. A Snap-inherited `GIO_MODULE_DIR` caused WebKit's network process to load a core20 `libpthread` against the host runtime and terminate on an unresolved private glibc symbol. Browser launch now removes only that inherited variable. WebKit remains in the acceptance gate.

Chromium assertions were reconciled with the accepted current product: consolidated Trade/TWF Order previews, current Broker position ownership columns, Candidate Ledger, compact navigation, and the light default theme. Two genuine frontend defects exposed by the repaired combined matrix were fixed narrowly: quote polling now waits two seconds after completion, and planned-route links do not prefetch unavailable protected RSC routes. No OE-4 backend production file or Queue workspace component changed.

## B. Preflight

| Item               | Recorded value                                                                             |
| ------------------ | ------------------------------------------------------------------------------------------ |
| Branch             | `main`                                                                                     |
| HEAD               | `209c6b1ef558ce8c6d04818b63818c3df479e532`                                                 |
| `origin/main`      | `f8b61d269be1a6416f9b83cf1a1aa7870e7969db`                                                 |
| Relationship       | local branch one commit ahead                                                              |
| Initial worktree   | only the pre-existing untracked independent-review document                                |
| Node               | `v20.20.2`                                                                                 |
| Playwright         | `1.63.0`                                                                                   |
| WebKit bundle      | WebKit 26.6, Playwright build 2359, Ubuntu 24.04 bundle                                    |
| OS/runtime         | Ubuntu 24.04.5; Linux `7.0.0-34-generic`, x86_64                                           |
| Acceptance command | `tools/test-postgres.sh --browser`                                                         |
| Database behavior  | private disposable PostgreSQL cluster and Unix socket; deployment credentials are not read |
| Projects           | Chromium and WebKit at 390, 768, 1024, 1440, 1920, and 2560                                |
| Workers            | 2                                                                                          |
| Failure artifacts  | traces retained on failure; screenshots on failure; generated results ignored              |

The configured suite has no Firefox project. No compensating browser was added.

## C. Original browser-gate reproduction

The independent-review result was reproduced before remediation:

| Browser  | Passed | Skipped | Failed | Primary result                                                          |
| -------- | -----: | ------: | -----: | ----------------------------------------------------------------------- |
| Chromium |    151 |       9 |     62 | Queue scenario passed; 11 stale/fixture failure cases repeated by width |
| WebKit   |      0 |      10 |    212 | every applicable case failed before application interaction             |
| Total    |    151 |      19 |    274 | required gate failed                                                    |

The Chromium failures formed 11 test cases across Broker positions, scanner and option ticket destinations, Discovery, navigation count, initial theme, and shared fixture identities. The OE-4 Queue scenario itself passed all six Chromium widths.

## D. Failure classification

The counts below classify the 274 original failed instances by their first decisive failure. Latent stale assertions exposed after fixture correction are also described in Sections H and I.

| Class                       | Failed instances | Root-cause families | Disposition                                                                                      |
| --------------------------- | ---------------: | ------------------: | ------------------------------------------------------------------------------------------------ |
| A. WEBKIT_ENVIRONMENT       |              212 |                   1 | fixed by scoped browser launch environment sanitation                                            |
| B. STALE_EXPECTATION        |               50 |                   9 | reconciled to accepted current UI and workflow                                                   |
| C. TEST_FIXTURE             |               12 |                   2 | isolated per browser/width users and broker callback tokens                                      |
| D. TIMING / SYNCHRONIZATION |       0 original |          0 original | a deterministic polling defect was later exposed under combined load and fixed                   |
| E. ACTUAL_PRODUCT_DEFECT    |       0 original |          0 original | two frontend defects were discovered during remediation and fixed; neither is OE-4 backend logic |
| F. TEST_INFRASTRUCTURE      |                0 |                   0 | WebKit's root cause is counted under A                                                           |
| G. UNKNOWN                  |                0 |                   0 | none remain                                                                                      |

The 50 stale instances comprise eight six-width cases plus the former Discovery surface's six-width main case and two representative-width cases. The 12 fixture instances were the Options and blue-white UX journeys using shared identities under a fully parallel matrix.

## E. WebKit investigation

The failure was reduced in layers:

| Probe                     | Before                                            | After                           | Result |
| ------------------------- | ------------------------------------------------- | ------------------------------- | ------ |
| Trivial local static page | WebKit navigation aborted                         | DOM/title readable              | PASS   |
| `/login`                  | `page.goto: WebKit encountered an internal error` | page and form load              | PASS   |
| Synthetic auth flow       | no application interaction possible               | 6/6 widths pass                 | PASS   |
| OE-4 Queue scenario       | 6/6 widths failed before login interaction        | 6/6 widths pass                 | PASS   |
| Full WebKit suite         | 0 passed, 10 skipped, 212 failed                  | 213 passed, 9 skipped, 0 failed | PASS   |

Browser executable and package compatibility were already correct: Playwright 1.63.0 expects and finds WebKit build 2359. Reinstalling or upgrading Playwright was therefore unnecessary. The production Next.js server, API proxy, loopback host, cookies, storage, and synthetic login all worked once the process-level library contamination was removed.

## F. WebKit root cause

The static-page probe produced the decisive network-process stderr:

```text
WPENetworkProcess: symbol lookup error: /snap/core20/current/lib/x86_64-linux-gnu/libpthread.so.0: undefined symbol: __libc_pthread_init, version GLIBC_PRIVATE
```

The IDE's Snap environment exported `GIO_MODULE_DIR` pointing into the Snap core20 cache. WebKit's network process inherited that path and loaded an ABI-incompatible runtime library. Chromium did not use that failing path. Removing only `GIO_MODULE_DIR` from the Playwright browser launch environment made the same installed WebKit binary navigate both trivial and application pages successfully.

## G. WebKit remediation

`apps/web/playwright.config.ts` clones the process environment for browser launch and deletes `GIO_MODULE_DIR`. It does not mutate the application server environment, alter browser policy, omit WebKit, change project widths, increase timeouts, or install unrelated system packages.

The Broker OAuth callback fixture now returns a trivial same-origin HTML redirect instead of relying on an intercepted synthetic 302 behavior that differed across engines. The resulting callback destination and state checks remain unchanged.

## H. Chromium stale-assertion inventory

| Spec                          | Old expectation                                             | Current accepted product behavior                                            | Updated assertion                                                                          | Result |
| ----------------------------- | ----------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------ |
| `brokers.spec.ts`             | position cells started at Product                           | positions include the accepted ownership/source column                       | ownership plus operational Qty/Avg/LTP/P&L cells                                           | PASS   |
| `derivatives-scanner.spec.ts` | direct Broker V2 option preview                             | Scanner Buy/Sell opens the trusted TWF Order preview and stops before create | exact canonical contract and terms reach TWF preview; no broker confirm                    | PASS   |
| `options.spec.ts`             | direct Broker option preview and shared broker user         | Options Analytics uses TWF Order preview                                     | exact instrument/terms/source; no Order creation or broker submit                          | PASS   |
| `scanner-v2.spec.ts`          | `Confirm Buy/Sell`                                          | preview offers `Create TWF Order`                                            | preview content and current action                                                         | PASS   |
| `watchlists.spec.ts`          | `Confirm Buy`                                               | preview offers `Create TWF Order`                                            | preview exists and no submission occurs                                                    | PASS   |
| `discovery.spec.ts`           | removed Scan & Discover workstation                         | current route is the Candidate Ledger                                        | navigation, empty evidence, refresh, inspector, responsiveness, absence of legacy controls | PASS   |
| `shell-design.spec.ts`        | 17 navigation links                                         | accepted navigation has 16 links                                             | groups, active route, planned and Settings destinations plus current count                 | PASS   |
| `shell.spec.ts`               | dark default                                                | accepted blue-white system defaults to light                                 | reduced motion, focus, and light scheme                                                    | PASS   |
| `theme.spec.ts`               | initial dark theme                                          | initial light theme; explicit dark/light persistence                         | toggle semantics, layout stability, persistence                                            | PASS   |
| `ux-blue-white.spec.ts`       | shared Trade identity and unsettled prior navigation errors | independent journey identity and errors scoped after navigation settles      | all five current workspaces, current compact headers, per-route page-error check           | PASS   |

## I. Chromium test updates

Assertions continue to use semantic roles, labels, current actions, exact payloads, navigation destinations, state, and no-submit boundaries. Obsolete headings, wrappers, historic Broker confirmation buttons, and the removed Discovery scanner surface were not restored.

The Discovery replacement does not claim removed functionality. One test covers navigation and compact responsiveness at every browser/width. A second test checks the desktop two-panel empty-evidence contract at widths of at least 1200 pixels.

Final Chromium result: **214 passed, 8 skipped, 0 failed**.

## J. Fixture/test-infrastructure changes

- Added dedicated `ux-blue-white-*` and `options-*` synthetic users for every browser/width.
- Made synthetic broker callback request tokens unique per project.
- Replaced the intercepted OAuth 302 with a same-origin HTML `location.replace` fixture for cross-engine consistency.
- Sanitized only `GIO_MODULE_DIR` for browser processes.
- Retained disposable PostgreSQL, two workers, both engines, all six widths, traces, and screenshot behavior.
- No arbitrary sleep or larger timeout was introduced.

## K. Production-code changes

Two frontend defects were proven under the repaired full matrix and fixed narrowly:

1. `useBrokerQuotes` scheduled the next poll relative to the prior request's start. A slow successful response could therefore trigger an immediate second poll, hit admission limits, and clear fresh quote data on the resulting 503. Polling is now paced two seconds from completion.
2. planned navigation links were still eligible for Next.js protected-route RSC prefetch. During logout, WebKit surfaced abandoned planned-route requests as access-control page errors. Prefetch is disabled only for planned routes; the links remain navigable.

No API, Queue dispatch, Queue policy, Broker V2 bridge, runtime setting, OE-4 endpoint, queue workspace, or queue policy component changed.

## L. Accepted UX preservation

The current blue-white design, consolidated Trade workspace, current Broker position columns, current Scanner controls, current Watchlist and Options Analytics ticket destination, light default theme, and Candidate Ledger remain authoritative. Production UI was not reverted to satisfy historical tests.

## M. PostgreSQL browser isolation

`tools/test-postgres.sh --browser` creates a private temporary PostgreSQL cluster, binds only a private Unix socket, sets `TWF_BROWSER_POSTGRES_URL` to its temporary database, runs the browser suite, and destroys the cluster on exit. The fixture creates only synthetic users, broker accounts, instruments, Orders, Queue Entries, and mock dispatch behavior in that database.

A post-gate read-only live check was rolled back and reported:

- backend: PostgreSQL;
- execution capability: `False`;
- dispatch attempts: `0` (same as the independent-review baseline);
- broker intents: `10` (same as baseline);
- Queue policy: `MANUAL`, version `7` (same as baseline).

No live provider write or broker order occurred.

## N. OE-4 safety spot-check

The complete `tests/test_queue_dispatch_oe4.py` module passed against both supported databases:

| Backend                  | Result    |
| ------------------------ | --------- |
| disposable PostgreSQL    | 21 passed |
| explicit SQLite fallback | 21 passed |

This module covers the default execution interlock, admission-time mode snapshot and immutability, manual double dispatch, multi-worker claim races, policy/admission races, definitive and ambiguous broker outcomes, crash recovery, claim rollback, source binding, tamper rejection, and exact derivative identity. All provider calls are synthetic.

Protected pre/post SHA-256 fingerprints are unchanged:

| Protected file             | SHA-256                                                            |
| -------------------------- | ------------------------------------------------------------------ |
| `queue/dispatch.py`        | `b0becef1d5f04dfdc85299bc525cf92f191a3d3d87c4215d76bd053cefbfe273` |
| `queue/policy.py`          | `2288a5fa25edbfb84eddf4f64963a8296e866553b3daab27d6e13d5914a27bb0` |
| `brokers/order_service.py` | `a1be4c9695d451c7b904c6279f9a5f189ee401a5b4453ca50a1e75a618a582f5` |
| `api/twf_queue.py`         | `10b24159d83ca95ce45c49f9499ea66afd6d8e066f949670e402e293267555f3` |
| `config/settings.py`       | `7ff290c87cd7d8930e45bdcaacddb1b419e1a0d7cd5e1bfabcb081d6a3e6bd8e` |
| `queue-workspace.tsx`      | `c9a64a85d2d7fd4f3a806213d9732959fc65a9cdc223e0e4ea4310da0f1e70b7` |
| `queue-policy-control.tsx` | `cc2ec6ec4ef191594ce775374f491523f6d4bbcf51fe9fe4961b7037b8de5116` |

## O. Frontend/static gates

| Gate                               | Result                        |
| ---------------------------------- | ----------------------------- |
| Frontend unit                      | PASS — 296 passed in 33 files |
| TypeScript                         | PASS                          |
| ESLint                             | PASS, zero warnings           |
| Prettier                           | PASS                          |
| Production build                   | PASS                          |
| Broker quote focused unit coverage | PASS — 13 passed              |
| `git diff --check`                 | PASS                          |

One watchlist unit test exceeded its five-second limit only while unit, TypeScript, ESLint, and Prettier gates were intentionally run concurrently. The unchanged test passed in the isolated full unit rerun; no timeout was increased and no test was weakened.

## P. Full browser matrix

| Browser  | 390  | 768  | 1024 | 1440 | 1920 | 2560 | Total                                |
| -------- | ---- | ---- | ---- | ---- | ---- | ---- | ------------------------------------ |
| Chromium | PASS | PASS | PASS | PASS | PASS | PASS | 214 passed, 8 skipped, 0 failed      |
| WebKit   | PASS | PASS | PASS | PASS | PASS | PASS | 213 passed, 9 skipped, 0 failed      |
| Combined | PASS | PASS | PASS | PASS | PASS | PASS | **427 passed, 17 skipped, 0 failed** |

The OE-4 Queue scenario passed all 12 engine/width combinations.

## Q. Remaining skips

All 17 skips are explicit applicability partitions, not failure suppression:

| Spec                                                      | Browser/widths                        | Count | Reason                                                                                                        | Status |
| --------------------------------------------------------- | ------------------------------------- | ----: | ------------------------------------------------------------------------------------------------------------- | ------ |
| `discovery.spec.ts` desktop two-panel empty-evidence case | Chromium and WebKit at 390, 768, 1024 |     6 | desktop-specific layout check; the preceding Candidate Ledger journey covers these compact widths             | valid  |
| `futures-ux-parity.spec.ts` catalog-failure case          | every project except Chromium 1440    |    11 | one representative viewport performs the API-failure contract; the main parity case covers every engine/width | valid  |

No skip was added for WebKit. The total skip count decreased from 19 to 17.

## R. Exact files changed

Browser environment and frontend production:

- `apps/web/playwright.config.ts`
- `apps/web/src/components/shell/primary-navigation.tsx`
- `apps/web/src/lib/broker-quotes.ts`

Fixtures and browser assertions:

- `apps/web/tests/browser/auth-test-server.mjs`
- `apps/web/tests/browser/brokers.spec.ts`
- `apps/web/tests/browser/derivatives-scanner.spec.ts`
- `apps/web/tests/browser/discovery.spec.ts`
- `apps/web/tests/browser/options.spec.ts`
- `apps/web/tests/browser/scanner-v2.spec.ts`
- `apps/web/tests/browser/shell-design.spec.ts`
- `apps/web/tests/browser/shell.spec.ts`
- `apps/web/tests/browser/theme.spec.ts`
- `apps/web/tests/browser/ux-blue-white.spec.ts`
- `apps/web/tests/browser/watchlists.spec.ts`

Documentation:

- `docs/TWF_OE4_BROWSER_GATE_REMEDIATION_REPORT.md`
- `docs/TWF_OE4_INDEPENDENT_ADVERSARIAL_REVIEW.md` (append-only remediation status; original FAIL retained)

Generated Playwright results remain ignored and untracked.

## S. Failure matrix

| Spec/family                                    | Browser  | Width                                   | Original failure                                       | Classification                             | Root cause                                                       | Change made                                          | Final result |
| ---------------------------------------------- | -------- | --------------------------------------- | ------------------------------------------------------ | ------------------------------------------ | ---------------------------------------------------------------- | ---------------------------------------------------- | ------------ |
| all applicable specs                           | WebKit   | all six                                 | internal error at first navigation                     | WEBKIT_ENVIRONMENT                         | Snap core20 GIO module path loaded incompatible `libpthread`     | remove inherited `GIO_MODULE_DIR` for browser launch | PASS         |
| Broker positions                               | Chromium | all six                                 | shifted/mismatched cell expectations                   | STALE_EXPECTATION                          | accepted ownership column added                                  | assert ownership and current operational cells       | PASS         |
| Derivatives exact contract                     | Chromium | all six                                 | historical direct Broker preview                       | STALE_EXPECTATION                          | accepted destination is trusted TWF Order preview                | assert exact TWF preview and no submission           | PASS         |
| Discovery main + representative chart          | Chromium | all six plus two representative         | old Scan & Discover surface absent                     | STALE_EXPECTATION                          | route now hosts Candidate Ledger                                 | test current ledger/evidence/responsiveness          | PASS         |
| Options Analytics                              | Chromium | all six                                 | shared account/callback conflict; old preview contract | TEST_FIXTURE plus latent STALE_EXPECTATION | fixture identity collision; accepted TWF Order destination       | unique identity/token; assert current exact preview  | PASS         |
| Scanner V2                                     | Chromium | all six                                 | `Confirm` button absent                                | STALE_EXPECTATION                          | accepted action is `Create TWF Order`                            | assert current preview boundary                      | PASS         |
| Shell navigation                               | Chromium | all six                                 | expected 17 links                                      | STALE_EXPECTATION                          | accepted navigation has 16                                       | retain semantic destination checks; update count     | PASS         |
| Shell reduced-motion/theme                     | Chromium | all six                                 | expected dark scheme                                   | STALE_EXPECTATION                          | accepted default is light                                        | assert light plus accessibility state                | PASS         |
| Theme                                          | Chromium | all six                                 | expected initial dark                                  | STALE_EXPECTATION                          | accepted initial light                                           | verify dark/light toggle and persistence             | PASS         |
| Blue-white workspaces                          | Chromium | all six                                 | shared user and cross-navigation errors                | TEST_FIXTURE                               | fully parallel identity collision and unsettled prior navigation | dedicated identities; settle then scope page errors  | PASS         |
| Watchlist ticket                               | Chromium | all six                                 | `Confirm Buy` absent                                   | STALE_EXPECTATION                          | accepted TWF Order preview                                       | assert `Create TWF Order`, zero submissions          | PASS         |
| Broker quote polling (remediation discovery)   | both     | load-dependent                          | fresh quote cleared after slow response                | ACTUAL_PRODUCT_DEFECT                      | next poll paced from request start                               | pace from completion                                 | PASS         |
| planned-route prefetch (remediation discovery) | WebKit   | all widths under logout/navigation load | access-control page errors from abandoned RSC requests | ACTUAL_PRODUCT_DEFECT                      | protected planned routes prefetched despite being placeholders   | disable prefetch only on planned links               | PASS         |

## T. Scorecard

```text
OE4_BROWSER_REMEDIATION_STATUS = PASS

ORIGINAL_BROWSER_GATE_REPRODUCED = PASS
FAILURES_CLASSIFIED = PASS

WEBKIT_ROOT_CAUSE_IDENTIFIED = PASS
WEBKIT_ENVIRONMENT_FIXED = PASS
WEBKIT_LOGIN_NAVIGATION = PASS
WEBKIT_QUEUE_SCENARIO = PASS
WEBKIT_FULL_MATRIX = PASS

CHROMIUM_STALE_ASSERTIONS_IDENTIFIED = PASS
CHROMIUM_STALE_ASSERTIONS_UPDATED = PASS
CHROMIUM_FULL_MATRIX = PASS

NO_ACCEPTED_UX_REGRESSION = PASS
NO_OE4_BACKEND_SEMANTIC_CHANGE = PASS
NO_TEST_WEAKENING = PASS
NO_MASS_SKIPS = PASS

BROWSER_FIXTURE_POSTGRES_ISOLATED = PASS
NO_LIVE_DB_CONTAMINATION = PASS
NO_LIVE_BROKER_ORDER = PASS

OE4_CRITICAL_SAFETY_SPOTCHECK = PASS

FRONTEND_UNIT = PASS
TYPESCRIPT = PASS
ESLINT = PASS
PRETTIER = PASS
BUILD = PASS

FULL_BROWSER_GATE = PASS
FULL_BROWSER_FAILED_COUNT = 0

GIT_DIFF_CHECK = PASS

OE4_READY_FOR_FINAL_REREVIEW =
    YES
```

## U. Final status

This remediation closes only the browser-gate blocker. It does not freeze OE-4, start OE-5, enable live execution, or change Queue/Broker semantics. The next permitted step is the independent OE-4 Final Focused Re-review and Freeze Decision.

```text
OE4_BROWSER_REMEDIATION_STATUS = PASS
OE4_READY_FOR_FINAL_REREVIEW = YES
```
