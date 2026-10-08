import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { BrokerWorkspace } from "../src/components/brokers/broker-workspace";
import {
  Account,
  newer,
  operational,
  readLabel,
  Snapshot,
} from "../src/lib/brokers";
const account: Account = {
  id: "11111111-1111-1111-1111-111111111111",
  provider: "zerodha",
  name: "Zerodha – Primary",
  identity: "AB1234",
  state: "connected",
  health: "healthy",
  generation: 3,
  updated_at: "2026-09-27T12:00:00Z",
  last_read_at: "2026-09-27T12:00:00Z",
};
const snapshot: Snapshot = {
  account,
  fetched_at: "2026-09-27T12:00:00Z",
  data: [],
};
afterEach(() => vi.restoreAllMocks());
test("new authoritative session state overrides retained healthy data", () => {
  const now = Date.parse(snapshot.fetched_at);
  expect(readLabel(account, snapshot, false, now)).toBe(
    "LIVE DATA · READ ONLY",
  );
  expect(
    readLabel({ ...account, state: "reauth_required" }, snapshot, false, now),
  ).toBe("REAUTH REQUIRED");
  expect(
    readLabel({ ...account, state: "disconnected" }, snapshot, false, now),
  ).toBe("NOT CONNECTED");
  expect(
    readLabel({ ...account, health: "degraded" }, snapshot, false, now),
  ).toBe("READ ONLY · DEGRADED");
  expect(readLabel(account, snapshot, true, now)).toBe("READ ONLY · DEGRADED");
  expect(readLabel(account, snapshot, false, now + 31_000)).toBe(
    "READ ONLY · STALE DATA",
  );
  expect(
    readLabel({ ...account, generation: 4 }, snapshot, false, now),
  ).not.toContain("LIVE");
});
test("out-of-order responses cannot revive disconnected accounts", () => {
  const disconnected: Account = {
    ...account,
    state: "disconnected",
    generation: 4,
  };
  expect(newer(account, disconnected)).toEqual(disconnected);
  expect(operational(disconnected)).toBe(false);
  expect(operational({ ...account, identity: null })).toBe(false);
  expect(operational({ ...account, state: "reauth_required" })).toBe(true);
});
function mock(accounts: Account[], storageMessage: string | null = null) {
  vi.spyOn(global, "fetch").mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith("/accounts")) return Response.json(accounts);
    if (path.endsWith("/providers"))
      return Response.json([
        { id: "zerodha", name: "Zerodha", supported: true },
        { id: "fyers", name: "Fyers", supported: false },
      ]);
    if (path.endsWith("/setup"))
      return Response.json({
        callback_url: "http://localhost:3000/brokers/callback",
        storage_available: storageMessage === null,
        storage_message: storageMessage,
      });
    return Response.json({
      ...snapshot,
      fetched_at: new Date().toISOString(),
      data: [
        {
          instrument: { symbol: "HAL", reference: "ZERODHA:NSE:HAL" },
          quantity: null,
          average: 0,
        },
      ],
    });
  });
}
test("empty UX only exposes Overview and Manage Brokers", async () => {
  mock([]);
  render(<BrokerWorkspace path={[]} />);
  await waitFor(() =>
    expect(
      screen.queryByText("Loading broker connections…"),
    ).not.toBeInTheDocument(),
  );
  const nav = screen.getByRole("navigation", { name: "Broker accounts" });
  expect(within(nav).getAllByRole("link")).toHaveLength(2);
  expect(screen.getByText("No broker connected yet")).toBeInTheDocument();
});
test("provider remains visible and unsupported cards cannot be set up", async () => {
  mock([account]);
  render(<BrokerWorkspace path={["manage"]} />);
  await screen.findByRole("heading", { name: "Fyers" });
  expect(screen.getByRole("button", { name: "Coming later" })).toBeDisabled();
  expect(screen.getByRole("link", { name: /^Manage$/ })).toHaveAttribute(
    "href",
    "/brokers/manage/my",
  );
  fireEvent.change(screen.getByRole("textbox", { name: "Search brokers" }), {
    target: { value: "fyers" },
  });
  expect(
    screen.queryByRole("heading", { name: "Zerodha" }),
  ).not.toBeInTheDocument();
});
test("setup uses only official app credentials and hides the secret", async () => {
  mock([]);
  render(<BrokerWorkspace path={["setup", "zerodha"]} />);
  await screen.findByText("http://localhost:3000/brokers/callback");
  expect(screen.getByLabelText("API Secret")).toHaveAttribute(
    "type",
    "password",
  );
  fireEvent.click(screen.getByRole("button", { name: "Show API secret" }));
  expect(screen.getByLabelText("API Secret")).toHaveAttribute("type", "text");
  expect(screen.queryByLabelText("TOTP")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Connect Broker" })).toBeEnabled();
});
test("mounted room drops LIVE when a focus refresh discovers auth loss", async () => {
  const current = [{ ...account }];
  mock(current);
  render(<BrokerWorkspace path={["accounts", account.id, "holdings"]} />);
  await screen.findByText(/LIVE DATA · READ ONLY/);
  current[0] = { ...account, generation: 4, state: "reauth_required" };
  fireEvent(window, new Event("focus"));
  await screen.findByText(/REAUTH REQUIRED · TRADING DISABLED/);
  expect(screen.queryByText(/LIVE DATA/)).not.toBeInTheDocument();
  expect(screen.getByText("HAL")).toBeInTheDocument();
});

test("missing master key disables setup and shows the actionable configuration message", async () => {
  const message =
    "Credential encryption key is not configured. Set TWF_CREDENTIAL_MASTER_KEY and restart TWF.";
  mock([], message);
  render(<BrokerWorkspace path={["setup", "zerodha"]} />);
  await screen.findByText(/Set TWF_CREDENTIAL_MASTER_KEY and restart TWF/);
  expect(screen.getByRole("alert")).toHaveTextContent(message);
  expect(screen.getByRole("button", { name: "Connect Broker" })).toBeDisabled();
});

test.each([
  [
    "mixed settlement",
    {
      quantity: "20",
      average: "100",
      last_price: "120",
      value: "2400",
      pnl: "400",
      pnl_percent: "20",
    },
    ["20", "100", "120", "2,400", "400", "20"],
  ],
  [
    "MTF with unknown combined cost",
    {
      quantity: "15",
      average: null,
      last_price: "120",
      value: "1800",
      pnl: "200",
      pnl_percent: null,
    },
    ["15", "—", "120", "1,800", "200", "—"],
  ],
  [
    "unknown ownership",
    {
      quantity: null,
      average: null,
      last_price: "120",
      value: null,
      pnl: "200",
      pnl_percent: null,
    },
    ["—", "—", "120", "—", "200", "—"],
  ],
  [
    "missing last price",
    {
      quantity: "20",
      average: "100",
      last_price: null,
      value: null,
      pnl: "400",
      pnl_percent: "20",
    },
    ["20", "100", "—", "—", "400", "20"],
  ],
] as const)(
  "Holdings renders %s without zeroing unknowns",
  async (_name, values, expected) => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) =>
      Response.json(
        String(input).endsWith("/accounts")
          ? [account]
          : {
              ...snapshot,
              fetched_at: new Date().toISOString(),
              data: [
                {
                  instrument: { symbol: "HAL", reference: "ZERODHA:NSE:HAL" },
                  ...values,
                },
              ],
            },
      ),
    );
    render(<BrokerWorkspace path={["accounts", account.id, "holdings"]} />);
    const header = await screen.findByRole("rowheader", { name: /HAL/ });
    expect(
      within(header.closest("tr")!)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual(expected);
  },
);

