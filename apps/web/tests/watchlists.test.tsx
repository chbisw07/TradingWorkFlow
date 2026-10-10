import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
  NewsPanel,
  ReferencePanel,
  WatchlistsWorkspace,
} from "../src/components/watchlists/watchlists-workspace";
import { MarketChart } from "../src/components/watchlists/market-chart";
import { InstrumentMetadataPanel } from "../src/components/instrument-metadata-panel";
import {
  change,
  changeText,
  previousClose,
  periodChange,
  indianVolume,
  indianMarketCap,
  marketCapCategoryText,
  metadataMarketCap,
  metricPercentText,
  groupWatchlistRows,
  GAIN_LOSS_NEUTRAL_BAND_PERCENT,
  WATCHLIST_GROUP_MODE,
} from "../src/lib/watchlists";

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
});
afterEach(() => vi.restoreAllMocks());

test("instrument metadata renders Indian cap, unknowns, stale state and underlying scope", () => {
  const metadata = {
    applies_to_symbol: "NIFTY99DECFUT",
    metadata_symbol: "RELIANCE",
    resolution_basis: "UNDERLYING" as const,
    sector: "Energy",
    industry: "Oil & Gas Exploration",
    market_cap: 20000000000000,
    market_cap_currency: "INR",
    market_cap_rank: 1,
    market_cap_category: "LARGE" as const,
    twf_cap_tier: "LARGE" as const,
    context_benchmark: "NIFTY OIL & GAS",
    context_benchmark_symbol: "NIFTYOILGAS",
    resolution_status: "RESOLVED",
    present_in_latest_snapshot: false,
    sector_as_of: "2026-10-09",
    industry_as_of: "2026-10-09",
    market_cap_as_of: "2026-10-09",
    dataset_generated_at: "2026-10-09T09:15:00+05:30",
    metadata_updated_at: "2026-10-09T09:20:00+05:30",
  };
  const view = render(<InstrumentMetadataPanel metadata={metadata} />);
  const panel = screen.getByRole("region", {
    name: "Underlying instrument metadata",
  });
  expect(panel).toHaveTextContent("Underlying sector");
  expect(panel).toHaveTextContent("Applies to RELIANCE");
  expect(panel).toHaveTextContent("₹20 L Cr");
  expect(panel).toHaveTextContent("Stale metadata");
  expect(panel).toHaveTextContent("Last-known values are retained");
  view.rerender(<InstrumentMetadataPanel metadata={null} />);
  expect(
    screen.getByText(
      "Authoritative metadata is unavailable for this instrument.",
    ),
  ).toBeVisible();
  expect(screen.getAllByText("—").length).toBeGreaterThan(0);
});
test("empty collections, create dialog and unavailable broker remain truthful", async () => {
  const mock = vi
    .spyOn(global, "fetch")
    .mockImplementation(async (_url, init) => {
      if (init?.method === "POST")
        return Response.json({ id: "one", name: "My Core" });
      return Response.json([]);
    });
  render(<WatchlistsWorkspace />);
  await waitFor(() => expect(mock).toHaveBeenCalled());
  expect(
    screen.getByRole("heading", { name: "Watchlists" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", {
      name: /Add from Scanner|Add from Discovery/,
    }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /New Watchlist/ }));
  expect(screen.getByRole("button", { name: "Save watchlist" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "My Core" },
  });
  expect(screen.getByRole("button", { name: "Save watchlist" })).toBeEnabled();
});
test("moving the selected watchlist opens Trash without stale active detail", async () => {
  let archived = false;
  const updatedAt = "2026-10-07T09:00:00Z";
  const core = {
    id: "core",
    name: "My Core",
    description: "",
    favorite: false,
    archived: false,
    ordering: 0,
    revision: 1,
    created_at: updatedAt,
    updated_at: updatedAt,
    count: 0,
  };
  const momentum = {
    ...core,
    id: "momentum",
    name: "Momentum",
    ordering: 1,
  };
  vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const path = String(input);
    if (path.endsWith("/brokers/accounts")) return Response.json([]);
    if (
      path.endsWith("/watchlists") &&
      (!init?.method || init.method === "GET")
    )
      return Response.json(
        archived ? [{ ...core, archived: true }, momentum] : [core, momentum],
      );
    if (path.endsWith("/watchlists/core") && init?.method === "PATCH") {
      archived = true;
      return Response.json({ ...core, archived: true });
    }
    if (path.endsWith("/watchlists/core"))
      return Response.json({ ...core, items: [], notes: [], activity: [] });
    if (path.endsWith("/watchlists/momentum"))
      return Response.json({ ...momentum, items: [], notes: [], activity: [] });
    if (path.endsWith("/quotes"))
      return Response.json({ quotes: [], error: null });
    throw new Error(`Unexpected path: ${path}`);
  });

  render(<WatchlistsWorkspace />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Move My Core to Trash" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Move to Trash" }));

  await screen.findByRole("heading", { name: "Trash" });
  expect(screen.getByLabelText("Select My Core")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Momentum/ })).not.toHaveAttribute(
    "aria-current",
  );
  expect(screen.getByRole("status")).toHaveTextContent(
    "My Core moved to Trash.",
  );
  expect(
    screen.queryByRole("button", { name: "Move My Core to Trash" }),
  ).not.toBeInTheDocument();
});

