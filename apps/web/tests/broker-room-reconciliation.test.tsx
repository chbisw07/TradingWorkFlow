import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { BrokerSession } from "../src/components/brokers/broker-session";
import { RealBrokerRoom } from "../src/components/brokers/real-broker-room";
import type { Connection } from "../src/lib/broker-connections";
import type { Portfolio } from "../src/lib/portfolio";

const id = "00000000-0000-0000-0000-000000000001";
function account(accountId = id): Connection {
  return {
    account: {
      broker_account_id: accountId,
      provider_id: "zerodha",
      label: "Primary",
      enabled: true,
      configured: true,
      provider_account_id: "fixture-user",
      authentication_state: "CONNECTED",
      connection_generation: 1,
      configuration_revision: 1,
      read_health: "UNKNOWN",
    },
    bound_at: "2026-09-01T00:00:00Z",
    can_configure: true,
    can_connect: false,
    can_disconnect: true,
    callback_url: "https://example.test/callback",
    cleanup_pending: 0,
    unavailable_reason: null,
  };
}
function portfolio(): Portfolio {
  const dataset = {
    rows: [],
    activity_rows: [],
    metadata: {
      source: "fixture",
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
      total_rows: 0,
    },
  };
  return {
    broker_account_id: id,
    provider_id: "zerodha",
    account_label: "Primary",
    connection_state: "CONNECTED",
    holdings: structuredClone(dataset),
    positions: structuredClone(dataset),
    summary: {
      holdings_count: 0,
      holdings_value: "550",
      open_positions_count: 0,
      realized_pnl: null,
      unrealized_pnl: null,
      position_pnl: null,
    },
  };
}
const status = () => screen.getByRole("status", { name: "Broker read status" });
async function mount() {
  const state = { accounts: [account()], data: portfolio() };
  const reads = vi.fn(async () => Response.json(state.data));
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      url.endsWith("broker-auth/accounts")
        ? Promise.resolve(Response.json(state.accounts))
        : reads(),
    ),
  );
  const result = render(
    <BrokerSession>
      <RealBrokerRoom accountId={id} />
    </BrokerSession>,
  );
  await waitFor(() => expect(status()).toHaveTextContent("LIVE DATA"));
  return { state, reads, result };
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

test.each([
  ["DISCONNECTED", "NOT CONNECTED", "Configure / Connect"],
  ["REAUTH_REQUIRED", "REAUTH REQUIRED", "Reconnect"],
  ["AUTH_IN_PROGRESS", "CONNECTING", "Manage connection"],
])(
  "mounted healthy room honors focus refresh to %s and retains observations",
  async (next, headline, action) => {
    const { state, reads } = await mount();
    state.accounts[0].account.authentication_state = next;
    state.accounts[0].account.connection_generation = 2;
    fireEvent.focus(window);
    await waitFor(() => expect(status()).toHaveTextContent(headline));
    expect(status()).not.toHaveTextContent("LIVE DATA");
    expect(screen.queryByText(/^Connected ·/)).toBeNull();
    expect(screen.getByRole("link", { name: action })).toHaveAttribute(
      "href",
      `/brokers/manage/accounts/${id}`,
    );
    expect(screen.getByText(/Showing last available snapshot/)).toBeVisible();
    expect(screen.getByText("550")).toBeVisible();
    expect(reads).toHaveBeenCalledTimes(1);
  },
);

test("mounted room honors degraded read health from session refresh", async () => {
  const { state, reads } = await mount();
  state.accounts[0].account.read_health = "DEGRADED";
  fireEvent.focus(window);
  await waitFor(() => expect(status()).toHaveTextContent("DEGRADED"));
  expect(status()).not.toHaveTextContent("LIVE DATA");
  expect(reads).toHaveBeenCalledTimes(1);
});

test("mounted read ages to stale without a new provider request", async () => {
  const { reads } = await mount();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(Date.now() + 61_000);
  await waitFor(() => expect(status()).toHaveTextContent("STALE DATA"), {
    timeout: 2000,
  });
  expect(status()).not.toHaveTextContent("LIVE DATA");
  expect(reads).toHaveBeenCalledTimes(1);
});

test("reconnection requires a read matching the new generation before becoming live", async () => {
  const { state } = await mount();
  state.accounts[0].account.authentication_state = "DISCONNECTED";
  state.accounts[0].account.connection_generation = 2;
  fireEvent.focus(window);
  await waitFor(() => expect(status()).toHaveTextContent("NOT CONNECTED"));
  state.accounts[0].account.authentication_state = "CONNECTED";
  state.accounts[0].account.connection_generation = 3;
  fireEvent.focus(window);
  await waitFor(() => expect(status()).toHaveTextContent("STALE DATA"));
  expect(screen.getByText("550")).toBeVisible();
  state.data.holdings.metadata.connection_generation = 3;
  state.data.positions.metadata.connection_generation = 3;
  fireEvent.click(screen.getByRole("button", { name: "Refresh data" }));
  await waitFor(() => expect(status()).toHaveTextContent("LIVE DATA"));
  expect(screen.queryByText(/Showing last available snapshot/)).toBeNull();
});

test("another account's status and generation cannot affect this room", async () => {
  const { state, reads } = await mount();
  const other = account("00000000-0000-0000-0000-000000000002");
  other.account.authentication_state = "DISCONNECTED";
  other.account.connection_generation = 99;
  state.accounts = [other, state.accounts[0]];
  fireEvent.focus(window);
  await act(async () => {});
  expect(status()).toHaveTextContent("LIVE DATA");
  expect(reads).toHaveBeenCalledTimes(1);
});

test.each(["DISCONNECTED", "REAUTH_REQUIRED"])(
  "late older-generation connected read cannot override newer %s session",
  async (next) => {
    const { state, reads } = await mount();
    let finish!: (response: Response) => void;
    reads.mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Refresh data" }));
    state.accounts[0].account.authentication_state = next;
    state.accounts[0].account.connection_generation = 2;
    fireEvent.focus(window);
    await waitFor(() =>
      expect(status()).toHaveTextContent(
        next === "DISCONNECTED" ? "NOT CONNECTED" : "REAUTH REQUIRED",
      ),
    );
    await act(async () => {
      finish(Response.json(state.data));
    });
    expect(status()).not.toHaveTextContent("LIVE DATA");
    expect(screen.getByText(/Showing last available snapshot/)).toBeVisible();
  },
);

test("newer same-generation session refresh wins over an older read auth claim", async () => {
  const { state } = await mount();
  state.accounts[0].account.authentication_state = "REAUTH_REQUIRED";
  fireEvent.focus(window);
  await waitFor(() => expect(status()).toHaveTextContent("REAUTH REQUIRED"));
  expect(status()).not.toHaveTextContent("LIVE DATA");
});

test("removed account never inherits another account's connected state", async () => {
  const { state } = await mount();
  state.accounts = [account("00000000-0000-0000-0000-000000000002")];
  fireEvent.focus(window);
  await waitFor(() => expect(status()).toHaveTextContent("UNAVAILABLE"));
  expect(screen.getByText("550")).toBeVisible();
  expect(screen.queryByRole("link", { name: "Manage connection" })).toBeNull();
});
