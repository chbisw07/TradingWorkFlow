"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  discoveryApi,
  type Candidate,
  type CandidateDetail,
  type ContextMode,
  type DiscoverySettings,
  type LlmExplanation,
  type ProviderChoice,
  type ProviderStatus,
  type ScanResult,
} from "../../lib/discovery";
import { SurfaceState } from "../ui/surface-state";

type View = "scan" | "candidates";

function percent(value: string | number | null) {
  return value === null ? "Unscored" : `${Math.round(Number(value) * 100)}%`;
}

function dateTime(value: string | null) {
  if (!value) return "Not supplied";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function CandidateTable({
  candidates,
  selected,
  onSelect,
}: {
  candidates: Candidate[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  if (candidates.length === 0) {
    return (
      <SurfaceState
        state="EMPTY"
        headingLevel={3}
        title="No candidates to review"
        description="Run a bounded scan or change the selected universe. No missing evidence is inferred."
      />
    );
  }
  return (
    <div className="discovery-table-wrap" tabIndex={0}>
      <table className="discovery-table">
        <caption className="sr-only">Discovery candidates</caption>
        <thead>
          <tr>
            <th scope="col">Instrument</th>
            <th scope="col">Intent / horizon</th>
            <th scope="col">Relevance</th>
            <th scope="col">Lifecycle</th>
            <th scope="col">Freshness</th>
            <th scope="col">Evidence sources</th>
            <th scope="col">Updated</th>
            <th scope="col">Review</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate) => (
            <tr
              key={candidate.candidate_id}
              data-selected={selected === candidate.candidate_id}
            >
              <td>
                <strong>{candidate.instrument.symbol}</strong>
                <span>
                  {candidate.instrument.exchange} ·{" "}
                  {candidate.instrument.segment}
                </span>
              </td>
              <td>
                <strong>{candidate.intent.replaceAll("_", " ")}</strong>
                <span>{candidate.horizon}</span>
              </td>
              <td>
                <strong>{percent(candidate.relevance.value)}</strong>
                <span>
                  {candidate.relevance_explanation.band || "UNSCORED"}
                </span>
              </td>
              <td>
                <span
                  className={`discovery-badge is-${candidate.lifecycle.toLowerCase()}`}
                >
                  {candidate.lifecycle}
                </span>
              </td>
              <td>{candidate.freshness}</td>
              <td>{candidate.provider_sources.join(", ")}</td>
              <td>{dateTime(candidate.updated_at)}</td>
              <td>
                <button
                  type="button"
                  onClick={() => onSelect(candidate.candidate_id)}
                >
                  Review
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CandidateInspector({
  detail,
  pending,
  onClose,
  onLifecycle,
  onExplain,
}: {
  detail: CandidateDetail;
  pending: boolean;
  onClose: () => void;
  onLifecycle: (action: "DISMISS" | "MARK_DEFUNCT" | "RECOVER") => void;
  onExplain: () => void;
}) {
  const latest = detail.snapshots.at(-1);
  return (
    <aside
      className="candidate-inspector"
      aria-labelledby="candidate-detail-heading"
    >
      <header>
        <div>
          <p className="eyebrow">CANDIDATE / EVIDENCE REVIEW</p>
          <h2 id="candidate-detail-heading">{detail.instrument.symbol}</h2>
          <p>
            {detail.instrument.exchange}:{detail.instrument.native.native_id} ·{" "}
            {detail.intent} · {detail.horizon}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close candidate review"
        >
          Close
        </button>
      </header>

      <div className="candidate-scorecard">
        <div>
          <span>Relevance</span>
          <strong>{percent(detail.relevance.value)}</strong>
          <small>Policy fit, not probability of profit</small>
        </div>
        <div>
          <span>Coverage</span>
          <strong>{percent(detail.relevance.coverage)}</strong>
          <small>{detail.relevance_explanation.policy}</small>
        </div>
        <div>
          <span>Episode</span>
          <strong>{detail.lifecycle}</strong>
          <small>{detail.snapshot_count} immutable snapshot(s)</small>
        </div>
        <div>
          <span>Tolerance</span>
          <strong>{detail.tolerance.state}</strong>
          <small>{detail.tolerance.horizon} horizon policy</small>
        </div>
      </div>

      <section aria-labelledby="contributions-heading">
        <h3 id="contributions-heading">Why it is relevant</h3>
        <ul className="contribution-list">
          {detail.relevance_explanation.contributions.map((item) => (
            <li key={item.factor}>
              <div>
                <strong>{item.factor.replaceAll("_", " ")}</strong>
                <span>{item.reason}</span>
              </div>
              <b>{Number(item.contribution).toFixed(2)}</b>
            </li>
          ))}
        </ul>
        {detail.relevance_explanation.missing.length > 0 && (
          <p className="discovery-callout is-warning">
            Missing: {detail.relevance_explanation.missing.join(", ")}. The
            score does not infer these inputs.
          </p>
        )}
      </section>

      <section aria-labelledby="tolerance-heading">
        <h3 id="tolerance-heading">Horizon-aware tolerance</h3>
        <p>
          Multidimensional policy state; it does not estimate profit or
          authorize a trade.
        </p>
        <ul className="context-dimensions">
          {detail.tolerance.dimensions.map((dimension) => (
            <li key={dimension.dimension}>
              <span>{dimension.dimension.replaceAll("_", " ")}</span>
              <strong title={dimension.reason}>{dimension.status}</strong>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="evidence-heading">
        <h3 id="evidence-heading">Latest evidence</h3>
        {!latest || latest.evidence.length === 0 ? (
          <p>No evidence records are available.</p>
        ) : (
          <ul className="evidence-list">
            {latest.evidence.map((item) => (
              <li key={item.evidence_id}>
                <div>
                  <strong>{item.category.replaceAll("_", " ")}</strong>
                  <span>
                    {item.provenance.producer.provider} · {item.provenance.mode}{" "}
                    · {item.polarity}
                  </span>
                </div>
                <p>
                  {item.measures
                    .map(
                      (measure) =>
                        `${measure.name}: ${String(measure.value)} ${measure.unit}`,
                    )
                    .join(" · ") ||
                    item.reason ||
                    "No measurement supplied"}
                </p>
                <small>Source time: {dateTime(item.source_data_time)}</small>
              </li>
            ))}
          </ul>
        )}
      </section>

      {detail.context && (
        <section aria-labelledby="candidate-context-heading">
          <h3 id="candidate-context-heading">Market context</h3>
          <p>
            {detail.context.market} · {detail.context.session} ·{" "}
            {detail.context.availability}
          </p>
          <ul className="context-dimensions">
            {detail.context.dimensions.map((dimension) => (
              <li key={dimension.name}>
                <span>{dimension.name.replaceAll("_", " ")}</span>
                <strong>
                  {dimension.value === null
                    ? dimension.availability
                    : String(dimension.value)}
                </strong>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="history-heading">
        <h3 id="history-heading">Snapshot history</h3>
        <ol className="snapshot-timeline">
          {[...detail.snapshots].reverse().map((snapshot) => (
            <li key={snapshot.snapshot_id}>
              <strong>Snapshot {snapshot.sequence}</strong>
              <span>{dateTime(snapshot.observed_at)}</span>
              <small>
                {snapshot.lifecycle} · {percent(snapshot.relevance.value)} ·
                tolerance {snapshot.tolerance.state} ·{" "}
                {snapshot.provider_sources.join(", ")}
              </small>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="explanation-heading">
        <div className="section-heading-row">
          <div>
            <h3 id="explanation-heading">Optional Level-0 explanation</h3>
            <p>
              Grounded summary only. It cannot score, transition, recommend, or
              trade.
            </p>
          </div>
          <button disabled={pending} type="button" onClick={onExplain}>
            Generate explanation
          </button>
        </div>
        {detail.explanations.map((item: LlmExplanation) => (
          <article className="llm-explanation" key={item.explanation_id}>
            <strong>{item.grounding}</strong>
            <p>{item.narrative}</p>
            <small>
              {item.provider}/{item.model} · prompt {item.prompt_version} ·{" "}
              {dateTime(item.generated_at)}
            </small>
          </article>
        ))}
      </section>

      <footer className="candidate-actions">
        <button
          disabled={pending}
          type="button"
          onClick={() => onLifecycle("DISMISS")}
        >
          Dismiss
        </button>
        <button
          disabled={pending}
          type="button"
          onClick={() => onLifecycle("MARK_DEFUNCT")}
        >
          Mark defunct
        </button>
        {(detail.lifecycle === "DEFUNCT" ||
          detail.lifecycle === "REJECTED") && (
          <button
            disabled={pending}
            type="button"
            onClick={() => onLifecycle("RECOVER")}
          >
            Recover
          </button>
        )}
      </footer>
    </aside>
  );
}

export function DiscoveryWorkspace({
  initialView = "scan",
}: {
  initialView?: View;
}) {
  const [view, setView] = useState<View>(initialView);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [settings, setSettings] = useState<DiscoverySettings | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [detail, setDetail] = useState<CandidateDetail | null>(null);
  const [universe, setUniverse] = useState("RELIANCE, TCS, INFY, HDFCBANK");
  const [provider, setProvider] = useState<ProviderChoice>("internal");
  const [profile, setProfile] = useState("RELATIVE_VOLUME");
  const [horizon, setHorizon] = useState("5d");
  const [intent, setIntent] = useState("MOMENTUM");
  const [contextMode, setContextMode] = useState<ContextMode>("partial");
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [providerState, candidatePage, currentSettings] = await Promise.all(
        [
          discoveryApi<ProviderStatus[]>("status"),
          discoveryApi<{ items: Candidate[] }>("candidates?limit=50"),
          discoveryApi<DiscoverySettings>("settings"),
        ],
      );
      setProviders(providerState);
      setCandidates(candidatePage.items);
      setSettings(currentSettings);
      setProvider(currentSettings.default_provider);
      setProfile(currentSettings.default_profile);
      setHorizon(currentSettings.default_horizon);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    Promise.all([
      discoveryApi<ProviderStatus[]>("status"),
      discoveryApi<{ items: Candidate[] }>("candidates?limit=50"),
      discoveryApi<DiscoverySettings>("settings"),
    ])
      .then(([providerState, candidatePage, currentSettings]) => {
        if (!active) return;
        setProviders(providerState);
        setCandidates(candidatePage.items);
        setSettings(currentSettings);
        setProvider(currentSettings.default_provider);
        setProfile(currentSettings.default_profile);
        setHorizon(currentSettings.default_horizon);
      })
      .catch((reason: unknown) => {
        if (active) setError((reason as Error).message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function runScan(event: FormEvent) {
    event.preventDefault();
    const symbols = universe
      .split(/[\s,]+/)
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean);
    setPending(true);
    setError("");
    setNotice("");
    setDetail(null);
    try {
      const next = await discoveryApi<ScanResult>("scans", "POST", {
        universe: symbols,
        provider,
        profile,
        horizon,
        intent,
        include_llm: false,
        context_mode: contextMode,
      });
      setResult(next);
      const page = await discoveryApi<{ items: Candidate[] }>(
        "candidates?limit=50",
      );
      setCandidates(page.items);
      setNotice(
        next.summary.match_count === 0
          ? "Scan completed with no matches. No candidates were invented."
          : `Scan completed with ${next.summary.match_count} match(es) and ${next.summary.candidate_count} candidate update(s).`,
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setPending(false);
    }
  }

  async function inspect(id: string) {
    setPending(true);
    setError("");
    try {
      setDetail(await discoveryApi<CandidateDetail>(`candidates/${id}`));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setPending(false);
    }
  }

  async function lifecycle(action: "DISMISS" | "MARK_DEFUNCT" | "RECOVER") {
    if (!detail) return;
    setPending(true);
    setError("");
    try {
      const next = await discoveryApi<CandidateDetail>(
        `candidates/${detail.candidate_id}/lifecycle`,
        "POST",
        { action, revision: detail.revision, reason: "user-review" },
      );
      setDetail(next);
      setCandidates((items) =>
        items.map((item) =>
          item.candidate_id === next.candidate_id ? next : item,
        ),
      );
      setNotice(`Candidate lifecycle changed to ${next.lifecycle}.`);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setPending(false);
    }
  }

  async function explain() {
    if (!detail) return;
    setPending(true);
    setError("");
    try {
      await discoveryApi<LlmExplanation>(
        `candidates/${detail.candidate_id}/explain`,
        "POST",
        {},
      );
      setDetail(
        await discoveryApi<CandidateDetail>(
          `candidates/${detail.candidate_id}`,
        ),
      );
      setNotice(
        "A grounded Level-0 explanation was saved without changing relevance or lifecycle.",
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="discovery-workspace">
      <header className="discovery-hero">
        <div>
          <p className="eyebrow">SPRINT 2 / SCAN &amp; DISCOVER</p>
          <h1>Evidence-led market discovery</h1>
          <p>
            Run bounded scans, compare provider evidence, and review candidate
            history. Discovery never authorizes a trade.
          </p>
        </div>
        <div className="discovery-mode-label">
          <span aria-hidden="true" />
          Validation foundation
        </div>
      </header>

      <nav className="discovery-tabs" aria-label="Scan and Discover views">
        <button
          type="button"
          aria-current={view === "scan" ? "page" : undefined}
          onClick={() => setView("scan")}
        >
          Scanner
        </button>
        <button
          type="button"
          aria-current={view === "candidates" ? "page" : undefined}
          onClick={() => setView("candidates")}
        >
          Candidates <span>{candidates.length}</span>
        </button>
      </nav>

      {error && (
        <div className="discovery-callout is-error" role="alert">
          <strong>Request not completed</strong>
          <p>{error}</p>
          <button type="button" onClick={() => void load()}>
            Reload discovery data
          </button>
        </div>
      )}
      {notice && (
        <p className="discovery-callout" role="status">
          {notice}
        </p>
      )}
      {loading && (
        <SurfaceState
          state="LOADING"
          headingLevel={2}
          title="Loading discovery workspace"
          description="Reading your provider status, settings, and candidate history."
        />
      )}

      {!loading && view === "scan" && (
        <>
          <section
            className="scan-control-panel"
            aria-labelledby="scan-controls-heading"
          >
            <div className="section-heading-row">
              <div>
                <p className="eyebrow">BOUNDED SCAN</p>
                <h2 id="scan-controls-heading">Define a validation universe</h2>
              </div>
              <span>Maximum 20 symbols</span>
            </div>
            <form onSubmit={runScan}>
              <label className="universe-field">
                <span>Universe symbols</span>
                <input
                  value={universe}
                  onChange={(event) => setUniverse(event.target.value)}
                  required
                  maxLength={300}
                  aria-describedby="universe-help"
                />
                <small id="universe-help">
                  Comma or space separated NSE validation symbols.
                </small>
              </label>
              <label>
                <span>Provider</span>
                <select
                  value={provider}
                  onChange={(event) =>
                    setProvider(event.target.value as ProviderChoice)
                  }
                >
                  <option value="internal">Internal Scanner V0</option>
                  <option value="tradingview-synthetic">
                    TradingView synthetic validation
                  </option>
                </select>
              </label>
              <label>
                <span>Profile</span>
                <select
                  value={profile}
                  onChange={(event) => setProfile(event.target.value)}
                >
                  <option value="RELATIVE_VOLUME">Relative volume</option>
                  <option value="TREND_CONTINUATION">Trend continuation</option>
                  <option value="BREAKOUT_WITH_VOLUME">
                    Breakout with volume
                  </option>
                  <option value="PULLBACK_IN_UPTREND">
                    Pullback in uptrend
                  </option>
                  <option value="MOMENTUM">Momentum</option>
                </select>
              </label>
              <label>
                <span>Intent</span>
                <select
                  value={intent}
                  onChange={(event) => setIntent(event.target.value)}
                >
                  <option value="MOMENTUM">Momentum</option>
                  <option value="BREAKOUT">Breakout</option>
                  <option value="PULLBACK">Pullback</option>
                  <option value="POSITIONAL_LONG">Positional long</option>
                  <option value="POSITIONAL_SHORT">Positional short</option>
                </select>
              </label>
              <label>
                <span>Horizon</span>
                <select
                  value={horizon}
                  onChange={(event) => setHorizon(event.target.value)}
                >
                  <option value="intraday">Intraday</option>
                  <option value="1d">1 day</option>
                  <option value="5d">5 days</option>
                  <option value="15d">15 days</option>
                </select>
              </label>
              <details className="advanced-controls">
                <summary>Validation conditions</summary>
                <label>
                  <span>Market-context condition</span>
                  <select
                    value={contextMode}
                    onChange={(event) =>
                      setContextMode(event.target.value as ContextMode)
                    }
                  >
                    <option value="partial">Partial</option>
                    <option value="healthy">Complete</option>
                    <option value="stale">Stale</option>
                    <option value="unavailable">Unavailable</option>
                  </select>
                </label>
              </details>
              <button
                className="run-scan-button"
                disabled={pending}
                type="submit"
              >
                {pending ? "Running…" : "Run scan"}
              </button>
            </form>
            <p className="scope-note">
              Internal Scanner V0 uses deterministic local validation series.
              TradingView mode validates the accepted adapter contract without a
              live provider call.
            </p>
          </section>

          <section aria-labelledby="providers-heading">
            <div className="section-heading-row">
              <div>
                <p className="eyebrow">PROVIDER LAYER</p>
                <h2 id="providers-heading">Provider readiness</h2>
              </div>
            </div>
            <div className="provider-grid">
              {providers.map((item) => (
                <article key={item.id}>
                  <div>
                    <span
                      className={`provider-health is-${item.health.toLowerCase()}`}
                      aria-hidden="true"
                    />
                    <strong>{item.label}</strong>
                  </div>
                  <b>{item.health.replaceAll("_", " ")}</b>
                  <p>{item.mode.replaceAll("_", " ")}</p>
                  <small>
                    {item.last_success_at
                      ? `Last successful validation ${dateTime(item.last_success_at)}`
                      : "No successful run recorded"}
                  </small>
                </article>
              ))}
            </div>
          </section>

          {result && (
            <section
              className="scan-result"
              aria-labelledby="scan-result-heading"
            >
              <div className="section-heading-row">
                <div>
                  <p className="eyebrow">
                    RUN {result.summary.run_id.slice(0, 8)}
                  </p>
                  <h2 id="scan-result-heading">Latest scan result</h2>
                </div>
                <span>{dateTime(result.summary.completed_at)}</span>
              </div>
              <div className="scan-metrics">
                <div>
                  <span>Universe</span>
                  <strong>{result.summary.universe_size}</strong>
                </div>
                <div>
                  <span>Matches</span>
                  <strong>{result.summary.match_count}</strong>
                </div>
                <div>
                  <span>Candidates</span>
                  <strong>{result.summary.candidate_count}</strong>
                </div>
                <div>
                  <span>Context</span>
                  <strong>{result.summary.context_availability}</strong>
                </div>
              </div>
              <div className="discovery-table-wrap" tabIndex={0}>
                <table className="discovery-table scan-match-table">
                  <caption className="sr-only">
                    Latest normalized scan matches
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Symbol</th>
                      <th scope="col">Provider</th>
                      <th scope="col">Why matched</th>
                      <th scope="col">Key metrics</th>
                      <th scope="col">Lineage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.matches.map((match) => (
                      <tr key={match.match_id}>
                        <td>
                          <strong>{match.symbol}</strong>
                          <span>{match.exchange}</span>
                        </td>
                        <td>
                          <strong>{match.provider}</strong>
                          <span>{match.source_mode}</span>
                        </td>
                        <td>{match.why_matched.join(", ")}</td>
                        <td>
                          {Object.entries(match.key_metrics)
                            .map(([key, value]) => `${key}: ${value}`)
                            .join(" · ")}
                        </td>
                        <td>
                          <span title={match.lineage}>
                            {match.lineage.slice(0, 16)}…
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {result.matches.length === 0 && (
                <p className="discovery-callout">
                  No normalized matches were returned.
                </p>
              )}
              {result.summary.degraded.length > 0 && (
                <p className="discovery-callout is-warning">
                  Degraded: {result.summary.degraded.join(", ")}
                </p>
              )}
              <CandidateTable
                candidates={result.candidates}
                selected={detail?.candidate_id || null}
                onSelect={(id) => void inspect(id)}
              />
            </section>
          )}
        </>
      )}

      {!loading && view === "candidates" && (
        <section
          className="candidate-ledger"
          aria-labelledby="candidate-ledger-heading"
        >
          <div className="section-heading-row">
            <div>
              <p className="eyebrow">OWNER-SCOPED HISTORY</p>
              <h2 id="candidate-ledger-heading">Candidate ledger</h2>
              <p>
                Current projections link back to immutable snapshots and
                provider evidence.
              </p>
            </div>
            <button
              type="button"
              disabled={pending}
              onClick={() => void load()}
            >
              Refresh
            </button>
          </div>
          <CandidateTable
            candidates={candidates}
            selected={detail?.candidate_id || null}
            onSelect={(id) => void inspect(id)}
          />
        </section>
      )}

      {detail && (
        <CandidateInspector
          detail={detail}
          pending={pending}
          onClose={() => setDetail(null)}
          onLifecycle={(action) => void lifecycle(action)}
          onExplain={() => void explain()}
        />
      )}

      {!loading && settings && !settings.llm_enabled && (
        <p className="discovery-footnote">
          Level-0 explanation is off. Enable it in Settings when you want
          grounded narrative summaries.
        </p>
      )}
    </div>
  );
}
