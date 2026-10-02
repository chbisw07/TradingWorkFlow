export type ProviderChoice = "internal" | "tradingview-synthetic";
export type ContextMode = "healthy" | "partial" | "unavailable" | "stale";
export type ContextPolicy = "REQUIRE_COMPLETE" | "ALLOW_PARTIAL" | "OPTIONAL";

export type ProviderStatus = {
  id: ProviderChoice;
  label: string;
  enabled: boolean;
  mode: "LOCAL_SYNTHETIC" | "REMOTE" | "SYNTHETIC_VALIDATION";
  health:
    "AVAILABLE" | "DEGRADED" | "AUTH_REQUIRED" | "RATE_LIMITED" | "UNAVAILABLE";
  capabilities: string[];
  last_success_at: string | null;
  last_error: string | null;
};

export type Instrument = {
  instrument_id: string;
  symbol: string;
  exchange: string;
  segment: string;
  native: { namespace: string; native_id: string; revision: string };
};

export type Relevance = {
  value: string | number | null;
  policy: { id: string; version: string };
  required_inputs_satisfied: boolean;
  coverage: string | number;
  reasons: string[];
};

export type RelevanceExplanation = {
  policy: string;
  score: string | number | null;
  band: "LOW" | "MEDIUM" | "HIGH" | null;
  coverage: string | number;
  contributions: Array<{
    factor: string;
    value: string | number;
    weight: string | number;
    contribution: string | number;
    reason: string;
  }>;
  conflicts: string[];
  missing: string[];
  freshness_penalty: string | number;
  horizon_adjustment: string | number;
};

export type ToleranceAssessment = {
  envelope: {
    policy: { id: string; version: string };
    rules: Array<{
      dimension: string;
      criterion: {
        metric: string;
        operator: string;
        threshold: string | number;
        unit: string;
      };
      reference_basis: string;
      required_categories: string[];
      confirmation_observations: number;
      recovery_rule: { id: string; version: string };
    }>;
  };
  horizon: string;
  state: "WITHIN" | "DEGRADED" | "BREACHED" | "UNKNOWN";
  dimensions: Array<{
    dimension: string;
    status: "WITHIN" | "DEGRADED" | "BREACHED" | "UNKNOWN";
    observed: string | number | null;
    threshold: string | number | null;
    reason: string;
  }>;
};

export type ObservationKind = "PRESENT" | "ABSENT" | "NOT_EVALUATED";

export type TemporalObservation = {
  observation_id: string;
  run_id: string;
  run_sequence: number;
  observed_at: string;
  source_data_time: string | null;
  kind: ObservationKind;
  coverage: string;
  novelty: "NOVEL" | "DUPLICATE" | "UNKNOWN" | "REGRESSED";
  relevance_score: string | number | null;
  relevance_band: "LOW" | "MEDIUM" | "HIGH" | null;
  relevance_model: string | null;
  lifecycle_after: Candidate["lifecycle"] | null;
  reason: string;
  comparison_scope_version: number;
  provider: string | null;
  is_hot: boolean;
};

export type TemporalSummary = {
  latest_observation_kind: ObservationKind;
  last_observed_at: string;
  latest_comparable_run_id: string;
  latest_attempted_run_id: string;
  latest_present_run_id: string | null;
  last_known_relevance: string | number | null;
  relevance_delta: string | number | null;
  relevance_model: string | null;
  hot_count: number;
  total_count: number;
  window_status: "OPEN" | "ENDED" | "UNKNOWN";
  observation_age_seconds: number;
  recent_observations: TemporalObservation[];
};

export type Candidate = {
  candidate_id: string;
  episode_id: string;
  revision: number;
  instrument: Instrument;
  intent: string;
  horizon: string;
  profile: string | null;
  profile_lineage:
    | "CURRENT_SNAPSHOT"
    | "ORIGINATING_SCAN"
    | "LATEST_SCAN"
    | "PERSISTED_SNAPSHOT"
    | "CANDIDATE_METADATA"
    | "LEGACY_UNAVAILABLE";
  legacy_profile: boolean;
  relevance: Relevance;
  relevance_explanation: RelevanceExplanation;
  tolerance: ToleranceAssessment;
  lifecycle: "NEW" | "CURRENT" | "STALE" | "DEFUNCT" | "EXPIRED" | "REJECTED";
  lifecycle_reason: string;
  freshness: "FRESH" | "STALE" | "UNKNOWN";
  snapshot_count: number;
  provider_sources: string[];
  originating_scan_run_id: string | null;
  latest_scan_run_id: string | null;
  updated_at: string;
  temporal: TemporalSummary | null;
};