test("quick-chart fallback is compact and missing market values stay unavailable", () => {
  render(<MarketChart bars={[]} compact />);
  expect(screen.getByLabelText("Quick chart unavailable")).toHaveTextContent(
    "—",
  );
  expect(screen.queryByText("Chart unavailable")).not.toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(change()).toBeNull();
  expect(changeText(change())).toBe("—");
});
test("change percentage keeps sign, neutral zero and sub-cent precision", () => {
  const quote = (
    last_price: string | null,
    previous_close: string | null = "100",
  ) => ({ last_price, previous_close }) as Parameters<typeof change>[0];
  expect(changeText(change(quote("101")))).toBe("+1.00%");
  expect(changeText(change(quote("99")))).toBe("-1.00%");
  expect(changeText(change(quote("100")))).toBe("0.00%");
  expect(changeText(change(quote("100.004")))).toBe("+0.004%");
  expect(changeText(change(quote("100", "0")))).toBe("—");
  expect(changeText(change(quote(null)))).toBe("—");
  expect(changeText(change(quote("not-a-price")))).toBe("—");
});
test("Watchlist market metrics use canonical presentation semantics", () => {
  expect(metricPercentText(2.135)).toBe("2.13%");
  expect(metricPercentText(-1.4)).toBe("-1.40%");
  expect(metricPercentText(null)).toBe("—");
  expect(marketCapCategoryText("LARGE")).toBe("Large");
  expect(marketCapCategoryText(undefined)).toBe("—");
  expect(
    metadataMarketCap({
      market_cap: 1080000000000,
      market_cap_currency: "INR",
    } as never),
  ).toBe("₹1.08 L Cr");
});

type GroupFixture = {
  symbol: string;
  ordering: number;
};
const groupRow = (
  symbol: string,
  ordering: number,
  overrides: Partial<{
    kind: "EQUITY" | "INDEX" | "FUTURE" | "OPTION" | null;
    sector: string | null;
    marketCapCategory: "LARGE" | "MID" | "SMALL" | null;
    trend: string | null;
    oneDayChangePercent: number | null;
  }> = {},
) => ({
  value: { symbol, ordering },
  kind: "kind" in overrides ? overrides.kind! : "EQUITY",
  sector: overrides.sector ?? null,
  marketCapCategory: overrides.marketCapCategory ?? null,
  trend: overrides.trend ?? null,
  oneDayChangePercent: overrides.oneDayChangePercent ?? null,
});
const groupSummary = (
  rows: ReturnType<typeof groupRow>[],
  mode: Parameters<typeof groupWatchlistRows<GroupFixture>>[1],
) =>
  groupWatchlistRows(
    rows,
    mode,
    (left, right) => left.value.ordering - right.value.ordering,
  ).map((group) => [group.label, group.rows.map((row) => row.value.symbol)]);

test("Watchlist grouping uses canonical type order and stable row ordering", () => {
  expect(
    groupSummary(
      [
        groupRow("OPTION", 4, { kind: "OPTION" }),
        groupRow("INDEX", 2, { kind: "INDEX" }),
        groupRow("EQUITY-B", 3),
        groupRow("FUTURE", 1, { kind: "FUTURE" }),
        groupRow("EQUITY-A", 0),
        groupRow("UNKNOWN", 5, { kind: null }),
      ],
      WATCHLIST_GROUP_MODE.TYPE,
    ),
  ).toEqual([
    ["Equity", ["EQUITY-A", "EQUITY-B"]],
    ["Index", ["INDEX"]],
    ["Future", ["FUTURE"]],
    ["Option", ["OPTION"]],
    ["Unknown", ["UNKNOWN"]],
  ]);
});

