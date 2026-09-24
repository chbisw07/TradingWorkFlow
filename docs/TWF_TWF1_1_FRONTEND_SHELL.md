# TWF-1.1 — Frontend Shell implementation record

Status: **implemented, pending independent review**. Recommendation: `GO_TWF1_1_REVIEW`.
This is implementation evidence, not independent acceptance. Next implementation
target after review: **TWF-1.2 Backend Shell**.

## Baseline and scope

Preflight passed before implementation: branch `main`, clean working tree,
local HEAD equal to `origin/main` at `7fd55a83098c91daa4452ecbecc8eac34da55947`.
Accepted scaffold commit: `5e46f7f`; architecture tag:
`twf-0-architecture-baseline` (ref `ec93331ee2fb50d3338a97d3bafa7b12c8e25cab`).
The prior untracked architecture clarification was committed before this resumed work.
No commit, tag, or push was performed for TWF-1.1.

The [responsive trading application architecture](TWF_RESPONSIVE_TRADING_APPLICATION_ARCHITECTURE.md)
and [UX architecture](TWF_UX_ARCHITECTURE.md) govern the shell. The accepted
[TWF-1.0 record](TWF_TWF1_0_REPOSITORY_PROJECT_SCAFFOLD.md) remains historical.

## Structure and behavior

The App Router root layout renders `AppShell`: top bar, primary navigation,
main workspace, contextual panels, collapsible console, and development status.
`FoundationView` provides an honest empty workspace preview. Unsupported nav
entries are disabled and labelled coming later; no fake business routes exist.
App Router loading, error/retry, and not-found/recovery views reuse state primitives.

The top bar reserves user, workspace, broker, market/session, active LLM, alerts,
and service context. Service rows cover TWF API, Scanner, TI, TM, LLM, and Broker.
All states explicitly describe development placeholders; no health calls run.
Only navigation disclosure and console expansion own client state. The root shell
is not a global client-state container. Layout changes preserve the same components
and workflow semantics.

`Panel` provides a labelled section and independently focusable, scrollable body,
with zero minimum sizing and bounded vertical overflow. Future chart/table/live
content can measure this body and own local state. Browser probes verify oversized
children scroll locally without widening the document. No chart, virtualization,
streaming, docking, or global-state library is included.

## Responsive composition and visual review

| Width | Composition | Chromium | WebKit |
|---|---|---|---|
| 390 | Disclosure navigation; single-column workspace/context; full-width console control | 3/3 pass | Runtime blocked |
| 768 | Compact labelled navigation rail; workspace first; two context panels below | 3/3 pass | Runtime blocked |
| 1024 | Compact rail; stacked workspace/context row | 3/3 pass | Runtime blocked |
| 1440 | Full navigation; workspace and right context; bottom console | 3/3 pass | Runtime blocked |
| 1920 | Wider context allocation and bounded text; modest spacing increase | 3/3 pass | Runtime blocked |
| 2560 | Workspace maximum 112rem; controlled panel ratios and outer breathing room | 3/3 pass | Runtime blocked |

Breakpoints are below 700px, below 1200px, and at 1920px. Navigation and actionable
controls have touch-friendly minimum sizing. Mobile permits deliberate vertical
scrolling to context and console, not an entire compressed desktop cockpit.

Rendered Chromium screenshots were inspected at all six widths. The 390px review
caught a service-panel width inconsistency; it was corrected and re-inspected.
The result has restrained dark surfaces, clear hierarchy, compact navigation,
readable bounded copy, and consistent borders. Focus visibility is evident in the
console screenshot. First-frame quality is judged professional/premium for this
bounded preview; generic admin dashboard feel is NO. These are implementation
review judgments, still subject to independent review. There are no fabricated
metrics, charts, activity, or trade controls.

Screenshots are reproducible under `apps/web/test-results/`, in each
`shell-shell-recomposes-…-<browser>-<width>/shell.png` directory. Test artifacts
are ignored, not committed. This is smoke coverage, not visual regression infrastructure.

## Theme and accessibility

`tokens.css` centralizes surfaces, borders, text, semantic state colors, type,
spacing, focus, radii, elevation, motion, and layout widths. `shell.css` supplies
component layout and responsive rules. No component contains arbitrary hex colors.
Dark mode is explicit; reduced-motion disables transitions/animations and smooth
scrolling. Fonts are system fonts with no external asset dependency.

State primitives cover LOADING, EMPTY, READY, STALE, UNAVAILABLE, ERROR,
DISCONNECTED, and COMING_SOON. Labels communicate state without relying on color.
Loading exposes busy state; errors use alert semantics; other state surfaces use
status semantics. Icons are decorative. The shell has semantic navigation/main,
labelled context and console, a skip link, visible focus, native disabled controls,
and Escape focus return from mobile navigation. Error details are not exposed.
Keyboard/landmark tests pass; this is an accessibility baseline, not a complete
screen-reader or WCAG certification.

## Browser compatibility and limits

Layout uses Grid/Flexbox, media queries, native controls, and CSS custom properties.
A `100vh` fallback precedes `100dvh`. There are no Chromium-specific application
APIs. Modern Chromium/Edge/Android Chrome and Safari/WebKit/iOS/iPadOS remain
architectural targets. Device emulation is not physical-device certification.

