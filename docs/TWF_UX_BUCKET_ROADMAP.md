# TWF UX Bucket Roadmap

## Status and purpose

**Normative cross-cutting UX plan, version 0.2, reconciled on 2026-09-26.**

UX-B1, UX-B2 and UX-B3 track the completeness of the user experience across
functional milestones. They preserve the accepted trading application design
language while allowing panel content and workflow details to evolve with real
Scanner, TI and TM contracts. They do not replace the TWF milestone sequence or
authorize implementation outside a bounded target.

The [configuration architecture v0.6](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md)
governs settings, realms, capabilities and authority. The
[UX architecture](TWF_UX_ARCHITECTURE.md) and
[responsive application architecture](TWF_RESPONSIVE_TRADING_APPLICATION_ARCHITECTURE.md)
govern workspace semantics, visual quality and recomposition. The
[detailed roadmap](TWF_DETAILED_ROADMAP.md) owns functional sequencing.

## Current position

| Track | Current evidence | Remaining work |
|---|---|---|
| UX-B1 | Partial: accepted shell, themes, login and TWF-1.5 settings; accepted TWF-1.6 status | Broader Setup, console behavior and bucket acceptance |
| UX-B2 | Planned; shell containers provide readiness only | Operational settings and trader workflows as TWF-2–7 mature |
| UX-B3 | Planned architecture hooks | Mature APS/ACS administration, subscriptions, diagnostics, IFL and operations |

TWF-1.5 is **accepted and committed at `664d4cf`**; see its historical
[implementation record](TWF_TWF1_5_SETTINGS_FOUNDATION.md). Its personal Settings and
profile surface advances partial UX-B1. The
[TWF-1.6 foundation](TWF_TWF1_6_SERVICE_CLIENT_FOUNDATION.md) adds on-demand configured
service status and explicitly labeled synthetic fixtures, accepted at `e3852d3`.
The existing `twf-1-application-foundation` tag closes TWF-1, not the whole UX bucket.
No bucket is declared complete by this work.
The existing WebKit host/runtime limitation remains an explicit verification gap;
Chromium evidence does not establish Safari compatibility.

## UX-B1 Foundational Complete UX

The application should feel coherent and professional before real trading
integrations are available. Home presents actual foundation/service state and a
useful next action; it must not invent P&L, trades, account privileges or live health.

Scope includes shell, login/logout/current user, responsive navigation, home,
Setup skeleton, appearance and basic user/workflow settings, personal profile
foundation, a read-only capability view, honest service status, a read-only console
foundation and the accessibility baseline. Most service data may be synthetic/local.

Work/Administration distinction means clear context and truthful availability.
Before administrative backend functionality exists, an unavailable preview or a
documented navigation design satisfies the foundation requirement. A fake role
toggle, fake save or client-only privilege grant does not. Production APS/ACS
administration is not required to close UX-B1.

### Acceptance criteria

1. A provisioned user can log in, identify the current user, navigate permitted
   surfaces, log out and recover from an expired session. Protected routes and
   data are enforced by the backend, with no stale identity shown after user switch.
2. Home and navigation preserve workspace/instrument context where it exists.
   Unimplemented features are labelled coming soon/unavailable with no deceptive
   actions; browser back/forward, active-route labels and keyboard focus are usable.
3. Setup provides an understandable feature/category entry, breadcrumbs or back
   navigation, clear owner/scope, and save/cancel/reset behavior for implemented
   settings. Unsupported scopes are not represented as working features.
4. Persisted appearance and safe workflow preferences have typed validation,
   defaults, visible save/failure state and ownership isolation. Dark remains the
   default. Both themes preserve density, contrast, semantic colors and the accepted
   first-paint/hydration behavior; user/device preference precedence is tested.
5. The bounded personal profile foundation demonstrates create/edit, validation,
   selection/apply, deactivate and reset where supported. The selected revision
   and effective/applied values are distinguishable. A stale edit cannot silently
   overwrite another tab's change. Clone/import/export may remain later work.
