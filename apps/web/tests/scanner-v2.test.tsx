import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ScannerWorkspace } from "../src/components/scanner/scanner-workspace";
import {
  filterCompatible,
  filterExpression,
  initialConfig,
  scannerApi,
  type FilterField,
  type Catalog,
} from "../src/lib/scanner";

function field(
  value: Partial<FilterField> &
    Pick<FilterField, "field" | "label" | "field_type">,
): FilterField {
  return {
    category: "Technical Indicators",
    enabled: true,
    operators: [">", ">=", "<", "<=", "equals", "not_equals", "between"],
    default_operator: ">",
    default_value: 0,
    comparison_fields: [],
    enum_values: [],
    minimum: null,
    maximum: null,
    minimum_exclusive: false,
    unit: null,
    ...value,
  };
}

const catalog: Catalog = {
  fields: [
    field({
      field: "rsi",
      label: "RSI (14)",
      field_type: "NUMBER",
      default_value: 50,
      minimum: 0,
      maximum: 100,
    }),
    field({
      field: "price",
      label: "Completed close",
      category: "Price & Volume",
      field_type: "PRICE",
      comparison_fields: ["high20", "sma20", "sma50", "ema20"],
      unit: "INR",
    }),
    field({
      field: "volume",
      label: "Volume",
      category: "Price & Volume",
      field_type: "VOLUME",
      comparison_fields: ["average_volume"],
      unit: "VOLUME",
    }),
    field({
      field: "average_volume",
      label: "Prior 20-day average volume",
      category: "Price & Volume",
      field_type: "VOLUME",
      comparison_fields: ["volume"],
      unit: "VOLUME",
    }),
    field({
      field: "sma20",
      label: "SMA (20)",
      field_type: "PRICE",
      comparison_fields: ["price", "high20", "sma50", "ema20"],
      unit: "INR",
    }),
    field({
      field: "sma50",
      label: "SMA (50)",
      field_type: "PRICE",
      comparison_fields: ["price", "high20", "sma20", "ema20"],
      unit: "INR",
    }),
    field({
      field: "ema20",
      label: "EMA (20)",
      field_type: "PRICE",
      comparison_fields: ["price", "high20", "sma20", "sma50"],
      unit: "INR",
    }),
    field({
      field: "high20",
      label: "Prior 20-day high",
      category: "Breakouts & Patterns",
      field_type: "PRICE",
      comparison_fields: ["price", "sma20", "sma50", "ema20"],
      unit: "INR",
    }),
    field({
      field: "market_cap_inr",
      label: "Market cap (INR)",
      category: "Fundamentals (TapTide)",
      field_type: "NUMBER",
      default_value: 10000,
      minimum: 0,
      minimum_exclusive: true,
      unit: "INR",
    }),
    field({
      field: "pe_ratio",
      label: "PE ratio",
      category: "Fundamentals (TapTide)",
      field_type: "RATIO",
      enabled: false,
      default_value: 25,
      unit: "RATIO",
    }),
    field({
      field: "trend",
      label: "Trend versus SMA20",
      category: "Trend & Momentum",
      field_type: "DIRECTION",
      operators: ["equals", "not_equals"],
      default_operator: "equals",
      default_value: "Up",
      enum_values: ["Up", "Down", "Sideways"],
    }),
    field({
      field: "supertrend",
      label: "Supertrend direction (10,3)",
      category: "Trend & Momentum",
      field_type: "ENUM",
      operators: ["equals", "not_equals"],
      default_operator: "equals",
      default_value: "Up",
      enum_values: ["Up", "Down"],
    }),
  ],
  context_fields: [
    field({
      field: "broad_regime",
      label: "Broad market regime",
      category: "Market Context",
      field_type: "ENUM",
      operators: ["equals", "not_equals"],
      default_operator: "equals",
      default_value: "BULLISH",
      enum_values: ["BULLISH", "NEUTRAL", "BEARISH"],
    }),
    field({
      field: "vix_state",
      label: "India VIX state",
      category: "Market Context",
      field_type: "ENUM",
      operators: ["equals", "not_equals"],
      default_operator: "not_equals",
      default_value: "HIGH",
      enum_values: ["LOW", "NORMAL", "ELEVATED", "HIGH"],
    }),
  ],
  templates: [
    {
      name: "RSI Oversold",
      filters: [
        {
          field: "rsi",
          operator: "<",
          value: 30,
          timeframe: "1d",
          version: "1",
          source: "internal",
        },
      ],
    },
  ],
  universes: { CUSTOM: true, WATCHLIST: true, INDEX: false },
  universe_limitation: "No verified constituent source",
};
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
});
afterEach(() => vi.restoreAllMocks());
function mockFetch() {
  return vi.spyOn(global, "fetch").mockImplementation(async (url, init) => {
    const path = String(url);
    if (path.endsWith("/catalog")) return Response.json(catalog);
    if (path.endsWith("/runs") && init?.method === "POST")
      return Response.json({
        id: "run1",
        created_at: "2026-10-06T10:00:00Z",
        config: JSON.parse(String(init.body)),
        counts: {
          requested: 1,
          resolved: 0,
          evaluated: 0,
          not_evaluated: 1,
          matches: 0,
        },
        rows: [
          {
            symbol: "INFY",
            outcome: "NOT_EVALUATED",
            failure: "AUTH_REQUIRED",
          },
        ],
      });
    return Response.json([]);
  });
}
test("fresh Scanner UI separates equity and active derivatives workspace", async () => {
  mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "PE ratio" });
  expect(screen.getByRole("option", { name: "PE ratio" })).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: "Index" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Remove filter 1" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /Watchlist: Choose watchlist/ }),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "Run Scan" })).toBeDisabled();
  fireEvent.click(screen.getByRole("tab", { name: /Derivatives Scanner/ }));
  expect(
    screen.getByRole("heading", { name: "Build an options scan" }),
  ).toBeVisible();
  expect(
    screen.getByLabelText("Active derivatives scan configuration"),
  ).toHaveTextContent("Expiry: Nearest active");
  expect(
    screen.queryByText("Candidates requiring review"),
  ).not.toBeInTheDocument();
});
test("explicit real Dhan payload and acquisition failures never become no-match", async () => {
  const fetch = mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "RSI (14)" });
  fireEvent.click(screen.getByRole("button", { name: /Add Filter/ }));
  fireEvent.click(screen.getByRole("button", { name: "Custom symbols" }));
  fireEvent.change(screen.getByLabelText("NSE symbols"), {
    target: { value: "INFY" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Run Scan" }));
  await screen.findByText("No instruments could be evaluated.");
  const call = fetch.mock.calls.find(
    ([url, init]) => String(url).endsWith("/runs") && init?.method === "POST",
  )!;
  const body = JSON.parse(String(call[1]?.body));
  expect(body.data_mode).toBe("REAL");
  expect(body.provider).toBe("dhan");
  expect(body.universe.symbols).toEqual(["INFY"]);
  expect(body.filters[0]).toEqual(catalog.templates[0].filters[0]);
});
test("evaluated non-match is distinct from an acquisition failure", async () => {
  vi.spyOn(global, "fetch").mockImplementation(async (url, init) => {
    const path = String(url);
    if (path.endsWith("/catalog")) return Response.json(catalog);
    if (path.endsWith("/runs") && init?.method === "POST")
      return Response.json({
        id: "non-match-run",
        created_at: "2026-10-12T10:00:00Z",
        config: JSON.parse(String(init.body)),
        data_mode: "REAL",
        market_data_provider: "dhan",
        counts: {
          requested: 1,
          resolved: 1,
          evaluated: 1,
          not_evaluated: 0,
          matches: 0,
        },
        rows: [
          {
            symbol: "INFY",
            outcome: "NON_MATCH",
            diagnostics: [
              {
                filter: catalog.templates[0].filters[0],
                observed: 55,
                threshold: 30,
                passed: false,
                reason: "RSI (14) < 30",
              },
            ],
          },
        ],
      });
    return Response.json([]);
  });
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "RSI (14)" });
  fireEvent.click(screen.getByRole("button", { name: /Add Filter/ }));
  fireEvent.click(screen.getByRole("button", { name: "Custom symbols" }));
  fireEvent.change(screen.getByLabelText("NSE symbols"), {
    target: { value: "INFY" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Run Scan" }));
  expect(
    await screen.findByText("No instruments matched the active filters."),
  ).toBeVisible();
  expect(
    screen.queryByText("No instruments could be evaluated."),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Run Evidence" }));
  expect(screen.getByText(/Per-symbol diagnostics/)).toBeVisible();
});

test("filter chips edit conditions and clear all disables execution", async () => {
  mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "RSI (14)" });
  fireEvent.change(screen.getByLabelText("Value"), {
    target: { value: "40" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Add Filter/ }));
  expect(
    screen.getByRole("button", { name: "Remove filter 1" }),
  ).toHaveTextContent("40");
  fireEvent.click(screen.getByRole("button", { name: "Remove filter 1" }));
  expect(
    screen.queryByRole("button", { name: "Remove filter 1" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Clear All" }));
  expect(screen.getByRole("button", { name: "Run Scan" })).toBeDisabled();
});
test("scanner tabs support keyboard navigation", async () => {
  mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "RSI (14)" });
  const tab = screen.getByRole("tab", { name: /Equity \/ Index Scanner/ });
  tab.focus();
  fireEvent.keyDown(tab, { key: "ArrowRight" });
  await waitFor(() =>
    expect(
      screen.getByRole("tab", { name: /Derivatives Scanner/ }),
    ).toHaveAttribute("aria-selected", "true"),
  );
});
test("typed API failure is surfaced instead of inventing a result", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    Response.json({ error: { message: "Dhan unavailable" } }, { status: 503 }),
  );
  await expect(scannerApi("runs", "POST", initialConfig)).rejects.toThrow(
    "Dhan unavailable",
  );
});

