import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { DiscoveryWorkspace } from "../src/components/discovery/discovery-workspace";
import { EvidenceChartDrawer } from "../src/components/discovery/evidence-chart-drawer";
import { DiscoverySettingsSection } from "../src/components/discovery/discovery-settings";

const settings = {
  revision: 0,
  llm_enabled: false,
  llm_provider: "synthetic",
  default_provider: "internal",
  default_profile: "RELATIVE_VOLUME",
  default_horizon: "5d",
  low_max: "0.60",
  medium_max: "0.90",
  freshness_seconds: 900,
  retention_days: 90,
  max_history_items: 50,
  hot_observation_count: 20,
};
const context = {
  context_id: "10000000-0000-0000-0000-000000000001",
  observed_at: "2026-09-30T06:00:00Z",
  source_data_time: null,
  market: "NSE",
  session: "OPEN",
  availability: "PARTIAL",
  dimensions: [
    {
      name: "market_regime",
      availability: "PRESENT",
      value: "TRENDING",
      source: "twf-context",
      reason: null,
    },
    {
      name: "breadth",
      availability: "MISSING",
      value: null,
      source: "twf-context",
      reason: "not-supplied",
    },
  ],
  producer: "twf-context",
  producer_version: "1",
  evidence_ids: [],
  limitations: ["validation-data"],
};
const candidate = {
  candidate_id: "20000000-0000-0000-0000-000000000001",
  episode_id: "30000000-0000-0000-0000-000000000001",
  revision: 1,
  instrument: {
    instrument_id: "40000000-0000-0000-0000-000000000001",
    symbol: "RELIANCE",
    exchange: "NSE",
    segment: "EQ",
    native: { namespace: "NSE", native_id: "NSE:RELIANCE", revision: "1" },
  },
  intent: "INTRADAY_LONG",
  horizon: "5d",
  profile: "RELATIVE_VOLUME",
  profile_lineage: "CURRENT_SNAPSHOT",
  legacy_profile: false,
  relevance: {
    value: "0.81",
    policy: { id: "deterministic-relevance-v2", version: "2" },
    required_inputs_satisfied: true,
    coverage: "0.75",
    reasons: ["evidence-fit"],
  },
  relevance_explanation: {
    policy: "deterministic-relevance-v2",
    score: "0.81",
    band: "MEDIUM",
    coverage: "0.75",
    contributions: [
      {
        factor: "provider_evidence",
        value: "0.9",
        weight: "0.5",
        contribution: "0.45",
        reason: "Bounded provider evidence is present.",
      },
    ],
    conflicts: ["price and market context disagree"],
    missing: ["breadth"],
    freshness_penalty: "0",
    horizon_adjustment: "0",
  },
  tolerance: {
    envelope: {
      policy: { id: "candidate-tolerance-v1", version: "1" },
      rules: [
        {
          dimension: "volume",
          criterion: {
            metric: "relative_volume",
            operator: "GTE",
            threshold: "1.0",
            unit: "ratio",
          },
          reference_basis: "5d-horizon",
          required_categories: ["VOLUME_LIQUIDITY"],
          confirmation_observations: 2,
          recovery_rule: { id: "deterministic-relevance-v1", version: "1" },
        },
      ],
    },
    horizon: "5d",
    state: "WITHIN",
    dimensions: [
      {
        dimension: "volume",
        status: "WITHIN",
        observed: "2.4",
        threshold: "1.0",
        reason: "Relative volume is within its horizon-aware tolerance.",
      },
      {
        dimension: "time_decay",
        status: "WITHIN",
        observed: "1",
        threshold: "0.25",
        reason: "The opportunity window remains open.",
      },
    ],
  },
  lifecycle: "NEW",
  lifecycle_reason: "first-observation",
  freshness: "FRESH",
  snapshot_count: 1,
  provider_sources: ["twf-native"],
  originating_scan_run_id: "70000000-0000-0000-0000-000000000000",
  latest_scan_run_id: "70000000-0000-0000-0000-000000000001",
  updated_at: "2026-09-30T06:00:00Z",
  temporal: {
    latest_observation_kind: "NOT_EVALUATED",
    last_observed_at: "2026-09-30T05:00:00Z",
    latest_comparable_run_id: "70000000-0000-0000-0000-000000000000",
    latest_attempted_run_id: "70000000-0000-0000-0000-000000000001",
    latest_present_run_id: "70000000-0000-0000-0000-000000000000",
    last_known_relevance: "0.76",
    relevance_delta: null,
    relevance_model: "deterministic-relevance-v2@2",
    hot_count: 2,
    total_count: 2,
    window_status: "OPEN",
    observation_age_seconds: 3600,
    recent_observations: [
      {
        observation_id: "80000000-0000-0000-0000-000000000001",
        run_id: "70000000-0000-0000-0000-000000000000",
        run_sequence: 1,
        observed_at: "2026-09-30T05:00:00Z",
        source_data_time: "2026-09-30T04:59:00Z",
        kind: "PRESENT",
        coverage: "EVALUATED",
        novelty: "NOVEL",
        relevance_score: "0.76",
        relevance_band: "MEDIUM",
        relevance_model: "deterministic-relevance-v2@2",
        lifecycle_after: "NEW",
        reason: "first-observation",
        comparison_scope_version: 1,
        provider: "twf-native",
        is_hot: true,
      },
      {
        observation_id: "80000000-0000-0000-0000-000000000002",
        run_id: "70000000-0000-0000-0000-000000000001",
        run_sequence: 2,
        observed_at: "2026-09-30T06:00:00Z",
        source_data_time: null,
        kind: "NOT_EVALUATED",
        coverage: "PARTIAL_FAILURE",
        novelty: "UNKNOWN",
        relevance_score: null,
        relevance_band: null,
        relevance_model: null,
        lifecycle_after: "NEW",
        reason: "provider-partial-failure",
        comparison_scope_version: 1,
        provider: "twf-native",
        is_hot: true,
      },
    ],
  },
};
const detail = {
  ...candidate,
  snapshots: [
    {
      snapshot_id: "50000000-0000-0000-0000-000000000001",
      sequence: 1,
      observed_at: "2026-09-30T06:00:00Z",
      source_data_time: null,
      lifecycle: "NEW",
      lifecycle_reason: "first-observation",
      relevance: candidate.relevance,
      relevance_explanation: candidate.relevance_explanation,
      tolerance: candidate.tolerance,
      provider_sources: ["twf-native"],
      evidence: [
        {
          evidence_id: "60000000-0000-0000-0000-000000000001",
          category: "VOLUME_LIQUIDITY",
          polarity: "POSITIVE",
          observation_basis: "daily",
          observed_at: "2026-09-30T06:00:00Z",
          source_data_time: null,
          availability: "PRESENT",
          measures: [
            { name: "relative_volume", value: "2.4", unit: "ratio" },
            { name: "breakout_condition", value: true, unit: "boolean" },
            { name: "broad_regime", value: "CONSTRUCTIVE", unit: "category" },
            { name: "input_digest", value: "sha256:technical", unit: "hash" },
          ],
          reason: null,
          provenance: {
            producer: {
              service_id: "internal-scanner-v0",
              provider: "twf-native",
              service_version: "1",
            },
            source: {
              namespace: "NSE",
              native_id: "NSE:RELIANCE",
              revision: "1",
            },
            mode: "SYNTHETIC",
            transformation: { id: "product-normalization", version: "1" },
          },
        },
      ],
    },
  ],
  transitions: [],
  explanations: [],
  context,
  previous_episode_id: null,
  observations: [
    {
      observation_id: "80000000-0000-0000-0000-000000000002",
      run_id: "70000000-0000-0000-0000-000000000001",
      run_sequence: 2,
      observed_at: "2026-09-30T06:00:00Z",
      source_data_time: null,
      kind: "NOT_EVALUATED",
      coverage: "PARTIAL_FAILURE",
      novelty: "UNKNOWN",
      relevance_score: null,
      relevance_band: null,
      relevance_model: null,
      lifecycle_after: "NEW",
      reason: "provider-partial-failure",
      comparison_scope_version: 1,
      provider: "twf-native",
      is_hot: true,
    },
    {
      observation_id: "80000000-0000-0000-0000-000000000001",
      run_id: "70000000-0000-0000-0000-000000000000",
      run_sequence: 1,
      observed_at: "2026-09-30T05:00:00Z",
      source_data_time: "2026-09-30T04:59:00Z",
      kind: "PRESENT",
      coverage: "EVALUATED",
      novelty: "NOVEL",
      relevance_score: "0.76",
      relevance_band: "MEDIUM",
      relevance_model: "deterministic-relevance-v2@2",
      lifecycle_after: "NEW",
      reason: "first-observation",
      comparison_scope_version: 1,
      provider: "twf-native",
      is_hot: true,
    },
  ],
};
const providers = [
  {
    id: "internal",
    label: "Internal Scanner V0",
    enabled: true,
    mode: "LOCAL_SYNTHETIC",
    health: "AVAILABLE",
    role: "DISCOVERY",
    capabilities: ["scan"],
    limitations: ["Discovery/matching only; no live market-evidence claim."],
    last_success_at: null,
    last_error: null,
  },
  {
    id: "real-tradingview",
    label: "TradingView real evidence",
    enabled: true,
    mode: "REMOTE",
    health: "AUTH_REQUIRED",
    role: "EVIDENCE",
    capabilities: ["exact-batch", "ohlcv"],
    limitations: [
      "Authentication required before live evidence can be fetched.",
    ],
    last_success_at: null,
    last_error: null,
  },
  {
    id: "tradingview-synthetic",
    label: "TradingView contract validation",
    enabled: true,
    mode: "SYNTHETIC_VALIDATION",
    health: "RATE_LIMITED",
    role: "VALIDATION",
    capabilities: ["exact-batch"],
    limitations: ["Synthetic contract validation only."],
    last_success_at: null,
    last_error: "Daily request budget reached",
  },
];

