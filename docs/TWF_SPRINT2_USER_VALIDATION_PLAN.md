# Sprint 2 Scan & Discover — user validation plan

**Product state:** IMPLEMENTED / READY FOR USER VALIDATION  
**Audience:** product owner/operator  
**Result of this plan:** observations for later adversarial review and hardening; it does not itself freeze Sprint 2

This plan reflects the **final product stabilization and scan-driven temporal-state implementation before formal user validation**.

## Before starting

1. Start the API with migrations applied and start the web application using the repository setup instructions.
2. Sign in with a non-production test user.
3. Open **Scanners** from the left navigation. Confirm the page states that discovery never authorizes a trade.
4. Confirm the sidebar is the single route navigation for **Scanners** and **Candidates**; there is no duplicate page-level Candidates destination.
5. Keep a second test user available for the isolation check. Do not use real TradingView calls for this plan.

## Validation workflows

### 1. Internal Scanner realistic-validation flow

- Leave **Provider** on **Internal Scanner V0 · synthetic**.
- Use `RELIANCE, MCX, HDFCBANK, INFY, BSE, NIFTY, BANKNIFTY` as the universe.
- Run the Relative Volume profile.
- Confirm the Relative Volume result set is narrower than the full universe and that other profiles produce meaningfully different subsets.
- Confirm prices, momentum, RVOL, relevance, evidence coverage, and explanations vary between matching instruments.
- Confirm synthetic truth appears persistently as **Synthetic Data** in the provider/status strip and no separate page-wide synthetic banner reserves space.

### 2. Profile, intent, horizon, and context policy

- Confirm **Scan profile** explains the market pattern TWF searches for.
- Select **Momentum**. Confirm the suggested purpose becomes **Positional long** with a **5 days** horizon.
- Explicitly change intent and horizon, then select another profile. Confirm both explicit choices remain unchanged.
- Select **Apply suggestion** and confirm the active profile recommendation is restored.
- Confirm **Discovery intent** explains how a match is interpreted and tracked, while **Horizon** explains how long it should remain relevant.
- Try intraday intent with `5d`, positional intent with `intraday`, and Pullback in Uptrend with short intent. Confirm concise guidance appears and **Run scan** is blocked without silently changing the selection.
- Verify Momentum and Breakout in both directions: bullish evidence may create long candidates, bearish evidence may create short candidates, and opposing evidence does not become a high-relevance candidate.
- Confirm the context choices read **Require complete context**, **Allow partial context**, and **Context optional**. Missing context must stay visible and must not be inferred as neutral. It blocks incomplete required-context admission, reduces coverage only when context participates under Allow partial, and does not reduce relevance/coverage or cause stale lifecycle under Context optional.

### 3. Workspace status, provider Mode, and Status

- Inspect the compact **Provider and evidence readiness** strip above the workstation. Confirm it includes provider readiness, current market-context state, optional AI state, and latest-scan state and does not reappear as a tall card in the setup rail.
- Confirm Internal Scanner V0 shows **Synthetic Data** mode and **Ready** status.
- Confirm TradingView separates **Validation · Synthetic** or **Live** mode from Ready, Rate limited, Authentication required, Unavailable, Disabled, or Degraded operational status.
- Confirm status is communicated in text with a dot and does not depend on color or look like a button.
- If TradingView is rate limited, confirm the strip states that live exact-row proof remains pending.

### 4. TradingView contract-validation flow

- Select **TradingView adapter · validation** and run a supported exact universe.
- Confirm the UI identifies synthetic validation data and makes no live-data claim.
- Confirm candidates retain TradingView evidence/provenance and source time remains unavailable when the provider supplied no authoritative source timestamp.

### 5. Canonical instrument identity

- In normalized results and candidate identity, confirm `NIFTY` and `BANKNIFTY` display as `NSE · INDEX` whenever they appear.
- Confirm equity symbols such as RELIANCE display as `NSE · EQ`.
- Confirm no page-only label contradicts the API/domain identity.

### 6. Scan result explanation