test("Positions totals aggregate realized, unrealized, and total P&L", async () => {
  vi.spyOn(global, "fetch").mockImplementation(async (input) =>
    Response.json(
      String(input).endsWith("/accounts")
        ? [account]
        : {
            ...snapshot,
            fetched_at: new Date().toISOString(),
            data: [
              {
                instrument: {
                  symbol: "NIFTY26OCT22000CE",
                  reference: "ZERODHA:NFO:NIFTY26OCT22000CE",
                },
                product: "NRML",
                quantity: "0",
                average: "0",
                last_price: "293.05",
                realized: "2314",
                unrealized: "0",
                pnl: "2314",
              },
              {
                instrument: {
                  symbol: "NIFTY26OCT22250PE",
                  reference: "ZERODHA:NFO:NIFTY26OCT22250PE",
                },
                product: "NRML",
                quantity: "0",
                average: "0",
                last_price: "151.5",
                realized: "-7562.75",
                unrealized: "125",
                pnl: "-7437.75",
              },
            ],
          },
    ),
  );

  render(<BrokerWorkspace path={["accounts", account.id, "positions"]} />);

  const totals = await screen.findByRole("row", { name: /Totals/ });
  expect(
    within(totals)
      .getAllByRole("cell")
      .map((cell) => cell.textContent),
  ).toEqual(["-5,248.75", "125", "-5,123.75"]);
  expect(within(totals).getByText("-5,248.75")).toHaveClass("broker-negative");
  expect(within(totals).getByText("125")).toHaveClass("broker-positive");
  expect(within(totals).getByText("-5,123.75")).toHaveClass("broker-negative");
});

test("Positions totals do not treat unavailable P&L components as zero", async () => {
  vi.spyOn(global, "fetch").mockImplementation(async (input) =>
    Response.json(
      String(input).endsWith("/accounts")
        ? [account]
        : {
            ...snapshot,
            fetched_at: new Date().toISOString(),
            data: [
              {
                instrument: {
                  symbol: "HDFCBANK26OCT730PE",
                  reference: "ZERODHA:NFO:HDFCBANK26OCT730PE",
                },
                product: "NRML",
                quantity: "5",
                average: "0",
                last_price: "20.15",
                realized: null,
                unrealized: null,
                pnl: "40",
              },
            ],
          },
    ),
  );

  render(<BrokerWorkspace path={["accounts", account.id, "positions"]} />);

  const totals = await screen.findByRole("row", { name: /Totals/ });
  expect(
    within(totals)
      .getAllByRole("cell")
      .map((cell) => cell.textContent),
  ).toEqual(["—", "—", "40"]);
});