function evidenceChart(mode: "as_scanned" | "current") {
  const unavailable = mode === "current";
  const bars = unavailable
    ? []
    : Array.from({ length: 24 }, (_, index) => ({
        timestamp: new Date(Date.UTC(2026, 8, 7 + index, 6)).toISOString(),
        open: String(100 + index * 0.45),
        high: String(101 + index * 0.45),
        low: String(99.5 + index * 0.45),
        close: String(100.6 + index * 0.45),
        volume: String(index === 23 ? 2400 : 1000),
        finality: "COMPLETED",
      }));
  return {
    mode,
    state: unavailable ? "CURRENT_UNAVAILABLE" : "AVAILABLE",
    message: unavailable
      ? "Current chart unavailable; retained as-scanned evidence remains usable."
      : null,
    run_id: "70000000-0000-0000-0000-000000000001",
    match_id: "71000000-0000-0000-0000-000000000001",
    instrument: candidate.instrument,
    scan_time: "2026-09-30T06:00:00Z",
    source_data_time: unavailable ? null : "2026-09-30T06:00:00Z",
    profile: "RELATIVE_VOLUME",
    profile_revision: 1,
    definition_revision: 1,
    intent: "INTRADAY_LONG",
    horizon: "5d",
    provider: "twf-native",
    data_mode: "SYNTHETIC",
    timeframe: "1d",
    price_unit: "INR",
    bar_finality: unavailable ? "PROVIDER_UNSPECIFIED" : "COMPLETED",
    bars,
    series: unavailable
      ? []
      : [
          {
            key: "average-volume-20",
            label: "20-day average volume",
            panel: "VOLUME",
            points: bars.map((bar) => ({
              timestamp: bar.timestamp,
              value: "1000",
            })),
          },
          {
            key: "roc.10",
            label: "10-day momentum",
            panel: "OSCILLATOR",
            points: bars.map((bar, index) => ({
              timestamp: bar.timestamp,
              value: String(index / 10),
            })),
          },
        ],
    thresholds: [
      {
        key: "roc.10-GT-0",
        label: "Required GT 0",
        panel: "OSCILLATOR",
        value: "0",
        kind: "LINE",
      },
    ],
    predicates: [
      {
        metric: "relative_volume.20",
        label: "Relative volume",
        observed: "2.4",
        operator: "GTE",
        threshold: "1.5",
        unit: "ratio",
        matched: true,
      },
      {
        metric: "roc.10",
        label: "10-day momentum",
        observed: "2.8",
        operator: "GT",
        threshold: "0",
        unit: "percent",
        matched: true,
      },
    ],
    metrics: unavailable
      ? []
      : [
          { key: "close", label: "Scan price", value: "111", unit: "INR" },
          {
            key: "relative_volume.20",
            label: "Relative volume",
            value: "2.4",
            unit: "ratio",
          },
        ],
    retention: {
      source_class: unavailable ? "PROVIDER_RESTRICTED" : "SYNTHETIC_RETAINED",
      historical_chart_reconstructable: !unavailable,
      scan_bars_retained: !unavailable,
      current_chart_available: false,
      archive_bar_count: unavailable ? 0 : 260,
      displayed_bar_count: bars.length,
      limitation: unavailable
        ? "Current source is unavailable."
        : "Deterministic validation bars are retained.",
    },
    provenance: "twf-native / 1 · internal-v0 1",
  };
}

