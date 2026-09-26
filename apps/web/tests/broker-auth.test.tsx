import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { RealBrokers } from "../src/components/brokers/real-brokers";
import { BrokerAuthComplete } from "../src/components/brokers/broker-auth-complete";
import { GET, POST } from "../src/app/api/v1/broker-auth/[...path]/route";

afterEach(() => vi.unstubAllGlobals());
const connection = {
  account: {
    broker_account_id: "00000000-0000-0000-0000-000000000001",
    label: "My Zerodha",
    configured: false,
    authentication_state: "NOT_CONFIGURED",
    provider_account_id: null,
    connection_generation: 0,
    configuration_revision: 1,
    read_health: "UNKNOWN",
  },
  can_configure: true,
  can_connect: false,
  can_disconnect: true,
  unavailable_reason: "Approved store unavailable.",
  callback_url: "https://example.test/api/v1/broker-auth/callback",
  cleanup_pending: 0,
};

test("real broker setup explains unavailable Connect without implying trading authority", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation(() => Promise.resolve(Response.json([connection]))),
  );
  render(<RealBrokers />);
  expect(
    await screen.findByRole("button", { name: "Connect Zerodha" }),
  ).toBeDisabled();
  expect(screen.getByText("Approved store unavailable.")).toBeVisible();
  expect(screen.getAllByText("TRADING DISABLED").length).toBeGreaterThan(0);
  expect(
    screen.getByText(
      /Real holdings, positions, orders and funds are not available/,
    ),
  ).toBeVisible();
});

test("configuration clears the secret input immediately and sends revision fences", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation((url: string) =>
      Promise.resolve(
        Response.json(
          url.endsWith("/configure") ? { configured: true } : [connection],
        ),
      ),
    );
  vi.stubGlobal("fetch", fetcher);
  render(<RealBrokers />);
  await screen.findByRole("button", { name: "Connect Zerodha" });
  fireEvent.click(screen.getByText("Configure Zerodha"));
  fireEvent.change(screen.getByLabelText("API key / app identifier"), {
    target: { value: "appkey" },
  });
  fireEvent.change(screen.getByLabelText("API secret"), {
    target: { value: "test-secret" },
  });
  fireEvent.submit(
    screen.getByRole("button", { name: "Save configuration" }).closest("form")!,
  );
  expect(screen.getByLabelText("API secret")).toHaveValue("");
  await waitFor(() =>
    expect(fetcher.mock.calls.some(([url]) => url.endsWith("/configure"))).toBe(
      true,
    ),
  );
  const call = fetcher.mock.calls.find(([url]) => url.endsWith("/configure"))!;
  expect(JSON.parse(call[1].body)).toEqual({
    api_key: "appkey",
    api_secret: "test-secret",
    expected_revision: 1,
    expected_generation: 0,
  });
  expect(document.body.textContent).not.toContain("test-secret");
});

test("clean landing finalizes once without reading query tokens", async () => {
  const fetcher = vi.fn().mockResolvedValue(
    Response.json({
      broker_account_id: connection.account.broker_account_id,
    }),
  );
  vi.stubGlobal("fetch", fetcher);
  render(<BrokerAuthComplete />);
  expect(
    await screen.findByText("Zerodha connected. Provider account verified."),
  ).toBeVisible();
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(fetcher.mock.calls[0][0]).toBe("/api/v1/broker-auth/finalize");
  expect(fetcher.mock.calls[0][1].body).toBe("{}");
});

test("auth proxy excludes callback and arbitrary destinations", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  for (const path of [
    ["callback"],
    ["accounts", "bad-id", "connect"],
    ["https://evil.test"],
  ]) {
    expect(
      (
        await GET(
          new Request("http://localhost/api/v1/broker-auth/" + path.join("/")),
          { params: Promise.resolve({ path }) },
        )
      ).status,
    ).toBe(404);
  }
  expect(fetcher).not.toHaveBeenCalled();
});

test("auth proxy forwards only scoped cookies and origin, bounds body size", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(Response.json({ broker_account_id: "id" }));
  vi.stubGlobal("fetch", fetcher);
  const request = new Request("http://localhost/api/v1/broker-auth/finalize", {
    method: "POST",
    headers: {
      Cookie: `twf_session=${"s".repeat(43)}; twf_broker_finalize=${"n".repeat(43)}; unrelated=secret`,
      Origin: "http://localhost",
      "Content-Type": "application/json",
    },
    body: "{}",
  });
  expect(
    (await POST(request, { params: Promise.resolve({ path: ["finalize"] }) }))
      .status,
  ).toBe(200);
  const headers = fetcher.mock.calls[0][1].headers as Headers;
  expect(headers.get("Cookie")).not.toContain("unrelated");
  expect(headers.get("Origin")).toBe("http://localhost");
  const large = new Request(request.url, {
    method: "POST",
    body: "x".repeat(8193),
  });
  expect(
    (await POST(large, { params: Promise.resolve({ path: ["finalize"] }) }))
      .status,
  ).toBe(413);
  expect(fetcher).toHaveBeenCalledTimes(1);
});