- Inspect **Why matched**, **Key metrics**, **Freshness**, and **Details**.
- Run Relative Volume, Momentum, Breakout with Volume, Pullback in Uptrend, and Trend Continuation. Confirm **Why matched** changes by profile and uses only the matched deterministic predicates, such as measured RVOL, signed momentum, trend relationships, pullback, breakout, or breakdown.
- Confirm key metrics use user-facing formatting such as INR price, signed percentage momentum, RVOL with an × suffix, and RSI where available.
- Expand **Details** and confirm raw reason bases, provider, source mode, lineage, and match ID remain available.
- Confirm a no-match universe such as `NOMATCH` produces an explicit no-match state and invents no candidate.
- Compare **Match admission** with matches and candidates. Confirm `matches = admitted + excluded`, expand **Admission details**, and verify every excluded match has a typed reason rather than disappearing silently.
- Run the same Momentum or Breakout profile through Internal Scanner and TradingView synthetic validation. Where their evidence overlaps, confirm the normalized **Why matched** reason categories agree while provider provenance remains distinct.

### 7. Center workflow and Scan History

- Confirm the center column reads in order as the current result/summary and **Candidates requiring review**. It must not contain a second large Recent scans surface.
- After a scan, confirm the queue defaults to **Current scan** and shows its candidate count. Switch to **Active** and **All** to inspect persisted candidates.
- Run a zero-match scan while active candidates already exist. Confirm **Current scan (0)** stays empty and explicitly reports the retained active count; confirm the prior rows appear only after switching to **Active** or **All**.
- Confirm queue rows show provider and latest scan-run traceability alongside symbol, profile, intent, horizon, relevance, update time, lifecycle, lifecycle reason, and Review.
- Confirm the default **Attention priority** puts current `deterministic-relevance-v2` candidates ahead of legacy-only relevance, then applies relevance, lifecycle, freshness, update recency, symbol, and candidate ID deterministically within the current bucket. A legacy 100% must not outrank current v2 values solely through the old scale. Repeat the same query and confirm ordering remains stable.
- Expand **Filter and sort**. Exercise symbol/native search, relevance, lifecycle, intent, horizon, profile, freshness, and provider filters. Verify alternate Relevance, Updated, Lifecycle, and Symbol sorts, the visible result count, Clear filters, and the text announcement of the active sort.
- Confirm the owner-scoped candidate request remains bounded to 50 rows in this workspace; the API supports explicit offset pages and caps page size at 100.
- Confirm **Scan History** sits directly below **Scan Setup** in the left rail and shows no more than the latest five active runs with profile, provider, universe size, result count, time, and status.
- Select **View** and confirm **Viewing historical scan** appears in the center with stored timestamp, provider, profile, universe, match rows, market-context state, and status. Confirm Scan Setup and candidate state do not change, no scan executes, and **Back to latest scan** restores the preserved current result without reload.
- Select **Use setup** and confirm universe, profile, provider, discovery intent, horizon, context mode, and context policy are restored for review without automatically rerunning a scan. Confirm the transient **Historical scan setup loaded. Review before running.** notification appears even when values were already identical.
- Select **Archive** and confirm the run immediately leaves Recent scans, the transient **Scan archived.** notification appears, and the run remains stored and available through active-and-archived or archived-only **Past scans**. Restore it and confirm it returns to recent history.
- Exercise failed View and Archive responses and an incompatible legacy setup. Confirm typed feedback is visible and no action fails silently.
- In **Past scans**, exercise Today, Last 7 days, Last 30 days, custom From/To, provider, profile, status, and active/archived filtering.
- Confirm there is no Clear history, permanent delete, purge, or physical deletion control.
- Open **Candidates** through the sidebar and confirm the evidence column leads with **Scan + market context** while exact source names remain under **Sources**.

### 8. Candidate relevance, evidence, and inspector

