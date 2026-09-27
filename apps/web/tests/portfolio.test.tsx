import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import {
  BrokerRoster,
  RealBrokerRoom,
} from "../src/components/brokers/real-broker-room";
import type { NativeDataset, NativeRow, Portfolio } from "../src/lib/portfolio";

afterEach(() => vi.unstubAllGlobals());
const id = "00000000-0000-0000-0000-000000000001";
function fixture(): Portfolio {
  const row: NativeRow = {
    instrument: {
      native_id: "3",
      symbol: "HAL26OCT4500CE",
      exchange: "NFO",
      canonical_id: null,
      catalog_version: id,
      catalog_state: "FRESH",
      name: "HAL",
      segment: "NFO-OPT",
      instrument_type: "CE",
      expiry: "2026-10-29",
      strike: "4500",
      derivative_kind: "CE",
      lot_size: 150,
      tick_size: "0.05",
    },
    product: "NRML",
    product_known: true,
    quantity: "150",
    average_price: "10",
    last_price: "12",
    close_price: null,
    pnl: "300",
    current_value: null,
    pnl_percent: null,
    used_quantity: null,
    available_quantity: null,
    unsettled_quantity: null,
    settled_quantity: null,
    authorised_quantity: null,
    collateral_quantity: null,
    collateral_type: null,
    financed_quantity: null,
    financed_value: null,
    day_change: null,
    day_change_percent: null,
    overnight_quantity: "150",
    buy_quantity: "150",
    sell_quantity: "0",
    buy_average: "10",
    sell_average: null,
    realized_pnl: "0",
    unrealized_pnl: "300",
    multiplier: "1",
  };
  const dataset: NativeDataset = {
    rows: [row],
    activity_rows: [],
    metadata: {
      source: "Kite observations",
      source_as_of: null,
      attempted_at: new Date().toISOString(),
      received_at: new Date().toISOString(),
      freshness: "FRESH",
      freshness_policy_seconds: 60,
      health: "AVAILABLE",
      completeness: "COMPLETE",
      failure_code: null,
      connection_generation: 1,
      rejected_rows: 0,
      total_rows: 1,
    },
  };
  return {
    broker_account_id: id,
    provider_id: "zerodha",
    account_label: "My Zerodha",
    connection_state: "CONNECTED",
    holdings: structuredClone(dataset),
    positions: structuredClone(dataset),
    summary: {
      holdings_count: 1,
      holdings_value: null,
      open_positions_count: 1,
      realized_pnl: "0",
      unrealized_pnl: "300",
      position_pnl: "300",
    },
  };
}
function api(data = fixture()) {
  const fetcher = vi
    .fn()
    .mockImplementation(() => Promise.resolve(Response.json(data)));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

test("Zerodha roster opens a useful account room and keeps administration separate", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      Response.json([
        {
          account: {
            broker_account_id: id,
            label: "My Zerodha",
            authentication_state: "CONNECTED",
          },
        },
      ]),
    ),
  );
  render(<BrokerRoster />);
  expect(
    await screen.findByRole("link", { name: /My Zerodha Connected/ }),
  ).toHaveAttribute("href", `/brokers/zerodha/${id}/dashboard`);
  expect(
    screen.getByRole("heading", { level: 2, name: "Zerodha" }),
  ).toBeVisible();
  expect(
    screen
      .getAllByRole("link", { name: "Manage connection" })
      .every((a) => a.getAttribute("href") === "/brokers/manage"),
  ).toBe(true);
});

test("unconfigured Zerodha remains a useful landing page", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json([])));
  render(<BrokerRoster />);
  expect(
    await screen.findByText(/Not connected. Add your Zerodha/),
  ).toBeVisible();
  expect(screen.getByRole("link", { name: "Zerodha" })).toHaveAttribute(
    "href",
    "/brokers/zerodha",
  );
});