function json(data: unknown, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: async () => data });
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("runs a bounded scan and exposes evidence, degradation, history and no trading authority", async () => {
  const scan = {
    summary: {
      run_id: "70000000-0000-0000-0000-000000000001",
      provider: "internal",
      status: "COMPLETE",
      started_at: "2026-09-30T06:00:00Z",
      completed_at: "2026-09-30T06:00:01Z",
      profile: "RELATIVE_VOLUME",
      horizon: "5d",
      intent: "INTRADAY_LONG",
      universe_size: 2,
      universe: ["RELIANCE", "TCS"],
      match_count: 1,
      candidate_count: 1,
      context_mode: "partial",
      context_policy: "ALLOW_PARTIAL",
      context_availability: "PARTIAL",
      degraded: ["market breadth unavailable"],
      archived_at: null,
    },
    matches: [
      {
        match_id: "71000000-0000-0000-0000-000000000001",
        symbol: "RELIANCE",
        exchange: "NSE",
        provider: "twf-native",
        segment: "EQ",
        why_matched: ["Relative volume 2.40×"],
        raw_reasons: ["1d.0.relative_volume.20"],
        key_metrics: {
          close: "2954.54",
          "momentum.10": "2.8",
          "relative_volume.20": "2.4",
        },
        source_mode: "SYNTHETIC",
        verification: "CONFIRMED",
        evidence_coverage: "COMPLETE",
        source_data_time: "2026-09-30T05:59:00Z",
        lineage: "internal-scanner-v0:relative-volume",
      },
    ],
    candidates: [candidate],
    market_context: context,
    admission: {
      match_count: 1,
      admitted_count: 1,
      excluded_count: 0,
      decisions: [
        {
          match_id: "71000000-0000-0000-0000-000000000001",
          symbol: "RELIANCE",
          status: "ADMITTED",
          reason: "ADMITTED",
        },
      ],
    },
  };
  const fetcher = vi.fn((input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("/scans?")) return json([scan.summary]);
    if (url.includes("/candidates?"))
      return json({ items: init?.method === "POST" ? [] : [candidate] });
    if (url.endsWith("/settings")) return json(settings);
    if (url.includes("/evidence-chart"))
      return json(
        evidenceChart(url.includes("mode=current") ? "current" : "as_scanned"),
      );
    if (url.endsWith(`/scans/${scan.summary.run_id}`))
      return json({
        summary: scan.summary,
        matches: scan.matches,
        market_context: scan.market_context,
      });
    if (url.endsWith("/scans")) return json(scan, 201);
    if (url.includes("/lifecycle"))
      return json({ ...detail, lifecycle: "REJECTED", revision: 2 });
    if (url.endsWith(candidate.candidate_id)) return json(detail);
    throw new Error(`Unexpected ${url}`);
  });
  const confirm = vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(true);
  vi.stubGlobal("fetch", fetcher);
  vi.stubGlobal("confirm", confirm);
  const { container } = render(<DiscoveryWorkspace />);
  await screen.findByRole("heading", {
    name: "Provider and evidence readiness",
  });
  expect(
    screen.getByText(/Discovery never authorizes a trade/),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("SYNTHETIC VALIDATION DATA"),
  ).not.toBeInTheDocument();
  expect(container.querySelector(".data-mode-banner")).not.toBeInTheDocument();
  expect(screen.getByText("Rate limited")).toBeInTheDocument();
  expect(screen.getByText(/Daily request budget reached/)).toBeInTheDocument();
  expect(screen.queryByText(/SPRINT 2/)).not.toBeInTheDocument();
  const statusStrip = screen
    .getByRole("heading", { name: "Provider and evidence readiness" })
    .closest("section");
  const setupPanel = screen
    .getByRole("heading", { name: "Configure scan" })
    .closest("section");
  expect(statusStrip).toHaveClass("workspace-status-strip");
  expect(within(statusStrip!).getByText("Synthetic Data")).toBeInTheDocument();
  expect(
    within(statusStrip!).getAllByText("Validation").length,
  ).toBeGreaterThan(0);
  expect(setupPanel).not.toContainElement(statusStrip);
  const history = screen.getByRole("list", { name: "Recent discovery scans" });
  expect(within(history).getByText(/Internal · 2 symbols/)).toBeInTheDocument();
  fireEvent.click(within(history).getByText("Actions"));
  const viewHistory = within(history).getByRole("button", { name: "View" });
  fireEvent.click(viewHistory);
  await screen.findByRole("heading", { name: /Viewing historical scan/ });
  expect(viewHistory).toHaveAttribute("aria-pressed", "true");
  expect(
    screen.getByRole("heading", { name: "Configure scan" }),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/Universe symbols/), {
    target: { value: "RELIANCE, TCS" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Run scan" }));
  await screen.findByRole("heading", { name: "Latest scan result" });
  expect(screen.getByText(/Market breadth unavailable/)).toBeInTheDocument();
  expect(screen.getByText("Relative volume 2.40×")).toBeInTheDocument();
  expect(
    screen.queryByText("Relative volume elevated"),
  ).not.toBeInTheDocument();
  expect(screen.getByText("Source timestamp available")).toBeInTheDocument();
  expect(screen.getAllByText(/1 admitted · 0 excluded/).length).toBeGreaterThan(
    0,
  );
  expect(screen.getByText("Admitted")).toBeInTheDocument();
  expect(screen.getAllByText("Details").length).toBeGreaterThan(1);
  expect(screen.getAllByText("RELIANCE").length).toBeGreaterThan(0);
  const evidenceTrigger = screen.getByRole("button", {
    name: "View scan evidence chart for RELIANCE",
  });
  fireEvent.click(evidenceTrigger);
  const chartDrawer = await screen.findByRole("dialog", {
    name: "RELIANCE evidence chart",
  });
  expect(
    within(chartDrawer).getByRole("tab", { name: "As scanned" }),
  ).toHaveAttribute("aria-selected", "true");
  expect(within(chartDrawer).getByText("SYNTHETIC DATA")).toBeInTheDocument();
  expect(within(chartDrawer).getByText("Price evidence")).toBeInTheDocument();
  expect(within(chartDrawer).getByText("Volume evidence")).toBeInTheDocument();
  expect(within(chartDrawer).getAllByText("Passed")).toHaveLength(2);
  fireEvent.click(
    within(chartDrawer).getByRole("tab", { name: "Current chart" }),
  );
  expect(
    await within(chartDrawer).findByText("CURRENT UNAVAILABLE"),
  ).toBeInTheDocument();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(
    screen.queryByRole("dialog", { name: /evidence chart/i }),
  ).not.toBeInTheDocument();
  await act(async () => undefined);
  expect(evidenceTrigger).toHaveFocus();
  expect(container.querySelector(".scan-workstation-grid")).toHaveClass(
    "without-inspector",
  );
  const queue = screen.getByRole("table", { name: "Discovery queue" });
  expect(
    within(queue).getByRole("img", {
      name: /Recent observation trend:.*Present.*Not evaluated/,
    }),
  ).toBeInTheDocument();
  const review = within(queue).getByRole("button", { name: "Review" });
  const selectedRow = review.closest("tr");
  fireEvent.click(review);
  const inspector = await screen.findByRole("complementary", {
    name: "RELIANCE",
  });
  expect(container.querySelector(".scan-workstation-grid")).toHaveClass(
    "has-inspector",
  );
  expect(selectedRow).toHaveAttribute("data-selected", "true");
  expect(within(selectedRow!).getByText("Relative volume")).toBeInTheDocument();
  expect(
    within(selectedRow!).getByText("First observation"),
  ).toBeInTheDocument();
  expect(
    within(inspector).getByText(/Attention score, not probability of profit/),
  ).toBeInTheDocument();
  expect(
    within(inspector).getByText(/Relative volume: 2.4 ratio/),
  ).toBeInTheDocument();
  expect(
    within(inspector).getByText(/Input digest: sha256:technical/),
  ).toBeInTheDocument();
  expect(
    within(inspector).getByText(/Relative volume: 2.4 ratio/),
  ).not.toHaveTextContent("sha256:technical");
  expect(within(inspector).getByText("Supports the setup")).toBeInTheDocument();
  expect(within(inspector).getAllByText("Evidence available")[0]).toHaveClass(
    "is-present",
  );
  expect(
    within(inspector).getByText(/Breakout condition: Condition matched/),
  ).toBeInTheDocument();
  expect(
    within(inspector).getByText(/Broad regime: Constructive/),
  ).toBeInTheDocument();
  expect(
    within(inspector).queryByText(/POSITIVE PRESENT/),
  ).not.toBeInTheDocument();
  expect(within(inspector).getByText("Missing evidence")).toBeInTheDocument();
  expect(
    within(inspector).getByText("Conflicting evidence"),
  ).toBeInTheDocument();
  expect(
    within(inspector).getByText(/Source time unavailable/),
  ).toBeInTheDocument();
  expect(
    within(inspector).getByText("Optional AI explanation"),
  ).toBeInTheDocument();
  expect(
    within(inspector).getByText(/Enable it under Settings/),
  ).toBeInTheDocument();
  expect(within(inspector).getByText(/Snapshot 1/)).toBeInTheDocument();
  const temporalHistory = within(inspector)
    .getByRole("heading", { name: "Observation history" })
    .closest("section");
  expect(temporalHistory).not.toBeNull();
  expect(
    within(temporalHistory as HTMLElement).getAllByText("Not evaluated").length,
  ).toBeGreaterThan(0);
  expect(temporalHistory).toHaveTextContent("Partial failure");
  expect(temporalHistory).toHaveTextContent("Provider partial failure");
  expect(
    within(inspector).getByRole("button", {
      name: "Copy candidate identifier",
    }),
  ).toBeInTheDocument();
  expect(
    within(inspector).getByRole("button", { name: "Copy evidence identifier" }),
  ).toBeInTheDocument();
  expect(
    within(inspector).getByRole("button", { name: "Copy native identifier" }),
  ).toBeInTheDocument();
  expect(
    within(inspector).getByRole("heading", { name: "Horizon-aware tolerance" }),
  ).toBeInTheDocument();
  expect(within(inspector).getAllByText("Within").length).toBeGreaterThan(0);
  expect(within(inspector).getAllByText("Within")[0]).toHaveClass("is-within");
  expect(
    within(screen.getByRole("table", { name: "Discovery queue" })).getByRole(
      "button",
      { name: "Reviewing" },
    ),
  ).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(
    within(inspector).getByRole("button", { name: "Dismiss candidate" }),
  );
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(
    fetcher.mock.calls.some((call) => String(call[0]).includes("/lifecycle")),
  ).toBe(false);
  const scanBody = JSON.parse(
    fetcher.mock.calls.find((call) => String(call[0]).endsWith("/scans"))?.[1]
      ?.body as string,
  );
  expect(scanBody.universe).toEqual(["RELIANCE", "TCS"]);
  expect(scanBody.include_llm).toBe(false);
  fireEvent.click(
    within(inspector).getByRole("button", { name: "Close candidate review" }),
  );
  expect(
    screen.queryByRole("complementary", { name: "RELIANCE" }),
  ).not.toBeInTheDocument();
  expect(container.querySelector(".scan-workstation-grid")).toHaveClass(
    "without-inspector",
  );
  expect(selectedRow).toHaveAttribute("data-selected", "false");
  expect(within(queue).getByRole("button", { name: "Review" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

test("uses compact first-run and inspector states inside one workstation", async () => {
  const fetcher = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("/scans?")) return json([]);
    if (url.includes("/candidates?")) return json({ items: [] });
    if (url.endsWith("/settings")) return json(settings);
    throw new Error(`Unexpected ${url}`);
  });
  vi.stubGlobal("fetch", fetcher);
  const { container } = render(<DiscoveryWorkspace />);

  await screen.findByRole("heading", {
    name: "Provider and evidence readiness",
  });
  expect(screen.queryByText(/SPRINT 2/)).not.toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "Ready to scan" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText("Configure the scan and run it to see results here."),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Scan results")).toHaveClass(
    "workspace-empty-state",
  );
  expect(
    screen.queryByLabelText("Candidate inspector"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText("Select a candidate to inspect evidence and history."),
  ).not.toBeInTheDocument();
  expect(container.querySelector(".scan-workstation-grid")).toHaveClass(
    "without-inspector",
  );
  const setupColumn = container.querySelector(".scan-workstation-setup");
  const setup = screen.getByRole("heading", { name: "Configure scan" });
  const history = screen.getByRole("heading", { name: "Recent scans" });
  expect(setupColumn).toContainElement(setup);
  expect(setupColumn).toContainElement(history);
  expect(
    setup.compareDocumentPosition(history) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  const hero = container.querySelector(".discovery-hero");
  const statusStrip = container.querySelector(".workspace-status-strip");
  expect(statusStrip).toBeInTheDocument();
  expect(hero?.nextElementSibling).toBe(statusStrip);
  expect(container.querySelector(".data-mode-banner")).not.toBeInTheDocument();
  expect(screen.getByText("Synthetic Data")).toBeInTheDocument();
  expect(screen.getAllByText("Ready").length).toBeGreaterThan(0);
});

test("manages five recent scans, complete setup reuse, archived history and past filters", async () => {
  const completedAt = new Date().toISOString();
  const summaries = Array.from({ length: 6 }, (_, index) => ({
    run_id: `70000000-0000-0000-0000-00000000000${index + 1}`,
    provider: index === 0 ? "tradingview-synthetic" : "internal",
    status: "COMPLETE",
    started_at: completedAt,
    completed_at: completedAt,
    profile: index === 0 ? "MOMENTUM" : "RELATIVE_VOLUME",
    horizon: index === 0 ? "15d" : "5d",
    intent: index === 0 ? "POSITIONAL_SHORT" : "INTRADAY_LONG",
    universe_size: index === 0 ? 2 : 1,
    universe: index === 0 ? ["AAA", "BBB"] : [`SYMBOL${index}`],
    match_count: index + 1,
    candidate_count: index + 1,
    context_mode: index === 0 ? "unavailable" : "partial",
    context_availability: "PARTIAL",
    degraded: [],
    archived_at: null as string | null,
  }));
  const archived = {
    ...summaries[0],
    archived_at: new Date().toISOString(),
  };
  const fetcher = vi.fn((input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("include_archived=true"))
      return json([archived, ...summaries.slice(1)]);
    if (url.includes("/scans?")) return json(summaries);
    if (url.includes("/candidates?")) return json({ items: [] });
    if (url.endsWith("/settings")) return json(settings);
    if (url.endsWith(`/scans/${summaries[0].run_id}`))
      return json({
        summary: summaries[0],
        matches: [
          {
            match_id: "71000000-0000-0000-0000-000000000001",
            symbol: "AAA",
            exchange: "NSE",
            segment: "EQ",
            provider: "tradingview",
            why_matched: ["Stored historical reason"],
            raw_reasons: ["stored-reason"],
            key_metrics: { close: "101.25" },
            source_mode: "SYNTHETIC_VALIDATION",
            verification: "CONFIRMED",
            evidence_coverage: "COMPLETE",
            source_data_time: completedAt,
            lineage: "stored-lineage",
          },
        ],
        market_context: context,
      });
    if (url.includes(`/scans/${summaries[0].run_id}/temporal?mode=`)) {
      const currentState = url.includes("mode=current_state");
      return json({
        run_id: summaries[0].run_id,
        mode: currentState ? "current_state" : "as_scanned",
        summary: summaries[0],
        items: [
          {
            instrument: { ...candidate.instrument, symbol: "AAA" },
            observation: candidate.temporal.recent_observations[0],
            candidate: currentState ? candidate : null,
          },
        ],
        limit: 100,
        offset: 0,
        total: 1,
      });
    }
    if (url.endsWith(`/${summaries[0].run_id}/archive`)) return json(archived);
    if (url.endsWith(`/${summaries[0].run_id}/restore`))
      return json(summaries[0]);
    throw new Error(`Unexpected ${url} ${init?.method || "GET"}`);
  });
  vi.stubGlobal("fetch", fetcher);
  render(<DiscoveryWorkspace />);

  const recent = await screen.findByRole("list", {
    name: "Recent discovery scans",
  });
  expect(within(recent).getAllByRole("listitem")).toHaveLength(5);
  expect(
    within(recent).getByText(/Tradingview synthetic · 2 symbols/),
  ).toBeInTheDocument();
  expect(within(recent).getByText(/1 matches/)).toBeInTheDocument();

  const first = within(recent).getAllByRole("listitem")[0];
  fireEvent.click(within(first).getByText("Actions"));
  fireEvent.click(within(first).getByRole("button", { name: "View" }));
  expect(
    await screen.findByRole("heading", { name: /Viewing historical scan/ }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("table", { name: "Historical scan matches" }),
  ).toHaveTextContent("Stored historical reason");
  expect(
    await screen.findByRole("table", {
      name: "Immutable observations from this run",
    }),
  ).toHaveTextContent("Present");
  fireEvent.click(screen.getByRole("button", { name: "Current state" }));
  expect(
    await screen.findByRole("table", {
      name: "Current candidate state for this run",
    }),
  ).toHaveTextContent("NEW");
  expect(
    fetcher.mock.calls.some((call) =>
      String(call[0]).includes("mode=current_state"),
    ),
  ).toBe(true);
  expect(screen.getByLabelText(/Universe symbols/)).toHaveValue(
    "RELIANCE, MCX, HDFCBANK, INFY, BSE, NIFTY, BANKNIFTY",
  );
  expect(
    fetcher.mock.calls.some(
      (call) =>
        String(call[0]).endsWith("/scans") && call[1]?.method === "POST",
    ),
  ).toBe(false);
  expect(within(first).getByRole("button", { name: "View" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  fireEvent.click(screen.getByRole("button", { name: "Back to latest scan" }));
  expect(
    await screen.findByRole("heading", { name: "Latest scan summary" }),
  ).toBeInTheDocument();
  expect(screen.queryByText(/Viewing historical scan/)).not.toBeInTheDocument();

  vi.useFakeTimers();
  fireEvent.click(within(first).getByRole("button", { name: "Use setup" }));
  const toast = screen.getByRole("status", { name: "Setup loaded" });
  expect(toast).toHaveClass("discovery-toast");
  expect(toast).toHaveTextContent(
    "Historical scan setup loaded. Review before running.",
  );
  expect(
    within(toast).getByRole("button", { name: "Dismiss notification" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText(/Universe symbols/)).toHaveValue("AAA, BBB");
  expect(screen.getByRole("combobox", { name: /^Scan profile/ })).toHaveValue(
    "MOMENTUM",
  );
  expect(
    screen.getByRole("combobox", { name: /^Discovery intent/ }),
  ).toHaveValue("POSITIONAL_SHORT");
  expect(screen.getByRole("combobox", { name: /^Horizon/ })).toHaveValue("15d");
  expect(screen.getByRole("combobox", { name: /^Provider/ })).toHaveValue(
    "tradingview-synthetic",
  );
  expect(
    screen.getByRole("combobox", { name: /^Market context requirement/ }),
  ).toHaveValue("unavailable");
  act(() => vi.advanceTimersByTime(5000));
  expect(
    screen.queryByRole("status", { name: "Setup loaded" }),
  ).not.toBeInTheDocument();
  expect(document.querySelector(".discovery-hero")?.nextElementSibling).toBe(
    document.querySelector(".workspace-status-strip"),
  );
  vi.useRealTimers();
  expect(
    fetcher.mock.calls.some(
      (call) =>
        String(call[0]).endsWith("/scans") && call[1]?.method === "POST",
    ),
  ).toBe(false);

  fireEvent.click(within(first).getByRole("button", { name: "Archive" }));
  expect(
    await screen.findByRole("status", { name: "Scan history updated" }),
  ).toHaveTextContent("Scan archived.");
  expect(within(recent).getAllByRole("listitem")).toHaveLength(5);
  expect(
    within(recent).queryByText(/Tradingview synthetic · 2 symbols/),
  ).not.toBeInTheDocument();
  expect(within(recent).getByText(/6 matches/)).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(
    /permanent delete|clear history/i,
  );
  expect(fetcher.mock.calls.some((call) => call[1]?.method === "DELETE")).toBe(
    false,
  );

  fireEvent.click(screen.getByRole("button", { name: "Past scans" }));
  const dialog = await screen.findByRole("dialog", { name: "Past scans" });
  expect(within(dialog).getByText(/remain persisted/)).toBeInTheDocument();
  expect(within(dialog).getByLabelText("Date range")).toHaveValue("30d");
  expect(within(dialog).getByLabelText("Provider")).toBeInTheDocument();
  expect(within(dialog).getByLabelText("Profile")).toBeInTheDocument();
  expect(within(dialog).getByLabelText("Status")).toBeInTheDocument();
  expect(within(dialog).getByLabelText("Visibility")).toBeInTheDocument();

  fireEvent.change(within(dialog).getByLabelText("Date range"), {
    target: { value: "custom" },
  });
  expect(within(dialog).getByLabelText("From")).toBeInTheDocument();
  expect(within(dialog).getByLabelText("To")).toBeInTheDocument();
  fireEvent.change(within(dialog).getByLabelText("From"), {
    target: { value: "2099-01-01T00:00" },
  });
  expect(
    within(dialog).getByText("No scans match these filters."),
  ).toBeInTheDocument();
  fireEvent.change(within(dialog).getByLabelText("Date range"), {
    target: { value: "all" },
  });
  fireEvent.change(within(dialog).getByLabelText("Provider"), {
    target: { value: "tradingview-synthetic" },
  });
  expect(
    within(
      within(dialog).getByRole("list", { name: "Past discovery scans" }),
    ).getAllByRole("listitem"),
  ).toHaveLength(1);
  fireEvent.change(within(dialog).getByLabelText("Provider"), {
    target: { value: "all" },
  });
  fireEvent.change(within(dialog).getByLabelText("Profile"), {
    target: { value: "MOMENTUM" },
  });
  expect(
    within(
      within(dialog).getByRole("list", { name: "Past discovery scans" }),
    ).getAllByRole("listitem"),
  ).toHaveLength(1);
  fireEvent.change(within(dialog).getByLabelText("Profile"), {
    target: { value: "all" },
  });
  fireEvent.change(within(dialog).getByLabelText("Status"), {
    target: { value: "FAILED" },
  });
  expect(
    within(dialog).getByText("No scans match these filters."),
  ).toBeInTheDocument();
  fireEvent.change(within(dialog).getByLabelText("Status"), {
    target: { value: "COMPLETE" },
  });
  fireEvent.change(within(dialog).getByLabelText("Visibility"), {
    target: { value: "archived" },
  });
  const past = within(dialog).getByRole("list", {
    name: "Past discovery scans",
  });
  expect(within(past).getAllByRole("listitem")).toHaveLength(1);
  expect(within(past).getByText("Archived")).toBeInTheDocument();
  fireEvent.click(within(past).getByRole("button", { name: "Restore" }));
  expect(
    await screen.findByRole("status", { name: "Scan history updated" }),
  ).toHaveTextContent("Scan restored to recent history.");
  expect(within(recent).getAllByRole("listitem")).toHaveLength(5);
});

test("separates a zero-candidate current scan from the persisted active queue", async () => {
  const fetcher = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("/scans?")) return json([]);
    if (url.includes("/candidates?")) return json({ items: [candidate] });
    if (url.endsWith("/settings")) return json(settings);
    if (url.endsWith("/scans"))
      return json({
        summary: {
          run_id: "70000000-0000-0000-0000-000000000002",
          provider: "internal",
          status: "COMPLETE",
          started_at: "2026-09-30T06:00:00Z",
          completed_at: "2026-09-30T06:00:01Z",
          profile: "RELATIVE_VOLUME",
          horizon: "5d",
          intent: "INTRADAY_LONG",
          universe_size: 1,
          match_count: 0,
          candidate_count: 0,
          context_availability: "PARTIAL",
          degraded: [],
        },
        matches: [],
        candidates: [],
        market_context: context,
      });
    throw new Error(`Unexpected ${url}`);
  });
  vi.stubGlobal("fetch", fetcher);
  render(<DiscoveryWorkspace />);
  await screen.findByRole("button", { name: "Run scan" });
  fireEvent.click(screen.getByRole("button", { name: "Run scan" }));
  expect(
    (await screen.findAllByText(/No candidates were invented/)).length,
  ).toBeGreaterThan(0);
  expect(
    screen.getByText(
      "No candidates came from the latest scan. 1 active candidate(s) remain available in Active.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Current scan (0)" }),
  ).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "Active (1)" }));
  expect(
    within(screen.getByRole("table", { name: "Discovery queue" })).getByText(
      "RELIANCE",
    ),
  ).toBeInTheDocument();
  expect(screen.getAllByText("Run 70000000").length).toBeGreaterThan(0);
});

test("discovery settings save all bounded values with revision", async () => {
  const fetcher = vi
    .fn()
    .mockImplementationOnce(() => json(settings))
    .mockImplementationOnce(() =>
      json({ ...settings, revision: 1, llm_enabled: true }),
    );
  vi.stubGlobal("fetch", fetcher);
  render(<DiscoverySettingsSection />);
  await screen.findByLabelText("Default provider");
  expect(screen.getByLabelText("Recent observation window")).toHaveValue(20);
  fireEvent.change(screen.getByLabelText("Recent observation window"), {
    target: { value: "5" },
  });
  fireEvent.click(screen.getByLabelText("Enable optional AI explanation"));
  fireEvent.click(
    screen.getByRole("button", { name: "Save discovery defaults" }),
  );
  await screen.findByText("Scan & Discover defaults saved.");
  const body = JSON.parse(fetcher.mock.calls[1][1].body);
  expect(body).toMatchObject({
    revision: 0,
    llm_enabled: true,
    llm_provider: "synthetic",
    hot_observation_count: 5,
  });
});

test("distinguishes fresh, stale and unavailable source-time candidate states", async () => {
  const candidates = [
    candidate,
    { ...candidate, candidate_id: "candidate-stale", freshness: "STALE" },
    { ...candidate, candidate_id: "candidate-unknown", freshness: "UNKNOWN" },
  ];
  const fetcher = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("/scans?")) return json([]);
    if (url.includes("/candidates?")) return json({ items: candidates });
    if (url.endsWith("/settings")) return json(settings);
    throw new Error(`Unexpected ${url}`);
  });
  vi.stubGlobal("fetch", fetcher);
  render(<DiscoveryWorkspace initialView="candidates" />);
  await screen.findByRole("heading", { name: "Candidate ledger" });
  expect(screen.getAllByText("Fresh").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Stale").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Source time unavailable").length).toBeGreaterThan(
    0,
  );
});