test.each([
  [
    "closed loss",
    "0",
    "-1007.5",
    "0",
    "-1007.5",
    ["-1,007.5", "0", "-1,007.5"],
  ],
  ["closed gain", "0", "100", "0", "100", ["100", "0", "100"]],
  ["partial", "5", "10", "30", "40", ["10", "30", "40"]],
  ["unknown open split", "5", null, null, "40", ["—", "—", "40"]],
  ["unknown closed total", "0", null, "0", null, ["—", "0", "—"]],
] as const)(
  "Positions renders %s truthfully",
  async (_name, quantity, realized, unrealized, pnl, expected) => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) =>
      Response.json(
        String(input).endsWith("/accounts")
          ? [account]
          : {
              ...snapshot,
              fetched_at: new Date().toISOString(),
              data: [
                {
                  instrument: {
                    symbol: "HDFCBANK26OCT730PE",
                    reference: "ZERODHA:NFO:HDFCBANK26OCT730PE",
                  },
                  product: "NRML",
                  quantity,
                  average: "0",
                  last_price: "20.15",
                  realized,
                  unrealized,
                  pnl,
                },
              ],
            },
      ),
    );
    render(<BrokerWorkspace path={["accounts", account.id, "positions"]} />);
    const header = await screen.findByRole("rowheader", {
      name: /HDFCBANK26OCT730PE/,
    });
    expect(
      within(header.closest("tr")!)
        .getAllByRole("cell")
        .slice(-3)
        .map((cell) => cell.textContent),
    ).toEqual(expected);
  },
);

test.each([
  ["2400", "2,400"],
  [null, "—"],
])("Overview renders holdings value %s truthfully", async (value, expected) => {
  vi.spyOn(global, "fetch").mockImplementation(async (input) =>
    Response.json(
      String(input).endsWith("/accounts")
        ? [account]
        : {
            ...snapshot,
            fetched_at: new Date().toISOString(),
            data: {
              cash: null,
              holdings_value: value,
              positions: 0,
              open_orders: 0,
            },
          },
    ),
  );
  render(<BrokerWorkspace path={["accounts", account.id, "overview"]} />);
  const label = await screen.findByText("Holdings value");
  expect(label.parentElement?.querySelector("strong")).toHaveTextContent(
    expected!,
  );
});

test("Orders filters preserve raw MODIFY VALIDATION PENDING and existing broker states", async () => {
  const active = [
    "OPEN",
    "TRIGGER PENDING",
    "VALIDATION PENDING",
    "OPEN PENDING",
    "MODIFY VALIDATION PENDING",
    "MODIFY PENDING",
    "CANCEL PENDING",
    "AMO REQ RECEIVED",
    "PUT ORDER REQ RECEIVED",
  ];
  const all = [
    ...active,
    "COMPLETE",
    "CANCELLED",
    "REJECTED",
    "UNKNOWN STATUS",
  ];
  const fetch = vi.spyOn(global, "fetch").mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith("/accounts")) return Response.json([account]);
    if (path.endsWith("/providers") || path.endsWith("/intents"))
      return Response.json([]);
    if (path.endsWith("/capabilities"))
      return Response.json({ enabled: false });
    if (path.includes("/orders?"))
      return Response.json({
        ...snapshot,
        fetched_at: new Date().toISOString(),
        data: all.map((status, index) => ({
          id: `order-${index}`,
          instrument: {
            symbol: `ORDER${index}`,
            reference: `ZERODHA:NSE:ORDER${index}`,
          },
          status,
        })),
      });
    throw new Error(`Unexpected request: ${path}`);
  });
  render(<BrokerWorkspace path={["accounts", account.id, "orders"]} />);
  await screen.findByRole("cell", {
    name: "MODIFY VALIDATION PENDING",
  });
  const filters = within(screen.getByRole("group", { name: "Order filter" }));
  for (const [filter, expected] of [
    ["All", all],
    ["Open", active],
    ["Completed", ["COMPLETE"]],
    ["Cancelled", ["CANCELLED"]],
    ["Rejected", ["REJECTED"]],
    ["All", all],
  ] as const) {
    fireEvent.click(filters.getByRole("button", { name: filter }));
    expect(filters.getByRole("button", { name: filter })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(
      rows.map((row) => within(row).getAllByRole("cell").at(-1)?.textContent),
    ).toEqual(expected);
  }
  expect(
    fetch.mock.calls.filter(([url]) => String(url).includes("/orders?")),
  ).toHaveLength(1);
});