test("Watchlist grouping uses metadata category, sector and canonical trend", () => {
  const rows = [
    groupRow("UNKNOWN", 4),
    groupRow("ENERGY", 3, {
      sector: "Energy",
      marketCapCategory: "SMALL",
      trend: "Down",
    }),
    groupRow("TECH", 1, {
      sector: "Technology",
      marketCapCategory: "LARGE",
      trend: "Up",
    }),
    groupRow("FINANCE", 2, {
      sector: "Financial Services",
      marketCapCategory: "MID",
      trend: "Sideways",
    }),
  ];
  expect(
    groupSummary(rows, WATCHLIST_GROUP_MODE.SECTOR).map(([name]) => name),
  ).toEqual(["Energy", "Financial Services", "Technology", "Unknown"]);
  expect(
    groupSummary(rows, WATCHLIST_GROUP_MODE.MARKET_CAP_CATEGORY).map(
      ([name]) => name,
    ),
  ).toEqual(["Large", "Mid", "Small", "Unknown"]);
  expect(
    groupSummary(rows, WATCHLIST_GROUP_MODE.TREND).map(([name]) => name),
  ).toEqual(["Up", "Sideways", "Down", "Unknown"]);
});

test("Gainers and losers use the inclusive plus/minus 0.50 neutral band", () => {
  expect(GAIN_LOSS_NEUTRAL_BAND_PERCENT).toBe(0.5);
  const changes = [10, 0.51, 0.5, 0.49, 0, -0.49, -0.5, -0.51, -10, null];
  const groups = groupWatchlistRows(
    changes.map((value, ordering) =>
      groupRow(value == null ? "NULL" : String(value), ordering, {
        oneDayChangePercent: value,
      }),
    ),
    WATCHLIST_GROUP_MODE.GAIN_LOSS,
  );
  expect(groups.map((group) => [group.label, group.rows.length])).toEqual([
    ["Gainers", 2],
    ["Flat", 5],
    ["Losers", 2],
    ["Unavailable", 1],
  ]);
  expect(groups[1].rows.map((row) => row.value.symbol)).toEqual([
    "0.5",
    "0.49",
    "0",
    "-0.49",
    "-0.5",
  ]);
});

test("search and filters precede grouping and hidden columns are irrelevant", () => {
  const rows = [
    groupRow("RELIANCE", 0, {
      sector: "Energy",
      marketCapCategory: "LARGE",
    }),
    groupRow("ONGC", 1, {
      sector: "Energy",
      marketCapCategory: "LARGE",
    }),
    groupRow("INFY", 2, {
      sector: "Technology",
      marketCapCategory: "LARGE",
    }),
  ];
  const matching = rows.filter((row) => row.value.symbol.includes("ON"));
  expect(groupSummary(matching, WATCHLIST_GROUP_MODE.SECTOR)).toEqual([
    ["Energy", ["ONGC"]],
  ]);
  expect(
    groupSummary(matching, WATCHLIST_GROUP_MODE.MARKET_CAP_CATEGORY),
  ).toEqual([["Large", ["ONGC"]]]);
});