- Before selecting a candidate, confirm no inspector card or right-side inspector column is rendered and the center expands into the freed width.
- Open **Review** for a candidate. Confirm the selected queue row remains visibly highlighted, the center contracts, and the sticky desktop inspector begins with symbol, intent, horizon, and instrument type.
- Close the inspector and confirm it is removed completely, selected-row state clears, and the center immediately expands again.
- Confirm relevance is described as an attention score, not probability of profit, and appears with a LOW/MEDIUM/HIGH band.
- Confirm a candidate created before profile-lineage persistence shows its recovered authoritative profile with a compact **Legacy** marker. If no originating/latest scan, stored snapshot, or candidate metadata can recover it, confirm the UI says **Profile unavailable**, not Unknown.
- Confirm a v1-only relevance value remains unchanged and visible as **Legacy score** with keyboard-accessible help explaining that it is not directly comparable with current v2 scoring. Current candidates expose `deterministic-relevance-v2` under inspector provenance/details without adding clutter to normal rows.
- Compare multiple matches and confirm scores form a useful deterministic spread rather than all saturating near 100%; partial or missing context must reduce contribution and coverage truthfully.
- Inspect evidence contributions, coverage, missing inputs, and conflicts. Present, Missing, Conflicting, Unavailable, and Stale states must use text plus distinct color treatments.
- Confirm evidence cards lead with evidence type, **Supports/Counters/Neutral/Conflicting** meaning, and concise user-facing measurements. Equivalent records from the same latest snapshot/category/producer semantic slot render once; older immutable evidence remains under Snapshot history. Strings such as `true boolean`, `POSITIVE PRESENT`, and raw enums must not be primary copy.
- Open **Candidate provenance** and an evidence card's **Provenance details**. Confirm candidate, episode, latest-run, native, and evidence identifiers wrap without horizontal scrolling, retain their full value, and provide keyboard-accessible labeled Copy actions.
- Where source time is absent, confirm it says **Source time unavailable** and is not labeled stale. Where a deterministic source timestamp exists, confirm it is labeled **Fresh**.

### 9. Market-context degradation

Run each **Market context requirement** policy:

- **Require complete context:** all expected context dimensions are required.
- **Allow partial context:** missing benchmark/sector data remains explicit and reduces coverage.
- **Context optional:** unavailable, stale, or partial context remains explicit while the bounded scan continues; missing context alone must not reduce relevance or required coverage, add a freshness penalty, or make the episode stale. Present optional context may enrich the explanation without becoming required.

Also exercise the existing stale-context test path where available. Confirm missing, unavailable, and stale are distinct and no absent evidence is presented as neutral.

### 10. Scan-driven temporal history and run truth

- In Discovery settings, confirm **Recent observation window** defaults to 20, accepts 5 through 100 and rejects values outside that range. It controls recent rich detail only; it must not imply deletion of older history.
- Run one setup where a symbol is PRESENT, then a complete comparable run where it is ABSENT, then another where it is PRESENT. Confirm the same eligible episode records three immutable observations and the latest queue state follows the last authoritative observation.
- Confirm an instrument outside the requested universe or unresolved by a partial provider run is NOT_EVALUATED, never ABSENT. Repeated/duplicate source samples must not create false confirmation or a false relevance delta.
- Inspect a queue row and candidate **Observation history**. Confirm it shows last observed time, observation kind, latest effective and present lineage, relevance delta only within a compatible model series, and an accessible sparkline with visible gaps/model breaks.
- Page beyond the configured HOT window through the observation endpoint/test workflow. Confirm older rows remain available and labelled cold rather than being deleted or overwritten.
- Open a stored run and switch between **As scanned** and **Current state**. Confirm the immutable run relation does not change, while Current state may show a newer projection or successor. A pre-temporal run must say temporal observations are unavailable instead of reconstructing false history.
- Leave the page open past a horizon/freshness boundary without running a scan. Confirm the labelled freshness/window projection may age, while lifecycle and observation count do not change.
- Confirm there is no timer, background-monitoring control, Watchlist/custom-horizon workflow, Opportunity/LOB promotion or trading action in these temporal surfaces.

### 11. Snapshot evolution and tolerance

- Run the same symbol, intent, horizon, and provider at least twice.
- Confirm the episode moves from a first observation to a comparable current projection and its relevance/evidence can progress deterministically.
- Confirm **Snapshot history** is newest-first and contains separately numbered immutable observations.
- Inspect **Horizon-aware tolerance**. Confirm the presentation uses text plus green/amber/red/grey semantics for **Within**, **Near limit**, **Outside**, **Unknown**, or **Unavailable**, retains backend state in accessible detail, explains that tolerance means structural validity for the selected horizon, and does not imply profit, sizing, stop-loss, or trading authority.

### 12. Lifecycle controls and fresh episode