test("confirms a terminal candidate action and records a specific audit reason", async () => {
  const confirm = vi.fn(() => true);
  const fetcher = vi.fn((input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("/scans?")) return json([]);
    if (url.includes("/candidates?")) return json({ items: [candidate] });
    if (url.endsWith("/settings")) return json(settings);
    if (url.includes("/lifecycle"))
      return json({ ...detail, lifecycle: "REJECTED", revision: 2 });
    if (url.endsWith(candidate.candidate_id)) return json(detail);
    throw new Error(`Unexpected ${url} ${init?.method || "GET"}`);
  });
  vi.stubGlobal("fetch", fetcher);
  vi.stubGlobal("confirm", confirm);
  render(<DiscoveryWorkspace initialView="candidates" />);
  fireEvent.click(
    within(
      await screen.findByRole("table", { name: "Discovery candidates" }),
    ).getByRole("button", { name: "Review" }),
  );
  const inspector = await screen.findByRole("complementary", {
    name: "RELIANCE",
  });
  fireEvent.click(
    within(inspector).getByRole("button", { name: "Dismiss candidate" }),
  );
  await screen.findByText("Candidate lifecycle changed to REJECTED.");
  expect(confirm).toHaveBeenCalledWith(
    expect.stringMatching(/ends the current discovery episode/),
  );
  const request = fetcher.mock.calls.find((call) =>
    String(call[0]).includes("/lifecycle"),
  );
  expect(JSON.parse(request?.[1]?.body as string)).toMatchObject({
    action: "DISMISS",
    reason: "manual-candidate-dismissal",
  });
});