test("symbol search clears by button or Escape without resetting table state", async () => {
  const at = "2026-10-09T09:00:00Z";
  const list = {
    id: "core",
    name: "My Core",
    description: "",
    favorite: false,
    archived: false,
    count: 3,
    updated_at: at,
    revision: 1,
    ownership_kind: "USER",
    read_only: false,
    system_code: null,
    enabled: true,
    availability: "READY",
    pending_reason: null,
    expected_count: null,
    instrument_type_summary: ["EQUITY"],
    source_reference: null,
    source_received_at: null,
    freshness: "CURRENT",
  };
  const definitions = [
    ["RELIANCE", "Energy", 1],
    ["INFY", "Technology", 2],
    ["HDFCBANK", "Financial Services", -1],
  ] as const;
  const items = definitions.map(([symbol, sector], ordering) => ({
    instrument: {
      instrument_id: symbol.toLowerCase(),
      symbol,
      exchange: "NSE",
      segment: "EQUITY",
      instrument_type: "EQUITY",
      native: { namespace: "dhan", native_id: symbol },
    },
    kind: "EQUITY",
    ordering,
    added_at: at,
    instrument_metadata: {
      sector,
      market_cap: 1_000_000_000_000,
      market_cap_currency: "INR",
      market_cap_category: "LARGE",
    },
  }));
  vi.spyOn(global, "fetch").mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith("/brokers/accounts")) return Response.json([]);
    if (path.endsWith("/watchlists")) return Response.json([list]);
    if (path.endsWith("/watchlists/core"))
      return Response.json({ ...list, items, notes: [], activity: [] });
    if (path.endsWith("/quotes"))
      return Response.json({
        error: null,
        quotes: items.map((item, index) => ({
          instrument: item.instrument,
          last_price: String(100 + index),
          previous_close: "100",
          change_percent: definitions[index][2],
          open: "100",
          high: "105",
          low: "95",
          volume: "1000",
          provider: "dhan",
          received_at: at,
          provider_source_time: at,
        })),
      });
    if (path.includes("/chart?"))
      return Response.json({
        provider: "dhan",
        interval: "1d",
        bars: [],
        metrics: null,
        error: null,
      });
    throw new Error(`Unexpected path: ${path}`);
  });

  render(<WatchlistsWorkspace />);
  const search = await screen.findByLabelText("Search symbols in this list");
  await screen.findByRole("button", { name: /^RELIANCE$/ });
  expect(
    screen.queryByRole("button", { name: "Clear search" }),
  ).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Group by"), {
    target: { value: "SECTOR" },
  });
  fireEvent.click(screen.getByText("Columns", { selector: "summary" }));
  fireEvent.click(screen.getByLabelText("Market Cap"));
  fireEvent.click(screen.getByText("Filters", { selector: "summary" }));
  const positive = screen.getByLabelText("Positive change only");
  fireEvent.click(positive);
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: /^HDFCBANK$/ }),
    ).not.toBeInTheDocument(),
  );

  fireEvent.change(search, { target: { value: "INF" } });
  expect(
    screen.queryByRole("button", { name: /^RELIANCE$/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /^Technology \(1\)$/ }),
  ).toBeVisible();
  const clear = screen.getByRole("button", { name: "Clear search" });
  expect(clear).toHaveAttribute("type", "button");
  fireEvent.click(clear);

  expect(search).toHaveValue("");
  expect(search).toHaveFocus();
  expect(screen.getByLabelText("Group by")).toHaveValue("SECTOR");
  expect(positive).toBeChecked();
  expect(
    screen.queryByRole("columnheader", { name: "Market Cap" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^Energy \(1\)$/ })).toBeVisible();
  expect(
    screen.getByRole("button", { name: /^Technology \(1\)$/ }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: /^HDFCBANK$/ }),
  ).not.toBeInTheDocument();

  fireEvent.change(search, { target: { value: "INF" } });
  search.focus();
  fireEvent.keyDown(search, { key: "Escape" });
  expect(search).toHaveValue("");
  expect(search).toHaveFocus();
  expect(
    screen.queryByRole("button", { name: "Clear search" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^RELIANCE$/ })).toBeVisible();
});
test("normalized bars render an accessible provider-attributed chart", () => {
  render(
    <MarketChart
      bars={[
        {
          timestamp: "2026-10-01T00:00:00Z",
          open: 10,
          high: 12,
          low: 9,
          close: 11,
          volume: 100,
        },
        {
          timestamp: "2026-10-02T00:00:00Z",
          open: 11,
          high: 14,
          low: 10,
          close: 13,
          volume: 150,
        },
      ]}
    />,
  );
  expect(
    screen.getByRole("img", { name: "Price chart, 2 completed bars" }),
  ).toBeInTheDocument();
});

const newsClaim = (overrides: Record<string, unknown> = {}) => ({
  kind: "NEWS_SENTIMENT",
  subject: "INDIA_MARKET",
  scope: "MARKET",
  values: { record_count: 1, latest_headline: "Markets open higher" },
  provider: "tapetide",
  provider_tool: "get_market_news",
  source_time: "2026-10-06T09:00:00Z",
  received_at: "2026-10-06T09:01:00Z",
  freshness: "CURRENT",
  ...overrides,
});

