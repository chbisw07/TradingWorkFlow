import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { BrokerWorkspace } from "../src/components/brokers/broker-workspace";
import type { BrokerView, Overview } from "../src/lib/brokers";
import { brokerFixture } from "./broker-fixtures";

afterEach(() => vi.unstubAllGlobals());
function api(data: Overview) {
  const fetcher = vi
    .fn()
    .mockImplementation((url: string) =>
      Promise.resolve(
        Response.json(url.endsWith("overview") ? data : data.accounts[0]),
      ),
    );
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

test("overview preserves account context, synthetic mode and qualified analytical totals", async () => {
  api(brokerFixture());
  render(<BrokerWorkspace />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  await screen.findByRole("heading", { name: "Broker overview" });
  expect(
    screen.getByRole("heading", { name: "Analytical position aggregate" }),
  ).toBeVisible();
  expect(screen.getByText(/Qualified subtotal/)).toBeVisible();
  expect(screen.getByText(/1 unmapped position rows/)).toBeVisible();
  expect(screen.getAllByText(/SYNTHETIC/).length).toBeGreaterThan(1);
  expect(screen.getByRole("link", { name: "Open Alpha A1 →" })).toHaveAttribute(
    "href",
    expect.stringContaining("/dashboard"),
  );
});

test.each([
  "dashboard",
  "holdings",
  "positions",
  "orders",
  "funds",
] as BrokerView[])(
  "room %s renders normalized observations and meaningful provenance",
  async (view) => {
    const data = brokerFixture();
    const fetcher = api(data);
    render(
      <BrokerWorkspace
        accountId={data.accounts[0].account.broker_account_id}
        view={view}
      />,
    );
    await screen.findByRole("heading", { level: 1, name: "Alpha A1" });
    expect(
      screen.getByRole("navigation", { name: "Broker room views" }),
    ).toHaveTextContent("DashboardHoldingsPositionsOrdersFunds");
    expect(screen.getAllByText(/FRESH.*COMPLETE/).length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Unavailable in this foundation/),
    ).toHaveTextContent("New Order");
    expect(fetcher.mock.calls.map(([url]) => url)).toContain(
      `/api/v1/brokers/accounts/${data.accounts[0].account.broker_account_id}`,
    );
    if (view === "dashboard") expect(screen.getByText("41,000")).toBeVisible();
    if (view === "orders")
      expect(screen.getByRole("table")).toHaveTextContent("PARTIALLY_FILLED");
    if (view === "funds") expect(screen.getByText("Unknown")).toBeVisible();
  },
);

test("stale, degraded and partial states do not become healthy or zero", async () => {
  const data = brokerFixture();
  data.accounts[0].operation.read = "DEGRADED";
  data.accounts[0].positions.metadata = {
    ...data.accounts[0].positions.metadata,
    freshness: "STALE",
    completeness: "PARTIAL",
    health: "DEGRADED",
  };
  data.accounts[0].positions.rows![0].instrument.canonical_id = null;
  api(data);
  render(
    <BrokerWorkspace
      accountId={data.accounts[0].account.broker_account_id}
      view="positions"
    />,
  );
  expect(
    await screen.findByText("Unmapped — excluded from canonical netting"),
  ).toBeVisible();
  expect(screen.getByText(/STALE.*PARTIAL/)).toHaveTextContent("DEGRADED");
});

test.each([null, []])(
  "missing and empty dataset %s have distinct copy",
  async (rows) => {
    const data = brokerFixture();
    data.accounts[0].holdings.rows = rows;
    api(data);
    render(
      <BrokerWorkspace
        accountId={data.accounts[0].account.broker_account_id}
        view="holdings"
      />,
    );
    expect(
      await screen.findByText(
        rows === null ? /Holdings unavailable/ : /No holdings in this snapshot/,
      ),
    ).toBeVisible();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  },
);

test("safe failure offers retry without retaining old observations", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(new Response(null, { status: 503 }))
    .mockResolvedValue(Response.json(brokerFixture()));
  vi.stubGlobal("fetch", fetcher);
  render(<BrokerWorkspace />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Broker observations unavailable",
  );
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByRole("heading", { name: "Broker overview" });
});

test("unmount aborts observation requests during account navigation", async () => {
  const fetcher = vi.fn().mockImplementation(() => new Promise(() => {}));
  vi.stubGlobal("fetch", fetcher);
  const { unmount } = render(<BrokerWorkspace />);
  await waitFor(() => expect(fetcher).toHaveBeenCalled());
  unmount();
  expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
});

test("room navigation identifies active view and only read views are links", async () => {
  const data = brokerFixture();
  api(data);
  render(
    <BrokerWorkspace
      accountId={data.accounts[0].account.broker_account_id}
      view="orders"
    />,
  );
  const nav = await screen.findByRole("navigation", {
    name: "Broker room views",
  });
  expect(within(nav).getByRole("link", { name: "Orders" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(within(nav).getAllByRole("link")).toHaveLength(5);
});

test.each(["SYNTHETIC", "SANDBOX", "LIVE"] as const)(
  "%s account mode drives overview, navigation and room identity",
  async (mode) => {
    const data = brokerFixture();
    data.accounts[0].account.mode = mode;
    data.accounts[0].positions.metadata.revision = "provider-alpha.snapshot.v2";
    api(data);
    const overview = render(<BrokerWorkspace />);
    await screen.findByRole("heading", { name: "Broker overview" });
    expect(
      screen.getByRole("navigation", { name: "Broker accounts" }),
    ).toHaveTextContent(mode);
    expect(document.querySelector(".broker-card .eyebrow")).toHaveTextContent(
      mode,
    );
    expect(
      document.querySelector(".broker-room-heading .broker-mode"),
    ).toHaveTextContent(mode);
    overview.unmount();
    render(
      <BrokerWorkspace
        accountId={data.accounts[0].account.broker_account_id}
        view="positions"
      />,
    );
    await screen.findByRole("heading", { name: "Alpha A1", level: 1 });
    expect(
      document.querySelector(".broker-room-heading .broker-mode"),
    ).toHaveTextContent(mode);
    expect(screen.getByText(/provider-alpha.snapshot.v2/)).toBeVisible();
    if (mode !== "SYNTHETIC") {
      expect(
        screen.queryByText(/Deterministic synthetic snapshots/),
      ).not.toBeInTheDocument();
    }
  },
);
