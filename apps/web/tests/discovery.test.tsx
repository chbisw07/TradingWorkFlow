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
  intent: "INTRADAY_LONG",
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
          measures: [
            { name: "relative_volume", value: "2.4", unit: "ratio" },
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
    health: "RATE_LIMITED",
    capabilities: ["exact-batch"],
    last_success_at: null,
    last_error: "Daily request budget reached",
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
      intent: "INTRADAY_LONG",
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
        segment: "EQ",
        why_matched: ["Relative volume 2.40×"],
        raw_reasons: ["1d.0.relative_volume.20"],
        key_metrics: {
          close: "2954.54",
          "momentum.10": "2.8",
          "relative_volume.20": "2.4",
        },
        source_mode: "SYNTHETIC",
        source_data_time: "2026-09-30T05:59:00Z",
        lineage: "internal-scanner-v0:relative-volume",
      },
    ],
    candidates: [candidate],
    market_context: context,
  };
  const fetcher = vi.fn((input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("/scans?")) return json([scan.summary]);
    if (url.includes("/candidates?"))
      return json({ items: init?.method === "POST" ? [] : [candidate] });
    if (url.endsWith("/settings")) return json(settings);
    if (url.endsWith("/scans")) return json(scan, 201);
    if (url.includes("/lifecycle"))
      return json({ ...detail, lifecycle: "REJECTED", revision: 2 });
    if (url.endsWith(candidate.candidate_id)) return json(detail);
    throw new Error(`Unexpected ${url}`);
  });
  const confirm = vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(true);
  vi.stubGlobal("fetch", fetcher);
  vi.stubGlobal("confirm", confirm);
  render(<DiscoveryWorkspace />);
  await screen.findByRole("heading", { name: "Provider status" });
  expect(
    screen.getByText(/Discovery never authorizes a trade/),
  ).toBeInTheDocument();
  expect(screen.getByText("SYNTHETIC VALIDATION DATA")).toBeInTheDocument();
  expect(screen.getByText("RATE LIMITED")).toBeInTheDocument();
  expect(screen.getByText(/Daily request budget reached/)).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Configure scan" }),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/Universe symbols/), {
    target: { value: "RELIANCE, TCS" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Run scan" }));
  await screen.findByRole("heading", { name: "Latest scan result" });
  expect(screen.getByText(/Market breadth unavailable/)).toBeInTheDocument();
  expect(screen.getByText("Relative volume elevated")).toBeInTheDocument();
  expect(screen.getByText("Fresh")).toBeInTheDocument();
  expect(screen.getAllByText("Details").length).toBeGreaterThan(1);
  expect(screen.getAllByText("RELIANCE").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: "Review" }));
  const inspector = await screen.findByRole("complementary", {
    name: "RELIANCE",
  });
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
  expect(
    within(inspector).getByRole("heading", { name: "Horizon-aware tolerance" }),
  ).toBeInTheDocument();
  expect(within(inspector).getAllByText("Within").length).toBeGreaterThan(0);
  expect(screen.getByRole("button", { name: "Reviewing" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
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
});

test("renders an honest no-match state", async () => {
  const fetcher = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/status")) return json(providers);
    if (url.includes("/scans?")) return json([]);
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
  expect(screen.getByText("No discovery candidates yet.")).toBeInTheDocument();
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
  fireEvent.click(await screen.findByRole("button", { name: "Review" }));
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
  ["AVAILABLE", true, "READY"],
  ["UNAVAILABLE", true, "UNAVAILABLE"],
  ["AUTH_REQUIRED", true, "AUTH REQUIRED"],
  ["RATE_LIMITED", true, "RATE LIMITED"],
  ["UNAVAILABLE", false, "DISABLED"],
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
    await screen.findByRole("heading", { name: "Provider status" });
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    const providerCard = screen
      .getByText("TradingView contract validation")
      .closest("article");
    expect(providerCard).not.toBeNull();
    expect(
      within(providerCard as HTMLElement).getByText(expected),
    ).toBeInTheDocument();
  },
);