test("news keeps symbol stories first and market claims in a separate section", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    Response.json({
      provider: "tapetide",
      state: "AVAILABLE",
      failures: [],
      received_at: "2026-10-06T09:01:00Z",
      claims: [
        newsClaim({
          kind: "CORPORATE_EVENT",
          subject: "HDFCBANK",
          scope: "INSTRUMENT",
          provider_tool: "get_stock_events",
          values: {
            record_count: 1,
            symbol: "HDFCBANK",
            event_type: "Earnings",
            event_date: "2026-10-10",
          },
        }),
        newsClaim({
          kind: "NEWS_SENTIMENT",
          subject: "BANKING",
          scope: "SECTOR",
          values: {
            record_count: 1,
            latest_headline: "Banks rally on fresh flows",
          },
        }),
        newsClaim(),
      ],
    }),
  );
  render(<NewsPanel listId="core" instrumentId="hdfc-id" symbol="HDFCBANK" />);
  const company = await screen.findByRole("region", {
    name: "HDFCBANK company and symbol news",
  });
  const sector = await screen.findByRole("region", {
    name: "Related sector context",
  });
  const market = await screen.findByRole("region", {
    name: "Market-wide context",
  });
  expect(sector).toHaveTextContent("Sector");
  await waitFor(() =>
    expect(company).toHaveTextContent("No recent HDFCBANK-specific news."),
  );
  expect(company).not.toHaveTextContent("Earnings");
  const events = screen.getByRole("region", { name: "Corporate events" });
  expect(events).toHaveTextContent("Earnings · 2026-10-10");
  expect(events).toHaveTextContent("TapTide · Corporate event · instrument");
  expect(market).toHaveTextContent("Markets open higher");
  expect(market).toHaveTextContent("India market");
  expect(
    company.compareDocumentPosition(market) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(document.body).not.toHaveTextContent("latest_headline");
});
test("market-only news does not masquerade as selected-symbol news", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    Response.json({ claims: [newsClaim()], state: "AVAILABLE" }),
  );
  render(<NewsPanel listId="core" instrumentId="hdfc-id" symbol="HDFCBANK" />);
  const company = await screen.findByRole("region", {
    name: "HDFCBANK company and symbol news",
  });
  await waitFor(() =>
    expect(company).toHaveTextContent("No recent HDFCBANK-specific news."),
  );
  expect(company).not.toHaveTextContent("Markets open higher");
  expect(
    await screen.findByRole("region", { name: "Market-wide context" }),
  ).toHaveTextContent("Markets open higher");
});
test("news distinguishes provider authorization failure from no symbol stories", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    Response.json({
      claims: [],
      state: "AUTH_REQUIRED",
      failures: ["auth-required"],
    }),
  );
  render(<NewsPanel listId="core" instrumentId="hdfc-id" symbol="HDFCBANK" />);
  expect(
    await screen.findByText(
      "Symbol-specific news is unavailable from TapTide.",
    ),
  ).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent(
    "TapTide authorization is required.",
  );
});

test.each([
  ["RATE_LIMITED", "TapTide is rate limited. Try again later."],
  ["UNAVAILABLE", "TapTide news is unavailable."],
  ["PROVIDER_ERROR", "TapTide news is unavailable."],
])(
  "news exposes %s provider state without raw provider errors",
  async (state, message) => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      Response.json({ claims: [], state, failures: ["provider-error"] }),
    );
    render(
      <NewsPanel listId="core" instrumentId="hdfc-id" symbol="HDFCBANK" />,
    );
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(
      screen.getByText("Symbol-specific news is unavailable from TapTide."),
    ).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("provider-error");
  },
);

test("change prefers normalized percent and dated prior-session history, never quote-day close", () => {
  const quote = {
    last_price: "1218",
    previous_close: null,
    provider_source_time: "2026-10-06T15:59:59+05:30",
  } as Parameters<typeof change>[0];
  const bars = [
    { timestamp: "2026-10-04T18:30:00Z", close: 1186.4 },
    { timestamp: "2026-10-05T18:30:00Z", close: 1218 },
  ] as Parameters<typeof previousClose>[1];
  expect(previousClose(quote, bars)).toBe(1186.4);
  expect(changeText(change(quote, bars))).toBe("+2.66%");
  expect(change({ ...quote!, change_percent: -1.25 }, bars)).toBe(-1.25);
  expect(change({ ...quote!, change_percent: 0 }, bars)).toBe(0);
  expect(change({ ...quote!, last_price: "1186.4" }, bars)).toBe(0);
  expect(change({ ...quote!, last_price: null }, bars)).toBeNull();
  expect(change({ ...quote!, provider_source_time: null }, bars)).toBeNull();
  expect(change(quote, [])).toBeNull();
  expect(
    change(quote, [{ ...bars![0], timestamp: "2026-09-01T00:00:00Z" }]),
  ).toBeNull();
});
test("metadata-only stock event is neither a headline nor an event card", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    Response.json({
      state: "AVAILABLE",
      claims: [
        newsClaim({
          kind: "CORPORATE_EVENT",
          scope: "INSTRUMENT",
          subject: "RELIANCE",
          values: { symbol: "RELIANCE", record_count: 1 },
        }),
      ],
    }),
  );
  render(<NewsPanel listId="core" instrumentId="r" symbol="RELIANCE" />);
  expect(
    await screen.findByText("No recent RELIANCE-specific news."),
  ).toBeInTheDocument();
  expect(
    screen.getByText("No recent RELIANCE-specific corporate events available."),
  ).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent("No headline details");
  expect(
    screen.queryByRole("region", { name: "Related sector context" }),
  ).not.toBeInTheDocument();
});

