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

const catalog = {
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
  templates: [{ name: "RSI Oversold", filters: initialConfig.filters }],
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
test("fresh Scanner UI separates derivatives and gates unsupported capabilities", async () => {
  mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "PE ratio" });
  expect(screen.getByRole("option", { name: "PE ratio" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Index" }));
  expect(screen.getByText("No verified constituent source")).toBeVisible();
  expect(screen.getByRole("button", { name: "Run Scan" })).toBeDisabled();
  fireEvent.click(screen.getByRole("tab", { name: /Derivatives Scanner/ }));
  expect(
    screen.getByText(/Derivative analytics are not available/),
  ).toBeVisible();
  expect(
    screen.queryByText("Candidates requiring review"),
  ).not.toBeInTheDocument();
});
test("explicit real Dhan payload and acquisition failures never become no-match", async () => {
  const fetch = mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "RSI (14)" });
  fireEvent.change(screen.getByLabelText("NSE symbols"), {
    target: { value: "INFY" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Run Scan" }));
  await screen.findByText(/Some instruments could not be evaluated/);
  const call = fetch.mock.calls.find(
    ([url, init]) => String(url).endsWith("/runs") && init?.method === "POST",
  )!;
  const body = JSON.parse(String(call[1]?.body));
  expect(body.data_mode).toBe("REAL");
  expect(body.provider).toBe("dhan");
  expect(body.universe.symbols).toEqual(["INFY"]);
  expect(body.filters[0]).toEqual(initialConfig.filters[0]);
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
    screen.getByRole("button", { name: "Remove filter 2" }),
  ).toHaveTextContent("40");
  fireEvent.click(screen.getByRole("button", { name: "Remove filter 1" }));
  expect(
    screen.queryByRole("button", { name: "Remove filter 2" }),
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
            name: "F&O 50",
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
  fireEvent.click(await screen.findByRole("button", { name: "Watchlist" }));
  const selector = screen.getByLabelText("Watchlist");
  expect(
    screen.getByRole("group", { name: "My Watchlists" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("group", { name: "Built-in Watchlists" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("option", { name: /F&O 50/ }),
  ).not.toBeInTheDocument();
  fireEvent.change(selector, { target: { value: systemId } });
  await screen.findByLabelText(/SYM21/);
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
    screen.getByRole("button", { name: "Remove filter 2" }),
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
    screen.getByRole("button", { name: "Remove filter 2" }),
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