Playwright 1.63.0 is the sole new direct development dependency. Its minimal
configuration runs Chromium and WebKit at all six widths with two workers and
retains failure traces. The production build serves tests on loopback port 3100;
existing servers are not reused. `next start` emits the known standalone-output
advisory; the independently tested Docker runtime uses the proper standalone server.

Chromium: **18/18 pass**, no uncaught page errors in shell smoke checks.
WebKit: **18/18 could not complete**. Download succeeded, but this host lacked
`libmanette-0.2.so.0`. Passwordless system installation was unavailable. Extracting
the Ubuntu package under `/tmp/twf-webkit-libs` and preloading it allowed launch,
but navigation failed with `WebKit encountered an internal error`. The launcher
overrides `LD_LIBRARY_PATH`; the preload workaround is not repository configuration.
No WebKit acceptance is claimed. Repeat on a supported host with standard browser
dependencies before cross-browser release acceptance. This disclosed limitation is
permitted for the bounded independent-review handoff by the TWF-1.1 prompt.

Reproduction from `apps/web`:

```bash
npm ci
npx playwright install --with-deps chromium webkit
npm run build
npm run test:e2e
# Chromium-only diagnosis:
npm run test:e2e -- --project='chromium-*'
```

The install-with-deps command may require system administrator privileges.
Technical references: [Playwright configuration](https://playwright.dev/docs/test-configuration),
[Next error boundary](https://nextjs.org/docs/app/api-reference/file-conventions/error),
and [Next not-found](https://nextjs.org/docs/app/api-reference/file-conventions/not-found).

## Validation evidence

| Check | Result |
|---|---|
| Fresh `npm ci` | Pass, 450 packages installed |
| `npm run type-check` | Pass |
| `npm run lint` | Pass, zero warnings |
| `npm test` | Pass, 14 tests in two files |
| `npm run format:check` | Pass |
| `npm run build` | Pass, static home and not-found |
| `npm audit` | Zero vulnerabilities |
| `npm ls --all` | Completes; existing optional Sharp/WASM extraneous entries remain |
| Chromium responsive smoke | 18 pass across all six widths |
| WebKit responsive smoke | Environment/runtime limitation above; not accepted |
| Docker web rebuild | Pass, `twf-web:twf1-1-review` |
| Docker smoke | Home HTTP 200 with shell; CSS and three JS assets HTTP 200 |
| Repository whitespace and local documentation links | Pass |
| Scope/secret hygiene | Frontend and documentation only; no secrets or generated artifacts added |

Unit coverage includes shell landmarks, nav state, service placeholders, console
toggle, all eight state variants, safe error retry, and not-found recovery.
Browser coverage includes mobile tap/Escape, keyboard console toggle, route recovery,
reduced-motion, skip-link focus, responsive region geometry, local overflow, and
page overflow. Initial selector and landmark failures were corrected before the
reported passing results. Backend/shared configuration is unchanged, so backend
checks were not rerun. The temporary smoke container was stopped and removed.

Lock changes add only Playwright and its two packages; no existing package versions
were upgraded. Optional `@img/sharp-wasm32@0.35.4` and `@emnapi/runtime@1.11.3`
remain reported extraneous after clean installation. No risky lockfile normalization
was attempted. Existing ESLint and whatwg-encoding deprecation notices remain
non-blocking; the audit is clean.

## Portability and non-goals

The shell introduces no localhost service endpoints, filesystem data dependencies,
auth/session assumptions, external fonts, or cloud-specific semantics. Relative
application navigation and the existing standalone image preserve reverse-proxy,
HTTPS, remote service, and later multi-user deployment options. Database migration
and PostgreSQL remain backend concerns unaffected by this work.

No authentication, watchlist/scanner/candidate logic, TI/TM/LLM/broker integration,
orders/positions, charts, grids, realtime, subscriptions, billing, or backend changes
were implemented. No UI component library was added.

## Exact file inventory

- `README.md`
- `apps/web/.gitignore`
- `apps/web/.prettierignore`
- `apps/web/eslint.config.mjs`
- `apps/web/package-lock.json`
- `apps/web/package.json`
- `apps/web/playwright.config.ts`
- `apps/web/src/app/error.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/app/layout.tsx`
- `apps/web/src/app/loading.tsx`
- `apps/web/src/app/not-found.tsx`
- `apps/web/src/app/page.tsx`
- `apps/web/src/components/shell/app-shell.tsx`
- `apps/web/src/components/shell/console-region.tsx`
- `apps/web/src/components/shell/context-panel.tsx`
- `apps/web/src/components/shell/foundation-view.tsx`
- `apps/web/src/components/shell/icon.tsx`
- `apps/web/src/components/shell/primary-navigation.tsx`
- `apps/web/src/components/shell/top-bar.tsx`
- `apps/web/src/components/ui/panel.tsx`
- `apps/web/src/components/ui/surface-state.tsx`
- `apps/web/src/styles/shell.css`
- `apps/web/src/styles/tokens.css`
- `apps/web/tests/browser/shell.spec.ts`
- `apps/web/tests/page.test.tsx`
- `apps/web/tests/shell.test.tsx`
- `docs/TWF_DOCUMENTATION_INDEX.md`
- `docs/TWF_TWF1_1_FRONTEND_SHELL.md`
