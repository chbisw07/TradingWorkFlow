import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { RealBrokerRoom } from "../src/components/brokers/real-broker-room";
import type { NativeDataset, NativeRow, Portfolio } from "../src/lib/portfolio";

let sessionState = "CONNECTED";
vi.mock("../src/components/brokers/broker-session", () => ({
  useBrokerSession: () => ({
    connections: [
      {
        account: {
          broker_account_id: "00000000-0000-0000-0000-000000000001",
          provider_id: "zerodha",
          label: "My Zerodha",
          enabled: true,
          configured: true,
          provider_account_id: "fixture-user",
          authentication_state: sessionState,
          connection_generation: 1,
          read_health: "AVAILABLE",
        },
        bound_at: "2026-09-01T00:00:00Z",
      },
    ],
    observedAt: 0,
    error: "",
  }),
}));
beforeEach(() => {
  sessionState = "CONNECTED";
});
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

test("dashboard and function views use the same response without duplicate fixture arithmetic", async () => {
  const fetcher = api();
  const view = render(<RealBrokerRoom accountId={id} />);
  await waitFor(() =>
    expect(screen.queryByText("Loading broker observations…")).toBeNull(),
  );
  const nav = screen.getByRole("navigation", { name: "Zerodha functions" });
  expect(within(nav).getAllByRole("link")).toHaveLength(4);
  expect(within(nav).getByRole("link", { name: "Overview" })).toHaveAttribute(
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
      await waitFor(() =>
        expect(screen.queryByText("Loading broker observations…")).toBeNull(),
      );
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
    ).toHaveAttribute("href", `/brokers/manage/accounts/${id}`);
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

test("direct Instruments entry uses session context without portfolio provider reads", async () => {
  sessionState = "REAUTH_REQUIRED";
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
  ).toHaveAttribute("href", `/brokers/manage/accounts/${id}`);
  expect(
    screen.getByRole("heading", { name: "Instrument Search", level: 2 }),
  ).toBeVisible();
  expect(
    fetcher.mock.calls.every(([url]) => !url.includes("broker-portfolio")),
  ).toBe(true);
});

const readStatus = () =>
  screen.getByRole("status", { name: "Broker read status" });
test.each([
  ["healthy", "LIVE DATA · READ ONLY"],
  ["degraded", "READ ONLY · DEGRADED"],
  ["stale", "READ ONLY · STALE DATA"],
  ["elapsed", "READ ONLY · STALE DATA"],
  ["reauth", "REAUTH REQUIRED"],
  ["disconnected", "NOT CONNECTED"],
  ["auth-required", "NOT CONNECTED"],
  ["connecting", "CONNECTING"],
  ["unavailable", "READ ONLY · UNAVAILABLE"],
  ["unknown-freshness", "READ ONLY · DEGRADED"],
  ["missing-timestamp", "READ ONLY · DEGRADED"],
])("room headline is truthful for %s", async (state, expected) => {
  const data = fixture();
  if (state === "degraded") {
    data.holdings.metadata.health = "DEGRADED";
    data.holdings.metadata.completeness = "PARTIAL";
  }
  if (state === "stale") data.holdings.metadata.freshness = "STALE";
  if (state === "elapsed")
    data.holdings.metadata.received_at = "2020-01-01T00:00:00Z";
  if (state === "unknown-freshness")
    data.holdings.metadata.freshness = "UNKNOWN";
  if (state === "missing-timestamp") data.holdings.metadata.received_at = null;
  if (state === "reauth") data.connection_state = "REAUTH_REQUIRED";
  if (state === "disconnected") data.connection_state = "DISCONNECTED";
  if (state === "auth-required") data.connection_state = "AUTH_REQUIRED";
  if (state === "connecting") data.connection_state = "AUTH_IN_PROGRESS";
  if (state === "unavailable") {
    for (const dataset of [data.holdings, data.positions]) {
      dataset.rows = null;
      dataset.metadata.health = "UNAVAILABLE";
      dataset.metadata.completeness = "MISSING";
    }
  }
  api(data);
  render(<RealBrokerRoom accountId={id} />);
  await waitFor(() => expect(readStatus()).toHaveTextContent(expected));
  expect(readStatus()).toHaveTextContent("TRADING DISABLED");
  if (state !== "healthy")
    expect(readStatus()).not.toHaveTextContent("LIVE DATA");
});

test("headline ages without a new request and follows the selected dataset", async () => {
  vi.useFakeTimers();
  try {
    const data = fixture();
    data.positions.metadata.health = "DEGRADED";
    const fetcher = api(data);
    const view = render(<RealBrokerRoom accountId={id} view="holdings" />);
    await act(async () => {});
    expect(readStatus()).toHaveTextContent("LIVE DATA");
    view.rerender(<RealBrokerRoom accountId={id} view="positions" />);
    expect(readStatus()).toHaveTextContent("DEGRADED");
    view.rerender(<RealBrokerRoom accountId={id} view="holdings" />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(61_000);
    });
    expect(readStatus()).toHaveTextContent("STALE DATA");
    expect(fetcher).toHaveBeenCalledTimes(1);
  } finally {
    vi.useRealTimers();
  }
});

test("loading and failed refresh never retain a live headline", async () => {
  let resolve!: (response: Response) => void;
  const fetcher = vi.fn().mockImplementationOnce(
    () =>
      new Promise<Response>((done) => {
        resolve = done;
      }),
  );
  vi.stubGlobal("fetch", fetcher);
  render(<RealBrokerRoom accountId={id} />);
  expect(readStatus()).not.toHaveTextContent("LIVE DATA");
  await act(async () => {
    resolve(Response.json(fixture()));
  });
  expect(readStatus()).toHaveTextContent("LIVE DATA");
  fetcher.mockResolvedValueOnce(new Response(null, { status: 503 }));
  fireEvent.click(screen.getByRole("button", { name: "Refresh data" }));
  expect(readStatus()).not.toHaveTextContent("LIVE DATA");
  await screen.findByRole("alert");
  expect(readStatus()).toHaveTextContent("UNAVAILABLE");
});

test("connected Instruments remains reference data without implying a healthy portfolio read", async () => {
  const fetcher = vi.fn().mockImplementation((url: string) =>
    Promise.resolve(
      url.includes("broker-auth")
        ? Response.json([
            {
              account: {
                broker_account_id: id,
                label: "Primary",
                authentication_state: "CONNECTED",
                read_health: "AVAILABLE",
              },
            },
          ])
        : new Response(null, { status: 503 }),
    ),
  );
  vi.stubGlobal("fetch", fetcher);
  render(<RealBrokerRoom accountId={id} view="instruments" />);
  await waitFor(() =>
    expect(readStatus()).toHaveTextContent("READ ONLY · REFERENCE DATA"),
  );
  expect(readStatus()).not.toHaveTextContent("LIVE DATA");
  expect(
    fetcher.mock.calls.every(([url]) => !url.includes("broker-portfolio")),
  ).toBe(true);
});
