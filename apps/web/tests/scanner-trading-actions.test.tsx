import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ScannerWorkspace } from "../src/components/scanner/scanner-workspace";
import type { Account, Instrument } from "../src/lib/brokers";

vi.mock("../src/components/brokers/order-ticket", () => ({
  OrderTicket: ({
    account,
    initial,
    close,
  }: {
    account: Account;
    initial: { instrument: Instrument; side: string };
    close: () => void;
  }) => (
    <div role="dialog" aria-label="Broker V2 ticket">
      <span>
        {account.name} · {initial.instrument.reference} · {initial.side}
      </span>
      <button onClick={close}>Close ticket</button>
    </div>
  ),
}));

const equityId = "11111111-1111-4111-8111-111111111111";
const account = {
  id: "44444444-4444-4444-8444-444444444444",
  provider: "zerodha",
  name: "Primary Equity",
  identity: "owner",
  state: "connected",
  health: "healthy",
  generation: 2,
  updated_at: "2026-10-11T09:00:00Z",
  last_read_at: null,
};
const brokerInstrument = {
  symbol: "RELIANCE",
  exchange: "NSE",
  reference: "ZERODHA:NSE:RELIANCE",
  native_token: "738561",
  kind: "EQ",
  segment: "NSE",
  lot_size: "1",
  tick_size: "0.05",
};
const catalog = {
  fields: [
    {
      field: "rsi",
      category: "Technical Indicators",
      label: "RSI (14)",
      enabled: true,
      field_type: "NUMBER",
      operators: ["<", ">"],
      default_operator: "<",
      default_value: 30,
      comparison_fields: [],
      enum_values: [],
      minimum: 0,
      maximum: 100,
      minimum_exclusive: false,
      unit: null,
    },
  ],
  context_fields: [],
  templates: [],
  universes: { CUSTOM: true, WATCHLIST: true, INDEX: false },
};
const rows = [
  {
    symbol: "RELIANCE",
    outcome: "MATCH",
    instrument: {
      instrument_id: equityId,
      symbol: "RELIANCE",
      exchange: "NSE",
      segment: "EQ",
      instrument_type: "EQUITY",
    },
    metrics: { rsi: 24, change: 1, volume: 1000 },
  },
  {
    symbol: "NIFTY",
    outcome: "MATCH",
    instrument: {
      instrument_id: "22222222-2222-4222-8222-222222222222",
      symbol: "NIFTY",
      exchange: "NSE",
      segment: "INDEX",
      instrument_type: "INDEX",
    },
    metrics: { rsi: 24 },
  },
  { symbol: "UNRESOLVED", outcome: "MATCH", metrics: { rsi: 24 } },
];
function mockApi(connected = true, multiple = false) {
  return vi.spyOn(global, "fetch").mockImplementation(async (url, init) => {
    const path = String(url);
    if (path.endsWith("/api/v1/scanner/catalog")) return Response.json(catalog);
    if (path.endsWith("/api/v1/watchlists")) return Response.json([]);
    if (path.endsWith("/api/v1/scanner/saved")) return Response.json([]);
    if (path.endsWith("/api/v1/brokers/accounts"))
      return Response.json(
        connected
          ? multiple
            ? [
                account,
                {
                  ...account,
                  id: "66666666-6666-4666-8666-666666666666",
                  name: "Alternate Equity",
                },
              ]
            : [account]
          : [],
      );
    if (path.includes("/order-entry/capabilities"))
      return Response.json({
        enabled: true,
        broker: { supports_equity: true },
      });
    if (path.endsWith("/api/v1/scanner/runs") && init?.method === "POST") {
      const config = JSON.parse(String(init.body));
      return Response.json({
        id: "55555555-5555-4555-8555-555555555555",
        created_at: "2026-10-11T09:00:00Z",
        config,
        data_mode: "REAL",
        market_data_provider: "dhan",
        counts: {
          requested: 3,
          resolved: 2,
          evaluated: 2,
          not_evaluated: 1,
          matches: 3,
        },
        rows,
      });
    }
    if (path.endsWith("/api/v1/scanner/runs")) return Response.json([]);
    if (path.includes("/broker-instrument?"))
      return Response.json(brokerInstrument);
    throw new Error(`Unexpected request: ${path}`);
  });
}
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
});
afterEach(() => vi.restoreAllMocks());
async function runScan() {
  render(<ScannerWorkspace />);
  await screen.findByRole("option", { name: "RSI (14)" });
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  fireEvent.click(screen.getByRole("button", { name: /Add Filter/ }));
  fireEvent.click(screen.getByRole("button", { name: "Custom symbols" }));
  fireEvent.change(screen.getByLabelText("NSE symbols"), {
    target: { value: "RELIANCE,NIFTY,UNRESOLVED" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Run Scan" }));
  await screen.findByRole("button", { name: "Buy RELIANCE" });
}

test("equity Buy and Sell launch exact Broker V2 ticket without dispatch and preserve scan state", async () => {
  const fetch = mockApi();
  await runScan();
  const row = screen
    .getByRole("button", { name: "Buy RELIANCE" })
    .closest("tr")!;
  await waitFor(() =>
    expect(
      within(row).getByRole("button", { name: "Buy RELIANCE" }),
    ).toBeEnabled(),
  );
  expect(
    within(row).getByRole("button", { name: "Add RELIANCE to Watchlist" }),
  ).toBeEnabled();
  fireEvent.click(within(row).getByRole("button", { name: "Buy RELIANCE" }));
  expect(
    await screen.findByRole("dialog", { name: "Broker V2 ticket" }),
  ).toHaveTextContent("ZERODHA:NSE:RELIANCE · BUY");
  fireEvent.click(screen.getByRole("button", { name: "Close ticket" }));
  expect(screen.getByRole("button", { name: "Buy RELIANCE" })).toBeEnabled();
  expect(screen.getByLabelText("NSE symbols")).toHaveValue(
    "RELIANCE,NIFTY,UNRESOLVED",
  );
  expect(
    screen.getByRole("button", { name: "Remove filter 1" }),
  ).toBeInTheDocument();
  fireEvent.click(within(row).getByRole("button", { name: "Sell RELIANCE" }));
  expect(
    await screen.findByRole("dialog", { name: "Broker V2 ticket" }),
  ).toHaveTextContent("ZERODHA:NSE:RELIANCE · SELL");
  const mappings = fetch.mock.calls.filter(([url]) =>
    String(url).includes("/broker-instrument?"),
  );
  expect(mappings).toHaveLength(2);
  expect(
    mappings.every(([url]) =>
      String(url).includes(
        `/items/${equityId}/broker-instrument?account_id=${account.id}`,
      ),
    ),
  ).toBe(true);
  expect(
    fetch.mock.calls.some(([url]) =>
      /\/preview|\/confirm|\/choices/.test(String(url)),
    ),
  ).toBe(false);
});

test("index and unresolved rows cannot launch an equity ticket", async () => {
  const fetch = mockApi();
  await runScan();
  for (const symbol of ["NIFTY", "UNRESOLVED"]) {
    expect(
      screen.getByRole("button", { name: `Buy ${symbol}` }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: `Sell ${symbol}` }),
    ).toBeDisabled();
  }
  fireEvent.click(screen.getByRole("button", { name: "Review NIFTY" }));
  expect(screen.getByRole("button", { name: "Buy" })).toBeDisabled();
  expect(
    fetch.mock.calls.some(([url]) =>
      String(url).includes("/broker-instrument?"),
    ),
  ).toBe(false);
});

test("without a capable broker, row actions explain unavailability", async () => {
  const fetch = mockApi(false);
  await runScan();
  const buy = screen.getByRole("button", { name: "Buy RELIANCE" });
  await waitFor(() =>
    expect(buy).toHaveAttribute(
      "title",
      "Connect/select an equity-capable broker to preview a trade.",
    ),
  );
  expect(buy).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Run Evidence" }));
  expect(screen.getByLabelText("Scanner contextual panel")).toHaveTextContent(
    "No equity-capable broker connected",
  );
  expect(screen.getByRole("button", { name: "Sell RELIANCE" })).toBeDisabled();
  expect(
    fetch.mock.calls.some(([url]) =>
      String(url).includes("/broker-instrument?"),
    ),
  ).toBe(false);
});

test("a mismatched broker contract never opens the ticket", async () => {
  const fetch = mockApi();
  const original = fetch.getMockImplementation()!;
  fetch.mockImplementation(async (url, init) =>
    String(url).includes("/broker-instrument?")
      ? Response.json({ ...brokerInstrument, symbol: "OTHER" })
      : original(url, init),
  );
  await runScan();
  const buy = screen.getByRole("button", { name: "Buy RELIANCE" });
  await waitFor(() => expect(buy).toBeEnabled());
  fireEvent.click(buy);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "An exact, currently tradable broker equity contract is unavailable.",
  );
  expect(
    screen.queryByRole("dialog", { name: "Broker V2 ticket" }),
  ).not.toBeInTheDocument();
});

test("multiple capable brokers use the existing detail-panel selection before ticket launch", async () => {
  const fetch = mockApi(true, true);
  await runScan();
  const buy = screen.getByRole("button", { name: "Buy RELIANCE" });
  await waitFor(() => expect(buy).toBeEnabled());
  fireEvent.click(buy);
  expect(
    screen.getByText("Select an equity-capable broker in Instrument Analysis."),
  ).toBeVisible();
  expect(
    screen.queryByRole("dialog", { name: "Broker V2 ticket" }),
  ).not.toBeInTheDocument();
  const panel = document.querySelector(".sc-inspector")!;
  fireEvent.change(within(panel as HTMLElement).getByLabelText("Broker"), {
    target: { value: "66666666-6666-4666-8666-666666666666" },
  });
  fireEvent.click(
    within(panel as HTMLElement).getByRole("button", { name: "Buy" }),
  );
  expect(
    await screen.findByRole("dialog", { name: "Broker V2 ticket" }),
  ).toHaveTextContent("Alternate Equity · ZERODHA:NSE:RELIANCE · BUY");
  expect(
    fetch.mock.calls.some(([url]) =>
      String(url).includes("account_id=66666666-6666-4666-8666-666666666666"),
    ),
  ).toBe(true);
});
