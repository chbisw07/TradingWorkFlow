import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
  NewsPanel,
  ReferencePanel,
  WatchlistsWorkspace,
} from "../src/components/watchlists/watchlists-workspace";
import { MarketChart } from "../src/components/watchlists/market-chart";
import {
  change,
  changeText,
  previousClose,
  periodChange,
  indianVolume,
  indianMarketCap,
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
  expect(
    screen.queryByRole("img", { name: /^Price chart/ }),
  ).not.toBeInTheDocument();
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
