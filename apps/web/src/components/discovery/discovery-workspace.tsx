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
  type ContextPolicy,
  type DiscoverySettings,
  type EvidenceChart,
  type EvidenceChartMode,
  type Evidence,
  type HistoricalScanDetail,
  type LlmExplanation,
  type ProviderChoice,
  type ProviderStatus,
  type RunTemporalView,
  type RunViewMode,
  type ScanResult,
  type TemporalObservation,
  type ScanSummary,
} from "../../lib/discovery";
import { EvidenceChartDrawer } from "./evidence-chart-drawer";
import { SurfaceState } from "../ui/surface-state";

type View = "scan" | "candidates";
type IntentValue =
  "INTRADAY_LONG" | "INTRADAY_SHORT" | "POSITIONAL_LONG" | "POSITIONAL_SHORT";
type HorizonValue = "intraday" | "1d" | "5d" | "15d";
type QueueView = "current" | "active" | "all";
type QueueSort = "attention" | "relevance" | "updated" | "lifecycle" | "symbol";

type ProfileRecommendation = {
  intent: IntentValue;
  horizon: HorizonValue;
};

const PROFILE_RECOMMENDATIONS: Record<string, ProfileRecommendation> = {
  RELATIVE_VOLUME: { intent: "INTRADAY_LONG", horizon: "1d" },
  MOMENTUM: { intent: "POSITIONAL_LONG", horizon: "5d" },
  BREAKOUT_WITH_VOLUME: { intent: "POSITIONAL_LONG", horizon: "5d" },
  PULLBACK_IN_UPTREND: { intent: "POSITIONAL_LONG", horizon: "5d" },
  TREND_CONTINUATION: { intent: "POSITIONAL_LONG", horizon: "15d" },
};

const ACTIVE_LIFECYCLES = new Set(["NEW", "CURRENT", "STALE"]);
const LIFECYCLE_PRIORITY: Record<Candidate["lifecycle"], number> = {
  CURRENT: 0,
  NEW: 1,
  STALE: 2,
  DEFUNCT: 3,
  EXPIRED: 4,
  REJECTED: 5,
};
const FRESHNESS_PRIORITY: Record<Candidate["freshness"], number> = {
  FRESH: 0,
  UNKNOWN: 1,
  STALE: 2,
};

const CURRENT_RELEVANCE_POLICY = "deterministic-relevance-v2";

function isLegacyScore(candidate: Candidate) {
  return candidate.relevance.policy?.id !== CURRENT_RELEVANCE_POLICY;
}

function profileLabel(candidate: Candidate) {
  return candidate.profile ? words(candidate.profile) : "Profile unavailable";
}

function LegacyProfileMarker({ candidate }: { candidate: Candidate }) {
  if (!candidate.legacy_profile) return null;
  return (
    <span
      className="discovery-badge is-legacy"
      tabIndex={0}
      title="Created before current profile-lineage metadata was persisted."
      aria-label="Legacy candidate. Created before current profile-lineage metadata was persisted."
    >
      Legacy
    </span>
  );
}

function CandidateRelevance({ candidate }: { candidate: Candidate }) {
  const legacy = isLegacyScore(candidate);
  return (
    <>
      <strong>{percent(candidate.relevance.value)}</strong>
      {legacy ? (
        <span
          className="legacy-score-label"
          tabIndex={0}
          title="Calculated using an earlier relevance model and not directly comparable with current v2 scores."
        >
          Legacy score
        </span>
      ) : null}
    </>
  );
}

function observationLabel(item: TemporalObservation) {
  if (item.kind === "PRESENT") return percent(item.relevance_score);
  return item.kind === "ABSENT" ? "Absent" : "Not evaluated";
}