test("built-in watchlists share the provider-neutral selector and submit a bounded snapshot selection", async () => {
  const systemId = "11111111-1111-4111-8111-111111111111";
  const customId = "22222222-2222-4222-8222-222222222222";
  const instruments = Array.from({ length: 21 }, (_, index) => ({
    instrument: {
      instrument_id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
      symbol: `SYM${index + 1}`,
      exchange: "NSE",
      segment: "EQUITY",
      instrument_type: "EQUITY",
      native: { namespace: "dhan", native_id: String(index + 1) },
      expiry: null,
      strike: null,
      right: null,
    },
    kind: "EQUITY",
    ordering: index,
    added_at: "2026-10-07T10:00:00Z",
  }));
  const fetch = vi
    .spyOn(global, "fetch")
    .mockImplementation(async (url, init) => {
      const path = String(url);
      if (path.endsWith("/catalog")) return Response.json(catalog);
      if (path.endsWith("/api/v1/watchlists"))
        return Response.json([
          {
            id: customId,
            name: "My Core",
            count: 1,
            archived: false,
            ownership_kind: "USER",
            read_only: false,
            enabled: true,
          },
          {
            id: systemId,
            name: "Nifty Bank",
            count: 21,
            archived: false,
            ownership_kind: "SYSTEM",
            read_only: true,
            enabled: true,
          },
          {
            id: "33333333-3333-4333-8333-333333333333",
            name: "F&O Liquidity 50",
            count: 0,
            archived: false,
            ownership_kind: "SYSTEM",
            read_only: true,
            enabled: false,
          },
        ]);
      if (path.endsWith(`/api/v1/watchlists/${systemId}`))
        return Response.json({
          id: systemId,
          name: "Nifty Bank",
          items: instruments,
        });
      if (path.endsWith("/runs") && init?.method === "POST") {
        const config = JSON.parse(String(init.body));
        return Response.json({
          id: "run-system",
          created_at: "2026-10-07T10:00:00Z",
          config,
          counts: {
            requested: 20,
            resolved: 20,
            evaluated: 20,
            not_evaluated: 0,
            matches: 0,
          },
          rows: [],
        });
      }
      return Response.json([]);
    });

  render(<ScannerWorkspace />);
  fireEvent.click(
    await screen.findByRole("button", { name: /Watchlist: Choose watchlist/ }),
  );
  expect(screen.getByText("My Watchlists")).toBeInTheDocument();
  expect(screen.getByText("Built-in Watchlists")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /F&O Liquidity 50/ }),
  ).toBeDisabled();
  fireEvent.click(
    screen.getByRole("button", {
      name: /Nifty Bank, 21 constituents, built-in read-only/,
    }),
  );
  await screen.findByText(/20 of 21 selected/);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "RSI (14)" });
  fireEvent.click(screen.getByRole("button", { name: /Add Filter/ }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Run Scan" })).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Run Scan" }));
  await screen.findByText(/Scan completed: 0 matches/);
  const call = fetch.mock.calls.find(
    ([url, init]) => String(url).endsWith("/runs") && init?.method === "POST",
  )!;
  const body = JSON.parse(String(call[1]?.body));
  expect(body.universe.source).toBe("WATCHLIST");
  expect(body.universe.watchlist_id).toBe(systemId);
  expect(body.universe.instrument_ids).toHaveLength(20);
});