6. Read-only capability/status views distinguish deployed, synthetic, coming soon,
   disabled, unauthorized and unavailable. Catalog visibility does not confer use
   permission. No internal capability or secret information leaks in a public card.
7. Service status includes source and observation time when observed. Placeholder
   state never claims a successful remote probe. The API's application-only `/ready`
   semantics remain explicit and separate from satellite health.
8. A read-only console foundation displays deterministic local/synthetic events
   with timestamp, source, severity and correlation, and usable bounded overflow.
   Empty/error/disconnected views are testable. Arbitrary shell commands and real
   streaming infrastructure are not foundation requirements.
9. All eight accepted primitives — LOADING, EMPTY, READY, STALE, UNAVAILABLE, ERROR,
   DISCONNECTED and COMING_SOON — have accessible examples and meaningful recovery
   or explanation. Disabled controls have reasons. Permission denial, incompatible
   versions and degraded service are explicit refinements, not silent empty data.
10. Both themes recompose at 390, 768, 1024, 1440, 1920 and 2560+ widths. Mobile
    uses nested views; tablet reduces simultaneous panes; large displays use extra
    context without inflating controls. Save/cancel, scope, validation and status
    stay reachable without document-wide horizontal scrolling. Wide data regions
    may scroll locally, retaining labels and context.
11. Keyboard-only navigation, visible focus, logical headings/landmarks, named
    controls, readable contrast, non-color status meaning, reduced motion and
    touch targets pass automated and manual review. Announcements describe errors
    and apply results without continuously interrupting screen readers.
12. Chromium and WebKit checks cover affected navigation, layout and theme flows.
    A host/runtime failure is documented separately from an application defect;
    affected browser acceptance remains unverified until run on a supported host.
13. Acceptance evidence includes rendered reviews, interaction/negative tests and
    exact implemented versus deferred surfaces. Fixtures cannot be mistaken for
    real orders, entitlements, secrets or working administration. Visual review
    confirms the restrained trading workspace character rather than generic metrics
    cards or an administration dashboard template.

Each functional target proves its applicable subset. Complete UX-B1 acceptance
requires the remaining foundation surfaces, including the TWF-2.4 console, without
holding TWF-2/3 work until every bucket item is closed.

## UX-B2 Operationally Useful Trading UX

UX-B2 makes the trader workspace useful as service contracts mature. It includes
hierarchical Setup, provider configuration, named profiles, HOT/WARM application,
connection tests, secret-reference status, effective-value explanations, relevant
account configuration, watchlists, candidates, Scanner results, TI results, TM
state, notifications and audit/history.

Account-level controls ship only when account ownership and backend permission
checks exist. Until then, personal/local configuration can support the trading
path. The lack of a full account administration portal is not a reason to invent
one or to block synthetic core workflows.

### Acceptance criteria

1. A user can move from watchlist or Scanner result to a selected candidate,
   inspect TI claims/evidence/horizon and actual producer identity, then review
   TM risk/authority and a governed manual handoff. Each surface appears under its
   functional milestone; TWF never manufactures TM approval or broker truth.
2. Setup follows feature → provider/capability → profile. Forms use central typed
   descriptors; required dependencies, permissions, rollout and entitlement are
   explained without leaking hidden catalog entries. Disabled use does not hide
   authorized repair/enable controls.
3. Profiles show desired, effective and applied revisions. HOT apply gives immediate
   confirmed feedback. WARM apply shows validating/applying/success/failure and the
   last known applied revision; rollback is reported only if verified. Editing,
   reset and activation enforce concurrency checks and preserve unsaved work.
