# TWF-1.1A — Theme Switching Foundation

Status: **implemented, pending independent review**. Recommendation: `GO_TWF1_1A_REVIEW`.

## Baseline and rationale

Preflight verified a clean `main`, equal to `origin/main`, at
`bc7847982162e7c75aea7c39049e19f80c546a17`. The accepted
`twf-1.1-frontend-shell` tag resolves to that commit. This bounded enhancement
adds a professional light palette for user preference while keeping dark the
primary/default trading theme. The historical TWF-1.1 record is preserved.

Governing sources: [responsive application architecture](TWF_RESPONSIVE_TRADING_APPLICATION_ARCHITECTURE.md),
[UX architecture](TWF_UX_ARCHITECTURE.md), and the
[shell implementation record](TWF_TWF1_1_FRONTEND_SHELL.md).

## Theme architecture and persistence

All existing dark tokens are unchanged. Light overrides live alongside them in
`tokens.css`, selected by `html[data-theme="light"]`. The palette combines a soft
neutral page, off-white panels, gray-green raised surfaces, charcoal text, subtle
borders, and restrained semantic colors. Spacing, typography, panel contracts,
responsive breakpoints, and workflow meaning do not change.

`ThemeToggle` is a small client component in the top bar. Its native button has
the stable accessible name **Light theme** and `aria-pressed` indicates whether
light is enabled. Activating it again restores dark. The target is 44×44 pixels.
No global provider or dependency was added; `useSyncExternalStore` observes a
document-level theme attribute through a local change event.

Selection is stored under the browser-local `twf-theme` key. Only the literal
`light` selects light; absent, invalid, or inaccessible storage defaults to dark.
Storage exceptions are contained: the current page can still switch, although
the choice cannot survive reload if storage is blocked. The preference is scoped
to the browser origin, not an authenticated user. Existing open tabs are not
synchronized; a reload restores the most recently stored choice.

A tiny static script in the document head restores the preference before body
paint. It contains no interpolated user content. Only the root HTML attribute
uses `suppressHydrationWarning`, because this intentional pre-hydration change
can differ from the dark server output. The control uses the dark server snapshot
and then reads the initialized attribute, avoiding a React hydration mismatch.
Browser tests also block hydration bundles to verify that saved light restoration
works independently of React. If JavaScript is unavailable, CSS remains dark.

There is no added theme animation; existing interaction transitions and the
reduced-motion contract remain in effect. A future restrictive Content Security
Policy must authorize this static initializer with a hash or nonce; no CSP or
deployment policy was changed for this target.

## Accessibility and visual review

The native toggle supports keyboard and touch, visible focus, a tooltip, and
an explicit pressed state. Existing status labels and disabled navigation remain
unchanged, so theme colors never replace semantic text.

Minimum light-theme contrast ratios across page, normal, raised, hover, and
accent surfaces were calculated from the centralized sRGB tokens:

| Foreground | Minimum ratio |
|---|---:|
| Primary text | 11.36:1 |
| Secondary text | 6.25:1 |
| Muted text | 4.87:1 |
| Accent / ready | 5.65:1 |
| Focus | 6.08:1 |
| Stale / warning | 5.31:1 |
| Error | 5.51:1 |
| Loading | 5.27:1 |
| Neutral status | 5.00:1 |

Light screenshots were inspected at 390, 768, 1024, 1440, 1920, and 2560px.
Panel hierarchy, dense typography, restrained state colors, and console styling
retain the trading-oriented character. Mobile disclosure, tablet context stacking,
desktop context rail, and ultrawide width constraints remain intact. Browser tests
confirm identical main-workspace geometry before and after switching and no
horizontal overflow. Dark mode retains its original palette and shell geometry.
This is baseline accessibility and visual review, not a full assistive-technology
certification or independent acceptance.

## Validation and browser considerations

| Check | Result |
|---|---|
| Type-check | Pass |
| ESLint | Pass, zero warnings |
| Unit tests | 22 pass across three files |
| Prettier check | Pass |
| Production build | Pass |
| Chromium Playwright | 30 pass across all six widths |
| Web Docker build | Pass, `twf-web:twf1-1a-review` |
| `git diff --check` | Pass |

New unit coverage checks dark default, accessible toggle state, both switching
directions, persisted dark/light, invalid preference fallback, and blocked storage.
New browser coverage checks keyboard switching, persistence after reload, no
page/hydration errors, geometry preservation, light color-scheme, overflow, and
pre-hydration restoration. Existing shell tests still run in dark mode. The suite
deliberately emulates an OS light preference to prove that product default remains
dark. Reproduction from `apps/web`:

```bash
npm run type-check
npm run lint
npm test
npm run format:check
npm run build
npm run test:e2e -- --project='chromium-*'
```

Screenshots are generated in ignored `test-results` directories as `shell.png`
and `light.png`; no visual regression infrastructure or cloud browser service was
added. The previously documented `next start` standalone advisory remains; Docker
continues to use the standalone server.

Implementation uses standard CSS custom properties, `color-scheme`, DOM attributes,
events, and guarded localStorage, without Chromium-specific APIs. The independent
TWF-1.1 review isolated the existing WebKit HTTP-navigation failure using a minimal
non-TWF server. That host/runtime limitation remains outstanding and was not
re-investigated here. Chromium success does not verify Safari/WebKit; rerun the
configured suite on a supported WebKit host before browser release certification.

## Exact changes and non-goals

- `apps/web/src/app/layout.tsx` — root attribute and pre-paint initializer.
- `apps/web/src/components/shell/app-shell.tsx` — remove obsolete fixed dark attribute.
- `apps/web/src/components/shell/top-bar.tsx` — mount theme control.
- `apps/web/src/components/shell/theme-toggle.tsx` — accessible local toggle.
- `apps/web/src/lib/theme.ts` — storage key and static initializer.
- `apps/web/src/styles/tokens.css` — centralized light overrides.
- `apps/web/src/styles/shell.css` — theme-control styling only.
- `apps/web/tests/theme.test.tsx` — preference and control unit coverage.
- `apps/web/tests/browser/theme.spec.ts` — responsive theme and initialization checks.
- `README.md` and `docs/TWF_DOCUMENTATION_INDEX.md` — preserve hierarchy, record accepted shell and current enhancement.
- `docs/TWF_TWF1_1A_THEME_SWITCHING_FOUNDATION.md` — this record.

No System mode, authentication, profile settings, backend/API/database work,
integrations, charts, realtime, billing, layout redesign, or UI framework was added.
Package manifests and lockfiles are unchanged. No commit, tag, or push was performed.
Next step is independent TWF-1.1A review; the next planned foundation target remains
TWF-1.2 Backend Shell.