test("RSI and Market Cap expose bounded literal inputs without technical fields", async () => {
  mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "RSI (14)" });

  fireEvent.change(screen.getByLabelText("Field"), {
    target: { value: "rsi" },
  });
  expect(screen.getByLabelText("Value")).toHaveAttribute("type", "number");
  expect(
    within(screen.getByLabelText("Compare to")).queryByRole("option", {
      name: "Field",
    }),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Value"), {
    target: { value: "50" },
  });

  fireEvent.change(screen.getByLabelText("Field"), {
    target: { value: "market_cap_inr" },
  });
  expect(screen.getByLabelText("Value")).toHaveAttribute("type", "number");
  expect(screen.getByLabelText("Value")).toHaveValue(10000);
  expect(
    within(screen.getByLabelText("Compare to")).queryByRole("option", {
      name: "Field",
    }),
  ).not.toBeInTheDocument();
});

test("price fields offer only compatible price comparisons", async () => {
  mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "Prior 20-day high" });
  fireEvent.change(screen.getByLabelText("Field"), {
    target: { value: "high20" },
  });
  expect(
    within(screen.getByLabelText("Compare to")).getByRole("option", {
      name: "Field",
    }),
  ).toBeVisible();
  fireEvent.change(screen.getByLabelText("Compare to"), {
    target: { value: "field" },
  });
  const comparison = screen.getByLabelText("Comparison field");
  expect(
    within(comparison).getByRole("option", { name: "SMA (20)" }),
  ).toBeVisible();
  expect(
    within(comparison).getByRole("option", { name: "SMA (50)" }),
  ).toBeVisible();
  expect(
    within(comparison).getByRole("option", { name: "EMA (20)" }),
  ).toBeVisible();
  expect(
    within(comparison).queryByRole("option", { name: "RSI (14)" }),
  ).not.toBeInTheDocument();
  expect(
    within(comparison).queryByRole("option", { name: "Market cap (INR)" }),
  ).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Field"), {
    target: { value: "sma20" },
  });
  fireEvent.change(screen.getByLabelText("Compare to"), {
    target: { value: "field" },
  });
  expect(
    within(screen.getByLabelText("Comparison field")).getByRole("option", {
      name: "Completed close",
    }),
  ).toBeVisible();
});