test("separates profile logic from purpose and preserves explicit overrides", async () => {
  const fetcher = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("/scans?")) return json([]);
    if (url.includes("/candidates?")) return json({ items: [candidate] });
    if (url.endsWith("/settings")) return json(settings);
    throw new Error(`Unexpected ${url}`);
  });
  vi.stubGlobal("fetch", fetcher);
  render(<DiscoveryWorkspace />);

  await screen.findByRole("heading", { name: "Configure scan" });
  expect(
    screen.queryByRole("navigation", { name: "Scan and Discover views" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /^Candidates/ }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: /^Horizon/ })).toHaveValue("5d");
  fireEvent.click(screen.getByRole("button", { name: "Apply suggestion" }));
  expect(screen.getByRole("combobox", { name: /^Horizon/ })).toHaveValue("1d");

  fireEvent.change(screen.getByRole("combobox", { name: /^Scan profile/ }), {
    target: { value: "MOMENTUM" },
  });
  expect(
    screen.getByRole("combobox", { name: /^Discovery intent/ }),
  ).toHaveValue("POSITIONAL_LONG");
  expect(screen.getByRole("combobox", { name: /^Horizon/ })).toHaveValue("5d");

  fireEvent.change(
    screen.getByRole("combobox", { name: /^Discovery intent/ }),
    {
      target: { value: "INTRADAY_SHORT" },
    },
  );
  fireEvent.change(screen.getByRole("combobox", { name: /^Horizon/ }), {
    target: { value: "1d" },
  });
  fireEvent.change(screen.getByRole("combobox", { name: /^Scan profile/ }), {
    target: { value: "PULLBACK_IN_UPTREND" },
  });
  expect(
    screen.getByText("Pullback in uptrend supports long-side intent only."),
  ).toHaveAttribute("role", "alert");
  expect(screen.getByRole("button", { name: "Run scan" })).toBeDisabled();

  fireEvent.change(screen.getByRole("combobox", { name: /^Scan profile/ }), {
    target: { value: "TREND_CONTINUATION" },
  });
  expect(
    screen.getByRole("combobox", { name: /^Discovery intent/ }),
  ).toHaveValue("INTRADAY_SHORT");
  expect(screen.getByRole("combobox", { name: /^Horizon/ })).toHaveValue("1d");

  fireEvent.click(screen.getByRole("button", { name: "Apply suggestion" }));
  expect(
    screen.getByRole("combobox", { name: /^Discovery intent/ }),
  ).toHaveValue("POSITIONAL_LONG");
  expect(screen.getByRole("combobox", { name: /^Horizon/ })).toHaveValue("15d");

  const contextPolicy = screen.getByRole("combobox", {
    name: /^Market context requirement/,
  });
  expect(
    within(contextPolicy).getByRole("option", {
      name: "Require complete context",
    }),
  ).toBeInTheDocument();
  expect(
    within(contextPolicy).getByRole("option", {
      name: "Allow partial context",
    }),
  ).toBeInTheDocument();
  expect(
    within(contextPolicy).getByRole("option", { name: "Context optional" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Missing evidence remains visible and reduces coverage/),
  ).toBeInTheDocument();
});

