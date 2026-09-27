import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { BrokerLinks } from "../src/components/brokers/broker-navigation";
import { BrokerSession } from "../src/components/brokers/broker-session";
import {
  BrokerSetup,
  BrokerRoster,
  RealBrokers,
} from "../src/components/brokers/real-brokers";
import { brokerDevToolsEnabled } from "../src/lib/broker-environment";
import { connectionHref, type Connection } from "../src/lib/broker-connections";
import BrokersPage from "../src/app/(protected)/brokers/[[...path]]/page";
import { RealBrokerRoom } from "../src/components/brokers/real-broker-room";
import { roomViews } from "../src/lib/portfolio";
import { brokerFixture } from "./broker-fixtures";
vi.mock("next/navigation", () => ({
  usePathname: () => "/brokers",
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));
afterEach(() => vi.unstubAllGlobals());
export const connection = (
  label = "Primary",
  id = "00000000-0000-0000-0000-000000000001",
): Connection => ({
  account: {
    broker_account_id: id,
    provider_id: "zerodha",
    label,
    enabled: true,
    configured: true,
    provider_account_id: "fixture-user",
    authentication_state: "CONNECTED",
    connection_generation: 3,
    configuration_revision: 2,
    read_health: "AVAILABLE",
  },
  bound_at: "2026-09-01T00:00:00Z",
  can_configure: true,
  can_connect: false,
  can_disconnect: true,
  callback_url: "https://example.test/callback",
  cleanup_pending: 0,
  unavailable_reason: null,
});
function api(accounts: Connection[]) {
  const fetcher = vi
    .fn()
    .mockImplementation(() => Promise.resolve(Response.json(accounts)));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}
const nav = () => screen.getByRole("navigation", { name: "Broker workspace" });

test("no connected accounts means only Overview and Manage Brokers, with no fixture request", async () => {
  const fetcher = api([]);
  render(
    <BrokerSession>
      <BrokerLinks />
      <BrokerRoster />
    </BrokerSession>,
  );
  await screen.findByText("No broker connected yet.");
  expect(
    within(nav())
      .getAllByRole("link")
      .map((link) => link.textContent),
  ).toEqual(["Overview", "Manage Brokers"]);
  expect(screen.queryByText("Development / Synthetic")).toBeNull();
  expect(screen.queryByText("Zerodha")).toBeNull();
  expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
    "/api/v1/broker-auth/accounts",
  ]);
});

test("only enabled, configured and bound connected accounts become distinct tabs", async () => {
  const rejected = [
    "NOT_CONFIGURED",
    "AUTH_IN_PROGRESS",
    "REAUTH_REQUIRED",
    "DISCONNECTED",
  ].map((state) => ({
    ...connection(state),
    account: { ...connection(state).account, authentication_state: state },
  }));
  rejected.push(
    { ...connection("Unbound"), bound_at: null },
    {
      ...connection("Disabled"),
      account: { ...connection("Disabled").account, enabled: false },
    },
    {
      ...connection("No configuration"),
      account: { ...connection("No configuration").account, configured: false },
    },
  );
  api([
    connection(),
    connection("Algo", "00000000-0000-0000-0000-000000000002"),
    ...rejected,
  ]);
  render(
    <BrokerSession>
      <BrokerLinks />
      <BrokerRoster />
    </BrokerSession>,
  );
  await within(nav()).findByRole("link", { name: "Zerodha · Algo" });
  expect(
    within(nav())
      .getAllByRole("link")
      .map((link) => link.textContent),
  ).toEqual([
    "Overview",
    "Zerodha · Primary",
    "Zerodha · Algo",
    "Manage Brokers",
  ]);
  expect(screen.getByRole("option", { name: "Zerodha · Algo" })).toHaveValue(
    "/brokers/zerodha/00000000-0000-0000-0000-000000000002/dashboard",
  );
});

test("disconnect removes the operational tab and transmits the current generation fence", async () => {
  const value = connection();
  const fetcher = api([value]);
  fetcher.mockImplementation((url: string) => {
    if (url.endsWith("/disconnect")) {
      value.account.authentication_state = "DISCONNECTED";
      return Promise.resolve(Response.json({ disconnected: true }));
    }
    return Promise.resolve(Response.json([value]));
  });
  render(
    <BrokerSession>
      <BrokerLinks />
      <BrokerSetup accountId={value.account.broker_account_id} />
    </BrokerSession>,
  );
  await within(nav()).findByRole("link", { name: "Zerodha · Primary" });
  fireEvent.click(screen.getByRole("button", { name: "Disconnect from TWF" }));
  await waitFor(() =>
    expect(
      within(nav()).queryByRole("link", { name: "Zerodha · Primary" }),
    ).toBeNull(),
  );
  expect(
    JSON.parse(
      fetcher.mock.calls.find(([url]) => url.endsWith("/disconnect"))![1].body,
    ),
  ).toEqual({ expected_generation: 3 });
});

test("removed accounts and failed refresh cannot leave stale operational tabs", async () => {
  const fetcher = api([connection()]);
  render(
    <BrokerSession>
      <BrokerLinks />
    </BrokerSession>,
  );
  await within(nav()).findByRole("link", { name: "Zerodha · Primary" });
  fetcher.mockImplementation(() => Promise.resolve(Response.json([])));
  fireEvent.focus(window);
  await waitFor(() =>
    expect(within(nav()).getAllByRole("link")).toHaveLength(2),
  );
  fetcher.mockImplementation(() =>
    Promise.resolve(Response.json([connection()])),
  );
  fireEvent.focus(window);
  await within(nav()).findByRole("link", { name: "Zerodha · Primary" });
  fetcher.mockRejectedValue(new Error("untrusted upstream details"));
  fireEvent.focus(window);
  await waitFor(() =>
    expect(within(nav()).getAllByRole("link")).toHaveLength(2),
  );
});