4. Secret UX shows ownership and configured/expired/revoked state without reading
   raw credentials. Authorized connection tests return bounded, sanitized results.
   Broker connection configuration respects the manual adapter secret boundary and
   the separate TM-managed authority path in [Broker Workspace v0.3](TWF_BROKER_WORKSPACE_ARCHITECTURE.md#183-manual-execution-and-managed-execution).
5. Scanner/TI/TM surfaces preserve timestamps, provenance, stale/denied/incompatible
   and degraded states. Retry, reconnect and cancellation have honest outcomes;
   remote failure cannot freeze navigation or silently change provider identity.
6. Notifications and history expose relevant action/result/correlation. Entitlement
   loss makes retained profiles inactive and prevents new gated work, while existing
   broker exposure follows the active command owner's separately accepted safety
   policy; manual unmanaged orders are not presumed to have TM supervision.
7. Applicable UX-B1 accessibility, themes, responsive and browser gates continue to
   pass with realistic dense tables and long results. Selection and authority meaning
   survive panel rearrangement and mobile/tablet recomposition.
8. Contract tests run equivalent synthetic/real adapter scenarios where real adapters
   exist. Synthetic success remains labelled and cannot be presented as acceptance
   of live service behavior. Actual TM public-contract reconciliation remains mandatory.

Layouts, field details, table columns and workflow steps may evolve with TWF-3/4/5
contracts. Preserve design tokens, panel responsibilities, semantics and source
identity; do not freeze trading details ahead of those contracts.

### Broker Workspace contribution

[Broker Workspace v0.3](TWF_BROKER_WORKSPACE_ARCHITECTURE.md) is a major UX-B2 workstream.
BW-1 synthetic read-only rooms precede one real broker, native search/watchlists,
draft/preview, synthetic recovery and separately gated live manual execution.
Broker Watchlists belong to explicit account rooms; the future canonical Global
Watchlist remains separate. Real provider cards expose deployed/eligible/configured/
enabled/auth/read/command status without pretending that connection grants trade rights.

Keep provider, account alias/masked reference and LIVE/SYNTHETIC/SANDBOX mode obvious
on every room/action. Overview reads/aggregates/navigates only, never routes an order.
Render source/as-of, stale/partial/unmapped contributions, unsupported capability,
pending commands and unknown submission without claiming success. Order previews
bind an exact account/instrument/revision and expire on context change. Manual
execution remains unmanaged; a TM-managed room disables competing direct commands.

Use existing themes, accessible tables/announcements and six-width recomposition.
Test actual account context after room switches, error recovery, keyboard operation
and request races. BW-1 does not implement later command interactions; each gate
must add evidence for its own UX. Provider neutrality needs a second adapter proof,
not a second provider logo. Advanced operations, bulk administration and commercial
broker quota diagnostics contribute to UX-B3 later; they do not block BW-1.

## UX-B3 Architecture-Complete UX

UX-B3 progressively covers mature APS operations, ACS account administration,
role/permission management, subscriptions/entitlements, rollout/beta/feature policy,
advanced Setup, profile clone/import/export, schema migration and rollback/history,
support access, diagnostics, service/plugin health, advanced consoles, accessibility
and mobile/tablet refinement, workspace customization, IFL/history/performance and
operational dashboards.

### Acceptance criteria

1. APS and ACS present distinct authenticated contexts, realm/account labels and
   scoped navigation. Work/Admin changes presentation only. Backend negative tests
   prove no direct or indirect role elevation and no default APS tenant-data access.
2. Role assignment follows bounded delegation and separate approval. Account
   ownership transfer, last-admin protection and service identities have explicit
   policies. Owner break-glass and support sessions show real operator, approved
   reason, scope, expiry, consent basis and audit; no silent impersonation.
3. Subscription and rollout views explain what is available and why. Upgrades,
   downgrades, expiry, suspension and restored entitlement retain configuration
   correctly and revalidate use. Price/plan labels never function as authority.
4. Advanced profile operations preserve ownership, schemas, provenance and revisions.
   Exports exclude secrets; imports validate and require secret rebinding. Migrations
   show compatibility/failure recovery; rollback never implies reversal of broker actions.
5. Diagnostics distinguish config, policy, health and runtime observations. Explain
   responses and consoles redact secrets, endpoints and other tenants' data. Platform
   operations are explicit governed commands, not arbitrary Settings fields.
6. IFL/history/performance retain the separation between intelligence quality,
   authority decisions and execution outcome. Mature customization and additional
   mobile workflows preserve that meaning and do not create a second authority.
7. Each released surface passes realistic load, accessibility and supported-browser
   review, including keyboard/screen-reader, dense data and touch workflows. Basic
   accessibility is required from UX-B1; UX-B3 deepens coverage rather than postponing it.

Complete bucket acceptance requires the declared mature release scope to be
implemented and reviewed. Individual features can ship earlier when justified;
all UX-B3 work is never a prerequisite for TWF-3/4/5 integration.

## Mapping to functional milestones

| Functional delivery | UX contribution | Dependency boundary |
|---|---|---|
| TWF-1.0, 1.1, 1.1A | Tooling, shell, state primitives, themes; partial UX-B1 | Already accepted; retain regression evidence |
| TWF-1.2, 1.3, 1.4 | API/persistence/identity supporting UX-B1 | No automatic tenant/admin authority |
| Architecture reconciliation | Configuration v0.6 and this plan | Design checkpoint before TWF-1.5, no runtime delivery |
| TWF-1.5 | Personal settings, Setup/profile foundation; advances UX-B1 | Finite bounded contract; no full SaaS administration |
| TWF-1.6 | Capability/client/status and synthetic foundations; advances UX-B1 | Payload detail stays with each integration target |
| TWF-2 | Broker BW-1–3 workspace/watchlist progression plus TWF-2.4 console; partial UX-B1 closure and UX-B2 | Synthetic first; real broker and persistent mutations have separate gates |
| TWF-3 | Scanner/candidate UX-B2 | Scanner contract and provenance |
| TWF-4 | TI/active LLM/profile UX-B2 | Typed intelligence and provider/secret boundary |
| TWF-5 | TM risk/authority/monitoring UX-B2 | Committed TM contract gate; manual approval and broker truth |
| TWF-6 | BW-4/5 command safety/recovery ahead of full intelligence/TM workflow acceptance | Synthetic recovery first; controlled live manual orders do not imply managed workflow or UX-B2 completion |
| TWF-7 | Realtime, notification and stale/reconnect UX-B2 | Authenticated topics and revocation/freshness policy |
| TWF-8 | IFL/history/performance portions of UX-B3 | Preserve external scientific and execution ownership |
| TWF-9 | Tenant/admin/subscription/support portions of UX-B3 | Ownership/realm controls before shared exposure, even if needed earlier |
| TWF-10 | Operations, diagnostics and production UX-B3 hardening | Production security, recovery and availability evidence |

Dependencies attach to the feature that needs them, not to a whole bucket number.
For example, shared profile editing requires account isolation and revision checks
before it ships, even if scheduled before TWF-9. A personal synthetic TI view need
not wait for commercial subscription management. Moving such work requires a bounded
target update and acceptance evidence, not silent expansion of TWF-1.5.

## Synthetic contract strategy

Use SyntheticScannerService, SyntheticTIService, SyntheticTMService and
SyntheticLLMService, plus the staged SyntheticBroker defined in broker v0.3,
behind the same versioned logical interfaces as future real
adapters. Keep deterministic fixtures for success, empty, timeout, error, stale,
denied, incompatible and degraded cases, with fixed identifiers/time inputs and
explicit synthetic provenance. Isolate fixture data, credentials and network access.

Contract suites verify semantics, correlation, source identity and typed failures;
UI tests verify rendering and safe interaction. Synthetic TM may simulate rejection,
approval and adoption but cannot produce live execution authority. Real adapters
must pass their public-contract reconciliation and authentication gates; fixtures
cannot declare that gate passed. No artificial randomized market metrics are needed.

## Evolution and non-goals

Bucket changes record affected contracts, ownership, viewport/browser evidence and
functional target. Preserve accepted visual tokens, authority labels and history.
Detailed trading composition may evolve through rendered review and real workflow
evidence. Track partial completion explicitly; a mock screen is not an implemented
backend capability.

This document does not implement settings, administration, billing, integrations,
plugin loading, charting, docking, realtime, broker actions or IFL. It introduces no
dependency, framework, deployment service or new freeze requirement. The historical
[configuration review](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md) records the
TWF-1.5 planning gate; the current [Broker Workspace review](TWF_BROKER_WORKSPACE_ARCHITECTURE_REVIEW.md)
records the next bounded BW-1 recommendation.