- Mark a current candidate defunct, then recover it while allowed; confirm each manual change explains its consequence, requires confirmation, and preserves transition history.
- Dismiss a test candidate and rerun the same setup.
- Confirm a new episode links to the prior terminal episode rather than resurrecting it.
- Attempt an action from a stale browser revision and confirm the UI requests a reload rather than overwriting newer state.

### 13. Optional Level-0 explanation

- With the feature disabled, confirm all core discovery behavior works and the candidate says how to enable Optional AI explanation.
- Enable the controlled synthetic provider, generate an explanation, and confirm grounding, provider/model, prompt version, time, evidence references, and limitations are shown.
- Select a non-synthetic provider and confirm a typed unavailable result without silent synthetic substitution.
- Confirm relevance and lifecycle never change because of the explanation.

### 14. Restart persistence

- Record one scan ID, candidate episode, snapshot count, lifecycle, and saved settings.
- Restart the API and web app without deleting the database.
- Confirm recent and archived scans, archive state, candidate state, immutable observations, HOT/COLD pagination, snapshots, transitions, context, explanations, checkpoints, and settings remain present and no terminal episode is resurrected.

### 15. Owner isolation

- Sign in as the second test user.
- Confirm the first user’s active and archived scans, candidates, observations, temporal summaries, evidence, context, explanations, and settings are absent.
- In a test environment, direct requests to view, archive, or restore another owner’s scan and to read another owner’s candidate must return the canonical not-found response.

### 16. UX and responsive review

Review Scanners, Candidates, candidate detail, and discovery settings at widths 390, 768, 1024, 1440, 1920, and 2560+:

- at wide widths with no selection, setup/history and center should form two columns with no reserved inspector space; with a selection, the grid should be approximately 20–22% / 50–55% / 25–28%, aligned at the top, with a sticky useful inspector and compact horizontal status strip;
- at intermediate widths, setup/history and results should form two columns while an open inspector moves below and the status strip wraps cleanly;
- at narrow widths, controls, status items, workflow sections, and inspector should stack while semantic tables become readable labeled cards; the Filter and sort disclosure must stack every control without toolbar or page overflow;
- before a first run, the center should show one compact in-context instruction; when scan history exists it should show the latest persisted summary instead;
- there must be no horizontal page overflow;
- dark/navy framing, white work surfaces, blue primary actions, restrained status colors, focus indicators, labels, headings, alerts, and status text should remain legible in both themes;
- no control should imply trade execution, recommendation, sizing, Opportunity, or LOB promotion.

## Record results

For each workflow, record PASS/FAIL, browser/viewport, user-visible behavior, screenshots where helpful, and any mismatch between product wording and actual evidence. Classify findings as blocker, high hardening, medium hardening, low, or deferred research. Feed results into the later independent Sprint-2 acceptance review; do not relabel Sprint 2 accepted/frozen before that sequence completes.

## Evidence-chart validation workflow — 2026-10-02

1. Run each of the five profiles with deterministic synthetic data and open a matched symbol from **Latest scan result**.
2. Confirm **As scanned** is selected, the synthetic badge is visible, the final candle/volume bar carries the scan marker, and the metric cards equal the normalized rule list.
3. For relative volume, verify the final volume spike is visually obvious against the 20-day baseline. For breakout, verify the prior-high threshold and crossing. For momentum, verify ROC/RSI evidence. For pullback/trend continuation, verify only the pinned moving-average and pullback/trend references appear.
4. Open an older run through **Recent scans → View → Stored match evidence** and confirm the selected historical run ID is shown rather than the latest candidate.
5. Select **Current chart**. Confirm it is visibly distinct; where current provider data is unavailable, confirm the typed notice does not remove historical predicates.
6. Repeat at 390, 768, 1024, 1440, 1920 and 2560 pixels. Confirm there is no page overflow, overlapping label, empty reserved region or clipped action, and that candles, thresholds and metric text remain legible.
7. Use keyboard only: Tab to a symbol, open the drawer, move through the mode tabs, press Escape and confirm focus returns to the same symbol.

Acceptance requires numerical reconciliation, no-lookahead behavior, owner isolation, truthful legacy/retention states and visual recognition of the matched evidence within seconds. This validation does not accept or freeze Sprint 2.
