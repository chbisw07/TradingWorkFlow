# Sprint 2 Scan & Discover — user validation plan

**Product state:** IMPLEMENTED / READY FOR USER VALIDATION  
**Audience:** product owner/operator  
**Result of this plan:** observations for later adversarial review and hardening; it does not itself freeze Sprint 2

This plan reflects the **final product stabilization before formal user validation**.

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
- Confirm some symbols match and some do not. HDFCBANK, BSE, and BANKNIFTY provide intentional non-match coverage for this fixture/profile state.
- Confirm prices, momentum, RVOL, relevance, evidence coverage, and explanations vary between matching instruments.
- Confirm the persistent **SYNTHETIC VALIDATION DATA** disclosure says results are deterministic test data and are not live-market claims.

### 2. Profile, intent, horizon, and context policy

- Confirm **Scan profile** explains the market pattern TWF searches for.
- Select **Momentum**. Confirm the suggested purpose becomes **Positional long** with a **5 days** horizon.
- Explicitly change intent and horizon, then select another profile. Confirm both explicit choices remain unchanged.
- Select **Apply suggestion** and confirm the active profile recommendation is restored.
- Confirm **Discovery intent** explains how a match is interpreted and tracked, while **Horizon** explains how long it should remain relevant.
- Confirm the context choices read **Require complete context**, **Allow partial context**, and **Context optional**. Missing context must stay visible and reduce coverage; it must not be inferred as neutral.

### 3. Provider Mode and Status

- Inspect **Provider status**.
- Confirm Internal Scanner V0 shows **Mode: SYNTHETIC DATA**, **Status: READY**, deterministic scanner wording, five scan profiles, and fixture-backed disclosure.
- Confirm TradingView separates its validation/synthetic or live mode from READY, RATE LIMITED, AUTH REQUIRED, UNAVAILABLE, DISABLED, or DEGRADED operational state.
- Confirm status is communicated in text with a dot and does not depend on color or look like a button.
- If TradingView is rate limited, confirm the card does not imply that successful live exact-row proof exists.

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
- Confirm Why matched uses the actual deterministic evidence, such as elevated relative volume, momentum, trend, pullback, or breakout.
- Confirm key metrics use user-facing formatting such as INR price, signed percentage momentum, RVOL with an × suffix, and RSI where available.
- Expand **Details** and confirm raw reason bases, provider, source mode, lineage, and match ID remain available.
- Confirm a no-match universe such as `NOMATCH` produces an explicit no-match state and invents no candidate.

### 7. Discovery queue and recent scans

- Confirm **Candidates requiring review** is visible in the scan workspace and shows symbol, setup, relevance, update time, lifecycle, and Review.
- Confirm **Recent scans** shows profile, universe size, result count, last run, status, and **Use setup**.
- Select **Use setup** and confirm the profile/provider/intent/horizon are loaded for review without automatically rerunning a scan.
- Open **Candidates** through the sidebar and confirm the evidence column leads with **Scan + market context** while exact source names remain under **Sources**.

### 8. Candidate relevance and evidence

- Open **Review** for a candidate.
- Confirm relevance is described as an attention score, not probability of profit, and appears with a LOW/MEDIUM/HIGH band.
- Inspect evidence contributions, coverage, missing inputs, and conflicts. Missing and conflicting evidence must use distinct treatments.
- Confirm evidence type, state/polarity, and concise measurements are primary; provider/source, mode, versions, IDs, and transformation provenance remain under **Provenance details**.
- Where source time is absent, confirm it says **Source time unavailable** and is not labeled stale. Where a deterministic source timestamp exists, confirm it is labeled **Fresh**.

### 9. Market-context degradation

Run each **Market context requirement** policy:

- **Require complete context:** all expected context dimensions are required.
- **Allow partial context:** missing benchmark/sector data remains explicit and reduces coverage.
- **Context optional:** unavailable context remains explicit while the bounded scan may continue.

Also exercise the existing stale-context test path where available. Confirm missing, unavailable, and stale are distinct and no absent evidence is presented as neutral.

### 10. Snapshot evolution and tolerance

- Run the same symbol, intent, horizon, and provider at least twice.
- Confirm the episode moves from a first observation to a comparable current projection and its relevance/evidence can progress deterministically.
- Confirm **Snapshot history** is newest-first and contains separately numbered immutable observations.
- Inspect **Horizon-aware tolerance**. Confirm the presentation uses **Within**, **Near limit**, **Outside**, **Unknown**, or **Unavailable**, retains backend state in accessible detail, and does not imply profit, sizing, or trading authority.

### 11. Lifecycle controls and fresh episode

- Mark a current candidate defunct, then recover it while allowed; confirm each manual change explains its consequence, requires confirmation, and preserves transition history.
- Dismiss a test candidate and rerun the same setup.
- Confirm a new episode links to the prior terminal episode rather than resurrecting it.
- Attempt an action from a stale browser revision and confirm the UI requests a reload rather than overwriting newer state.

### 12. Optional Level-0 explanation

- With the feature disabled, confirm all core discovery behavior works and the candidate says how to enable Optional AI explanation.
- Enable the controlled synthetic provider, generate an explanation, and confirm grounding, provider/model, prompt version, time, evidence references, and limitations are shown.
- Select a non-synthetic provider and confirm a typed unavailable result without silent synthetic substitution.
- Confirm relevance and lifecycle never change because of the explanation.

### 13. Restart persistence

- Record one scan ID, candidate episode, snapshot count, lifecycle, and saved settings.
- Restart the API and web app without deleting the database.
- Confirm recent scans, candidate state, snapshots, transitions, context, explanations, and settings remain present and no terminal episode is resurrected.

### 14. Owner isolation

- Sign in as the second test user.
- Confirm the first user’s scans, candidates, evidence, context, explanations, and settings are absent.
- In a test environment, a direct request for another owner’s candidate must return the canonical not-found response.

### 15. UX and responsive review

Review Scanners, Candidates, candidate detail, and discovery settings at widths 390, 768, 1024, 1440, 1920, and 2560+:

- at wide widths, scan setup, results/queue, and candidate inspector should use the available width as a compact workstation;
- at intermediate widths, the inspector may move below the setup/results regions;
- at narrow widths, controls should stack and semantic tables should become readable labeled cards;
- there must be no horizontal page overflow;
- dark/navy framing, white work surfaces, blue primary actions, restrained status colors, focus indicators, labels, headings, alerts, and status text should remain legible in both themes;
- no control should imply trade execution, recommendation, sizing, Opportunity, or LOB promotion.

## Record results

For each workflow, record PASS/FAIL, browser/viewport, user-visible behavior, screenshots where helpful, and any mismatch between product wording and actual evidence. Classify findings as blocker, high hardening, medium hardening, low, or deferred research. Feed results into the later independent Sprint-2 acceptance review; do not relabel Sprint 2 accepted/frozen before that sequence completes.