export type MarketContext = {
  context_id: string;
  observed_at: string;
  source_data_time: string | null;
  market: string;
  session: string;
  availability: "COMPLETE" | "PARTIAL" | "UNAVAILABLE" | "STALE";
  dimensions: Array<{
    name: string;
    availability: "PRESENT" | "MISSING" | "UNAVAILABLE" | "STALE";
    value: string | number | null;
    source: string;
    reason: string | null;
  }>;
  producer: string;
  producer_version: string;
  evidence_ids: string[];
  limitations: string[];
};

export type Evidence = {
  evidence_id: string;
  category: string;
  polarity: string;
  observation_basis: string;
  observed_at: string;
  source_data_time: string | null;
  availability: string;
  measures: Array<{
    name: string;
    value: string | number | boolean;
    unit: string;
  }>;
  reason: string | null;
  provenance: {
    producer: { service_id: string; provider: string; service_version: string };
    source: { namespace: string; native_id: string; revision: string };
    mode: string;
    transformation: { id: string; version: string };
  };
};

export type CandidateDetail = Candidate & {
  snapshots: Array<{
    snapshot_id: string;
    sequence: number;
    observed_at: string;
    source_data_time: string | null;
    lifecycle: string;
    lifecycle_reason: string;
    relevance: Relevance;
    relevance_explanation: RelevanceExplanation;
    tolerance: ToleranceAssessment;
    evidence: Evidence[];
    provider_sources: string[];
  }>;
  transitions: Array<Record<string, unknown>>;
  explanations: LlmExplanation[];
  context: MarketContext | null;
  previous_episode_id: string | null;
  observations: TemporalObservation[];
};

export type LlmExplanation = {
  explanation_id: string;
  provider: string;
  model: string;
  model_version: string;
  prompt_version: string;
  generated_at: string;
  grounding: "GROUNDED" | "PARTIALLY_GROUNDED" | "CONTEXT_ONLY";
  evidence_ids: string[];
  narrative: string;
  limitations: string[];
};

export type ScanMatch = {
  match_id: string;
  symbol: string;
  exchange: string;
  segment: string;
  provider: string;
  why_matched: string[];
  raw_reasons: string[];
  key_metrics: Record<string, string>;
  source_mode: string;
  source_data_time: string | null;
  lineage: string;
};

export type ScanSummary = {
  run_id: string;
  provider: ProviderChoice;
  status: "COMPLETE" | "FAILED";
  started_at: string;
  completed_at: string;
  profile: string;
  horizon: string;
  intent: string;
  universe_size: number;
  universe?: string[];
  match_count: number;
  candidate_count: number;
  context_mode?: ContextMode;
  context_policy?: ContextPolicy;
  context_availability: MarketContext["availability"];
  degraded: string[];
  archived_at?: string | null;
};

export type AdmissionDecision = {
  match_id: string;
  symbol: string;
  status: "ADMITTED" | "EXCLUDED";
  reason: "ADMITTED" | "EXCLUDED_DIRECTION" | "EXCLUDED_CONTEXT_POLICY";
};

export type HistoricalScanDetail = {
  summary: ScanSummary;
  matches: ScanMatch[];
  market_context: MarketContext | null;
};

export type TemporalHistoryPage = {
  items: TemporalObservation[];
  total: number;
  limit: number;
  offset: number;
  hot_size: number;
  as_of: string;
};

export type RunViewMode = "as_scanned" | "current_state";

export type RunTemporalView = {
  run_id: string;
  mode: RunViewMode;
  summary: ScanSummary;
  items: Array<{
    instrument: Instrument;
    observation: TemporalObservation;
    candidate: Candidate | null;
  }>;
  limit: number;
  offset: number;
  total: number;
};

export type ScanResult = {
  summary: ScanSummary;
  matches: ScanMatch[];
  candidates: Candidate[];
  market_context: MarketContext;
  admission: {
    match_count: number;
    admitted_count: number;
    excluded_count: number;
    decisions: AdmissionDecision[];
  };
};

export type DiscoverySettings = {
  revision: number;
  llm_enabled: boolean;
  llm_provider: "synthetic" | "openai" | "anthropic" | "google";
  default_provider: ProviderChoice;
  default_profile: string;
  default_horizon: string;
  low_max: string | number;
  medium_max: string | number;
  freshness_seconds: number;
  retention_days: number;
  max_history_items: number;
  hot_observation_count: number;
};

export async function discoveryApi<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api/v1/discovery/" + path, {
    method,
    cache: "no-store",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      error?: { code?: string };
    } | null;
    const code = payload?.error?.code;
    throw new Error(
      response.status === 401
        ? "Your session has expired. Sign in again."
        : response.status === 409
          ? code === "LLM_DISABLED"
            ? "Level-0 explanation is disabled in Scan & Discover settings."
            : "Discovery state changed. Reload current data before retrying."
          : response.status === 422
            ? "Check the universe and scan controls. No scan was started."
            : "Scan & Discover is unavailable. Retry after checking provider status.",
    );
  }
  return response.json() as Promise<T>;
}