test("visible rows hydrate serially without selection and detail reuses history", async () => {
  const list = {
    id: "core",
    name: "My Core",
    description: "",
    favorite: false,
    archived: false,
    count: 12,
    updated_at: "2026-10-06T12:00:00Z",
    revision: 1,
  };
  const items = Array.from({ length: 12 }, (_, i) => ({
    instrument: {
      instrument_id: `id-${i}`,
      symbol: `SYMBOL${i}`,
      exchange: "NSE",
      segment: "EQUITY",
      instrument_type: "EQUITY",
      native: { namespace: "dhan", native_id: `NSE_EQ:${i}` },
    },
    kind: "EQUITY",
    ordering: i,
    added_at: list.updated_at,
    instrument_metadata: {
      market_cap: 1080000000000,
      market_cap_currency: "INR",
      market_cap_category: "LARGE",
    },
  }));
  let calls = 0,
    active = 0,
    maxActive = 0;
  vi.spyOn(global, "fetch").mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith("/brokers/accounts")) return Response.json([]);
    if (path.endsWith("/watchlists")) return Response.json([list]);
    if (path.endsWith("/core"))
      return Response.json({ ...list, items, notes: [], activity: [] });
    if (path.endsWith("/quotes"))
      return Response.json({ quotes: [], error: null });
    if (path.endsWith("/reference"))
      return Response.json({
        state: "NOT_AVAILABLE",
        provider: "tapetide",
        tool: "get_stock_quote",
        received_at: list.updated_at,
        freshness: "UNAVAILABLE",
      });
    if (path.includes("/chart?")) {
      calls++;
      active++;
      maxActive = Math.max(active, maxActive);
      await new Promise((resolve) => setTimeout(resolve, 2));
      active--;
      return Response.json({
        provider: "dhan",
        error: null,
        interval: "1d",
        metrics: {
          rsi14: 60,
          trend: "Up",
          average_volume20: 1000,
          atr14: 2.5,
          atr_percent: 2.25,
          high_52w: 150,
          low_52w: 80,
          high_52w_distance_percent: 5,
          low_52w_distance_percent: 78.13,
          history_coverage_sessions: 252,
          basis: "Daily",
          as_of: list.updated_at,
        },
        bars: Array.from({ length: 22 }, (_, i) => ({
          timestamp: `2026-09-${String(i + 1).padStart(2, "0")}T00:00:00Z`,
          open: 100 + i,
          high: 102 + i,
          low: 99 + i,
          close: 101 + i,
          volume: 1000,
        })),
      });
    }
    throw new Error("Unexpected path");
  });
  const first = render(<WatchlistsWorkspace />);
  await waitFor(
    () =>
      expect(
        screen.getAllByRole("img", { name: "Quick chart, 22 completed bars" }),
      ).toHaveLength(10),
    { timeout: 5000 },
  );
  expect(calls).toBe(10);
  expect(maxActive).toBe(1);
  for (const header of [
    "Market Cap Category",
    "Market Cap",
    "ATR %",
    "52W High Distance",
    "52W Low Distance",
  ])
    expect(
      screen.getByRole("columnheader", { name: header }),
    ).toBeInTheDocument();
  const marketCapChoice = screen.getByLabelText("Market Cap");
  expect(marketCapChoice).toBeChecked();
  fireEvent.click(marketCapChoice);
  expect(
    screen.queryByRole("columnheader", { name: "Market Cap" }),
  ).not.toBeInTheDocument();
  fireEvent.click(marketCapChoice);
  expect(screen.getAllByText("₹1.08 L Cr").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Large").length).toBeGreaterThan(0);
  expect(screen.getAllByText("2.25%").length).toBeGreaterThan(0);
  expect(
    screen.queryByRole("img", { name: /^Price chart/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByLabelText("Selected instrument"),
  ).not.toBeInTheDocument();
  expect(document.querySelector(".wl-layout")).not.toHaveClass("has-detail");
  fireEvent.click(screen.getByRole("button", { name: "SYMBOL0" }));
  await screen.findByRole("img", { name: /^Price chart/ });
  expect(
    screen.queryByRole("tab", { name: /^Chart$/ }),
  ).not.toBeInTheDocument();
  expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
    "Overview",
    "Option Chain",
    "News",
  ]);
  expect(screen.getByRole("tabpanel", { name: "Overview" })).toBeVisible();
  fireEvent.keyDown(screen.getByRole("tab", { name: "Overview" }), {
    key: "ArrowRight",
  });
  expect(screen.getByRole("tab", { name: "Option Chain" })).toHaveFocus();
  expect(screen.getByText("Option chain coming later")).toBeVisible();
  fireEvent.keyDown(screen.getByRole("tab", { name: "Option Chain" }), {
    key: "Home",
  });
  expect(screen.getByRole("img", { name: /^Price chart/ })).toBeVisible();
  expect(screen.getByText("Data details")).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  expect(calls).toBe(10);
  fireEvent.click(screen.getByLabelText("Next page"));
  await waitFor(() =>
    expect(
      screen.getAllByRole("img", { name: "Quick chart, 22 completed bars" }),
    ).toHaveLength(2),
  );
  expect(calls).toBe(12);
  fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
  expect(
    screen.queryByRole("dialog", { name: "SYMBOL0 details" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByLabelText("Selected instrument"),
  ).not.toBeInTheDocument();
  expect(document.querySelector(".wl-layout")).not.toHaveClass("has-detail");
  expect(screen.getByRole("button", { name: "All 12" })).toBeInTheDocument();
  first.unmount();
  render(<WatchlistsWorkspace />);
  await waitFor(
    () =>
      expect(
        screen.getAllByRole("img", { name: "Quick chart, 22 completed bars" }),
      ).toHaveLength(10),
    { timeout: 5000 },
  );
  expect(calls).toBe(22);
});

test.each(["1W", "1M", "3M", "1Y"])(
  "%s return uses the actual first/last completed daily close, independent of row 1D",
  (period) => {
    const quote = { last_price: "150", previous_close: "100" } as Parameters<
      typeof change
    >[0];
    const bars = [
      { timestamp: "2026-09-01T00:00:00Z", close: 100 },
      { timestamp: "2026-09-30T00:00:00Z", close: 110 },
    ] as Parameters<typeof previousClose>[1];
    const chart = {
      interval: "1d",
      provider: "dhan",
      bars: bars!,
      error: null,
    };
    const result = periodChange(period, quote, chart);
    expect(result.value).toBeCloseTo(10);
    expect(result.startTime).toBe(bars![0].timestamp);
    expect(result.end).toBe(110);
    expect(change(quote)).toBe(50);
    expect(periodChange(period, quote, null).value).toBeNull();
    expect(
      periodChange(period, quote, { ...chart, bars: bars!.slice(0, 1) }).value,
    ).toBeNull();
  },
);
test("1D detail retains previous-session comparison and missing data stays unavailable", () => {
  const quote = { last_price: "99", previous_close: "100" } as Parameters<
    typeof change
  >[0];
  expect(periodChange("1D", quote, null).value).toBe(-1);
  expect(periodChange("1D", undefined, null).value).toBeNull();
});
test("reference metrics retain units, provenance and individual unavailable fields", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    Response.json({
      symbol: "RELIANCE",
      provider: "tapetide",
      tool: "get_stock_quote",
      state: "PARTIAL",
      market_cap_inr: "16482632200000",
      pe_ratio: "22.06",
      high_52_week: "1611.8",
      low_52_week: null,
      received_at: "2026-10-06T15:00:00Z",
      source_time: "2026-10-06T10:30:00Z",
      freshness: "CURRENT",
    }),
  );
  render(<ReferencePanel listId="core" instrumentId="r" />);
  expect(await screen.findByText("₹16.48 L Cr")).toBeInTheDocument();
  expect(screen.getByText("22.06")).toBeInTheDocument();
  expect(screen.getByText("1,611.8")).toBeInTheDocument();
  expect(screen.getByText("—")).toHaveAttribute(
    "title",
    "Data unavailable from configured providers",
  );
  const disclosure = screen.getByText("Data details");
  expect(disclosure).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByText(/Reference data · TapTide/)).not.toBeVisible();
  fireEvent.click(disclosure);
  await waitFor(() =>
    expect(disclosure).toHaveAttribute("aria-expanded", "true"),
  );
  expect(screen.getByText(/Reference data · TapTide/)).toBeVisible();
  expect(document.querySelector(".wl-data-details")).toHaveTextContent(
    "get stock quote",
  );
  expect(document.querySelector(".wl-data-details")).toHaveTextContent(
    "PARTIAL",
  );
  expect(screen.getByRole("status")).toHaveTextContent(
    "TapTide returned only some reference values",
  );
});
test("reference transport failure stays unavailable without raw errors", async () => {
  vi.spyOn(global, "fetch").mockRejectedValue(new Error("raw upstream error"));
  render(<ReferencePanel listId="core" instrumentId="r" />);
  await waitFor(() =>
    expect(document.querySelector(".wl-data-details")).toHaveTextContent(
      "UNAVAILABLE",
    ),
  );
  expect(screen.getAllByText("—")).toHaveLength(4);
  expect(screen.getByRole("status")).toHaveTextContent(
    "TapTide reference data is temporarily unavailable",
  );
  expect(
    screen.getByRole("link", { name: "TapTide connection" }),
  ).toHaveAttribute("href", "/settings#integrations");
  expect(screen.getByRole("status")).toHaveTextContent(
    "This does not affect Dhan market data or imported instrument metadata",
  );
  expect(document.body).not.toHaveTextContent("raw upstream error");
});

