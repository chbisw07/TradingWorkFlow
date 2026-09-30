"use client";

import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type RefObject,
} from "react";
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

function words(value: string) {
  return value
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replaceAll(".", " ")
    .replace(/\bv\d+\b/gi, "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (letter) => letter.toUpperCase());
}

function reasonLabel(reason: string) {
  const value = reason.toLowerCase();
  if (value.includes("input")) return "Required scan inputs available";
  if (value.includes("relative") && value.includes("volume"))
    return "Relative volume elevated";
  if (value.includes("breakout")) return "Breakout condition matched";
  if (value.includes("momentum")) return "Momentum condition met";
  if (value.includes("trend")) return "Trend continuation condition met";
  if (value.includes("pullback")) return "Pullback condition matched";
  if (value.includes("close") || value.includes("price"))
    return "Price condition met";
  if (value === "provider-current") return "Provider conditions matched";
  return words(reason);
}

function freshnessLabel(
  value: Candidate["freshness"],
  sourceTime?: string | null,
) {
  if (value === "FRESH") return "Fresh";
  if (value === "STALE") return "Stale";
  if (sourceTime === null || sourceTime === undefined)
    return "Source time unavailable";
  if (sourceTime === "") return "Not yet evaluated";
  return "Unknown";
}

function toleranceLabel(value: string) {
  if (value === "DEGRADED") return "Near limit";
  if (value === "BREACHED") return "Outside";
  if (value === "UNKNOWN") return "Unknown";
  return value === "WITHIN" ? "Within" : "Unavailable";
}

function contextValue(availability: string, value: string | number | null) {
  if (value !== null) return String(value);
  if (availability === "MISSING") return "No current evidence";
  if (availability === "UNAVAILABLE") return "Not available";
  if (availability === "STALE") return "Stale evidence";
  return "Unknown";
}

function providerModeLabel(mode: ProviderStatus["mode"]) {
  return mode === "REMOTE" ? "LIVE" : "SYNTHETIC";
}

function providerHealthLabel(
  health: ProviderStatus["health"],
  enabled: boolean,
) {
  if (!enabled) return "UNAVAILABLE";
  return health.replaceAll("_", " ");
}

function contextHint(value: string) {
  const hints: Record<string, string> = {
    COMPLETE: "All expected context evidence is available.",
    PARTIAL:
      "Some context evidence is missing; no neutral values are inferred.",
    STALE: "Context evidence is older than the configured freshness window.",
    MISSING: "No current context evidence was supplied.",
    UNAVAILABLE: "The context source could not provide evidence.",
  };
  return hints[value] || "Context state is not yet known.";
}

function evidenceLabel(category: string) {
  const labels: Record<string, string> = {
    PROVIDER_SCAN: "Provider scan",
    PRICE: "Instrument price",
    INSTRUMENT_PRICE: "Instrument price",
    MARKET_CONTEXT: "Market context",
    TECHNICAL: "Technical",
    VOLUME_LIQUIDITY: "Volume / liquidity",
  };
  return labels[category] || words(category);
}

function isTechnicalMeasure(name: string) {
  const value = name.toLowerCase();
  return (
    value.includes("digest") ||
    value.includes("hash") ||
    value.endsWith("_id") ||
    value.includes("version")
  );
}

function snapshotChangeLabel(
  current: CandidateDetail["snapshots"][number],
  previous?: CandidateDetail["snapshots"][number],
) {
  if (!previous) return "First recorded observation";
  const changes: string[] = [];
  if (current.lifecycle !== previous.lifecycle)
    changes.push(`Lifecycle changed to ${current.lifecycle}`);
  if (percent(current.relevance.value) !== percent(previous.relevance.value))
    changes.push(`Relevance changed to ${percent(current.relevance.value)}`);
  if (current.tolerance.state !== previous.tolerance.state)
    changes.push(
      `Tolerance changed to ${toleranceLabel(current.tolerance.state)}`,
    );
  const currentEvidence = new Set(
    current.evidence.map((item) => item.category),
  );
  const added = current.evidence.find(
    (item) =>
      !new Set(previous.evidence.map((prior) => prior.category)).has(
        item.category,
      ),
  );
  if (added) changes.push(`${evidenceLabel(added.category)} evidence added`);
  if (changes.length === 0 && currentEvidence.size === previous.evidence.length)
    return "No material evidence change";
  return changes[0] || "Evidence set updated";
}

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
      <table className="discovery-table candidate-table">
        <caption className="sr-only">Discovery candidates</caption>
        <thead>
          <tr>
            <th scope="col">Instrument</th>
            <th scope="col">Intent / horizon</th>
            <th scope="col">Relevance</th>
            <th scope="col">Lifecycle</th>
            <th scope="col">Freshness</th>
            <th scope="col">Evidence</th>
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
              <td data-label="Instrument">
                <strong>{candidate.instrument.symbol}</strong>
                <span>
                  {candidate.instrument.exchange} ·{" "}
                  {candidate.instrument.segment}
                </span>
              </td>
              <td data-label="Intent / horizon">
                <strong>{words(candidate.intent)}</strong>
                <span>{candidate.horizon}</span>
              </td>
              <td data-label="Relevance">
                <strong className="relevance-score">
                  {percent(candidate.relevance.value)}
                </strong>
                <span className="discovery-badge">
                  {candidate.relevance_explanation.band || "UNSCORED"}
                </span>
              </td>
              <td data-label="Lifecycle">
                <span
                  className={`discovery-badge is-${candidate.lifecycle.toLowerCase()}`}
                >
                  {candidate.lifecycle}
                </span>
              </td>
              <td data-label="Freshness">
                <span
                  className={`discovery-badge is-${candidate.freshness.toLowerCase()}`}
                >
                  {freshnessLabel(candidate.freshness)}
                </span>
              </td>
              <td data-label="Evidence">
                {candidate.provider_sources.join(", ")}
              </td>
              <td data-label="Updated">{dateTime(candidate.updated_at)}</td>
              <td data-label="Review">
                <button
                  type="button"
                  aria-pressed={selected === candidate.candidate_id}
                  onClick={() => onSelect(candidate.candidate_id)}
                >
                  {selected === candidate.candidate_id ? "Reviewing" : "Review"}
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
  explaining,
  llmEnabled,
  panelRef,
  onClose,
  onLifecycle,
  onExplain,
}: {
  detail: CandidateDetail;
  pending: boolean;
  explaining: boolean;
  llmEnabled: boolean;
  panelRef: RefObject<HTMLElement | null>;
  onClose: () => void;
  onLifecycle: (action: "DISMISS" | "MARK_DEFUNCT" | "RECOVER") => void;
  onExplain: () => void;
}) {
  const latest = detail.snapshots.at(-1);
  const snapshots = [...detail.snapshots].reverse();
  const requestLifecycle = (action: "DISMISS" | "MARK_DEFUNCT" | "RECOVER") => {
    const messages = {
      DISMISS:
        "Dismiss this candidate? This ends the current discovery episode and records a manual audit transition.",
      MARK_DEFUNCT:
        "Mark this candidate as defunct? Use this when the setup has materially deteriorated. The manual transition is audited.",
      RECOVER:
        "Reopen this candidate as a new reviewable episode? This manual transition is audited.",
    };
    if (window.confirm(messages[action])) onLifecycle(action);
  };
  return (
    <aside
      ref={panelRef}
      className="candidate-inspector"
      aria-labelledby="candidate-detail-heading"
      tabIndex={-1}
    >
      <header>
        <div>
          <p className="eyebrow">CANDIDATE REVIEW</p>
          <h2 id="candidate-detail-heading">{detail.instrument.symbol}</h2>
          <p>
            {words(detail.intent)} · {detail.horizon} ·{" "}
            {detail.instrument.exchange} {detail.instrument.segment}
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
          <small>Attention score, not probability of profit</small>
        </div>
        <div>
          <span>Coverage</span>
          <strong>{percent(detail.relevance.coverage)}</strong>
          <small>Share of expected evidence currently available</small>
        </div>
        <div>
          <span>Episode</span>
          <strong>{detail.lifecycle}</strong>
          <small>
            Current discovery episode · {detail.snapshot_count} snapshot(s)
          </small>
        </div>
        <div>
          <span>Tolerance</span>
          <strong>{toleranceLabel(detail.tolerance.state)}</strong>
          <small>
            Within its {detail.tolerance.horizon} horizon-aware envelope
          </small>
        </div>
      </div>

      <section aria-labelledby="contributions-heading">
        <div className="section-heading-row compact-heading">
          <div>
            <h3 id="contributions-heading">Why it is relevant</h3>
            <p>
              Deterministic evidence contributions; these are not probabilities.
            </p>
          </div>
          <strong className="relevance-total">
            Total {percent(detail.relevance.value)}
          </strong>
        </div>
        <ul className="contribution-list">
          {detail.relevance_explanation.contributions.map((item) => (
            <li key={item.factor}>
              <div>
                <strong>{words(item.factor)}</strong>
                <span>{item.reason}</span>
              </div>
              <b>+{Number(item.contribution).toFixed(2)}</b>
              <span className="discovery-badge is-present">
                {Number(item.contribution) > 0 ? "Present" : "Missing"}
              </span>
            </li>
          ))}
        </ul>
        {detail.relevance_explanation.missing.length > 0 && (
          <div className="evidence-gap is-missing">
            <strong>Missing evidence</strong>
            <p>
              {detail.relevance_explanation.missing.map(words).join(", ")}.
              These inputs are not inferred or assigned a neutral value.
            </p>
          </div>
        )}
        {detail.relevance_explanation.conflicts.length > 0 && (
          <div className="evidence-gap is-conflicting">
            <strong>Conflicting evidence</strong>
            <p>
              {detail.relevance_explanation.conflicts.map(words).join(", ")}
            </p>
          </div>
        )}
      </section>

      <section aria-labelledby="tolerance-heading">
        <h3 id="tolerance-heading">Horizon-aware tolerance</h3>
        <p>
          Tolerance checks whether the setup has materially deteriorated for the
          selected horizon. It does not set risk, a stop-loss, or trading
          authority.
        </p>
        <ul className="context-dimensions">
          {detail.tolerance.dimensions.map((dimension) => (
            <li key={dimension.dimension}>
              <span>{words(dimension.dimension)}</span>
              <strong
                className={`discovery-badge is-${dimension.status.toLowerCase()}`}
                title={`${dimension.reason} Internal state: ${dimension.status}.`}
              >
                {toleranceLabel(dimension.status)}
              </strong>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="evidence-heading">
        <h3 id="evidence-heading">Latest evidence</h3>
        {!latest || latest.evidence.length === 0 ? (
          <p>No current evidence is available.</p>
        ) : (
          <ul className="evidence-list">
            {latest.evidence.map((item) => (
              <li key={item.evidence_id}>
                <div className="evidence-card-heading">
                  <div>
                    <strong>{evidenceLabel(item.category)}</strong>
                    <span>
                      {words(item.polarity)} · {words(item.availability)}
                    </span>
                  </div>
                  <span
                    className={`discovery-badge is-${item.provenance.mode.toLowerCase()}`}
                  >
                    {item.provenance.mode.includes("SYNTHETIC")
                      ? "Synthetic"
                      : words(item.provenance.mode)}
                  </span>
                </div>
                <p>
                  {item.measures
                    .filter((measure) => !isTechnicalMeasure(measure.name))
                    .map(
                      (measure) =>
                        `${words(measure.name)}: ${String(measure.value)} ${measure.unit}`,
                    )
                    .join(" · ") ||
                    item.reason ||
                    "No current measurement supplied"}
                </p>
                <small>
                  {item.source_data_time
                    ? `Source time ${dateTime(item.source_data_time)}`
                    : "Source time unavailable"}
                </small>
                <details className="provenance-details">
                  <summary>Provenance details</summary>
                  <dl>
                    <div>
                      <dt>Provider</dt>
                      <dd>{item.provenance.producer.provider}</dd>
                    </div>
                    <div>
                      <dt>Source</dt>
                      <dd>{item.provenance.source.namespace}</dd>
                    </div>
                    <div>
                      <dt>Mode</dt>
                      <dd>{words(item.provenance.mode)}</dd>
                    </div>
                    <div>
                      <dt>Version</dt>
                      <dd>{item.provenance.producer.service_version}</dd>
                    </div>
                    <div>
                      <dt>Native ID</dt>
                      <dd>{item.provenance.source.native_id}</dd>
                    </div>
                    <div>
                      <dt>Evidence ID</dt>
                      <dd>{item.evidence_id}</dd>
                    </div>
                    {item.measures.some((measure) =>
                      isTechnicalMeasure(measure.name),
                    ) && (
                      <div>
                        <dt>Technical values</dt>
                        <dd>
                          {item.measures
                            .filter((measure) =>
                              isTechnicalMeasure(measure.name),
                            )
                            .map(
                              (measure) =>
                                `${words(measure.name)}: ${String(measure.value)}`,
                            )
                            .join(" · ")}
                        </dd>
                      </div>
                    )}
                  </dl>
                </details>
              </li>
            ))}
          </ul>
        )}
      </section>

      {detail.context && (
        <section aria-labelledby="candidate-context-heading">
          <div className="section-heading-row compact-heading">
            <div>
              <h3 id="candidate-context-heading">Market context</h3>
              <p>
                {detail.context.market} · {words(detail.context.session)}
              </p>
            </div>
            <span
              className={`discovery-badge is-${detail.context.availability.toLowerCase()}`}
            >
              {words(detail.context.availability)}
            </span>
          </div>
          <ul className="context-dimensions">
            {detail.context.dimensions.map((dimension) => (
              <li key={dimension.name}>
                <span>{words(dimension.name)}</span>
                <strong title={dimension.reason || undefined}>
                  {contextValue(dimension.availability, dimension.value)}
                </strong>
              </li>
            ))}
          </ul>
          {detail.context.limitations.length > 0 && (
            <p className="scope-note">
              Limitations: {detail.context.limitations.map(words).join(", ")}
            </p>
          )}
        </section>
      )}

      <section aria-labelledby="history-heading">
        <h3 id="history-heading">Snapshot history</h3>
        <p>Immutable observations, newest first.</p>
        <ol className="snapshot-timeline">
          {snapshots.map((snapshot, index) => (
            <li
              key={snapshot.snapshot_id}
              className={index === 0 ? "is-latest" : undefined}
            >
              <div className="snapshot-title">
                <strong>Snapshot {snapshot.sequence}</strong>
                {index === 0 && <span className="discovery-badge">Newest</span>}
              </div>
              <span>{dateTime(snapshot.observed_at)}</span>
              <dl>
                <div>
                  <dt>Lifecycle</dt>
                  <dd>{snapshot.lifecycle}</dd>
                </div>
                <div>
                  <dt>Relevance</dt>
                  <dd>{percent(snapshot.relevance.value)}</dd>
                </div>
                <div>
                  <dt>Tolerance</dt>
                  <dd>{toleranceLabel(snapshot.tolerance.state)}</dd>
                </div>
              </dl>
              <small>
                {snapshotChangeLabel(snapshot, snapshots[index + 1])}
              </small>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="explanation-heading">
        <div className="section-heading-row">
          <div>
            <h3 id="explanation-heading">Optional AI explanation</h3>
            <p>
              Grounded summary only. It cannot score, transition, recommend, or
              trade.
            </p>
          </div>
          <span className="discovery-badge">
            {explaining ? "Generating" : llmEnabled ? "Available" : "Disabled"}
          </span>
        </div>
        {!llmEnabled && (
          <p className="discovery-callout">
            AI explanation is disabled. Enable it under Settings → Scan &amp;
            Discover → LLM.
          </p>
        )}
        {llmEnabled && detail.explanations.length === 0 && (
          <button disabled={pending} type="button" onClick={onExplain}>
            Generate explanation
          </button>
        )}
        {detail.explanations.map((item: LlmExplanation) => (
          <article className="llm-explanation" key={item.explanation_id}>
            <strong className="discovery-badge">{words(item.grounding)}</strong>
            <p>{item.narrative}</p>
            <small>
              {item.provider}/{item.model} · prompt {item.prompt_version} ·{" "}
              {dateTime(item.generated_at)}
            </small>
          </article>
        ))}
      </section>

      <footer className="candidate-actions">
        <div>
          <strong>Manual episode actions</strong>
          <p>Each state change is confirmed and recorded in the audit trail.</p>
        </div>
        <button
          disabled={pending}
          type="button"
          onClick={() => requestLifecycle("DISMISS")}
        >
          Dismiss candidate
        </button>
        <button
          disabled={pending}
          type="button"
          onClick={() => requestLifecycle("MARK_DEFUNCT")}
        >
          Mark as defunct
        </button>
        {(detail.lifecycle === "DEFUNCT" ||
          detail.lifecycle === "REJECTED") && (
          <button
            disabled={pending}
            type="button"
            onClick={() => requestLifecycle("RECOVER")}
          >
            Reopen candidate
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
  const [explaining, setExplaining] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const inspectorRef = useRef<HTMLElement>(null);

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

  useEffect(() => {
    if (!detail || !inspectorRef.current) return;
    if (typeof inspectorRef.current.scrollIntoView === "function") {
      inspectorRef.current.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
    inspectorRef.current.focus({ preventScroll: true });
  }, [detail]);

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
        {
          action,
          revision: detail.revision,
          reason:
            action === "DISMISS"
              ? "manual-candidate-dismissal"
              : action === "MARK_DEFUNCT"
                ? "manual-material-deterioration"
                : "manual-candidate-recovery",
        },
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
    setExplaining(true);
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
      setExplaining(false);
    }
  }

  const syntheticOnly =
    providers.length > 0 && providers.every((item) => item.mode !== "REMOTE");

  return (
    <div className="discovery-workspace">
      <header className="discovery-hero">
        <div>
          <p className="eyebrow">SPRINT 2 / SCAN &amp; DISCOVER</p>
          <h1>Evidence-led market discovery</h1>
          <p>
            Scan a defined universe, understand why instruments matched, and
            follow candidate evidence over time. Discovery never authorizes a
            trade.
          </p>
        </div>
        <div className="discovery-mode-label">
          <span aria-hidden="true" />
          Discovery status
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

      {!loading && syntheticOnly && (
        <div className="data-mode-banner" role="status">
          <strong>SYNTHETIC / VALIDATION DATA</strong>
          <span>
            Current providers use deterministic validation data. No live
            market-data claim is made.
          </span>
        </div>
      )}
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
                <h2 id="scan-controls-heading">Set up a discovery scan</h2>
                <p>
                  Choose what to scan, the logic and intent, the time horizon,
                  and the evidence source.
                </p>
              </div>
              <span>Maximum 20 symbols</span>
            </div>
            <form onSubmit={runScan}>
              <div className="scan-control-group is-universe">
                <p>Universe</p>
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
                    Comma or space separated NSE symbols.
                  </small>
                </label>
              </div>
              <div className="scan-control-group">
                <p>Scan logic</p>
                <label>
                  <span>Profile</span>
                  <select
                    value={profile}
                    onChange={(event) => setProfile(event.target.value)}
                  >
                    <option value="RELATIVE_VOLUME">Relative volume</option>
                    <option value="TREND_CONTINUATION">
                      Trend continuation
                    </option>
                    <option value="BREAKOUT_WITH_VOLUME">
                      Breakout with volume
                    </option>
                    <option value="PULLBACK_IN_UPTREND">
                      Pullback in uptrend
                    </option>
                    <option value="MOMENTUM">Momentum</option>
                  </select>
                </label>
              </div>
              <div className="scan-control-group">
                <p>Discovery intent</p>
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
              </div>
              <div className="scan-control-group">
                <p>Horizon</p>
                <label>
                  <span>Time window</span>
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
              </div>
              <div className="scan-control-group">
                <p>Provider</p>
                <label>
                  <span>Evidence source</span>
                  <select
                    value={provider}
                    onChange={(event) =>
                      setProvider(event.target.value as ProviderChoice)
                    }
                  >
                    <option value="internal">
                      Internal Scanner V0 · synthetic
                    </option>
                    <option value="tradingview-synthetic">
                      TradingView adapter · synthetic
                    </option>
                  </select>
                </label>
              </div>
              <details className="advanced-controls">
                <summary>Scan conditions</summary>
                <label>
                  <span>Market context requirement</span>
                  <select
                    value={contextMode}
                    onChange={(event) =>
                      setContextMode(event.target.value as ContextMode)
                    }
                  >
                    <option value="partial">Partial context</option>
                    <option value="healthy">Complete context</option>
                    <option value="stale">Stale context</option>
                    <option value="unavailable">Context unavailable</option>
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
          </section>

          <section aria-labelledby="providers-heading">
            <div className="section-heading-row">
              <div>
                <p className="eyebrow">EVIDENCE SOURCES</p>
                <h2 id="providers-heading">Provider status</h2>
                <p>
                  Operational availability and data mode for each configured
                  source.
                </p>
              </div>
            </div>
            <div className="provider-grid">
              {providers.map((item) => {
                const modeLabel = providerModeLabel(item.mode);
                const healthLabel = providerHealthLabel(
                  item.health,
                  item.enabled,
                );
                return (
                  <article key={item.id}>
                    <div className="provider-card-heading">
                      <div>
                        <span
                          className={`provider-health is-${item.health.toLowerCase()}`}
                          aria-hidden="true"
                        />
                        <strong>{item.label}</strong>
                      </div>
                      <div className="provider-badges">
                        <span
                          className={`discovery-badge is-${modeLabel.toLowerCase()}`}
                        >
                          {modeLabel}
                        </span>
                        <span
                          className={`discovery-badge is-${item.health.toLowerCase()}`}
                        >
                          {healthLabel}
                        </span>
                      </div>
                    </div>
                    <p>
                      {item.capabilities.map(words).join(" · ") ||
                        "No capabilities reported"}
                    </p>
                    <small>
                      {item.last_success_at
                        ? `Last success ${dateTime(item.last_success_at)}`
                        : "No successful use recorded"}
                    </small>
                    {item.last_error && (
                      <p className="provider-error">
                        Last error: {item.last_error}
                      </p>
                    )}
                    <details className="provenance-details">
                      <summary>Provider details</summary>
                      <p>
                        Mode: {words(item.mode)} · ID: {item.id}
                      </p>
                    </details>
                  </article>
                );
              })}
            </div>
          </section>

          {result && (
            <section
              className="scan-result"
              aria-labelledby="scan-result-heading"
            >
              <div className="section-heading-row">
                <div>
                  <p className="eyebrow">LATEST COMPLETED SCAN</p>
                  <h2 id="scan-result-heading">Latest scan result</h2>
                  <p>
                    {words(result.summary.profile)} ·{" "}
                    {words(result.summary.intent)} · {result.summary.horizon}
                  </p>
                </div>
                <span>{dateTime(result.summary.completed_at)}</span>
              </div>
              {result.matches.some((match) =>
                match.source_mode.includes("SYNTHETIC"),
              ) && (
                <p className="result-mode-note">
                  <strong>SYNTHETIC DATA</strong> Results below are suitable for
                  workflow validation, not live-market interpretation.
                </p>
              )}
              <div className="scan-metrics">
                <div>
                  <span>Universe size</span>
                  <strong>{result.summary.universe_size}</strong>
                  <small>Symbols evaluated</small>
                </div>
                <div>
                  <span>Matches</span>
                  <strong>{result.summary.match_count}</strong>
                  <small>Met the selected scan logic</small>
                </div>
                <div>
                  <span>Discovery candidates</span>
                  <strong>{result.summary.candidate_count}</strong>
                  <small>Created or updated episodes</small>
                </div>
                <div>
                  <span>Market context</span>
                  <strong
                    className={`discovery-badge is-${result.summary.context_availability.toLowerCase()}`}
                  >
                    {words(result.summary.context_availability)}
                  </strong>
                  <small>
                    {contextHint(result.summary.context_availability)}
                  </small>
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
                      <th scope="col">Freshness</th>
                      <th scope="col">Lineage / details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.matches.map((match) => (
                      <tr key={match.match_id}>
                        <td data-label="Symbol">
                          <strong>{match.symbol}</strong>
                          <span>{match.exchange}</span>
                        </td>
                        <td data-label="Provider">
                          <strong>{match.provider}</strong>
                          <span className="discovery-badge is-synthetic">
                            {match.source_mode.includes("SYNTHETIC")
                              ? "Synthetic"
                              : words(match.source_mode)}
                          </span>
                        </td>
                        <td data-label="Why matched">
                          <ul className="match-reasons">
                            {match.why_matched.map((reason) => (
                              <li key={reason}>{reasonLabel(reason)}</li>
                            ))}
                          </ul>
                        </td>
                        <td data-label="Key metrics">
                          {Object.entries(match.key_metrics)
                            .map(([key, value]) => `${words(key)}: ${value}`)
                            .join(" · ")}
                        </td>
                        <td data-label="Freshness">
                          <span className="discovery-badge is-unknown">
                            Source time unavailable
                          </span>
                        </td>
                        <td data-label="Lineage / details">
                          <details className="provenance-details">
                            <summary>Details</summary>
                            <p>Lineage: {match.lineage}</p>
                            <p>Match ID: {match.match_id}</p>
                            <p>Raw reasons: {match.why_matched.join(", ")}</p>
                          </details>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {result.matches.length === 0 && (
                <p className="discovery-callout">
                  No instruments matched the selected conditions. No candidates
                  were invented.
                </p>
              )}
              {result.summary.degraded.length > 0 && (
                <div className="discovery-callout is-warning">
                  <strong>Some evidence is limited</strong>
                  <ul>
                    {result.summary.degraded.map((item) => (
                      <li key={item}>{words(item)}</li>
                    ))}
                  </ul>
                </div>
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
              <p className="eyebrow">DISCOVERY HISTORY</p>
              <h2 id="candidate-ledger-heading">Candidate ledger</h2>
              <p>
                Review attention scores, evidence freshness, lifecycle, and
                immutable history for your candidates.
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
          explaining={explaining}
          llmEnabled={Boolean(settings?.llm_enabled)}
          panelRef={inspectorRef}
          onClose={() => setDetail(null)}
          onLifecycle={(action) => void lifecycle(action)}
          onExplain={() => void explain()}
        />
      )}

      {!loading && settings && !settings.llm_enabled && (
        <p className="discovery-footnote">
          Optional AI explanation is disabled. Enable it in Settings when a
          grounded narrative summary is useful.
        </p>
      )}
    </div>
  );
}