test.each([
  ["AVAILABLE", true, "Ready"],
  ["UNAVAILABLE", true, "Unavailable"],
  ["AUTH_REQUIRED", true, "Auth required"],
  ["RATE_LIMITED", true, "Rate limited"],
  ["UNAVAILABLE", false, "Disabled"],
])(
  "renders provider operational state %s/%s as text",
  async (health, enabled, expected) => {
    const providerStates = [
      providers[0],
      {
        ...providers[1],
        enabled,
        mode: "REMOTE",
        health,
        last_error: null,
      },
    ];
    const fetcher = vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/status")) return json(providerStates);
      if (url.includes("/scans?")) return json([]);
      if (url.includes("/candidates?")) return json({ items: [] });
      if (url.endsWith("/settings")) return json(settings);
      throw new Error(`Unexpected ${url}`);
    });
    vi.stubGlobal("fetch", fetcher);
    render(<DiscoveryWorkspace />);
    await screen.findByRole("heading", {
      name: "Provider and evidence readiness",
    });
    expect(screen.getByText("Live")).toBeInTheDocument();
    const providerCard = screen
      .getByText("TradingView real evidence")
      .closest("article");
    expect(providerCard).not.toBeNull();
    expect(
      within(providerCard as HTMLElement).getByText(expected),
    ).toBeInTheDocument();
  },
);