function ageLabel(seconds: number) {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

function TemporalSparkline({ candidate }: { candidate: Candidate }) {
  const observations = candidate.temporal?.recent_observations || [];
  if (observations.length === 0) return <span>History unavailable</span>;
  const description = observations
    .map(
      (item) =>
        `${dateTime(item.observed_at)} ${words(item.kind)} ${observationLabel(item)} ${item.lifecycle_after || "unchanged"}`,
    )
    .join("; ");
  return (
    <span
      className="temporal-sparkline"
      role="img"
      aria-label={`Recent observation trend: ${description}`}
    >
      {observations.map((item, index) => {
        const modelBreak =
          index > 0 &&
          item.relevance_model !== observations[index - 1].relevance_model;
        const score =
          item.kind === "PRESENT" && item.relevance_score !== null
            ? Number(item.relevance_score)
            : null;
        return (
          <span
            key={item.observation_id}
            className={`temporal-point is-${item.kind.toLowerCase().replace("_", "-")}${modelBreak ? " is-model-break" : ""}`}
            style={
              score === null
                ? undefined
                : { height: `${Math.max(5, score * 28)}px` }
            }
            title={`${dateTime(item.observed_at)} · ${words(item.kind)} · ${observationLabel(item)} · ${item.relevance_model || "no relevance model"}`}
            aria-hidden="true"
          />
        );
      })}
    </span>
  );
}

function compareCandidates(left: Candidate, right: Candidate, sort: QueueSort) {
  const version = Number(isLegacyScore(left)) - Number(isLegacyScore(right));
  const relevance =
    Number(right.relevance.value || 0) - Number(left.relevance.value || 0);
  const updated =
    new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
  const lifecycle =
    LIFECYCLE_PRIORITY[left.lifecycle] - LIFECYCLE_PRIORITY[right.lifecycle];
  const symbol = left.instrument.symbol.localeCompare(right.instrument.symbol);
  if (sort === "relevance") return version || relevance || updated || symbol;
  if (sort === "updated") return updated || version || relevance || symbol;
  if (sort === "lifecycle")
    return lifecycle || version || relevance || updated || symbol;
  if (sort === "symbol") return symbol || version || relevance || updated;
  return (
    version ||
    relevance ||
    lifecycle ||
    FRESHNESS_PRIORITY[left.freshness] - FRESHNESS_PRIORITY[right.freshness] ||
    updated ||
    symbol ||
    left.candidate_id.localeCompare(right.candidate_id)
  );
}

function evidenceSemanticKey(item: Evidence) {
  const metric = item.measures.find(
    (measure) =>
      ![
        "threshold",
        "operator",
        "matched",
        "price-unit",
        "input-digest",
      ].includes(measure.name),
  )?.name;
  return [
    item.category,
    item.provenance.producer.provider,
    item.category === "PROVIDER_SCAN" ? metric : "category",
  ].join(":");
}

function latestEvidence(evidence: Evidence[]) {
  const latest = new Map<string, Evidence>();
  for (const item of evidence) {
    const key = evidenceSemanticKey(item);
    const current = latest.get(key);
    if (
      !current ||
      new Date(item.observed_at) >= new Date(current.observed_at)
    ) {
      latest.set(key, item);
    }
  }
  return [...latest.values()].sort((left, right) =>
    left.category.localeCompare(right.category),
  );
}

function admissionFor(scan: ScanResult) {
  return (
    scan.admission || {
      match_count: scan.summary.match_count,
      admitted_count: scan.summary.candidate_count,
      excluded_count: Math.max(
        0,
        scan.summary.match_count - scan.summary.candidate_count,
      ),
      decisions: scan.matches.map((match) => ({
        match_id: match.match_id,
        symbol: match.symbol,
        status: scan.candidates.some(
          (candidate) => candidate.instrument.symbol === match.symbol,
        )
          ? ("ADMITTED" as const)
          : ("EXCLUDED" as const),
        reason: scan.candidates.some(
          (candidate) => candidate.instrument.symbol === match.symbol,
        )
          ? ("ADMITTED" as const)
          : ("EXCLUDED_DIRECTION" as const),
      })),
    }
  );
}

function compatibilityMessage(
  profile: string,
  intent: IntentValue,
  horizon: HorizonValue,
) {
  const shortSide =
    intent === "INTRADAY_SHORT" || intent === "POSITIONAL_SHORT";
  if (profile === "PULLBACK_IN_UPTREND" && shortSide)
    return "Pullback in uptrend supports long-side intent only.";
  if (
    (intent === "INTRADAY_LONG" || intent === "INTRADAY_SHORT") &&
    horizon !== "intraday" &&
    horizon !== "1d"
  )
    return "Intraday intent requires an intraday or 1-day horizon.";
  if (
    (intent === "POSITIONAL_LONG" || intent === "POSITIONAL_SHORT") &&
    horizon !== "5d" &&
    horizon !== "15d"
  )
    return "Positional intent requires a multi-day horizon.";
  return null;
}

function compatibleIntentForHorizon(
  preferred: IntentValue,
  horizon: HorizonValue,
): IntentValue {
  const intradayHorizon = horizon === "intraday" || horizon === "1d";
  if (preferred === "INTRADAY_LONG" && !intradayHorizon)
    return "POSITIONAL_LONG";
  if (preferred === "INTRADAY_SHORT" && !intradayHorizon)
    return "POSITIONAL_SHORT";
  if (preferred === "POSITIONAL_LONG" && intradayHorizon)
    return "INTRADAY_LONG";
  if (preferred === "POSITIONAL_SHORT" && intradayHorizon)
    return "INTRADAY_SHORT";
  return preferred;
}

function shortId(value: string | null | undefined) {
  return value ? value.slice(0, 8) : "Unavailable";
}

function words(value: string) {
  return value
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replaceAll(".", " ")
    .replace(/\bv\d+\b/gi, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase()
    .replace(/^./, (letter) => letter.toUpperCase());
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
  if (mode === "REMOTE") return "Live";
  if (mode === "SYNTHETIC_VALIDATION") return "Validation";
  return "Synthetic Data";
}

function providerHealthLabel(
  health: ProviderStatus["health"],
  enabled: boolean,
) {
  if (!enabled) return "Disabled";
  if (health === "AVAILABLE") return "Ready";
  return words(health);
}

function evidenceState(availability: string, polarity?: string) {
  if (polarity === "CONFLICTING")
    return { className: "is-conflicting", label: "Conflicting evidence" };
  const states: Record<string, { className: string; label: string }> = {
    PRESENT: { className: "is-present", label: "Evidence available" },
    COMPLETE: { className: "is-complete", label: "Complete context" },
    PARTIAL: { className: "is-partial", label: "Partial context" },
    MISSING: { className: "is-missing", label: "Evidence missing" },
    UNAVAILABLE: {
      className: "is-unavailable",
      label: "Evidence unavailable",
    },
    STALE: { className: "is-stale", label: "Evidence stale" },
  };
  return (
    states[availability] || {
      className: "is-unknown",
      label: "Evidence state unknown",
    }
  );
}

function evidenceDirection(polarity: string) {
  const directions: Record<string, string> = {
    POSITIVE: "Supports the setup",
    NEGATIVE: "Counters the setup",
    NEUTRAL: "Neutral evidence",
    CONFLICTING: "Conflicts with other evidence",
  };
  return directions[polarity] || words(polarity);
}

function evidenceMeasure(
  name: string,
  value: string | number | boolean,
  unit: string,
) {
  const label = words(name);
  if (typeof value === "boolean")
    return `${label}: ${value ? "Condition matched" : "Condition not matched"}`;
  if (unit === "category") return `${label}: ${words(String(value))}`;
  return `${label}: ${String(value)}${unit ? ` ${unit}` : ""}`;
}

function sourceLabel(value: string) {
  if (value === "twf-native") return "TWF scan + market context";
  if (value === "tradingview") return "TradingView";
  return words(value);
}

function evidenceSummary(sources: string[]) {
  if (sources.includes("tradingview") && sources.includes("twf-native"))
    return "Scan + market context";
  if (sources.includes("twf-native")) return "Scan + market context";
  return `${sources.length} evidence source${sources.length === 1 ? "" : "s"}`;
}

function metricLabel(name: string) {
  const labels: Record<string, string> = {
    close: "Price",
    "momentum.10": "Momentum",
    "roc.10": "Momentum",
    "relative_volume.20": "RVOL",
    "rsi.14": "RSI",
    "breakout.20": "20-day breakout",
    "breakdown.20": "20-day breakdown",
  };
  return labels[name] || words(name);
}

function formatMetric(name: string, raw: string) {
  const value = Number(raw);
  if (!Number.isFinite(value)) return raw;
  if (name === "close")
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(value);
  if (name.includes("relative_volume")) return `${value.toFixed(2)}×`;
  if (name.includes("momentum") || name.startsWith("roc."))
    return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
  if (name.startsWith("rsi")) return value.toFixed(0);
  if (name.startsWith("breakout") || name.startsWith("breakdown"))
    return value === 1 ? "Yes" : "No";
  return value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
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

function CandidateMobileList({
  candidates,
  selected,
  onSelect,
  label,
  compact = false,
}: {
  candidates: Candidate[];
  selected: string | null;
  onSelect: (id: string) => void;
  label: string;
  compact?: boolean;
}) {
  return (
    <ul className="discovery-mobile-list" aria-label={label}>
      {candidates.map((candidate) => (
        <li
          key={candidate.candidate_id}
          className="discovery-mobile-card"
          data-candidate-symbol={candidate.instrument.symbol}
          data-selected={selected === candidate.candidate_id}
        >
          <div className="mobile-card-heading">
            <div>
              <strong>{candidate.instrument.symbol}</strong>
              <span>
                {candidate.instrument.exchange} · {candidate.instrument.segment}
              </span>
              <span>
                {candidate.provider_sources.map(sourceLabel).join(" · ")}
              </span>
              <span>Run {shortId(candidate.latest_scan_run_id)}</span>
            </div>
            <span
              className={`discovery-badge is-${candidate.lifecycle.toLowerCase()}`}
              title={words(candidate.lifecycle_reason || "persisted state")}
            >
              {candidate.lifecycle}
            </span>
          </div>
          <dl className="mobile-card-facts">
            <div>
              <dt>Setup</dt>
              <dd>
                {profileLabel(candidate)} · {words(candidate.intent)} ·{" "}
                {candidate.horizon}
                <LegacyProfileMarker candidate={candidate} />
              </dd>
            </div>
            <div>
              <dt>Relevance</dt>
              <dd>
                <CandidateRelevance candidate={candidate} /> ·{" "}
                {candidate.relevance_explanation.band || "Unscored"}
              </dd>
            </div>
            {!compact ? (
              <>
                <div>
                  <dt>Freshness</dt>
                  <dd>{freshnessLabel(candidate.freshness)}</dd>
                </div>
                <div>
                  <dt>Evidence</dt>
                  <dd>{evidenceSummary(candidate.provider_sources)}</dd>
                </div>
              </>
            ) : null}
            <div>
              <dt>Latest observation</dt>
              <dd>
                {candidate.temporal
                  ? `${words(candidate.temporal.latest_observation_kind)} · ${dateTime(candidate.temporal.last_observed_at)}`
                  : dateTime(candidate.updated_at)}
              </dd>
            </div>
            <div>
              <dt>Recent trend</dt>
              <dd>
                <TemporalSparkline candidate={candidate} />
              </dd>
            </div>
          </dl>
          <button
            type="button"
            aria-pressed={selected === candidate.candidate_id}
            onClick={() => onSelect(candidate.candidate_id)}
          >
            {selected === candidate.candidate_id ? "Reviewing" : "Review"}
          </button>
        </li>
      ))}
    </ul>
  );
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
    <>
      <div
        className="discovery-table-wrap discovery-table-desktop"
        tabIndex={0}
      >
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
                data-candidate-symbol={candidate.instrument.symbol}
                data-selected={selected === candidate.candidate_id}
              >
                <td data-label="Instrument">
                  <strong>{candidate.instrument.symbol}</strong>
                  <span>
                    {candidate.instrument.exchange} ·{" "}
                    {candidate.instrument.segment}
                  </span>
                  <LegacyProfileMarker candidate={candidate} />
                </td>
                <td data-label="Intent / horizon">
                  <strong>{words(candidate.intent)}</strong>
                  <span>{candidate.horizon}</span>
                </td>
                <td data-label="Relevance">
                  <span className="relevance-score">
                    <CandidateRelevance candidate={candidate} />
                  </span>
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
                  <strong>{evidenceSummary(candidate.provider_sources)}</strong>
                  <details className="provenance-details">
                    <summary>Sources</summary>
                    <p>
                      {candidate.provider_sources.map(sourceLabel).join(" · ")}
                    </p>
                  </details>
                </td>
                <td data-label="Updated">{dateTime(candidate.updated_at)}</td>
                <td data-label="Review">
                  <button
                    type="button"
                    aria-pressed={selected === candidate.candidate_id}
                    onClick={() => onSelect(candidate.candidate_id)}
                  >
                    {selected === candidate.candidate_id
                      ? "Reviewing"
                      : "Review"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <CandidateMobileList
        candidates={candidates}
        selected={selected}
        onSelect={onSelect}
        label="Discovery candidates"
      />
    </>
  );
}

function CandidateQueue({
  candidates,
  selected,
  onSelect,
  emptyMessage = "No discovery candidates yet.",
}: {
  candidates: Candidate[];
  selected: string | null;
  onSelect: (id: string) => void;
  emptyMessage?: string;
}) {
  if (candidates.length === 0) {
    return <p className="workspace-empty-copy">{emptyMessage}</p>;
  }
  const queue = candidates;
  return (
    <>
      <div
        className="discovery-table-wrap discovery-table-desktop"
        tabIndex={0}
      >
        <table className="discovery-table candidate-queue-table">
          <caption className="sr-only">Discovery queue</caption>
          <thead>
            <tr>
              <th scope="col">Symbol</th>
              <th scope="col">Setup</th>
              <th scope="col">Relevance</th>
              <th scope="col">Observation</th>
              <th scope="col">Trend</th>
              <th scope="col">State</th>
              <th scope="col">Review</th>
            </tr>
          </thead>
          <tbody>
            {queue.map((candidate) => (
              <tr
                key={candidate.candidate_id}
                data-candidate-symbol={candidate.instrument.symbol}
                data-selected={selected === candidate.candidate_id}
              >
                <td data-label="Symbol">
                  <strong>{candidate.instrument.symbol}</strong>
                  <span>
                    {candidate.instrument.exchange} ·{" "}
                    {candidate.instrument.segment}
                  </span>
                  <span>
                    {candidate.provider_sources.map(sourceLabel).join(" · ")}
                  </span>
                </td>
                <td data-label="Setup">
                  <strong>{profileLabel(candidate)}</strong>
                  <span>
                    {words(candidate.intent)} · {candidate.horizon}
                  </span>
                  <LegacyProfileMarker candidate={candidate} />
                </td>
                <td data-label="Relevance">
                  <CandidateRelevance candidate={candidate} />
                  <span>
                    {candidate.relevance_explanation.band || "UNSCORED"}
                  </span>
                </td>
                <td data-label="Observation">
                  <strong>
                    {candidate.temporal
                      ? words(candidate.temporal.latest_observation_kind)
                      : "Legacy"}
                  </strong>
                  <span>
                    {candidate.temporal
                      ? `${dateTime(candidate.temporal.last_observed_at)} · ${ageLabel(candidate.temporal.observation_age_seconds)} ago`
                      : dateTime(candidate.updated_at)}
                  </span>
                  {candidate.temporal?.relevance_delta !== null &&
                  candidate.temporal?.relevance_delta !== undefined ? (
                    <span>
                      Delta{" "}
                      {Number(candidate.temporal.relevance_delta) >= 0
                        ? "+"
                        : ""}
                      {Math.round(
                        Number(candidate.temporal.relevance_delta) * 100,
                      )}{" "}
                      pts
                    </span>
                  ) : null}
                </td>
                <td data-label="Trend">
                  <TemporalSparkline candidate={candidate} />
                </td>
                <td data-label="State">
                  <span
                    className={`discovery-badge is-${candidate.lifecycle.toLowerCase()}`}
                    title={words(
                      candidate.lifecycle_reason || "persisted state",
                    )}
                  >
                    {candidate.lifecycle}
                  </span>
                  <span>
                    {words(candidate.lifecycle_reason || "persisted state")}
                  </span>
                  <span>Run {shortId(candidate.latest_scan_run_id)}</span>
                </td>
                <td data-label="Review">
                  <button
                    type="button"
                    aria-pressed={selected === candidate.candidate_id}
                    onClick={() => onSelect(candidate.candidate_id)}
                  >
                    {selected === candidate.candidate_id
                      ? "Reviewing"
                      : "Review"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <CandidateMobileList
        candidates={queue}
        selected={selected}
        onSelect={onSelect}
        label="Discovery queue"
        compact
      />
    </>
  );
}

function ScanHistory({
  scans,
  selectedRunId,
  pending,
  onView,
  onReuse,
  onArchive,
  onOpenPast,
}: {
  scans: ScanSummary[];
  selectedRunId: string | null;
  pending: boolean;
  onView: (scan: ScanSummary) => void;
  onReuse: (scan: ScanSummary) => void;
  onArchive: (scan: ScanSummary) => void;
  onOpenPast: () => void;
}) {
  return (
    <section
      className="scan-history-panel"
      aria-labelledby="scan-history-heading"
    >
      <div className="section-heading-row compact-heading">
        <div>
          <p className="eyebrow">SCAN HISTORY</p>
          <h2 id="scan-history-heading">Recent scans</h2>
          <p>Latest persisted executions.</p>
        </div>
      </div>
      {scans.length === 0 ? (
        <p className="history-empty">No active scan history.</p>
      ) : (
        <ol className="scan-history-list" aria-label="Recent discovery scans">
          {scans.slice(0, 5).map((scan) => (
            <li key={scan.run_id} data-selected={selectedRunId === scan.run_id}>
              <div className="scan-history-entry-heading">
                <strong>{words(scan.profile)}</strong>
                <span
                  className={`discovery-badge is-${scan.status.toLowerCase()}`}
                >
                  {scan.status}
                </span>
              </div>
              <p>
                {words(scan.provider)} · {scan.universe_size} symbols ·{" "}
                {scan.match_count} matches
              </p>
              <time dateTime={scan.completed_at}>
                {dateTime(scan.completed_at)}
              </time>
              <details className="scan-history-actions">
                <summary>Actions</summary>
                <div>
                  <button
                    type="button"
                    aria-pressed={selectedRunId === scan.run_id}
                    onClick={() => onView(scan)}
                  >
                    View
                  </button>
                  <button type="button" onClick={() => onReuse(scan)}>
                    Use setup
                  </button>
                  <button
                    type="button"
                    disabled={pending}
                    onClick={() => onArchive(scan)}
                  >
                    Archive
                  </button>
                </div>
              </details>
            </li>
          ))}
        </ol>
      )}
      <button className="past-scans-button" type="button" onClick={onOpenPast}>
        Past scans
      </button>
    </section>
  );
}

function PastScansDialog({
  open,
  scans,
  selectedRunId,
  pending,
  onClose,
  onView,
  onReuse,
  onArchive,
  onRestore,
}: {
  open: boolean;
  scans: ScanSummary[];
  selectedRunId: string | null;
  pending: boolean;
  onClose: () => void;
  onView: (scan: ScanSummary) => void;
  onReuse: (scan: ScanSummary) => void;
  onArchive: (scan: ScanSummary) => void;
  onRestore: (scan: ScanSummary) => void;
}) {
  const [datePreset, setDatePreset] = useState("30d");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [providerFilter, setProviderFilter] = useState("all");
  const [profileFilter, setProfileFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [archiveFilter, setArchiveFilter] = useState("all");
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    dialogRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      previousFocus?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  const now = new Date();
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  );
  const providers = [...new Set(scans.map((scan) => scan.provider))];
  const profiles = [...new Set(scans.map((scan) => scan.profile))];
  const filtered = scans.filter((scan) => {
    const completed = new Date(scan.completed_at);
    let inRange = true;
    if (datePreset === "today") inRange = completed >= startOfToday;
    if (datePreset === "7d")
      inRange = completed >= new Date(now.getTime() - 7 * 86_400_000);
    if (datePreset === "30d")
      inRange = completed >= new Date(now.getTime() - 30 * 86_400_000);
    if (datePreset === "custom") {
      if (customFrom) inRange = inRange && completed >= new Date(customFrom);
      if (customTo) inRange = inRange && completed <= new Date(customTo);
    }
    return (
      inRange &&
      (providerFilter === "all" || scan.provider === providerFilter) &&
      (profileFilter === "all" || scan.profile === profileFilter) &&
      (statusFilter === "all" || scan.status === statusFilter) &&
      (archiveFilter === "all" ||
        (archiveFilter === "archived"
          ? Boolean(scan.archived_at)
          : !scan.archived_at))
    );
  });

  return (
    <div className="past-scans-backdrop">
      <section
        ref={dialogRef}
        className="past-scans-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="past-scans-heading"
        tabIndex={-1}
      >
        <header>
          <div>
            <p className="eyebrow">PERSISTED HISTORY</p>
            <h2 id="past-scans-heading">Past scans</h2>
            <p>Archived scans remain persisted and available for analysis.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close past scans">
            Close
          </button>
        </header>
        <div className="past-scan-filters">
          <label>
            <span>Date range</span>
            <select
              value={datePreset}
              onChange={(event) => setDatePreset(event.target.value)}
            >
              <option value="today">Today</option>
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
              <option value="all">All time</option>
              <option value="custom">Custom range</option>
            </select>
          </label>
          {datePreset === "custom" ? (
            <>
              <label>
                <span>From</span>
                <input
                  type="datetime-local"
                  value={customFrom}
                  onChange={(event) => setCustomFrom(event.target.value)}
                />
              </label>
              <label>
                <span>To</span>
                <input
                  type="datetime-local"
                  value={customTo}
                  onChange={(event) => setCustomTo(event.target.value)}
                />
              </label>
            </>
          ) : null}
          <label>
            <span>Provider</span>
            <select
              value={providerFilter}
              onChange={(event) => setProviderFilter(event.target.value)}
            >
              <option value="all">All providers</option>
              {providers.map((item) => (
                <option key={item} value={item}>
                  {words(item)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Profile</span>
            <select
              value={profileFilter}
              onChange={(event) => setProfileFilter(event.target.value)}
            >
              <option value="all">All profiles</option>
              {profiles.map((item) => (
                <option key={item} value={item}>
                  {words(item)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Status</span>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="all">All statuses</option>
              <option value="COMPLETE">Complete</option>
              <option value="FAILED">Failed</option>
            </select>
          </label>
          <label>
            <span>Visibility</span>
            <select
              value={archiveFilter}
              onChange={(event) => setArchiveFilter(event.target.value)}
            >
              <option value="all">Active and archived</option>
              <option value="active">Active only</option>
              <option value="archived">Archived only</option>
            </select>
          </label>
        </div>
        <p className="past-scan-count">{filtered.length} scan(s)</p>
        {filtered.length === 0 ? (
          <p className="history-empty">No scans match these filters.</p>
        ) : (
          <ol className="past-scan-list" aria-label="Past discovery scans">
            {filtered.map((scan) => (
              <li
                key={scan.run_id}
                data-selected={selectedRunId === scan.run_id}
              >
                <div>
                  <strong>{words(scan.profile)}</strong>
                  <span>
                    {words(scan.provider)} · {scan.universe_size} symbols
                  </span>
                  <span>
                    {scan.match_count} matches · {dateTime(scan.completed_at)}
                  </span>
                </div>
                <span
                  className={`discovery-badge is-${scan.status.toLowerCase()}`}
                >
                  {scan.archived_at ? "Archived" : scan.status}
                </span>
                <div className="history-actions">
                  <button type="button" onClick={() => onView(scan)}>
                    View
                  </button>
                  <button type="button" onClick={() => onReuse(scan)}>
                    Use setup
                  </button>
                  {scan.archived_at ? (
                    <button
                      type="button"
                      disabled={pending}
                      onClick={() => onRestore(scan)}
                    >
                      Restore
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={pending}
                      onClick={() => onArchive(scan)}
                    >
                      Archive
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

function ProviderStatusStrip({
  providers,
  contextAvailability,
  llmEnabled,
  latestScan,
}: {
  providers: ProviderStatus[];
  contextAvailability: string | null;
  llmEnabled: boolean;
  latestScan: ScanSummary | null;
}) {
  return (
    <section
      className="workspace-status-strip"
      aria-labelledby="workspace-status-heading"
    >
      <div className="status-strip-heading">
        <p className="eyebrow">WORKSPACE STATUS</p>
        <h2 id="workspace-status-heading">Provider and evidence readiness</h2>
      </div>
      <div className="status-strip-items">
        {providers.map((item) => (
          <article key={item.id} className="status-strip-item">
            <div>
              <strong>{item.label}</strong>
              <span className="provider-mode">
                {providerModeLabel(item.mode)}
              </span>
            </div>
            <span
              className={`provider-operational is-${item.enabled ? item.health.toLowerCase() : "disabled"}`}
            >
              <i aria-hidden="true" />
              {providerHealthLabel(item.health, item.enabled)}
            </span>
            {item.last_error && <small>{item.last_error}</small>}
            {item.id === "tradingview-synthetic" &&
              item.health === "RATE_LIMITED" && (
                <small>Live exact-row proof pending</small>
              )}
          </article>
        ))}
        <article className="status-strip-item">
          <div>
            <strong>Market context</strong>
            <span>Evidence state</span>
          </div>
          <span
            className={`evidence-state ${contextAvailability ? evidenceState(contextAvailability).className : "is-unknown"}`}
          >
            {contextAvailability ? words(contextAvailability) : "Not evaluated"}
          </span>
        </article>
        <article className="status-strip-item">
          <div>
            <strong>Optional AI</strong>
            <span>Level-0 explanation</span>
          </div>
          <span
            className={`provider-operational is-${llmEnabled ? "available" : "disabled"}`}
          >
            <i aria-hidden="true" />
            {llmEnabled ? "Ready" : "Disabled"}
          </span>
        </article>
        <article className="status-strip-item">
          <div>
            <strong>Latest scan</strong>
            <span>
              {latestScan
                ? dateTime(latestScan.completed_at)
                : "No execution yet"}
            </span>
          </div>
          <span
            className={`provider-operational is-${latestScan?.status.toLowerCase() || "disabled"}`}
          >
            <i aria-hidden="true" />
            {latestScan ? words(latestScan.status) : "Waiting"}
          </span>
        </article>
      </div>
    </section>
  );
}

function HistoricalScanSummary({ scan }: { scan: ScanSummary }) {
  return (
    <section
      className="scan-result scan-history-summary"
      aria-labelledby="scan-result-heading"
    >
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">PERSISTED EXECUTION SUMMARY</p>
          <h2 id="scan-result-heading">Latest scan summary</h2>
          <p>
            {words(scan.profile)} · {words(scan.intent)} · {scan.horizon}
          </p>
        </div>
        <span>{dateTime(scan.completed_at)}</span>
      </div>
      <div className="scan-metrics">
        <div>
          <span>Provider</span>
          <strong>{words(scan.provider)}</strong>
          <small>Evidence source</small>
        </div>
        <div>
          <span>Universe size</span>
          <strong>{scan.universe_size}</strong>
          <small>Symbols evaluated</small>
        </div>
        <div>
          <span>Results</span>
          <strong>{scan.match_count}</strong>
          <small>Matches recorded</small>
        </div>
        <div>
          <span>Status</span>
          <strong className={`discovery-badge is-${scan.status.toLowerCase()}`}>
            {words(scan.status)}
          </strong>
          <small>{scan.candidate_count} candidate update(s)</small>
        </div>
      </div>
      <p className="history-summary-note">
        Select View on a recent scan to inspect its stored matches, or Use setup
        to load its configuration without rerunning it.
      </p>
    </section>
  );
}

function HistoricalScanView({
  detail,
  temporal,
  mode,
  onMode,
  onBack,
  onOpenEvidence,
}: {
  detail: HistoricalScanDetail;
  temporal: RunTemporalView | null;
  mode: RunViewMode;
  onMode: (mode: RunViewMode) => void;
  onBack: () => void;
  onOpenEvidence: (
    runId: string,
    matchId: string,
    trigger: HTMLButtonElement,
  ) => void;
}) {
  const { summary, matches, market_context: context } = detail;
  return (
    <section
      className="scan-result historical-scan-view"
      aria-labelledby="historical-scan-heading"
    >
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">READ-ONLY HISTORICAL MODE</p>
          <h2 id="historical-scan-heading">
            Viewing historical scan — {dateTime(summary.completed_at)}
          </h2>
          <p>
            {words(summary.provider)} · {words(summary.profile)} ·{" "}
            {words(summary.intent)} · {summary.horizon}
          </p>
        </div>
        <button type="button" onClick={onBack}>
          Back to latest scan
        </button>
      </div>
      <p className="history-summary-note" role="note">
        Historical rows remain immutable. Current state is a separate latest
        projection.
      </p>
      <div className="scan-metrics">
        <div>
          <span>Universe</span>
          <strong>{summary.universe_size}</strong>
          <small>{summary.universe?.join(", ") || "Stored symbol set"}</small>
        </div>
        <div>
          <span>Results</span>
          <strong>{summary.match_count}</strong>
          <small>Stored match rows</small>
        </div>
        <div>
          <span>Market context</span>
          <strong>
            {words(context?.availability || summary.context_availability)}
          </strong>
          <small>{words(summary.context_policy || "ALLOW_PARTIAL")}</small>
        </div>
        <div>
          <span>Historical status</span>
          <strong
            className={`discovery-badge is-${summary.status.toLowerCase()}`}
          >
            {words(summary.status)}
          </strong>
          <small>{summary.archived_at ? "Archived" : "Active history"}</small>
        </div>
      </div>
      <div
        className="run-view-toggle"
        role="group"
        aria-label="Historical run view"
      >
        <button
          type="button"
          aria-pressed={mode === "as_scanned"}
          onClick={() => onMode("as_scanned")}
        >
          As scanned
        </button>
        <button
          type="button"
          aria-pressed={mode === "current_state"}
          onClick={() => onMode("current_state")}
        >
          Current state
        </button>
      </div>
      {temporal ? (
        <div className="discovery-table-wrap" tabIndex={0}>
          <table className="discovery-table temporal-run-table">
            <caption>
              {mode === "as_scanned"
                ? "Immutable observations from this run"
                : "Current candidate state for this run"}
            </caption>
            <thead>
              <tr>
                <th scope="col">Instrument</th>
                <th scope="col">Outcome</th>
                <th scope="col">Relevance</th>
                <th scope="col">Lifecycle</th>
                <th scope="col">Reason</th>
              </tr>
            </thead>
            <tbody>
              {temporal.items.map((item) => (
                <tr key={item.observation.observation_id}>
                  <td data-label="Instrument">
                    <strong>{item.instrument.symbol}</strong>
                    <span>
                      {item.instrument.exchange} · {item.instrument.segment}
                    </span>
                  </td>
                  <td data-label="Outcome">
                    <strong>{words(item.observation.kind)}</strong>
                    <span>{dateTime(item.observation.observed_at)}</span>
                  </td>
                  <td data-label="Relevance">
                    {mode === "current_state" && item.candidate
                      ? percent(
                          item.candidate.temporal?.last_known_relevance ??
                            item.candidate.relevance.value,
                        )
                      : observationLabel(item.observation)}
                    <span>
                      {item.observation.relevance_model || "No score model"}
                    </span>
                  </td>
                  <td data-label="Lifecycle">
                    {mode === "current_state" && item.candidate
                      ? item.candidate.lifecycle
                      : item.observation.lifecycle_after || "Unchanged"}
                  </td>
                  <td data-label="Reason">{words(item.observation.reason)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {temporal.items.length === 0 ? (
            <p className="workspace-empty-copy">
              No temporal observations were recorded for this legacy run.
            </p>
          ) : null}
        </div>
      ) : (
        <p className="workspace-empty-copy">
          Temporal observations are unavailable for this legacy run.
        </p>
      )}
      <details className="historical-match-details">
        <summary>Stored match evidence ({matches.length})</summary>
        <div className="discovery-table-wrap" tabIndex={0}>
          <table className="discovery-table scan-match-table">
            <caption>Historical scan matches</caption>
            <thead>
              <tr>
                <th scope="col">Symbol</th>
                <th scope="col">Why matched</th>
                <th scope="col">Key metrics</th>
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              {matches.map((match) => (
                <tr key={match.match_id}>
                  <td data-label="Symbol">
                    <button
                      type="button"
                      className="evidence-symbol-link"
                      aria-label={`View scan evidence chart for ${match.symbol}`}
                      title="View scan evidence chart"
                      onClick={(event) =>
                        onOpenEvidence(
                          summary.run_id,
                          match.match_id,
                          event.currentTarget,
                        )
                      }
                    >
                      {match.symbol}
                      <span aria-hidden="true">↗</span>
                    </button>
                    <span>
                      {match.exchange} · {match.segment}
                    </span>
                  </td>
                  <td data-label="Why matched">
                    <ul className="match-reasons">
                      {match.why_matched.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </td>
                  <td data-label="Key metrics">
                    <ul className="metric-list">
                      {Object.entries(match.key_metrics)
                        .slice(0, 4)
                        .map(([key, value]) => (
                          <li key={key}>
                            <span>{metricLabel(key)}</span>
                            <strong>{formatMetric(key, value)}</strong>
                          </li>
                        ))}
                    </ul>
                  </td>
                  <td data-label="Source">
                    <strong>{sourceLabel(match.provider)}</strong>
                    <span>{words(match.source_mode)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

function IdentifierValue({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard?.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }
  return (
    <div className="identifier-value">
      <code title={value}>{value}</code>
      <button
        type="button"
        onClick={() => void copy()}
        aria-label={`Copy ${label}`}
      >
        {copied ? "Copied" : "Copy"}
      </button>
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
  const visibleEvidence = latest ? latestEvidence(latest.evidence) : [];
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
            {profileLabel(detail)} · {words(detail.intent)} · {detail.horizon} ·{" "}
            {detail.instrument.exchange} {detail.instrument.segment}
          </p>
          <LegacyProfileMarker candidate={detail} />
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
          <CandidateRelevance candidate={detail} />
          <small>
            Attention score, not probability of profit ·{" "}
            {detail.relevance.policy.id}
          </small>
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
            {words(detail.lifecycle_reason || "persisted state")} ·{" "}
            {detail.snapshot_count} snapshot(s)
          </small>
        </div>
        <div>
          <span>Tolerance</span>
          <strong
            className={`tolerance-state is-${detail.tolerance.state.toLowerCase()}`}
          >
            {toleranceLabel(detail.tolerance.state)}
          </strong>
          <small>
            Within its {detail.tolerance.horizon} horizon-aware envelope
          </small>
        </div>
      </div>

      <details className="candidate-provenance provenance-details">
        <summary>Candidate provenance</summary>
        <dl>
          <div>
            <dt>Candidate ID</dt>
            <dd>
              <IdentifierValue
                label="candidate identifier"
                value={detail.candidate_id}
              />
            </dd>
          </div>
          <div>
            <dt>Episode ID</dt>
            <dd>
              <IdentifierValue
                label="episode identifier"
                value={detail.episode_id}
              />
            </dd>
          </div>
          {detail.latest_scan_run_id && (
            <div>
              <dt>Latest run</dt>
              <dd>
                <IdentifierValue
                  label="latest scan run identifier"
                  value={detail.latest_scan_run_id}
                />
              </dd>
            </div>
          )}
        </dl>
      </details>

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
              <span
                className={`evidence-state ${Number(item.contribution) > 0 ? "is-present" : "is-missing"}`}
              >
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
                className={`tolerance-state is-${dimension.status.toLowerCase()}`}
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
        {!latest || visibleEvidence.length === 0 ? (
          <p>No current evidence is available.</p>
        ) : (
          <ul className="evidence-list">
            {visibleEvidence.map((item) => {
              const state = evidenceState(item.availability, item.polarity);
              return (
                <li key={item.evidence_id} className={state.className}>
                  <div className="evidence-card-heading">
                    <div>
                      <strong>{evidenceLabel(item.category)}</strong>
                      <span>{evidenceDirection(item.polarity)}</span>
                    </div>
                    <span className={`evidence-state ${state.className}`}>
                      {state.label}
                    </span>
                  </div>
                  <p>
                    {item.measures
                      .filter((measure) => !isTechnicalMeasure(measure.name))
                      .map((measure) =>
                        evidenceMeasure(
                          measure.name,
                          measure.value,
                          measure.unit,
                        ),
                      )
                      .join(" · ") ||
                      item.reason ||
                      "No current measurement supplied"}
                  </p>
                  <small>
                    {item.provenance.mode.includes("SYNTHETIC")
                      ? "Synthetic source"
                      : words(item.provenance.mode)}
                    {" · "}
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
                        <dd>
                          <IdentifierValue
                            label="native identifier"
                            value={item.provenance.source.native_id}
                          />
                        </dd>
                      </div>
                      <div>
                        <dt>Evidence ID</dt>
                        <dd>
                          <IdentifierValue
                            label="evidence identifier"
                            value={item.evidence_id}
                          />
                        </dd>
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
              );
            })}
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
                <div>
                  <strong title={dimension.reason || undefined}>
                    {contextValue(dimension.availability, dimension.value)}
                  </strong>
                  <small
                    className={`evidence-state ${evidenceState(dimension.availability).className}`}
                  >
                    {evidenceState(dimension.availability).label}
                  </small>
                </div>
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

      <section aria-labelledby="temporal-history-heading">
        <div className="section-heading-row compact-heading">
          <div>
            <h3 id="temporal-history-heading">Observation history</h3>
            <p>Explicit comparable scan outcomes, newest first.</p>
          </div>
          <TemporalSparkline candidate={detail} />
        </div>
        {detail.temporal ? (
          <dl className="temporal-facts">
            <div>
              <dt>Last observed</dt>
              <dd>{dateTime(detail.temporal.last_observed_at)}</dd>
            </div>
            <div>
              <dt>Latest comparable scan</dt>
              <dd>{shortId(detail.temporal.latest_comparable_run_id)}</dd>
            </div>
            <div>
              <dt>Latest present scan</dt>
              <dd>{shortId(detail.temporal.latest_present_run_id)}</dd>
            </div>
            <div>
              <dt>Observation age / window</dt>
              <dd>
                {ageLabel(detail.temporal.observation_age_seconds)} ·{" "}
                {words(detail.temporal.window_status)}
              </dd>
            </div>
          </dl>
        ) : (
          <p>Legacy candidate has no reconstructed temporal observations.</p>
        )}
        <ol className="temporal-timeline">
          {(detail.observations || []).map((item) => (
            <li key={item.observation_id}>
              <time dateTime={item.observed_at}>
                {dateTime(item.observed_at)}
              </time>
              <strong>{words(item.kind)}</strong>
              <span>{observationLabel(item)}</span>
              <span>{item.lifecycle_after || "Lifecycle unchanged"}</span>
              <small>
                Run {shortId(item.run_id)} · {words(item.reason)} ·{" "}
                {words(item.coverage)}
              </small>
            </li>
          ))}
        </ol>
      </section>

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
                  <dd>
                    {snapshot.lifecycle} ·{" "}
                    {words(
                      snapshot.lifecycle_reason || "persisted snapshot state",
                    )}
                  </dd>
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
  const view = initialView;
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [recentScans, setRecentScans] = useState<ScanSummary[]>([]);
  const [pastScans, setPastScans] = useState<ScanSummary[]>([]);
  const [pastScansOpen, setPastScansOpen] = useState(false);
  const [historyPending, setHistoryPending] = useState(false);
  const [selectedHistory, setSelectedHistory] = useState<ScanSummary | null>(
    null,
  );
  const [historicalDetail, setHistoricalDetail] =
    useState<HistoricalScanDetail | null>(null);
  const [runTemporal, setRunTemporal] = useState<RunTemporalView | null>(null);
  const [runViewMode, setRunViewMode] = useState<RunViewMode>("as_scanned");
  const [settings, setSettings] = useState<DiscoverySettings | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [detail, setDetail] = useState<CandidateDetail | null>(null);
  const [universe, setUniverse] = useState(
    "RELIANCE, MCX, HDFCBANK, INFY, BSE, NIFTY, BANKNIFTY",
  );
  const [provider, setProvider] = useState<ProviderChoice>("internal");
  const [profile, setProfile] = useState("RELATIVE_VOLUME");
  const [horizon, setHorizon] = useState<HorizonValue>("5d");
  const [intent, setIntent] = useState<IntentValue>("INTRADAY_LONG");
  const [intentOverridden, setIntentOverridden] = useState(false);
  const [horizonOverridden, setHorizonOverridden] = useState(false);
  const [contextMode, setContextMode] = useState<ContextMode>("partial");
  const [contextPolicy, setContextPolicy] =
    useState<ContextPolicy>("ALLOW_PARTIAL");
  const [queueView, setQueueView] = useState<QueueView>("active");
  const [queueSort, setQueueSort] = useState<QueueSort>("attention");
  const [queueSearch, setQueueSearch] = useState("");
  const [queueBand, setQueueBand] = useState("all");
  const [queueLifecycle, setQueueLifecycle] = useState("all");
  const [queueIntent, setQueueIntent] = useState("all");
  const [queueHorizon, setQueueHorizon] = useState("all");
  const [queueProfile, setQueueProfile] = useState("all");
  const [queueFreshness, setQueueFreshness] = useState("all");
  const [queueProvider, setQueueProvider] = useState("all");
  const [pending, setPending] = useState(false);
  const [explaining, setExplaining] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [toast, setToast] = useState("");
  const [evidenceChart, setEvidenceChart] = useState<EvidenceChart | null>(
    null,
  );
  const [evidenceIdentity, setEvidenceIdentity] = useState<{
    runId: string;
    matchId: string;
  } | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const evidenceTriggerRef = useRef<HTMLButtonElement | null>(null);
  const inspectorRef = useRef<HTMLElement>(null);

  async function loadEvidenceChart(
    runId: string,
    matchId: string,
    mode: EvidenceChartMode,
  ) {
    setEvidenceLoading(true);
    try {
      setEvidenceChart(
        await discoveryApi<EvidenceChart>(
          `scans/${runId}/matches/${matchId}/evidence-chart?mode=${mode}`,
        ),
      );
    } catch {
      setEvidenceChart(null);
      setError("Unable to load scan evidence chart.");
      setEvidenceIdentity(null);
    } finally {
      setEvidenceLoading(false);
    }
  }

  function openEvidenceChart(
    runId: string,
    matchId: string,
    trigger: HTMLButtonElement,
  ) {
    evidenceTriggerRef.current = trigger;
    setEvidenceIdentity({ runId, matchId });
    setEvidenceChart(null);
    setError("");
    void loadEvidenceChart(runId, matchId, "as_scanned");
  }

  function changeEvidenceMode(mode: EvidenceChartMode) {
    if (!evidenceIdentity || mode === evidenceChart?.mode) return;
    void loadEvidenceChart(
      evidenceIdentity.runId,
      evidenceIdentity.matchId,
      mode,
    );
  }

  function closeEvidenceChart() {
    evidenceTriggerRef.current?.focus();
    setEvidenceIdentity(null);
    setEvidenceChart(null);
  }

  function applyLoadedState(
    providerState: ProviderStatus[],
    candidatePage: { items: Candidate[] },
    currentSettings: DiscoverySettings,
    history: ScanSummary[],
  ) {
    setProviders(providerState);
    setCandidates(candidatePage.items);
    setSettings(currentSettings);
    setRecentScans(history);
    const defaultRecommendation =
      PROFILE_RECOMMENDATIONS[currentSettings.default_profile] ||
      PROFILE_RECOMMENDATIONS.RELATIVE_VOLUME;
    setProvider(currentSettings.default_provider);
    setProfile(currentSettings.default_profile);
    const defaultHorizon = currentSettings.default_horizon as HorizonValue;
    setHorizon(defaultHorizon);
    setIntent(
      compatibleIntentForHorizon(defaultRecommendation.intent, defaultHorizon),
    );
    setIntentOverridden(false);
    setHorizonOverridden(
      currentSettings.default_horizon !== defaultRecommendation.horizon,
    );
  }

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [providerState, candidatePage, currentSettings, history] =
        await Promise.all([
          discoveryApi<ProviderStatus[]>("status"),
          discoveryApi<{ items: Candidate[] }>("candidates?limit=50"),
          discoveryApi<DiscoverySettings>("settings"),
          discoveryApi<ScanSummary[]>("scans?limit=5"),
        ]);
      applyLoadedState(providerState, candidatePage, currentSettings, history);
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
      discoveryApi<ScanSummary[]>("scans?limit=5"),
    ])
      .then(([providerState, candidatePage, currentSettings, history]) => {
        if (!active) return;
        applyLoadedState(
          providerState,
          candidatePage,
          currentSettings,
          history,
        );
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
        block: "nearest",
      });
    }
    inspectorRef.current.focus({ preventScroll: true });
  }, [detail]);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(""), 5000);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  function changeProfile(nextProfile: string) {
    const recommendation = PROFILE_RECOMMENDATIONS[nextProfile];
    setProfile(nextProfile);
    if (!recommendation) return;
    if (!intentOverridden) setIntent(recommendation.intent);
    if (!horizonOverridden) setHorizon(recommendation.horizon);
  }

  function applyProfileRecommendation() {
    const recommendation = PROFILE_RECOMMENDATIONS[profile];
    if (!recommendation) return;
    setIntent(recommendation.intent);
    setHorizon(recommendation.horizon);
    setIntentOverridden(false);
    setHorizonOverridden(false);
  }

  function reuseScan(scan: ScanSummary) {
    const recommendation = PROFILE_RECOMMENDATIONS[scan.profile];
    const supportedIntents: IntentValue[] = [
      "INTRADAY_LONG",
      "INTRADAY_SHORT",
      "POSITIONAL_LONG",
      "POSITIONAL_SHORT",
    ];
    const supportedHorizons: HorizonValue[] = ["intraday", "1d", "5d", "15d"];
    if (
      !recommendation ||
      !supportedIntents.includes(scan.intent as IntentValue) ||
      !supportedHorizons.includes(scan.horizon as HorizonValue) ||
      !scan.universe?.length
    ) {
      setError("Setup could not be restored.");
      return;
    }
    setError("");
    setProfile(scan.profile);
    setProvider(scan.provider);
    setUniverse(scan.universe.join(", "));
    setContextMode(scan.context_mode || "partial");
    setContextPolicy(scan.context_policy || "ALLOW_PARTIAL");
    setIntent(scan.intent as IntentValue);
    setHorizon(scan.horizon as HorizonValue);
    setIntentOverridden(true);
    setHorizonOverridden(true);
    setPastScansOpen(false);
    setNotice("");
    setToast("Historical scan setup loaded. Review before running.");
  }

  async function loadRunTemporal(runId: string, mode: RunViewMode) {
    setRunTemporal(null);
    const view = await discoveryApi<RunTemporalView>(
      `scans/${runId}/temporal?mode=${mode}&limit=100`,
    );
    setRunTemporal(view);
    setRunViewMode(mode);
  }

  async function viewScan(scan: ScanSummary) {
    setHistoryPending(true);
    setError("");
    try {
      const historical = await discoveryApi<HistoricalScanDetail>(
        `scans/${scan.run_id}`,
      );
      setHistoricalDetail(historical);
      setRunTemporal(null);
      setRunViewMode("as_scanned");
      setQueueView("active");
      setSelectedHistory(scan);
      setPastScansOpen(false);
      try {
        setRunTemporal(
          await discoveryApi<RunTemporalView>(
            `scans/${scan.run_id}/temporal?mode=as_scanned&limit=100`,
          ),
        );
      } catch {
        // Pre-temporal runs remain reviewable through their immutable match detail.
      }
    } catch {
      setError("Unable to load historical scan.");
    } finally {
      setHistoryPending(false);
    }
  }

  async function changeRunView(mode: RunViewMode) {
    if (!selectedHistory || mode === runViewMode) return;
    setHistoryPending(true);
    setError("");
    try {
      await loadRunTemporal(selectedHistory.run_id, mode);
    } catch {
      setError("Unable to load temporal run state.");
    } finally {
      setHistoryPending(false);
    }
  }

  async function openPastScans() {
    setPastScansOpen(true);
    setHistoryPending(true);
    setError("");
    try {
      setPastScans(
        await discoveryApi<ScanSummary[]>(
          "scans?limit=100&include_archived=true",
        ),
      );
    } catch {
      setError("Unable to load scan history.");
    } finally {
      setHistoryPending(false);
    }
  }

  async function setArchived(scan: ScanSummary, archived: boolean) {
    setHistoryPending(true);
    setError("");
    try {
      const next = await discoveryApi<ScanSummary>(
        `scans/${scan.run_id}/${archived ? "archive" : "restore"}`,
        "POST",
      );
      setPastScans((items) => [
        next,
        ...items.filter((item) => item.run_id !== next.run_id),
      ]);
      if (archived) {
        setRecentScans((items) =>
          items.filter((item) => item.run_id !== next.run_id),
        );
      } else {
        setRecentScans((items) =>
          [next, ...items.filter((item) => item.run_id !== next.run_id)]
            .sort(
              (left, right) =>
                new Date(right.completed_at).getTime() -
                new Date(left.completed_at).getTime(),
            )
            .slice(0, 5),
        );
      }
      setHistoricalDetail((current) =>
        current?.summary.run_id === next.run_id
          ? { ...current, summary: next }
          : current,
      );
      setSelectedHistory((current) =>
        current?.run_id === next.run_id ? next : current,
      );
      setNotice("");
      setToast(
        archived ? "Scan archived." : "Scan restored to recent history.",
      );
    } catch {
      setError(
        archived ? "Unable to archive scan." : "Unable to restore scan.",
      );
    } finally {
      setHistoryPending(false);
    }
  }

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
    setHistoricalDetail(null);
    try {
      const next = await discoveryApi<ScanResult>("scans", "POST", {
        universe: symbols,
        provider,
        profile,
        horizon,
        intent,
        include_llm: false,
        context_mode: contextMode,
        context_policy: contextPolicy,
      });
      setResult(next);
      const nextAdmission = admissionFor(next);
      setQueueView("current");
      setSelectedHistory(null);
      setHistoricalDetail(null);
      const page = await discoveryApi<{ items: Candidate[] }>(
        "candidates?limit=50",
      );
      setCandidates(page.items);
      setRecentScans((items) =>
        [
          next.summary,
          ...items.filter((item) => item.run_id !== next.summary.run_id),
        ].slice(0, 5),
      );
      setPastScans((items) =>
        items.length === 0
          ? items
          : [
              next.summary,
              ...items.filter((item) => item.run_id !== next.summary.run_id),
            ],
      );
      setNotice(
        next.summary.match_count === 0
          ? "Scan completed with no matches. No candidates were invented."
          : `Scan completed with ${nextAdmission.match_count} match(es): ${nextAdmission.admitted_count} admitted and ${nextAdmission.excluded_count} excluded.`,
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

  const recommendation =
    PROFILE_RECOMMENDATIONS[profile] || PROFILE_RECOMMENDATIONS.RELATIVE_VOLUME;
  const compatibility = compatibilityMessage(profile, intent, horizon);
  const activeCandidates = candidates.filter((candidate) =>
    ACTIVE_LIFECYCLES.has(candidate.lifecycle),
  );
  const currentCandidates = result?.candidates || [];
  const baseQueueCandidates =
    queueView === "current"
      ? currentCandidates
      : queueView === "active"
        ? activeCandidates
        : candidates;
  const normalizedSearch = queueSearch.trim().toUpperCase();
  const queueCandidates = baseQueueCandidates
    .filter((candidate) => {
      const matchesSearch =
        !normalizedSearch ||
        candidate.instrument.symbol.includes(normalizedSearch) ||
        candidate.instrument.native.native_id
          .toUpperCase()
          .includes(normalizedSearch);
      return (
        matchesSearch &&
        (queueBand === "all" ||
          candidate.relevance_explanation.band === queueBand) &&
        (queueLifecycle === "all" || candidate.lifecycle === queueLifecycle) &&
        (queueIntent === "all" || candidate.intent === queueIntent) &&
        (queueHorizon === "all" || candidate.horizon === queueHorizon) &&
        (queueProfile === "all" || candidate.profile === queueProfile) &&
        (queueFreshness === "all" || candidate.freshness === queueFreshness) &&
        (queueProvider === "all" ||
          candidate.provider_sources.includes(queueProvider))
      );
    })
    .sort((left, right) => compareCandidates(left, right, queueSort));
  const filterValues = {
    intents: [
      ...new Set(candidates.map((candidate) => candidate.intent)),
    ].sort(),
    horizons: [
      ...new Set(candidates.map((candidate) => candidate.horizon)),
    ].sort(),
    profiles: [
      ...new Set(
        candidates
          .map((candidate) => candidate.profile)
          .filter((value): value is string => Boolean(value)),
      ),
    ].sort(),
    providers: [
      ...new Set(candidates.flatMap((candidate) => candidate.provider_sources)),
    ].sort(),
  };
  const scanAdmission = result ? admissionFor(result) : null;
  const latestSummary =
    result?.summary || recentScans[0] || selectedHistory || null;
  const topCandidate = [...candidates].sort((left, right) =>
    compareCandidates(left, right, "attention"),
  )[0];
  const inspector = detail ? (
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
  ) : (
    <aside className="inspector-placeholder" aria-label="Candidate inspector">
      <div>
        <p className="eyebrow">CANDIDATE INSPECTOR</p>
        <h2>Evidence and history</h2>
      </div>
      <p>Select a candidate to inspect evidence and history.</p>
      {topCandidate && (
        <small>
          {candidates.length} candidate(s) in queue · highest relevance{" "}
          {topCandidate.instrument.symbol} at{" "}
          {percent(topCandidate.relevance.value)}
        </small>
      )}
    </aside>
  );

  return (
    <div className="discovery-workspace">
      {evidenceIdentity ? (
        <EvidenceChartDrawer
          chart={evidenceChart}
          loading={evidenceLoading}
          onClose={closeEvidenceChart}
          onMode={changeEvidenceMode}
        />
      ) : null}
      <header className="discovery-hero">
        <div>
          <p className="eyebrow">SCAN &amp; DISCOVER</p>
          <h1>
            {view === "scan"
              ? "Evidence-led market discovery"
              : "Discovery candidate review"}
          </h1>
          <p>
            {view === "scan"
              ? "Scan a defined universe, understand why instruments matched, and follow candidate evidence over time. Discovery never authorizes a trade."
              : "Review persisted candidates, evidence changes, and lifecycle history. Attention scores are not trade recommendations."}
          </p>
        </div>
        <div className="discovery-mode-label">
          <span aria-hidden="true" />
          {view === "scan" ? "Scan workspace" : "Candidate ledger"}
        </div>
      </header>

      {toast && (
        <div
          className="discovery-toast"
          role="status"
          aria-label={
            toast.startsWith("Historical scan setup")
              ? "Setup loaded"
              : "Scan history updated"
          }
          aria-live="polite"
        >
          <span>{toast}</span>
          <button
            type="button"
            onClick={() => setToast("")}
            aria-label="Dismiss notification"
          >
            Dismiss
          </button>
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
          description="Reading your provider status, settings, scan history, and candidate history."
        />
      )}

      {!loading && view === "scan" && (
        <>
          <ProviderStatusStrip
            providers={providers}
            contextAvailability={latestSummary?.context_availability || null}
            llmEnabled={Boolean(settings?.llm_enabled)}
            latestScan={latestSummary}
          />
          <div
            className={`scan-workstation-grid ${detail ? "has-inspector" : "without-inspector"}`}
          >
            <div className="scan-workstation-setup">
              <section
                className="scan-control-panel"
                aria-labelledby="scan-controls-heading"
              >
                <div className="section-heading-row">
                  <div>
                    <p className="eyebrow">SCAN SETUP</p>
                    <h2 id="scan-controls-heading">Configure scan</h2>
                    <p>Maximum 20 NSE symbols.</p>
                  </div>
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
                      <span>Scan profile</span>
                      <select
                        value={profile}
                        onChange={(event) => changeProfile(event.target.value)}
                        aria-describedby="profile-help"
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
                      <small id="profile-help">
                        The market pattern TWF scans for.
                      </small>
                    </label>
                  </div>
                  <div className="scan-control-group">
                    <p>Purpose</p>
                    <label>
                      <span>Discovery intent</span>
                      <select
                        value={intent}
                        onChange={(event) => {
                          setIntent(event.target.value as IntentValue);
                          setIntentOverridden(true);
                        }}
                        aria-describedby="intent-help"
                      >
                        <option value="INTRADAY_LONG">Intraday long</option>
                        <option value="INTRADAY_SHORT">Intraday short</option>
                        <option value="POSITIONAL_LONG">Positional long</option>
                        <option value="POSITIONAL_SHORT">
                          Positional short
                        </option>
                      </select>
                      <small id="intent-help">
                        How a matched setup should be interpreted and tracked.
                      </small>
                    </label>
                  </div>
                  <div className="scan-control-group">
                    <p>Time window</p>
                    <label>
                      <span>Horizon</span>
                      <select
                        value={horizon}
                        onChange={(event) => {
                          setHorizon(event.target.value as HorizonValue);
                          setHorizonOverridden(true);
                        }}
                        aria-describedby="horizon-help"
                      >
                        <option value="intraday">Intraday</option>
                        <option value="1d">1 day</option>
                        <option value="5d">5 days</option>
                        <option value="15d">15 days</option>
                      </select>
                      <small id="horizon-help">
                        How long this discovery setup is expected to remain
                        relevant.
                      </small>
                    </label>
                  </div>
                  <div className="profile-suggestion" role="note">
                    <span>
                      Suggested: {words(recommendation.intent)} ·{" "}
                      {recommendation.horizon}
                    </span>
                    {(intentOverridden || horizonOverridden) && (
                      <button
                        type="button"
                        onClick={applyProfileRecommendation}
                      >
                        Apply suggestion
                      </button>
                    )}
                  </div>
                  <div className="scan-control-group">
                    <p>Evidence</p>
                    <label>
                      <span>Provider</span>
                      <select
                        value={provider}
                        onChange={(event) =>
                          setProvider(event.target.value as ProviderChoice)
                        }
                        aria-describedby="provider-help"
                      >
                        <option value="internal">
                          Internal Scanner V0 · synthetic
                        </option>
                        <option value="tradingview-synthetic">
                          TradingView adapter · validation
                        </option>
                      </select>
                      <small id="provider-help">
                        Where the scan evidence comes from.
                      </small>
                    </label>
                  </div>
                  <div className="scan-control-group">
                    <p>Context policy</p>
                    <label>
                      <span>Market context requirement</span>
                      <select
                        value={contextMode}
                        onChange={(event) => {
                          const nextMode = event.target.value as ContextMode;
                          setContextMode(nextMode);
                          setContextPolicy(
                            nextMode === "healthy"
                              ? "REQUIRE_COMPLETE"
                              : nextMode === "unavailable"
                                ? "OPTIONAL"
                                : "ALLOW_PARTIAL",
                          );
                        }}
                        aria-describedby="context-help"
                      >
                        <option value="healthy">
                          Require complete context
                        </option>
                        <option value="partial">Allow partial context</option>
                        <option value="unavailable">Context optional</option>
                      </select>
                      <small id="context-help">
                        {contextMode === "healthy"
                          ? "Incomplete context blocks candidate admission."
                          : contextMode === "unavailable"
                            ? "Context is optional; missing context does not reduce relevance coverage."
                            : "Missing evidence remains visible and reduces coverage when context participates."}
                      </small>
                    </label>
                  </div>
                  {compatibility && (
                    <p
                      id="scan-compatibility"
                      className="scan-compatibility-warning"
                      role="alert"
                    >
                      {compatibility}
                    </p>
                  )}
                  <button
                    className="run-scan-button"
                    disabled={pending || Boolean(compatibility)}
                    aria-describedby={
                      compatibility ? "scan-compatibility" : undefined
                    }
                    type="submit"
                  >
                    {pending ? "Running…" : "Run scan"}
                  </button>
                </form>
              </section>
              <ScanHistory
                scans={recentScans}
                selectedRunId={selectedHistory?.run_id || null}
                pending={historyPending}
                onView={(scan) => void viewScan(scan)}
                onReuse={reuseScan}
                onArchive={(scan) => void setArchived(scan, true)}
                onOpenPast={() => void openPastScans()}
              />
            </div>

            <div className="scan-workstation-results">
              {historicalDetail ? (
                <HistoricalScanView
                  detail={historicalDetail}
                  temporal={runTemporal}
                  mode={runViewMode}
                  onMode={(mode) => void changeRunView(mode)}
                  onBack={() => {
                    setHistoricalDetail(null);
                    setRunTemporal(null);
                    setSelectedHistory(null);
                  }}
                  onOpenEvidence={openEvidenceChart}
                />
              ) : result ? (
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
                        {words(result.summary.intent)} ·{" "}
                        {result.summary.horizon}
                      </p>
                    </div>
                    <span>{dateTime(result.summary.completed_at)}</span>
                  </div>
                  {result.matches.some((match) =>
                    match.source_mode.includes("SYNTHETIC"),
                  ) && (
                    <p className="result-mode-note">
                      <strong>SYNTHETIC DATA</strong> Deterministic validation
                      results; no live-market claim.
                    </p>
                  )}
                  <div className="scan-metrics">
                    <div>
                      <span>Universe size</span>
                      <strong>{result.summary.universe_size}</strong>
                      <small>Symbols evaluated</small>
                    </div>
                    <div>
                      <span>Match admission</span>
                      <strong>{scanAdmission!.match_count} matches</strong>
                      <small>
                        {scanAdmission!.admitted_count} admitted ·{" "}
                        {scanAdmission!.excluded_count} excluded
                      </small>
                    </div>
                    <div>
                      <span>Discovery candidates</span>
                      <strong>{result.summary.candidate_count}</strong>
                      <small>Episodes updated</small>
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
                  <details className="admission-summary">
                    <summary>
                      Admission details: {scanAdmission!.admitted_count}{" "}
                      admitted · {scanAdmission!.excluded_count} excluded
                    </summary>
                    <ul>
                      {scanAdmission!.decisions.map((decision) => (
                        <li key={decision.match_id}>
                          <strong>{decision.symbol}</strong>
                          <span>{words(decision.reason)}</span>
                        </li>
                      ))}
                    </ul>
                  </details>
                  <div className="discovery-table-wrap" tabIndex={0}>
                    <table className="discovery-table scan-match-table">
                      <caption className="sr-only">
                        Latest normalized scan matches
                      </caption>
                      <thead>
                        <tr>
                          <th scope="col">Symbol</th>
                          <th scope="col">Why matched</th>
                          <th scope="col">Key metrics</th>
                          <th scope="col">Freshness</th>
                          <th scope="col">Details</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.matches.map((match) => (
                          <tr key={match.match_id}>
                            <td data-label="Symbol">
                              <button
                                type="button"
                                className="evidence-symbol-link"
                                aria-label={`View scan evidence chart for ${match.symbol}`}
                                title="View scan evidence chart"
                                onClick={(event) =>
                                  openEvidenceChart(
                                    result.summary.run_id,
                                    match.match_id,
                                    event.currentTarget,
                                  )
                                }
                              >
                                {match.symbol}
                                <span aria-hidden="true">↗</span>
                              </button>
                              <span>
                                {match.exchange} · {match.segment}
                              </span>
                            </td>
                            <td data-label="Why matched">
                              <ul className="match-reasons">
                                {match.why_matched.map((reason) => (
                                  <li key={reason}>{reason}</li>
                                ))}
                              </ul>
                            </td>
                            <td data-label="Key metrics">
                              <ul className="metric-list">
                                {Object.entries(match.key_metrics)
                                  .slice(0, 4)
                                  .map(([key, value]) => (
                                    <li key={key}>
                                      <span>{metricLabel(key)}</span>
                                      <strong>
                                        {formatMetric(key, value)}
                                      </strong>
                                    </li>
                                  ))}
                              </ul>
                            </td>
                            <td data-label="Freshness">
                              <span
                                className={`discovery-badge is-${match.source_data_time ? "fresh" : "unknown"}`}
                              >
                                {match.source_data_time
                                  ? "Fresh"
                                  : "Source time unavailable"}
                              </span>
                            </td>
                            <td data-label="Details">
                              <details className="provenance-details">
                                <summary>Details</summary>
                                <p>Provider: {sourceLabel(match.provider)}</p>
                                <p>Mode: {words(match.source_mode)}</p>
                                <p>Lineage: {match.lineage}</p>
                                <p>Match ID: {match.match_id}</p>
                                <p>
                                  Raw reasons: {match.raw_reasons.join(", ")}
                                </p>
                              </details>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {result.matches.length === 0 && (
                    <p className="discovery-callout">
                      No instruments matched the selected conditions. No
                      candidates were invented.
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
                </section>
              ) : latestSummary ? (
                <HistoricalScanSummary scan={latestSummary} />
              ) : (
                <section
                  className="workspace-empty-state"
                  aria-label="Scan results"
                >
                  <strong>Results will appear here</strong>
                  <span>
                    Configure the scan and run it to see results here.
                  </span>
                </section>
              )}

              <section
                className="candidate-queue"
                aria-labelledby="candidate-queue-heading"
              >
                <div className="section-heading-row compact-heading">
                  <div>
                    <p className="eyebrow">DISCOVERY QUEUE</p>
                    <h2 id="candidate-queue-heading">
                      Candidates requiring review
                    </h2>
                    <p>
                      Current scan: {currentCandidates.length} · Active queue:{" "}
                      {activeCandidates.length}
                    </p>
                  </div>
                  <span>{candidates.length} persisted</span>
                </div>
                <div
                  className="queue-view-tabs"
                  role="group"
                  aria-label="Discovery queue view"
                >
                  <button
                    type="button"
                    aria-pressed={queueView === "current"}
                    disabled={!result}
                    onClick={() => setQueueView("current")}
                  >
                    Current scan ({currentCandidates.length})
                  </button>
                  <button
                    type="button"
                    aria-pressed={queueView === "active"}
                    onClick={() => setQueueView("active")}
                  >
                    Active ({activeCandidates.length})
                  </button>
                  <button
                    type="button"
                    aria-pressed={queueView === "all"}
                    onClick={() => setQueueView("all")}
                  >
                    All ({candidates.length})
                  </button>
                </div>
                <details className="queue-controls">
                  <summary>Filter and sort</summary>
                  <div className="queue-filter-grid">
                    <label>
                      <span>Search symbol</span>
                      <input
                        type="search"
                        value={queueSearch}
                        onChange={(event) => setQueueSearch(event.target.value)}
                        placeholder="Symbol or native ID"
                      />
                    </label>
                    <label>
                      <span>Relevance</span>
                      <select
                        value={queueBand}
                        onChange={(event) => setQueueBand(event.target.value)}
                      >
                        <option value="all">All bands</option>
                        <option value="HIGH">High</option>
                        <option value="MEDIUM">Medium</option>
                        <option value="LOW">Low</option>
                      </select>
                    </label>
                    <label>
                      <span>Lifecycle</span>
                      <select
                        value={queueLifecycle}
                        onChange={(event) =>
                          setQueueLifecycle(event.target.value)
                        }
                      >
                        <option value="all">All states</option>
                        {Object.keys(LIFECYCLE_PRIORITY).map((value) => (
                          <option key={value} value={value}>
                            {words(value)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Intent</span>
                      <select
                        value={queueIntent}
                        onChange={(event) => setQueueIntent(event.target.value)}
                      >
                        <option value="all">All intents</option>
                        {filterValues.intents.map((value) => (
                          <option key={value} value={value}>
                            {words(value)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Queue horizon</span>
                      <select
                        value={queueHorizon}
                        onChange={(event) =>
                          setQueueHorizon(event.target.value)
                        }
                      >
                        <option value="all">All horizons</option>
                        {filterValues.horizons.map((value) => (
                          <option key={value} value={value}>
                            {value}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Profile</span>
                      <select
                        value={queueProfile}
                        onChange={(event) =>
                          setQueueProfile(event.target.value)
                        }
                      >
                        <option value="all">All profiles</option>
                        {filterValues.profiles.map((value) => (
                          <option key={value} value={value}>
                            {words(value)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Freshness</span>
                      <select
                        value={queueFreshness}
                        onChange={(event) =>
                          setQueueFreshness(event.target.value)
                        }
                      >
                        <option value="all">All freshness</option>
                        {Object.keys(FRESHNESS_PRIORITY).map((value) => (
                          <option key={value} value={value}>
                            {value === "FRESH"
                              ? "Fresh evidence"
                              : value === "STALE"
                                ? "Stale evidence"
                                : "Unknown freshness"}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Evidence provider</span>
                      <select
                        value={queueProvider}
                        onChange={(event) =>
                          setQueueProvider(event.target.value)
                        }
                      >
                        <option value="all">All providers</option>
                        {filterValues.providers.map((value) => (
                          <option key={value} value={value}>
                            {sourceLabel(value)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Sort</span>
                      <select
                        value={queueSort}
                        onChange={(event) =>
                          setQueueSort(event.target.value as QueueSort)
                        }
                      >
                        <option value="attention">Attention priority</option>
                        <option value="relevance">Relevance</option>
                        <option value="updated">Updated</option>
                        <option value="lifecycle">Lifecycle</option>
                        <option value="symbol">Symbol</option>
                      </select>
                    </label>
                  </div>
                  <div className="queue-filter-footer">
                    <span aria-live="polite">
                      Showing {queueCandidates.length} of{" "}
                      {baseQueueCandidates.length}.{" "}
                      {queueSort === "attention"
                        ? "Sorted by current relevance model, relevance, lifecycle, freshness, and recency."
                        : `Sorted by ${words(queueSort)}.`}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setQueueSearch("");
                        setQueueBand("all");
                        setQueueLifecycle("all");
                        setQueueIntent("all");
                        setQueueHorizon("all");
                        setQueueProfile("all");
                        setQueueFreshness("all");
                        setQueueProvider("all");
                        setQueueSort("attention");
                      }}
                    >
                      Clear filters
                    </button>
                  </div>
                </details>
                <CandidateQueue
                  candidates={queueCandidates}
                  selected={detail?.candidate_id || null}
                  onSelect={(id) => void inspect(id)}
                  emptyMessage={
                    queueView === "current"
                      ? `No candidates came from the latest scan. ${activeCandidates.length} active candidate(s) remain available in Active.`
                      : queueView === "active"
                        ? "No active discovery candidates."
                        : "No persisted discovery candidates."
                  }
                />
              </section>
            </div>

            {detail ? (
              <div className="scan-workstation-inspector">{inspector}</div>
            ) : null}
          </div>
          <PastScansDialog
            open={pastScansOpen}
            scans={pastScans}
            selectedRunId={selectedHistory?.run_id || null}
            pending={historyPending}
            onClose={() => setPastScansOpen(false)}
            onView={viewScan}
            onReuse={reuseScan}
            onArchive={(scan) => void setArchived(scan, true)}
            onRestore={(scan) => void setArchived(scan, false)}
          />
        </>
      )}

      {!loading && view === "candidates" && (
        <div className="candidate-workstation-grid">
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
          <div className="candidate-workstation-inspector">{inspector}</div>
        </div>
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
