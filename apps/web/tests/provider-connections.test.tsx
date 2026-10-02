import { StrictMode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ProviderConnectionsSection } from "../src/components/settings/provider-connections";
import { McpOAuthCallback } from "../src/components/settings/mcp-oauth-callback";

const identity = "855fb13f-848b-4937-b6a9-703d1faa912f";

function response(data: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => data };
}

function registration(providerId = "tapetide") {
  return {
    provider_id: providerId,
    display_name: providerId === "tapetide" ? "TapTide" : "Legacy provider",
    auth_mode: "OAUTH_2_1",
  };
}

function connection(changes: Record<string, unknown> = {}) {
  return {
    id: identity,
    provider_id: "tapetide",
    display_name: "TapTide",
    enabled: true,
    generation: 1,
    state: "CONNECTED",
    health: "AVAILABLE",
    error: null,
    cleanup_pending: false,
    operations_pending: 0,
    recovery_required: false,
    tools: [{ name: "get_market_pulse" }],
    last_success_at: "2026-10-02T12:00:00Z",
    ...changes,
  };
}

function dhanStatus(changes: Record<string, unknown> = {}) {
  return {
    state: "NOT_CONFIGURED",
    configured: false,
    enabled: false,
    generation: 0,
    source: "NONE",
    checked_at: null,
    last_error: null,
    ...changes,
  };
}

const statuses = [
  {
    id: "dhan",
    label: "Dhan market data",
    enabled: true,
    mode: "REMOTE",
    health: "AVAILABLE",
    role: "MARKET_DATA",
    capabilities: [],
    limitations: [],
    last_success_at: null,
    last_error: null,
  },
];

function fetchByPath(options: {
  registrations?: unknown[];
  connections?: unknown[];
  create?: unknown;
  operation?: unknown;
  dhan?: unknown;
  dhanSave?: unknown;
  dhanTest?: unknown;
  dhanDisconnect?: unknown;
}) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path.includes("/settings/market-data/dhan")) {
      if (path.endsWith("/credentials"))
        return Promise.resolve(response(options.dhanSave || options.dhan));
      if (path.endsWith("/test"))
        return Promise.resolve(response(options.dhanTest || options.dhan));
      if (path.endsWith("/disconnect"))
        return Promise.resolve(
          response(options.dhanDisconnect || options.dhan),
        );
      return Promise.resolve(response(options.dhan || dhanStatus()));
    }
    if (path.endsWith("/providers"))
      return Promise.resolve(response(options.registrations || []));
    if (path.endsWith("/connections")) {
      const value =
        init?.method === "POST" ? options.create : options.connections || [];
      return Promise.resolve(response(value));
    }
    if (path.endsWith("/status")) return Promise.resolve(response(statuses));
    return Promise.resolve(response(options.operation || connection()));
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  window.history.replaceState(null, "", "/");
});

test("shows Dhan market data and creates a configured TapTide connection", async () => {
  const fetcher = fetchByPath({
    registrations: [registration()],
    create: connection({
      enabled: false,
      generation: 0,
      state: "DISCONNECTED",
      health: "UNKNOWN",
      tools: [],
      last_success_at: null,
    }),
  });
  vi.stubGlobal("fetch", fetcher);

  render(<ProviderConnectionsSection />);
  expect(await screen.findByText("Dhan market data")).toBeVisible();
  fireEvent.click(
    await screen.findByRole("button", { name: "Add TapTide connection" }),
  );
  await screen.findByRole("button", { name: "Authorize TapTide" });
  const createCall = fetcher.mock.calls.find(
    ([url, init]) =>
      String(url).endsWith("/connections") && init?.method === "POST",
  );
  expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
    provider_id: "tapetide",
    display_name: "TapTide",
  });
});

test("uses generation-fenced generic connection operations", async () => {
  const fetcher = fetchByPath({
    registrations: [registration()],
    connections: [connection()],
    operation: connection(),
  });
  vi.stubGlobal("fetch", fetcher);

  render(<ProviderConnectionsSection />);
  await screen.findAllByText("Ready");
  fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
  await screen.findByText("TapTide: Test completed.");
  const call = fetcher.mock.calls.find(([url]) =>
    String(url).endsWith("/test"),
  );
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({ generation: 1 });
});

test("does not expose a configured legacy TradingView registration or connection as active", async () => {
  vi.stubGlobal(
    "fetch",
    fetchByPath({
      registrations: [registration("tradingview")],
      connections: [
        connection({ provider_id: "tradingview", display_name: "TradingView" }),
      ],
    }),
  );
  render(<ProviderConnectionsSection />);
  await screen.findByText(
    "No market-intelligence MCP providers are configured.",
  );
  expect(screen.queryByText("TradingView")).not.toBeInTheDocument();
});

