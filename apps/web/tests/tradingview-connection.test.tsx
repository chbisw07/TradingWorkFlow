import { StrictMode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { TradingViewConnectionSection } from "../src/components/settings/tradingview-connection";
import { TradingViewOAuthCallback } from "../src/components/settings/tradingview-oauth-callback";

const identity = "855fb13f-848b-4937-b6a9-703d1faa912f";

function response(data: unknown, status = 200) {
  return {
    ok: status < 400,
    status,
    json: async () => data,
  };
}

function connection(changes: Record<string, unknown> = {}) {
  return {
    id: identity,
    provider_id: "tradingview",
    display_name: "TradingView",
    enabled: true,
    generation: 1,
    state: "CONNECTED",
    health: "AVAILABLE",
    error: null,
    cleanup_pending: false,
    operations_pending: 0,
    recovery_required: false,
    tools: [{ name: "mcp-tv-get-ohlcv" }],
    last_success_at: "2026-10-02T12:00:00Z",
    ...changes,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  window.history.replaceState(null, "", "/");
});

test("creates an owner-scoped TradingView connection from Settings", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(response([]))
    .mockResolvedValueOnce(
      response(
        connection({
          enabled: false,
          generation: 0,
          state: "DISCONNECTED",
          health: "UNKNOWN",
          tools: [],
          last_success_at: null,
        }),
      ),
    );
  vi.stubGlobal("fetch", fetcher);

  render(<TradingViewConnectionSection />);
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Add TradingView connection",
    }),
  );

  await screen.findByRole("button", { name: "Authorize TradingView" });
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({
    provider_id: "tradingview",
    display_name: "TradingView",
  });
});

test("shows connected status and uses generation-fenced operations", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(response([connection()]))
    .mockResolvedValueOnce(response(connection()));
  vi.stubGlobal("fetch", fetcher);

  render(<TradingViewConnectionSection />);
  await screen.findByText("Ready for real evidence");
  fireEvent.click(screen.getByRole("button", { name: "Test connection" }));

  await screen.findByText("TradingView connection test completed.");
  expect(fetcher.mock.calls[1][0]).toContain("/test");
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ generation: 1 });
});

test("offers a provider test after OAuth before health is ready", async () => {
  const fetcher = vi.fn().mockResolvedValue(
    response([
      connection({
        enabled: true,
        state: "CONNECTED",
        health: "UNKNOWN",
        tools: [],
        last_success_at: null,
      }),
    ]),
  );
  vi.stubGlobal("fetch", fetcher);

  render(<TradingViewConnectionSection />);

  expect(
    await screen.findByRole("button", { name: "Test connection" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Authorize TradingView" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText("Action required")).toBeVisible();
});

test("offers a replacement when operator registration changed", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(
      response([
        connection({
          enabled: false,
          state: "REAUTH_REQUIRED",
          health: "UNAVAILABLE",
          error: "STALE_GENERATION",
        }),
      ]),
    )
    .mockResolvedValueOnce(
      response(
        connection({
          enabled: false,
          generation: 0,
          state: "DISCONNECTED",
          health: "UNKNOWN",
          error: null,
          tools: [],
          last_success_at: null,
        }),
      ),
    );
  vi.stubGlobal("fetch", fetcher);

  render(<TradingViewConnectionSection />);
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Create replacement TradingView connection",
    }),
  );

  await screen.findByRole("button", { name: "Authorize TradingView" });
  expect(fetcher.mock.calls[1][0]).toBe("/api/v1/settings/mcp/connections");
});

test("reports missing operator registration instead of fake connection success", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(response([]))
    .mockResolvedValueOnce(
      response({ error: { code: "NOT_CONFIGURED" } }, 404),
    );
  vi.stubGlobal("fetch", fetcher);

  render(<TradingViewConnectionSection />);
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Add TradingView connection",
    }),
  );

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Configure TWF_MCP_PROVIDERS",
  );
});

test("callback scrubs OAuth parameters and completes the same-origin conduit", async () => {
  sessionStorage.setItem("twf.mcp.connection_id", identity);
  window.history.pushState(
    null,
    "",
    "/settings/mcp/callback?code=provider-code&state=bound-state",
  );
  const fetcher = vi.fn().mockResolvedValue(response(connection()));
  vi.stubGlobal("fetch", fetcher);

  render(
    <StrictMode>
      <TradingViewOAuthCallback />
    </StrictMode>,
  );
  await screen.findByText("TradingView connected");

  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(window.location.search).toBe("");
  expect(sessionStorage.getItem("twf.mcp.connection_id")).toBeNull();
  expect(fetcher.mock.calls[0][0]).toContain(identity + "/callback");
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
    state: "bound-state",
    code: "provider-code",
  });
});

test("callback rejects missing browser binding without a provider request", async () => {
  window.history.pushState(
    null,
    "",
    "/settings/mcp/callback?code=provider-code&state=bound-state",
  );
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);

  render(<TradingViewOAuthCallback />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "no longer belongs to this browser session",
  );
  expect(fetcher).not.toHaveBeenCalled();
});