test("enum fields use canonical selectors and typed chips", async () => {
  mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "Supertrend direction (10,3)" });
  fireEvent.change(screen.getByLabelText("Field"), {
    target: { value: "supertrend" },
  });
  expect(screen.getByLabelText("Operator")).toHaveValue("equals");
  expect(
    within(screen.getByLabelText("Operator")).queryByRole("option", {
      name: ">",
    }),
  ).not.toBeInTheDocument();
  expect(
    within(screen.getByLabelText("Operator")).getByRole("option", {
      name: "≠",
    }),
  ).toBeVisible();
  const enumValue = screen.getByLabelText("Value");
  expect(enumValue.tagName).toBe("SELECT");
  expect(within(enumValue).getByRole("option", { name: "Up" })).toBeVisible();
  expect(within(enumValue).getByRole("option", { name: "Down" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /Add Filter/ }));
  expect(
    screen.getByRole("button", { name: "Remove filter 1" }),
  ).toHaveTextContent("Supertrend direction (10,3) = Up");
});

test("field and operator changes clear incompatible right-hand sides", async () => {
  mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "Prior 20-day high" });
  fireEvent.change(screen.getByLabelText("Field"), {
    target: { value: "high20" },
  });
  fireEvent.change(screen.getByLabelText("Compare to"), {
    target: { value: "field" },
  });
  fireEvent.change(screen.getByLabelText("Comparison field"), {
    target: { value: "sma20" },
  });

  fireEvent.change(screen.getByLabelText("Field"), {
    target: { value: "market_cap_inr" },
  });
  expect(screen.getByLabelText("Compare to")).toHaveValue("value");
  expect(screen.queryByLabelText("Comparison field")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Value")).toHaveValue(10000);

  fireEvent.change(screen.getByLabelText("Field"), {
    target: { value: "high20" },
  });
  fireEvent.change(screen.getByLabelText("Compare to"), {
    target: { value: "field" },
  });
  fireEvent.change(screen.getByLabelText("Operator"), {
    target: { value: "between" },
  });
  expect(screen.getByLabelText("Compare to")).toHaveValue("value");
  expect(screen.queryByLabelText("Comparison field")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Lower value")).toHaveAttribute(
    "type",
    "number",
  );
  expect(screen.getByLabelText("Upper value")).toHaveAttribute(
    "type",
    "number",
  );
});