test.each([
  [999, "999"],
  [1500, "1.50 K"],
  [8252213, "82.52 L"],
  [18003127, "1.80 Cr"],
  [0, "0"],
  [null, "—"],
  [-1, "—"],
  ["bad", "—"],
])("volume %s has explicit Indian count units", (input, expected) => {
  expect(indianVolume(input)).toBe(expected);
});
test.each([
  [85400000000, "₹8,540 Cr"],
  [1240000000000, "₹1.24 L Cr"],
  [16482632200000, "₹16.48 L Cr"],
  [null, "—"],
  ["", "—"],
  [0, "—"],
])("normalized INR market cap %s is formatted once", (input, expected) => {
  expect(indianMarketCap(input)).toBe(expected);
});

test("built-in watchlists are grouped, read-only and copy into custom lists", async () => {
  const at = "2026-10-07T09:00:00Z";
  const custom = {
    id: "00000000-0000-0000-0000-000000000001",
    name: "My Core",
    description: "",
    favorite: false,
    archived: false,
    count: 0,
    updated_at: at,
    revision: 1,
    ownership_kind: "USER",
    read_only: false,
    system_code: null,
    enabled: true,
    availability: "READY",
    pending_reason: null,
    expected_count: null,
    instrument_type_summary: [],
    source_reference: null,
    source_received_at: null,
    freshness: "CURRENT",
  };
  const system = {
    ...custom,
    id: "00000000-0000-0000-0000-000000000002",
    name: "Nifty Bank",
    description: "Official bank index constituents.",
    count: 1,
    updated_at: null,
    revision: 2,
    ownership_kind: "SYSTEM",
    read_only: true,
    system_code: "NIFTY_BANK",
    expected_count: 14,
    instrument_type_summary: [],
    source_reference:
      "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-bank",
    source_received_at: at,
    freshness: "CURRENT",
  };
  const pending = {
    ...system,
    id: "00000000-0000-0000-0000-000000000003",
    name: "F&O 50",
    system_code: "FNO_50",
    enabled: false,
    availability: "DEFINITION_PENDING",
    pending_reason: "Definition pending",
    count: 50,
  };
  const reliance = {
    instrument: {
      instrument_id: "00000000-0000-0000-0000-000000000010",
      symbol: "RELIANCE",
      exchange: "NSE",
      segment: "EQ",
      instrument_type: "EQUITY",
      native: { namespace: "dhan", native_id: "1" },
      expiry: null,
      strike: null,
      right: null,
    },
    kind: "EQUITY",
    ordering: 0,
    added_at: at,
  };
  const calls: { path: string; method: string; body?: unknown }[] = [];
  vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const path = String(input);
    const method = init?.method || "GET";
    calls.push({
      path,
      method,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    if (path.endsWith("/brokers/accounts")) return Response.json([]);
    if (path.endsWith("/watchlists"))
      return Response.json([custom, system, pending]);
    if (path.endsWith("/watchlists/" + custom.id))
      return Response.json({ ...custom, items: [], notes: [], activity: [] });
    if (path.endsWith("/watchlists/" + system.id))
      return Response.json({
        ...system,
        instrument_type_summary: ["EQUITY"],
        items: [reliance],
        notes: [],
        activity: [],
      });
    if (path.endsWith("/quotes"))
      return Response.json({ quotes: [], error: null });
    if (path.endsWith("/copy") && method === "POST")
      return Response.json({ added: 1, duplicates: 0 });
    if (path.includes("/chart"))
      return Response.json({ provider: "dhan", bars: [], error: null });
    throw new Error("Unexpected path: " + path);
  });

  render(<WatchlistsWorkspace />);
  expect(
    await screen.findByRole("heading", { name: "Built-in Watchlists" }),
  ).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: /F&O 50/ })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: /Nifty Bank/ }));
  expect(
    await screen.findByRole("heading", { name: /Nifty Bank/ }),
  ).toBeInTheDocument();
  expect(screen.getAllByText("Built-in").length).toBeGreaterThan(0);
  expect(screen.getAllByText("EQ").length).toBeGreaterThan(0);
  expect(screen.getByRole("button", { name: /Import/ })).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: /Move Nifty Bank to Trash/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Add Symbols" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Watchlist note")).not.toBeInTheDocument();

  fireEvent.click(
    await screen.findByRole("checkbox", { name: "Select RELIANCE" }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Add Selected to Watchlist" }),
  );
  fireEvent.change(screen.getByLabelText("Copy destination"), {
    target: { value: custom.id },
  });
  fireEvent.click(screen.getByRole("button", { name: "Add selected" }));
  await waitFor(() =>
    expect(
      calls.some(
        (call) =>
          call.path.endsWith("/" + system.id + "/copy") &&
          call.method === "POST" &&
          JSON.stringify(call.body).includes(custom.id),
      ),
    ).toBe(true),
  );
});
