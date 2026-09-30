# Sprint 2 Scan & Discover — user validation plan

**Product state:** IMPLEMENTED / READY FOR USER VALIDATION  
**Audience:** product owner/operator  
**Result of this plan:** observations for later adversarial review and hardening; it does not itself freeze Sprint 2

## Before starting

1. Start the API with migrations applied and start the web application using the repository setup instructions.
2. Sign in with a non-production test user.
3. Open **Scanners** from the left navigation. Confirm the page states that discovery never authorizes a trade.
4. Keep a second test user available for the isolation check. Do not use real TradingView calls for this plan.

## Validation workflows

### 1. Internal Scanner flow

- Leave **Provider** on **Internal Scanner V0**.
- Enter a small universe such as `RELIANCE, TCS, INFY`.
- Choose a profile, intent, and horizon, then run the scan.
- Confirm the result shows universe count, match count, candidate count, context state, normalized metrics, provider identity, and lineage.
- Confirm the UI identifies the source as deterministic local validation data.

### 2. TradingView contract-validation flow

- Select **TradingView synthetic validation** and run the same universe.
- Confirm the UI identifies it as synthetic validation and makes no live-data claim.
- Confirm candidates retain TradingView evidence/provenance.

### 3. Both-provider evidence

- Run the Internal Scanner and TradingView synthetic path for the same symbol, intent, and horizon.
- Open **Candidates** and review the symbol.
- Confirm one current episode can contain distinct provider evidence rather than blind duplicate candidates.

### 4. Scan match inspection

- Check **Why matched**, key metrics, exchange, source mode, and lineage.
- Confirm a no-match universe such as `NOMATCH` produces an explicit no-match state and invents no candidate.

### 5. Candidate relevance

- Open **Review** for a candidate.
- Confirm relevance is described as policy fit, not probability of profit.
- Inspect contribution, weight, missing inputs, coverage, freshness penalty, and horizon adjustment.
- Change the horizon on a later scan and confirm the candidate/episode identity and tolerance thresholds remain horizon-specific.

### 6. Evidence and provenance

- Inspect the latest evidence list.
- Confirm source/producer, mode, polarity, measures, observed time, and source time are visible.
- Where source time is absent, confirm it says **Not supplied** rather than inventing a timestamp.

### 7. Market-context degradation

Use **Validation conditions** to run each context mode:

- **Complete:** all available dimensions should be present.
- **Partial:** missing benchmark/sector data should be explicit.
- **Stale:** stale dimensions and stale candidate projection should be visible.
- **Unavailable:** unavailable evidence should remain explicit while the scan remains usable.

### 8. Horizon-aware tolerance

- In candidate review, inspect **Horizon-aware tolerance**.
- Confirm price, volume, market, sector, and time decay each show `WITHIN`, `DEGRADED`, `BREACHED`, or `UNKNOWN`.
- Confirm unknown dimensions are not presented as healthy facts and the panel states that tolerance is not a profit estimate or trading authority.

### 9. Snapshot evolution

- Run the same symbol, intent, and horizon at least twice.
- Confirm the episode moves from a first observation to a comparable current projection.
- Confirm **Snapshot history** contains separately numbered immutable observations with their own lifecycle, relevance, tolerance, time, and source list.

### 10. Lifecycle controls and fresh episode

- Mark a current candidate defunct, then recover it while allowed; confirm transition history is preserved.
- Dismiss a test candidate and rerun the same setup.
- Confirm a new episode is created and links to the prior terminal episode rather than resurrecting it.
- Attempt a lifecycle action from a stale browser revision and confirm the UI requests a reload instead of overwriting newer state.

### 11. LLM disabled

- Open **Settings → Scan & Discover** and leave Level-0 explanation disabled.
- Confirm all scanning, evidence, relevance, lifecycle, history, and context functions still work.
- Requesting an explanation should return a specific disabled message without damaging the candidate.

### 12. Controlled LLM enabled

- Enable Level-0 explanation with provider **synthetic** and save.
- Generate a candidate explanation.
- Confirm grounding, model/provider, prompt version, time, evidence references, and limitations are shown.
- Confirm relevance and lifecycle are unchanged.

### 13. Unavailable LLM/provider state

- Select a non-synthetic LLM provider and request an explanation.
- Confirm the UI says the optional explanation is unavailable while discovery remains usable.
- Review provider readiness and ensure auth/rate/degraded labels are specific when such states are supplied; no provider should be silently substituted.

### 14. Restart persistence

- Record one scan ID, candidate episode, snapshot count, lifecycle, and saved settings.
- Restart the API and web app without deleting the database.
- Confirm scan history, candidate state, snapshots, transitions, context, explanations, and settings remain present and no terminal episode is resurrected.

### 15. Owner isolation

- Sign in as the second test user.
- Confirm the first user’s scans, candidates, evidence, context, explanations, and settings are absent.
- Do not use guessed IDs against production data. In a test environment, a direct request for another owner’s candidate should return the canonical not-found response.

### 16. UX and responsive review

Review Scanners, Candidates, candidate detail, and discovery settings at widths 390, 768, 1024, 1440, 1920, and 2560+:

- controls should recompose without horizontal page overflow;
- data tables may use their bounded internal scroll container;
- keyboard focus, labels, headings, buttons, alerts, and status messages should remain understandable;
- dark and light themes should preserve information hierarchy;
- no control should imply trade execution or Opportunity/LOB promotion.

## Record results

For each workflow, record PASS/FAIL, browser/viewport, user-visible behavior, screenshots where helpful, and any mismatch between product wording and actual evidence. Classify findings as blocker, high hardening, medium hardening, low, or deferred research. Feed results into the later independent Sprint-2 acceptance review; do not relabel Sprint 2 accepted/frozen before that sequence completes.