test("field comparison chip names both sides of the expression", async () => {
  mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "Prior 20-day high" });
  fireEvent.change(screen.getByLabelText("Field"), {
    target: { value: "high20" },
  });
  fireEvent.change(screen.getByLabelText("Compare to"), {
    target: { value: "field" },
  });
  fireEvent.change(screen.getByLabelText("Comparison field"), {
    target: { value: "sma20" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Add Filter/ }));
  expect(
    screen.getByRole("button", { name: "Remove filter 1" }),
  ).toHaveTextContent("Prior 20-day high > SMA (20)");
});

test("legacy filters stay readable but cannot execute until corrected", () => {
  const legacy = {
    field: "rsi",
    operator: ">",
    value: "sma20",
    timeframe: "1d" as const,
    version: "1" as const,
    source: "internal" as const,
  };
  expect(filterCompatible(legacy, catalog)).toBe(false);
  expect(filterExpression(legacy, catalog)).toBe("RSI (14) > SMA (20)");
});

test("Market Context defaults to ranking and hard filters use typed enum controls", async () => {
  const fetch = mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("Market Context"));
  expect(
    await screen.findByRole("button", { name: "Ranking" }),
  ).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "Hard filter" }));
  fireEvent.change(screen.getByLabelText("Context field"), {
    target: { value: "vix_state" },
  });
  expect(screen.getByLabelText("Context operator")).toHaveValue("not_equals");
  expect(screen.getByLabelText("Context value")).toHaveValue("HIGH");
  fireEvent.click(
    screen.getByRole("button", { name: "＋ Add Context Filter" }),
  );
  expect(
    screen.getByRole("button", { name: "Remove context filter 1" }),
  ).toHaveTextContent("India VIX state ≠ HIGH");
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "RSI (14)" });
  fireEvent.click(screen.getByRole("button", { name: /Add Filter/ }));
  fireEvent.click(screen.getByRole("button", { name: "Custom symbols" }));
  fireEvent.change(screen.getByLabelText("NSE symbols"), {
    target: { value: "INFY" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Run Scan" }));
  await screen.findByText("No instruments could be evaluated.");
  const call = fetch.mock.calls.find(
    ([url, init]) => String(url).endsWith("/runs") && init?.method === "POST",
  )!;
  const body = JSON.parse(String(call[1]?.body));
  expect(body.context_mode).toBe("HARD_FILTER");
  expect(body.context_filters).toEqual([
    {
      field: "vix_state",
      operator: "not_equals",
      value: "HIGH",
      source: "market_context",
      version: "1",
    },
  ]);
});

test.each(["Up", "Down"] as const)(
  "stored deterministic Reason and %s trend open complete no-LLM Evidence analysis",
  async (trend) => {
    vi.spyOn(global, "fetch").mockImplementation(async (url, init) => {
      const path = String(url);
      if (path.endsWith("/catalog")) return Response.json(catalog);
      if (path.endsWith("/runs") && init?.method === "POST") {
        const config = JSON.parse(String(init.body));
        return Response.json({
          id: "context-run",
          created_at: "2026-10-08T10:00:00Z",
          config,
          data_mode: "REAL",
          market_data_provider: "dhan",
          counts: {
            requested: 1,
            resolved: 1,
            evaluated: 1,
            not_evaluated: 0,
            matches: 1,
          },
          context_snapshot: {
            as_of: "2026-10-08T10:00:00Z",
            provider: "tapetide",
            status: "PARTIAL",
            source_health: "AVAILABLE",
            coverage_count: 2,
            dimension_count: 6,
            missing_dimensions: [
              "broad_regime",
              "sector",
              "breadth",
              "event_news",
            ],
            warnings: [],
            evidence: [],
          },
          rows: [
            {
              symbol: "RELIANCE",
              instrument: {
                instrument_id: "11111111-1111-4111-8111-111111111111",
                symbol: "RELIANCE",
                exchange: "NSE",
                segment: "EQ",
              },
              outcome: "MATCH",
              instrument_metadata: {
                applies_to_symbol: "RELIANCE",
                metadata_symbol: "RELIANCE",
                resolution_basis: "DIRECT",
                sector: "Energy",
                industry: "Oil & Gas Exploration",
                market_cap: 20000000000000,
                market_cap_currency: "INR",
                market_cap_rank: 1,
                market_cap_category: "LARGE",
                twf_cap_tier: "LARGE",
                context_benchmark: "NIFTY OIL & GAS",
                context_benchmark_symbol: "NIFTYOILGAS",
                resolution_status: "RESOLVED",
                present_in_latest_snapshot: true,
                sector_as_of: "2026-10-09",
                industry_as_of: "2026-10-09",
                market_cap_as_of: "2026-10-09",
                dataset_generated_at: "2026-10-09T09:15:00+05:30",
                metadata_updated_at: "2026-10-09T09:20:00+05:30",
              },
              metrics: { change: 1.2, volume: 1000, rsi: 58, trend },
              diagnostics: [
                {
                  filter: config.filters[0],
                  observed: 58,
                  threshold: 30,
                  passed: true,
                  reason: "RSI (14) < 30",
                },
              ],
              analysis: {
                run_id: "context-run",
                candidate_instrument_id: "11111111-1111-4111-8111-111111111111",
                candidate_symbol: "RELIANCE",
                analyzed_at: "2026-10-08T10:00:00Z",
                setup_direction: "BULLISH",
                matched: true,
                technical_match: true,
                technical_evidence: { passed: 1, total: 1, diagnostics: [] },
                technical_score: 80,
                context_mode: "RANKING",
                context_status: "PARTIAL",
                context_coverage: "2/6",
                context_contributions: [
                  {
                    factor: "vix",
                    observed_state: "NORMAL",
                    interpretation: "SUPPORTIVE",
                    contribution: 1,
                    explanation: "India VIX 14",
                    source: "tapetide",
                    freshness: "FRESH",
                  },
                  {
                    factor: "breadth",
                    observed_state: "UNKNOWN",
                    interpretation: "MISSING",
                    contribution: 0,
                    explanation: "Authoritative breadth evidence unavailable",
                    source: null,
                    freshness: "UNAVAILABLE",
                  },
                ],
                supporting_factors: ["India VIX 14"],
                contradicting_factors: ["FII selling pressure"],
                neutral_factors: [],
                missing_evidence: ["breadth"],
                context_adjustment: 1,
                final_relevance: 81,
                context_classification: "MIXED",
                short_reason: "1/1 technical · Context +1 Mixed · Final 81",
                provenance: [
                  {
                    dimension: "vix",
                    state: "NORMAL",
                    detail: "India VIX 14",
                    provider: "tapetide",
                    provider_tool: "get_india_vix",
                    source_time: "2026-10-08T10:00:00Z",
                    received_at: "2026-10-08T10:00:00Z",
                    freshness: "FRESH",
                  },
                ],
                warnings: [],
                context_filter_diagnostics: [],
              },
            },
          ],
        });
      }
      return Response.json([]);
    });
    render(<ScannerWorkspace />);
    await screen.findByText("Context: RANKING");
    expect(document.querySelector(".sc-inspector")).not.toBeInTheDocument();
    expect(document.querySelector(".sc-grid")).not.toHaveClass("has-detail");
    fireEvent.click(screen.getByText("＋ Add / edit filter"));
    await screen.findByRole("option", { name: "RSI (14)" });
    fireEvent.click(screen.getByRole("button", { name: /Add Filter/ }));
    fireEvent.click(screen.getByRole("button", { name: "Custom symbols" }));
    fireEvent.change(screen.getByLabelText("NSE symbols"), {
      target: { value: "RELIANCE" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run Scan" }));
    expect(await screen.findByText("RSI (14) < 30")).toBeVisible();
    expect(screen.getByRole("columnheader", { name: "Reason" })).toBeVisible();
    expect(
      screen.getByLabelText("Technical Indicators active filters"),
    ).toHaveTextContent("1");
    expect(screen.getByRole("button", { name: "Remove filter 1" })).toHaveClass(
      "derivative-predicate-chip",
    );
    expect(screen.getByRole("button", { name: "Clear All" })).toHaveClass(
      "derivative-clear-all",
    );
    const counts = screen.getByLabelText("Scan run counts");
    for (const [label, value] of [
      ["Requested", "1"],
      ["Resolved", "1"],
      ["Evaluated", "1"],
      ["Not evaluated", "0"],
      ["Matches", "1"],
    ]) {
      const card = within(counts)
        .getByText(label)
        .closest(".derivative-count-card");
      expect(card).toHaveTextContent(value);
      expect(card?.querySelector(".derivative-count-icon svg")).not.toBeNull();
    }
    expect(
      within(screen.getByRole("region", { name: /Equity scan results/ }))
        .getByText(trend)
        .closest(".derivative-trend"),
    ).toHaveClass(`derivative-trend-${trend.toLowerCase()}`);
    expect(
      screen.queryByText("1/1 technical · Context +1 Mixed · Final 81"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run Evidence" }));
    const runEvidence = screen.getByLabelText("Scanner contextual panel");
    expect(within(runEvidence).getByText("Data source & mode")).toBeVisible();
    expect(
      within(runEvidence).getByText("Evaluation diagnostics"),
    ).toBeVisible();
    expect(
      within(runEvidence).getByText(/Per-symbol diagnostics/),
    ).toBeVisible();
    fireEvent.click(
      within(runEvidence).getByRole("button", { name: "Close panel" }),
    );
    expect(screen.getByRole("columnheader", { name: "Sector" })).toBeVisible();
    expect(screen.getByText("Energy")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "RELIANCE" }));
    const metadataPanels = await screen.findAllByRole("region", {
      name: "Instrument metadata",
    });
    const metadata = metadataPanels.at(-1)!;
    expect(metadata).toHaveTextContent("Oil & Gas Exploration");
    expect(metadata).toHaveTextContent("₹20 L Cr");
    expect(metadata).toHaveTextContent("NIFTY OIL & GAS");
    fireEvent.click(screen.getByRole("button", { name: "Close panel" }));
    fireEvent.click(screen.getByRole("button", { name: "Why?" }));
    const panels = await screen.findAllByLabelText(
      "Deterministic candidate analysis",
    );
    const panel = panels.at(-1)!;
    expect(panel).toBeVisible();
    expect(within(panel).getByText("Final relevance")).toBeVisible();
    expect(within(panel).getByText("Supporting factors")).toBeVisible();
    expect(within(panel).getByText("Contradictions")).toBeVisible();
    expect(within(panel).getByText("Missing evidence")).toBeVisible();
    fireEvent.click(within(panel).getByText("Provenance and freshness"));
    expect(within(panel).getByText(/get_india_vix/)).toBeVisible();
    expect(document.querySelector(".sc-grid")).toHaveClass("has-detail");
    fireEvent.click(
      within(screen.getByLabelText("Scanner contextual panel")).getByRole(
        "button",
        {
          name: "Clear selection",
        },
      ),
    );
    expect(document.querySelector(".sc-inspector")).not.toBeInTheDocument();
    expect(document.querySelector(".sc-grid")).not.toHaveClass("has-detail");
    expect(screen.getByText("RSI (14) < 30")).toBeInTheDocument();
  },
);

test("derivatives uses the same top selector and only O2-optionable watchlist underlyings", async () => {
  const key = "44444444-4444-4444-8444-444444444444";
  const fetcher = vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const path = String(url);
    if (path.endsWith("/api/v1/watchlists"))
      return Response.json([
        {
          id: key,
          name: "Nifty Pharma",
          count: 20,
          ownership_kind: "SYSTEM",
          read_only: true,
          archived: false,
          enabled: true,
        },
      ]);
    if (path.endsWith(`/api/v1/watchlists/${key}`))
      return Response.json({ id: key, name: "Nifty Pharma", items: [] });
    if (path.endsWith(`/derivatives/watchlists/${key}/optionable`))
      return Response.json({
        watchlist_id: key,
        members: 20,
        optionable: 1,
        symbols: ["SUNPHARMA"],
        max_underlyings: 5,
      });
    if (path.endsWith("/derivatives/catalog"))
      return Response.json({ fields: [], max_underlyings: 5 });
    if (path.endsWith("/catalog")) return Response.json(catalog);
    return Response.json([]);
  });
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByRole("tab", { name: /Derivatives Scanner/ }));
  const trigger = await screen.findByRole("button", {
    name: "Watchlist: Choose watchlist",
  });
  fireEvent.click(trigger);
  fireEvent.click(
    screen.getByRole("button", {
      name: /Nifty Pharma, 20 constituents, built-in read-only/,
    }),
  );
  expect(await screen.findByText(/20 watchlist members/)).toHaveTextContent(
    "1 optionable",
  );
  expect(screen.getByText(/20 watchlist members/)).toHaveTextContent(
    "1 selected",
  );
  expect(
    screen.getByLabelText("Active derivatives scan configuration"),
  ).toHaveTextContent("Nifty Pharma");
  expect(
    screen.queryByRole("combobox", { name: "Watchlist" }),
  ).not.toBeInTheDocument();
  expect(
    fetcher.mock.calls.some(([url]) =>
      String(url).endsWith(`/derivatives/watchlists/${key}/optionable`),
    ),
  ).toBe(true);
});