test("dashboard and function views use the same response without duplicate fixture arithmetic", async () => {
  const fetcher = api();
  const view = render(<RealBrokerRoom accountId={id} />);
  await screen.findByText(/^Connected/);
  const nav = screen.getByRole("navigation", { name: "Zerodha functions" });
  expect(within(nav).getAllByRole("link")).toHaveLength(4);
  expect(within(nav).getByRole("link", { name: "Dashboard" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(within(nav).queryByRole("link", { name: /Orders|Funds/ })).toBeNull();
  expect(
    screen.getByText("Holdings value · INR").nextElementSibling,
  ).toHaveTextContent("—");
  for (const name of ["holdings", "positions"] as const) {
    view.rerender(<RealBrokerRoom accountId={id} view={name} />);
    expect(screen.getByRole("table").textContent).toContain("HAL26OCT4500CE");
    expect(screen.getByText("HAL · 2026-10-29 · 4,500 CE")).toBeVisible();
    expect(screen.getByText("TRADING DISABLED")).toBeVisible();
    expect(screen.getByText("LIVE DATA · READ ONLY")).toBeVisible();
  }
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(fetcher.mock.calls[0][0]).toBe(
    `/api/v1/broker-portfolio/accounts/${id}`,
  );
  expect(screen.getByRole("table").textContent).toContain("+300");
});

test.each(["holdings", "positions"] as const)(
  "%s distinguishes empty, missing and stale",
  async (name) => {
    for (const state of ["empty", "missing", "stale"] as const) {
      const data = fixture();
      if (state === "empty") data[name].rows = [];
      if (state === "missing") {
        data[name].rows = null;
        data[name].metadata.completeness = "MISSING";
        data[name].metadata.failure_code = "TIMEOUT";
      }
      if (state === "stale")
        data[name].metadata.received_at = "2020-01-01T00:00:00Z";
      api(data);
      const view = render(<RealBrokerRoom accountId={id} view={name} />);
      await screen.findByText(/^Connected/);
      if (state === "empty")
        expect(screen.getByText(`No ${name}`)).toBeVisible();
      if (state === "missing") {
        expect(screen.getByText(/broker took too long/)).toBeVisible();
        expect(screen.queryByRole("table")).toBeNull();
      }
      if (state === "stale")
        expect(screen.getByText(/Stale · refresh/)).toBeVisible();
      view.unmount();
    }
  },
);

test.each(["NOT_CONFIGURED", "REAUTH_REQUIRED"])(
  "%s offers the correct connection action",
  async (state) => {
    const data = fixture();
    data.connection_state = state;
    api(data);
    render(<RealBrokerRoom accountId={id} />);
    expect(
      await screen.findByRole("link", {
        name: state === "REAUTH_REQUIRED" ? "Reconnect" : "Configure / Connect",
      }),
    ).toHaveAttribute("href", "/brokers/manage");
  },
);

test("failed refresh drops prior observations and retry restores safe data", async () => {
  const fetcher = api();
  render(<RealBrokerRoom accountId={id} view="holdings" />);
  await screen.findByRole("table");
  fetcher.mockResolvedValueOnce(new Response(null, { status: 409 }));
  fireEvent.click(screen.getByRole("button", { name: "Refresh data" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Connection changed during the read",
  );
  expect(screen.queryByRole("table")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Refresh data" }));
  expect(await screen.findByRole("table")).toBeVisible();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("account navigation aborts late reads", async () => {
  const fetcher = vi.fn().mockImplementation(() => new Promise(() => {}));
  vi.stubGlobal("fetch", fetcher);
  const view = render(<RealBrokerRoom accountId={id} />);
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  view.unmount();
  expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
});

test("all-invalid partial rows are not presented as a successful empty account", async () => {
  const data = fixture();
  data.holdings.rows = [];
  data.holdings.metadata.completeness = "PARTIAL";
  data.holdings.metadata.failure_code = "PARTIAL_RESPONSE";
  api(data);
  render(<RealBrokerRoom accountId={id} view="holdings" />);
  expect(await screen.findByText("No readable holdings rows")).toBeVisible();
  expect(screen.getByText(/Totals are unavailable/)).toBeVisible();
  expect(screen.queryByText("No holdings")).toBeNull();
});

test("direct Instruments entry loads account context without portfolio provider reads", async () => {
  const fetcher = vi.fn().mockImplementation((url: string) =>
    Promise.resolve(
      url.includes("broker-auth")
        ? Response.json([
            {
              account: {
                broker_account_id: id,
                label: "My Zerodha",
                authentication_state: "REAUTH_REQUIRED",
              },
            },
          ])
        : new Response(null, { status: 503 }),
    ),
  );
  vi.stubGlobal("fetch", fetcher);
  render(<RealBrokerRoom accountId={id} view="instruments" />);
  expect(
    await screen.findByRole("link", { name: "Reconnect" }),
  ).toHaveAttribute("href", "/brokers/manage");
  expect(
    screen.getByRole("heading", { name: "Instrument Search", level: 2 }),
  ).toBeVisible();
  expect(
    fetcher.mock.calls.every(([url]) => !url.includes("broker-portfolio")),
  ).toBe(true);
});

test("Zerodha opens its only connected account directly", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        Response.json(
          url.includes("broker-auth")
            ? [
                {
                  account: {
                    broker_account_id: id,
                    label: "My Zerodha",
                    authentication_state: "CONNECTED",
                  },
                },
              ]
            : fixture(),
        ),
      ),
    ),
  );
  render(<BrokerRoster landing />);
  expect(
    await screen.findByRole("heading", { name: "Dashboard", level: 2 }),
  ).toBeVisible();
  expect(
    screen.getByRole("navigation", { name: "Zerodha functions" }),
  ).toBeVisible();
  expect(screen.queryByRole("link", { name: /Open workspace/ })).toBeNull();
});