test("orders the queue deterministically and applies compact triage controls", async () => {
  const makeCandidate = (
    symbol: string,
    score: string,
    lifecycle: "NEW" | "CURRENT" | "STALE" | "REJECTED",
    freshness: "FRESH" | "STALE" | "UNKNOWN",
    updatedAt: string,
  ) => ({
    ...candidate,
    candidate_id: `candidate-${symbol.toLowerCase()}`,
    episode_id: `episode-${symbol.toLowerCase()}`,
    instrument: {
      ...candidate.instrument,
      symbol,
      native: { ...candidate.instrument.native, native_id: `NSE:${symbol}` },
    },
    relevance: { ...candidate.relevance, value: score },
    relevance_explanation: {
      ...candidate.relevance_explanation,
      score,
      band: Number(score) >= 0.9 ? "HIGH" : "MEDIUM",
    },
    lifecycle,
    lifecycle_reason:
      lifecycle === "STALE"
        ? "source-freshness-expired"
        : "comparable-observation",
    freshness,
    updated_at: updatedAt,
    profile: symbol === "AAA" ? "MOMENTUM" : "RELATIVE_VOLUME",
  });
  const queueCandidates = [
    makeCandidate("AAA", "0.82", "CURRENT", "FRESH", "2026-09-30T05:00:00Z"),
    makeCandidate("ZZZ", "0.88", "STALE", "STALE", "2026-09-30T06:00:00Z"),
    makeCandidate("BBB", "0.84", "NEW", "FRESH", "2026-09-30T06:00:00Z"),
    makeCandidate("CCC", "0.88", "CURRENT", "UNKNOWN", "2026-09-30T06:00:00Z"),
    makeCandidate("DDD", "0.88", "CURRENT", "FRESH", "2026-09-30T06:00:00Z"),
    makeCandidate("EEE", "0.99", "REJECTED", "FRESH", "2026-09-30T06:00:00Z"),
  ];
  const fetcher = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("/scans?")) return json([]);
    if (url.includes("/candidates?")) return json({ items: queueCandidates });
    if (url.endsWith("/settings")) return json(settings);
    throw new Error(`Unexpected ${url}`);
  });
  vi.stubGlobal("fetch", fetcher);
  render(<DiscoveryWorkspace />);

  const queue = await screen.findByRole("table", { name: "Discovery queue" });
  const symbols = () =>
    [...queue.querySelectorAll("tbody tr")].map((row) =>
      row.getAttribute("data-candidate-symbol"),
    );
  expect(symbols()).toEqual(["DDD", "CCC", "ZZZ", "BBB", "AAA"]);
  expect(screen.getByRole("button", { name: "Active (5)" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  fireEvent.click(screen.getByRole("button", { name: "All (6)" }));
  expect(symbols()[0]).toBe("EEE");
  fireEvent.click(screen.getByRole("button", { name: "Active (5)" }));
  expect(symbols()).toEqual(["DDD", "CCC", "ZZZ", "BBB", "AAA"]);

  fireEvent.click(screen.getByText("Filter and sort"));
  expect(screen.getByLabelText("Sort")).toHaveValue("attention");
  expect(
    screen.getByText(
      /Sorted by current relevance model, relevance, lifecycle, freshness, and recency/,
    ),
  ).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Search symbol"), {
    target: { value: "AAA" },
  });
  expect(symbols()).toEqual(["AAA"]);
  expect(screen.getByText(/Showing 1 of 5/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  fireEvent.change(screen.getByLabelText("Lifecycle"), {
    target: { value: "STALE" },
  });
  expect(symbols()).toEqual(["ZZZ"]);
  expect(
    within(queue).getByText("Source freshness expired"),
  ).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  fireEvent.change(screen.getByLabelText("Profile"), {
    target: { value: "MOMENTUM" },
  });
  expect(symbols()).toEqual(["AAA"]);

  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  fireEvent.change(screen.getByLabelText("Sort"), {
    target: { value: "symbol" },
  });
  expect(symbols()).toEqual(["AAA", "BBB", "CCC", "DDD", "ZZZ"]);
});

test("groups duplicate current evidence while preserving usable provenance", async () => {
  const currentEvidence = detail.snapshots[0].evidence[0];
  const duplicateDetail = {
    ...detail,
    snapshots: [
      {
        ...detail.snapshots[0],
        evidence: [
          {
            ...currentEvidence,
            evidence_id: "60000000-0000-0000-0000-000000000000",
            observed_at: "2026-09-30T05:00:00Z",
            measures: currentEvidence.measures.map((measure) =>
              measure.name === "relative_volume"
                ? { ...measure, value: "1.8" }
                : measure,
            ),
          },
          currentEvidence,
        ],
      },
    ],
  };
  const fetcher = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("/scans?")) return json([]);
    if (url.includes("/candidates?")) return json({ items: [candidate] });
    if (url.endsWith("/settings")) return json(settings);
    if (url.endsWith(candidate.candidate_id)) return json(duplicateDetail);
    throw new Error(`Unexpected ${url}`);
  });
  vi.stubGlobal("fetch", fetcher);
  render(<DiscoveryWorkspace />);
  const queue = await screen.findByRole("table", { name: "Discovery queue" });
  fireEvent.click(within(queue).getByRole("button", { name: "Review" }));
  const inspector = await screen.findByRole("complementary", {
    name: "RELIANCE",
  });
  const evidenceList = within(inspector).getByRole("heading", {
    name: "Latest evidence",
  }).nextElementSibling;
  expect(evidenceList?.querySelectorAll(":scope > li")).toHaveLength(1);
  expect(
    within(inspector).getByText(/Relative volume: 2.4 ratio/),
  ).toBeInTheDocument();
  expect(
    within(inspector).queryByText(/Relative volume: 1.8 ratio/),
  ).not.toBeInTheDocument();
  expect(
    within(inspector).getByRole("button", { name: "Copy evidence identifier" }),
  ).toBeInTheDocument();
  expect(inspector).toHaveClass("candidate-inspector");
});

