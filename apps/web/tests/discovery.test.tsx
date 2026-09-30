import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { DiscoveryWorkspace } from "../src/components/discovery/discovery-workspace";
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
  intent: "MOMENTUM",
  horizon: "5d",
  relevance: {
    value: "0.81",
    required_inputs_satisfied: true,
    coverage: "0.75",
    reasons: ["evidence-fit"],
  },
  relevance_explanation: {
    policy: "deterministic-relevance-v1",
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
    conflicts: [],
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
  freshness: "FRESH",
  snapshot_count: 1,
  provider_sources: ["twf-native"],
  updated_at: "2026-09-30T06:00:00Z",
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
          measures: [{ name: "relative_volume", value: "2.4", unit: "ratio" }],
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
};
const providers = [
  {
    id: "internal",
    label: "Internal Scanner V0",
    enabled: true,
    mode: "LOCAL_SYNTHETIC",
    health: "AVAILABLE",
    capabilities: ["scan"],
    last_success_at: null,
    last_error: null,
  },
  {
    id: "tradingview-synthetic",
    label: "TradingView contract validation",
    enabled: true,
    mode: "SYNTHETIC_VALIDATION",
    health: "AVAILABLE",
    capabilities: ["exact-batch"],
    last_success_at: null,
    last_error: null,
  },
];

function json(data: unknown, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: async () => data });
}

afterEach(() => vi.unstubAllGlobals());

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
      intent: "MOMENTUM",
      universe_size: 2,
      match_count: 1,
      candidate_count: 1,
      context_availability: "PARTIAL",
      degraded: ["market breadth unavailable"],
    },
    matches: [
      {
        match_id: "71000000-0000-0000-0000-000000000001",
        symbol: "RELIANCE",
        exchange: "NSE",
        provider: "twf-native",
        why_matched: ["relative-volume-v1"],
        key_metrics: { relative_volume: "2.4" },
        source_mode: "SYNTHETIC",
        lineage: "internal-scanner-v0:relative-volume",
      },
    ],
    candidates: [candidate],
    market_context: context,
  };
  const fetcher = vi.fn((input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("/candidates?"))
      return json({ items: init?.method === "POST" ? [] : [candidate] });
    if (url.endsWith("/settings")) return json(settings);
    if (url.endsWith("/scans")) return json(scan, 201);
    if (url.endsWith(candidate.candidate_id)) return json(detail);
    throw new Error(`Unexpected ${url}`);
  });
  vi.stubGlobal("fetch", fetcher);
  render(<DiscoveryWorkspace />);
  await screen.findByRole("heading", { name: "Provider readiness" });
  expect(
    screen.getByText(/Discovery never authorizes a trade/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/deterministic local validation series/),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/Universe symbols/), {
    target: { value: "RELIANCE, TCS" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Run scan" }));
  await screen.findByRole("heading", { name: "Latest scan result" });
  expect(screen.getByText(/market breadth unavailable/)).toBeInTheDocument();
  expect(screen.getAllByText("RELIANCE").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: "Review" }));
  const inspector = await screen.findByRole("complementary", {
    name: "RELIANCE",
  });
  expect(
    within(inspector).getByText(/Policy fit, not probability of profit/),
  ).toBeInTheDocument();
  expect(
    within(inspector).getByText(/relative_volume: 2.4 ratio/),
  ).toBeInTheDocument();
  expect(within(inspector).getByText(/Missing: breadth/)).toBeInTheDocument();
  expect(within(inspector).getByText(/Snapshot 1/)).toBeInTheDocument();
  expect(
    within(inspector).getByRole("heading", { name: "Horizon-aware tolerance" }),
  ).toBeInTheDocument();
  expect(within(inspector).getAllByText("WITHIN").length).toBeGreaterThan(0);
  const scanBody = JSON.parse(
    fetcher.mock.calls.find((call) => String(call[0]).endsWith("/scans"))?.[1]
      ?.body as string,
  );
  expect(scanBody.universe).toEqual(["RELIANCE", "TCS"]);
  expect(scanBody.include_llm).toBe(false);
});

test("renders an honest no-match state", async () => {
  const fetcher = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("/candidates?")) return json({ items: [] });
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
          intent: "MOMENTUM",
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
    await screen.findByText(/No candidates were invented/),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "No candidates to review" }),
  ).toBeInTheDocument();
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
  fireEvent.click(
    screen.getByLabelText("Enable controlled Level-0 explanation"),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Save discovery defaults" }),
  );
  await screen.findByText("Scan & Discover defaults saved.");
  const body = JSON.parse(fetcher.mock.calls[1][1].body);
  expect(body).toMatchObject({
    revision: 0,
    llm_enabled: true,
    llm_provider: "synthetic",
  });
});
