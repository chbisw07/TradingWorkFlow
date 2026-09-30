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

- Leave **Evidence source** on **Internal Scanner V0 · synthetic**.
- Enter a small universe such as `RELIANCE, TCS, INFY`.
- Choose a profile, intent, and horizon, then run the scan.
- Confirm the result shows **Universe size**, **Matches**, **Discovery candidates**, **Market context**, concise metrics, provider identity, and a **Details** disclosure for lineage.
- Confirm the persistent **SYNTHETIC / VALIDATION DATA** indicator makes the non-live source unmistakable.

### 2. TradingView contract-validation flow

- Select **TradingView adapter · synthetic** and run the same universe.
- Confirm the UI identifies it as synthetic validation and makes no live-data claim.
- Confirm candidates retain TradingView evidence/provenance.

### 3. Both-provider evidence

- Run the Internal Scanner and TradingView synthetic path for the same symbol, intent, and horizon.
- Open **Candidates** and review the symbol.
- Confirm one current episode can contain distinct provider evidence rather than blind duplicate candidates.

### 4. Scan match inspection

- Check **Why matched**, key metrics, exchange, source mode, and freshness. Confirm human-readable reasons appear first and raw reason codes/lineage remain under **Details**.
- Confirm a no-match universe such as `NOMATCH` produces an explicit no-match state and invents no candidate.

### 5. Candidate relevance

- Open **Review** for a candidate.
- Confirm relevance is described as an attention score, not probability of profit, and appears with a LOW/MEDIUM/HIGH band.
- Inspect each evidence factor, contribution, availability/state, total relevance, missing inputs, and conflicts. Confirm missing and conflicting evidence use distinct treatments.
- Change the horizon on a later scan and confirm the candidate/episode identity and tolerance thresholds remain horizon-specific.

### 6. Evidence and provenance

- Inspect the latest evidence list.
- Confirm evidence type, state/polarity, and concise measurements are primary, while provider/source, mode, version, IDs, and transformation provenance remain under **Provenance details**.
- Where source time is absent, confirm it says **Source time unavailable** and is not labeled stale.

### 7. Market-context degradation

Use **Scan conditions → Market context requirement** to run each context mode:

- **Complete:** all available dimensions should be present.
- **Partial:** missing benchmark/sector data should be explicit.
- **Stale:** stale dimensions and stale candidate projection should be visible.
- **Unavailable:** unavailable evidence should remain explicit while the scan remains usable.

### 8. Horizon-aware tolerance

- In candidate review, inspect **Horizon-aware tolerance**.
- Confirm price, volume, market, sector, and time decay use the presentation labels **Within**, **Near limit**, **Outside**, **Unknown**, or **Unavailable** while preserving the backend state in accessible detail.
- Confirm unknown dimensions are not presented as healthy facts and the panel states that tolerance is not a profit estimate or trading authority.

### 9. Snapshot evolution

- Run the same symbol, intent, and horizon at least twice.
- Confirm the episode moves from a first observation to a comparable current projection.
- Confirm **Snapshot history** is newest-first and contains separately numbered immutable observations with observed time, lifecycle, relevance, tolerance, and a concise change summary.

### 10. Lifecycle controls and fresh episode

- Mark a current candidate defunct, then recover it while allowed; confirm each manual change explains its consequence, requires confirmation, and preserves transition history.
- Dismiss a test candidate and rerun the same setup.
- Confirm a new episode is created and links to the prior terminal episode rather than resurrecting it.
- Attempt a lifecycle action from a stale browser revision and confirm the UI requests a reload instead of overwriting newer state.

### 11. LLM disabled

- Open **Settings → Scan & Discover → LLM** and leave optional AI explanation disabled.
- Confirm all scanning, evidence, relevance, lifecycle, history, and context functions still work.
- Requesting an explanation should return a specific disabled message without damaging the candidate.

### 12. Controlled LLM enabled

- Enable **Optional AI explanation** with provider **synthetic** and save.
- Generate a candidate explanation.
- Confirm grounding, model/provider, prompt version, time, evidence references, and limitations are shown.
- Confirm relevance and lifecycle are unchanged.

### 13. Unavailable LLM/provider state

- Select a non-synthetic LLM provider and request an explanation.
- Confirm the UI says the optional explanation is unavailable while discovery remains usable.
- Review **Provider status** and ensure LIVE/SYNTHETIC mode remains separate from AUTH REQUIRED/RATE LIMITED/DEGRADED/UNAVAILABLE state; no provider should be silently substituted.

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
- data tables should recompose into labeled cards on mobile and may use bounded internal scrolling at wider widths;
- keyboard focus, labels, headings, buttons, alerts, and status messages should remain understandable;
- dark and light themes should preserve information hierarchy;
- no control should imply trade execution or Opportunity/LOB promotion.

## Record results

For each workflow, record PASS/FAIL, browser/viewport, user-visible behavior, screenshots where helpful, and any mismatch between product wording and actual evidence. Classify findings as blocker, high hardening, medium hardening, low, or deferred research. Feed results into the later independent Sprint-2 acceptance review; do not relabel Sprint 2 accepted/frozen before that sequence completes.