test("shows typed feedback when history actions cannot complete", async () => {
  const completedAt = new Date().toISOString();
  const invalidSummary = {
    run_id: "70000000-0000-0000-0000-000000000099",
    provider: "internal",
    status: "COMPLETE",
    started_at: completedAt,
    completed_at: completedAt,
    profile: "UNKNOWN_LEGACY_PROFILE",
    horizon: "5d",
    intent: "INTRADAY_LONG",
    universe_size: 0,
    universe: [],
    match_count: 0,
    candidate_count: 0,
    context_mode: "partial",
    context_policy: "ALLOW_PARTIAL",
    context_availability: "PARTIAL",
    degraded: [],
    archived_at: null,
  };
  const fetcher = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("/scans?")) return json([invalidSummary]);
    if (url.includes("/candidates?")) return json({ items: [] });
    if (url.endsWith("/settings")) return json(settings);
    if (url.endsWith(`/scans/${invalidSummary.run_id}`)) return json({}, 500);
    if (url.endsWith(`/${invalidSummary.run_id}/archive`)) return json({}, 500);
    throw new Error(`Unexpected ${url}`);
  });
  vi.stubGlobal("fetch", fetcher);
  render(<DiscoveryWorkspace />);

  const recent = await screen.findByRole("list", {
    name: "Recent discovery scans",
  });
  const row = within(recent).getByRole("listitem");
  fireEvent.click(within(row).getByText("Actions"));
  fireEvent.click(within(row).getByRole("button", { name: "View" }));
  expect(
    await screen.findByText("Unable to load historical scan."),
  ).toBeInTheDocument();

  fireEvent.click(within(row).getByRole("button", { name: "Use setup" }));
  expect(
    await screen.findByText("Setup could not be restored."),
  ).toBeInTheDocument();

  fireEvent.click(within(row).getByRole("button", { name: "Archive" }));
  expect(
    await screen.findByText("Unable to archive scan."),
  ).toBeInTheDocument();
});

test("ranks current v2 relevance before legacy scores and labels legacy provenance", async () => {
  const make = (symbol: string, score: string, legacy: boolean) => ({
    ...candidate,
    candidate_id: `candidate-${symbol.toLowerCase()}`,
    episode_id: `episode-${symbol.toLowerCase()}`,
    instrument: {
      ...candidate.instrument,
      symbol,
      native: { ...candidate.instrument.native, native_id: `NSE:${symbol}` },
    },
    profile: legacy ? null : "RELATIVE_VOLUME",
    profile_lineage: legacy ? "LEGACY_UNAVAILABLE" : "CURRENT_SNAPSHOT",
    legacy_profile: legacy,
    relevance: {
      ...candidate.relevance,
      value: score,
      policy: legacy
        ? { id: "deterministic-relevance-v1", version: "1" }
        : { id: "deterministic-relevance-v2", version: "2" },
    },
    relevance_explanation: {
      ...candidate.relevance_explanation,
      score,
      policy: legacy
        ? "deterministic-relevance-v1"
        : "deterministic-relevance-v2",
    },
  });
  const mixed = [
    make("LEGACY", "1.00", true),
    make("CURRENT84", "0.84", false),
    make("CURRENT82", "0.82", false),
  ];
  const fetcher = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("/scans?")) return json([]);
    if (url.includes("/candidates?")) return json({ items: mixed });
    if (url.endsWith("/settings")) return json(settings);
    throw new Error(`Unexpected ${url}`);
  });
  vi.stubGlobal("fetch", fetcher);
  render(<DiscoveryWorkspace />);

  const queue = await screen.findByRole("table", { name: "Discovery queue" });
  const symbols = [...queue.querySelectorAll("tbody tr")].map((row) =>
    row.getAttribute("data-candidate-symbol"),
  );
  expect(symbols).toEqual(["CURRENT84", "CURRENT82", "LEGACY"]);
  const legacyRow = queue.querySelector('[data-candidate-symbol="LEGACY"]');
  expect(legacyRow).not.toBeNull();
  expect(
    within(legacyRow as HTMLElement).getByText("Profile unavailable"),
  ).toBeInTheDocument();
  expect(
    within(legacyRow as HTMLElement).getByText("Legacy score"),
  ).toHaveAttribute(
    "title",
    expect.stringContaining("not directly comparable"),
  );
  expect(
    within(legacyRow as HTMLElement).getByLabelText(/Legacy candidate/),
  ).toBeInTheDocument();
});

test("renders real TradingView current-chart provenance without realtime or completed-bar claims", () => {
  const base = evidenceChart("as_scanned");
  const chart = {
    ...base,
    mode: "current",
    state: "AVAILABLE",
    message: null,
    provider: "tradingview",
    data_mode: "LIVE_SNAPSHOT",
    bar_finality: "PROVIDER_UNSPECIFIED",
    bars: base.bars.map((bar) => ({
      ...bar,
      finality: "PROVIDER_UNSPECIFIED",
    })),
    retention: {
      ...base.retention,
      source_class: "PROVIDER_RESTRICTED",
      historical_chart_reconstructable: false,
      scan_bars_retained: false,
      current_chart_available: true,
      limitation: "TradingView retention rights are unknown.",
    },
  } as Parameters<
    typeof import("../src/components/discovery/evidence-chart-drawer").EvidenceChartDrawer
  >[0]["chart"];
  render(
    <EvidenceChartDrawer
      chart={chart}
      loading={false}
      onClose={vi.fn()}
      onMode={vi.fn()}
    />,
  );
  expect(screen.getByText("TRADINGVIEW MARKET DATA")).toBeInTheDocument();
  expect(screen.getByText(/Finality unspecified/)).toBeInTheDocument();
  expect(screen.queryByText(/realtime/i)).not.toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Current chart" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});

test("renders retention-restricted real as-scanned evidence without inventing bars", () => {
  const base = evidenceChart("as_scanned");
  const chart = {
    ...base,
    state: "RETENTION_RESTRICTED",
    message:
      "Numerical evidence retained. Historical chart reconstruction unavailable due provider retention policy.",
    provider: "tradingview",
    data_mode: "LIVE_SNAPSHOT",
    bar_finality: "PROVIDER_UNSPECIFIED",
    bars: [],
    series: [],
    thresholds: [],
    retention: {
      ...base.retention,
      source_class: "PROVIDER_RESTRICTED",
      historical_chart_reconstructable: false,
      scan_bars_retained: false,
      current_chart_available: true,
      archive_bar_count: 0,
      displayed_bar_count: 0,
      limitation: "TradingView retention rights are unknown.",
    },
  } as Parameters<
    typeof import("../src/components/discovery/evidence-chart-drawer").EvidenceChartDrawer
  >[0]["chart"];
  render(
    <EvidenceChartDrawer
      chart={chart}
      loading={false}
      onClose={vi.fn()}
      onMode={vi.fn()}
    />,
  );
  expect(screen.getByText("RETENTION RESTRICTED")).toBeInTheDocument();
  expect(screen.getByText(/Numerical evidence retained/)).toBeInTheDocument();
  expect(
    screen.getByText(/Historical numerical predicates remain available/),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText("Visual evidence")).not.toBeInTheDocument();
});

test.each(["AUTH_REQUIRED", "RATE_LIMITED", "EXACT_MISSING"] as const)(
  "renders typed real chart failure %s",
  (state) => {
    const base = evidenceChart("as_scanned");
    const chart = {
      ...base,
      mode: "current",
      state,
      message: `Typed ${state.toLowerCase()} provider state.`,
      provider: "tradingview",
      data_mode: "LIVE_SNAPSHOT",
      bar_finality: "PROVIDER_UNSPECIFIED",
      bars: [],
      series: [],
      thresholds: [],
      metrics: [],
      retention: {
        ...base.retention,
        source_class: "PROVIDER_RESTRICTED",
        historical_chart_reconstructable: false,
        scan_bars_retained: false,
        current_chart_available: true,
        archive_bar_count: 0,
        displayed_bar_count: 0,
      },
    } as Parameters<
      typeof import("../src/components/discovery/evidence-chart-drawer").EvidenceChartDrawer
    >[0]["chart"];
    render(
      <EvidenceChartDrawer
        chart={chart}
        loading={false}
        onClose={vi.fn()}
        onMode={vi.fn()}
      />,
    );
    expect(screen.getByText(state.replaceAll("_", " "))).toBeInTheDocument();
  },
);
