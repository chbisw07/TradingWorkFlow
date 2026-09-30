import { act, fireEvent, render, screen, within } from "@testing-library/react";
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
  expect(within(statusStrip!).getByText("Validation")).toBeInTheDocument();
  expect(setupPanel).not.toContainElement(statusStrip);
  const history = screen.getByRole("list", { name: "Recent discovery scans" });
  expect(within(history).getByText(/Internal · 2 symbols/)).toBeInTheDocument();
  fireEvent.click(within(history).getByText("Actions"));
  const viewHistory = within(history).getByRole("button", { name: "View" });
  fireEvent.click(viewHistory);
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
  expect(screen.getByText("Relative volume elevated")).toBeInTheDocument();
  expect(screen.getByText("Fresh")).toBeInTheDocument();
  expect(screen.getAllByText("Details").length).toBeGreaterThan(1);
  expect(screen.getAllByText("RELIANCE").length).toBeGreaterThan(0);
  expect(container.querySelector(".scan-workstation-grid")).toHaveClass(
    "without-inspector",
  );
  const queue = screen.getByRole("table", { name: "Discovery queue" });
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
    await screen.findByText(/Select View on another recent scan/),
  ).toBeInTheDocument();
  expect(within(first).getByRole("button", { name: "View" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  vi.useFakeTimers();
  fireEvent.click(within(first).getByRole("button", { name: "Use setup" }));
  const toast = screen.getByRole("status", { name: "Setup loaded" });
  expect(toast).toHaveClass("discovery-toast");
  expect(toast).toHaveTextContent(
    "Scan setup loaded. Review it before selecting Run scan.",
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
  await screen.findByText("Scan archived. It remains available in Past scans.");
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
  await screen.findByText("Scan restored to recent history.");
  expect(within(recent).getAllByRole("listitem")).toHaveLength(5);
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
      .getByText("TradingView contract validation")
      .closest("article");
    expect(providerCard).not.toBeNull();
    expect(
      within(providerCard as HTMLElement).getByText(expected),
    ).toBeInTheDocument();
  },
);