test("generic callback scrubs OAuth parameters and completes the same-origin conduit", async () => {
  sessionStorage.setItem("twf.mcp.connection_id", identity);
  sessionStorage.setItem("twf.mcp.provider_name", "TapTide");
  window.history.pushState(
    null,
    "",
    "/settings/mcp/callback?code=provider-code&state=bound-state",
  );
  const fetcher = vi.fn().mockResolvedValue(response(connection()));
  vi.stubGlobal("fetch", fetcher);

  render(
    <StrictMode>
      <McpOAuthCallback />
    </StrictMode>,
  );
  await screen.findByText("TapTide connected");
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(window.location.search).toBe("");
  expect(sessionStorage.getItem("twf.mcp.connection_id")).toBeNull();
  expect(fetcher.mock.calls[0][0]).toContain(identity + "/callback");
});

test("configures Dhan with a masked token field and never renders the saved token", async () => {
  const saved = dhanStatus({
    state: "CONFIGURED",
    configured: true,
    enabled: true,
    generation: 1,
    source: "DATABASE",
  });
  const fetcher = fetchByPath({ dhan: dhanStatus(), dhanSave: saved });
  vi.stubGlobal("fetch", fetcher);

  render(<ProviderConnectionsSection />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Configure Dhan" }),
  );
  const token = screen.getByLabelText("Dhan access token");
  expect(token).toHaveAttribute("type", "password");
  fireEvent.change(screen.getByLabelText("Dhan client ID"), {
    target: { value: "1100000001" },
  });
  fireEvent.change(token, {
    target: { value: "private-dhan-access-token" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Save Dhan credentials" }),
  );

  await screen.findByText("Configured");
  expect(screen.queryByDisplayValue("private-dhan-access-token")).toBeNull();
  expect(
    screen.getByRole("button", { name: "Update credentials" }),
  ).toBeVisible();
  const call = fetcher.mock.calls.find(([url]) =>
    String(url).endsWith("/credentials"),
  );
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({
    generation: 0,
    client_id: "1100000001",
    access_token: "private-dhan-access-token",
  });
});

test("cancels Dhan credential entry without persisting browser state", async () => {
  vi.stubGlobal("fetch", fetchByPath({ dhan: dhanStatus() }));
  render(<ProviderConnectionsSection />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Configure Dhan" }),
  );
  fireEvent.change(screen.getByLabelText("Dhan access token"), {
    target: { value: "private-dhan-access-token" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByLabelText("Dhan access token")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Configure Dhan" }));
  expect(screen.getByLabelText("Dhan access token")).toHaveValue("");
});

test("tests, synchronizes READY, and disconnects Dhan", async () => {
  const configured = dhanStatus({
    state: "CONFIGURED",
    configured: true,
    enabled: true,
    generation: 3,
    source: "DATABASE",
  });
  const ready = {
    ...configured,
    state: "READY",
    checked_at: "2026-10-02T12:00:00Z",
  };
  const disabled = dhanStatus({
    state: "DISABLED",
    generation: 4,
    source: "NONE",
  });
  const fetcher = fetchByPath({
    dhan: configured,
    dhanTest: ready,
    dhanDisconnect: disabled,
  });
  vi.stubGlobal("fetch", fetcher);

  render(<ProviderConnectionsSection />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Test Dhan connection" }),
  );
  await screen.findByText("Dhan connection verified and ready for real scans.");
  expect(screen.getAllByText("Ready").length).toBeGreaterThan(0);
  const testCall = fetcher.mock.calls.find(([url]) =>
    String(url).endsWith("/market-data/dhan/test"),
  );
  expect(JSON.parse(String(testCall?.[1]?.body))).toEqual({ generation: 3 });

  fireEvent.click(screen.getByRole("button", { name: "Disconnect Dhan" }));
  await screen.findByText("Disabled");
  expect(
    screen.getByText(
      "Dhan market-data access disabled and saved credentials removed.",
    ),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Test Dhan connection" }),
  ).toBeNull();
});

test.each([
  [
    "AUTH_FAILED",
    "Authentication failed",
    "Dhan rejected the saved credentials. Replace them and test again.",
  ],
  [
    "RATE_LIMITED",
    "Rate limited",
    "Dhan rate limited the last test. Retry after its window resets.",
  ],
  [
    "PROVIDER_ERROR",
    "Provider error",
    "Dhan could not complete the last connection test.",
  ],
])("renders explicit Dhan state %s", async (state, label, message) => {
  vi.stubGlobal(
    "fetch",
    fetchByPath({
      dhan: dhanStatus({
        state,
        configured: true,
        enabled: true,
        generation: 1,
        source: "DATABASE",
      }),
    }),
  );
  render(<ProviderConnectionsSection />);
  expect(await screen.findByText(label)).toBeVisible();
  expect(screen.getByText(message)).toBeVisible();
});