test("All Brokers retains connected Zerodha and search never offers unsupported setup", async () => {
  api([connection()]);
  render(
    <BrokerSession>
      <RealBrokers />
    </BrokerSession>,
  );
  await screen.findByText("Connected: 1");
  expect(screen.getByRole("link", { name: "Add connection" })).toHaveAttribute(
    "href",
    "/brokers/manage/setup/zerodha",
  );
  for (const name of ["Fyers", "Angel One", "Dhan"]) {
    const card = screen.getByRole("heading", { name }).closest("article")!;
    expect(card).toHaveTextContent("Coming later");
    expect(within(card).queryByRole("link")).toBeNull();
    expect(within(card).queryByRole("button")).toBeNull();
  }
  fireEvent.change(screen.getByRole("searchbox"), {
    target: { value: "zero" },
  });
  expect(screen.getAllByRole("article")).toHaveLength(1);
  expect(screen.getByRole("heading", { name: "Zerodha" })).toBeVisible();
});

test("My Brokers shows account actions and can find one of several accounts", async () => {
  const reconnect = connection("Algo");
  reconnect.account.authentication_state = "REAUTH_REQUIRED";
  api([
    connection(),
    {
      ...reconnect,
      account: {
        ...reconnect.account,
        broker_account_id: "00000000-0000-0000-0000-000000000002",
      },
    },
  ]);
  render(
    <BrokerSession>
      <RealBrokers view="my" />
    </BrokerSession>,
  );
  await screen.findByRole("link", { name: "Open" });
  expect(screen.getByRole("link", { name: "Reconnect" })).toHaveAttribute(
    "href",
    "/brokers/manage/accounts/00000000-0000-0000-0000-000000000002",
  );
  fireEvent.change(screen.getByRole("searchbox"), {
    target: { value: "algo" },
  });
  expect(screen.queryByRole("link", { name: "Open" })).toBeNull();
  expect(screen.getByRole("heading", { name: "Zerodha · Algo" })).toBeVisible();
});

test("synthetic discovery is explicit dev-only and loads fixtures on disclosure", async () => {
  const fetcher = api([]);
  fetcher.mockImplementation((url: string) =>
    Promise.resolve(
      Response.json(url.includes("brokers/overview") ? brokerFixture() : []),
    ),
  );
  render(
    <BrokerSession development>
      <BrokerLinks />
    </BrokerSession>,
  );
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole("link", { name: /Alpha/ })).toBeNull();
  fireEvent.click(
    screen.getByText("Development / Synthetic", { selector: "summary" }),
  );
  await screen.findByRole("link", { name: /Alpha A1/ });
  expect(within(nav()).queryByRole("link", { name: /Alpha/ })).toBeNull();
});

test("production and unknown runtime environments hide fixture discovery", () => {
  expect(brokerDevToolsEnabled("production", "development")).toBe(false);
  expect(brokerDevToolsEnabled(undefined, "production")).toBe(false);
  expect(brokerDevToolsEnabled("staging", "production")).toBe(false);
  expect(brokerDevToolsEnabled("test", "production")).toBe(true);
  expect(brokerDevToolsEnabled(undefined, "development")).toBe(true);
});

test("a previously bound expired account offers reconnect on Overview without an operational tab", async () => {
  const expired = connection();
  expired.account.authentication_state = "REAUTH_REQUIRED";
  api([expired]);
  render(
    <BrokerSession>
      <BrokerLinks />
      <BrokerRoster />
    </BrokerSession>,
  );
  expect(
    await screen.findByRole("link", {
      name: "Zerodha · Primary Reconnect required →",
    }),
  ).toHaveAttribute(
    "href",
    `/brokers/manage/accounts/${expired.account.broker_account_id}`,
  );
  expect(within(nav()).getAllByRole("link")).toHaveLength(2);
  expect(screen.queryByText("No broker connected yet.")).toBeNull();
});

test("every supported connected-account destination resolves to the implemented room and its functions", async () => {
  for (const value of [
    connection(),
    connection("Algo", "00000000-0000-0000-0000-000000000002"),
  ]) {
    const href = connectionHref(value)!;
    expect(href).toBeTruthy();
    for (const view of roomViews) {
      const path = href.slice("/brokers/".length).split("/");
      path[2] = view;
      const page = await BrokersPage({ params: Promise.resolve({ path }) });
      expect(page.type).toBe(RealBrokerRoom);
      expect(page.props).toMatchObject({
        accountId: value.account.broker_account_id,
        view,
      });
    }
  }
});

test("connected unsupported-room accounts stay visible in My Brokers without dead operational links", async () => {
  const fyers = connection("Trading", "00000000-0000-0000-0000-000000000002");
  fyers.account.provider_id = "fyers";
  const unknown = connection("Unknown", "00000000-0000-0000-0000-000000000003");
  unknown.account.provider_id = "unknown";
  const malformed = connection("Malformed", "not-an-account-id");
  for (const value of [fyers, unknown, malformed])
    expect(connectionHref(value)).toBeNull();
  api([connection(), fyers]);
  render(
    <BrokerSession>
      <BrokerLinks />
      <RealBrokers view="my" />
    </BrokerSession>,
  );
  const card = (
    await screen.findByRole("heading", { name: "Fyers · Trading" })
  ).closest("article")!;
  expect(
    within(nav()).queryByRole("link", { name: "Fyers · Trading" }),
  ).toBeNull();
  expect(screen.queryByRole("option", { name: "Fyers · Trading" })).toBeNull();
  expect(within(card).queryByRole("link")).toBeNull();
  expect(card).toHaveTextContent("Workspace not available for this broker.");
  expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute(
    "href",
    connectionHref(connection()),
  );
});
