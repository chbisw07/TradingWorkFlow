// @vitest-environment node
import { afterEach, expect, test, vi } from "vitest";
import { GET, POST, PUT } from "../src/app/api/v1/settings/[...path]/route";
vi.mock("../src/lib/auth-server", () => ({
  apiOrigin: () => "http://api.example",
}));
afterEach(() => vi.unstubAllGlobals());
test("settings proxy forwards only session and original origin, preserving safe errors", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(
      Response.json(
        { error: { code: "HTTP_409" } },
        { status: 409, headers: { "X-Request-ID": "settings-conflict" } },
      ),
    );
  vi.stubGlobal("fetch", fetcher);
  const result = await PUT(
    new Request("https://web.example/api/v1/settings/values", {
      method: "PUT",
      headers: {
        Cookie: "private=other; twf_session=dev; __Host-twf_session=prod",
        Origin: "https://evil.example",
        "Content-Type": "application/json",
        "X-Actor": "owner",
      },
      body: JSON.stringify({ revision: 0, values: {} }),
    }),
    { params: Promise.resolve({ path: ["values"] }) },
  );
  const headers: Headers = fetcher.mock.calls[0][1].headers;
  expect(headers.get("Cookie")).toBe("__Host-twf_session=prod");
  expect(headers.get("Origin")).toBe("https://evil.example");
  expect(headers.get("X-Actor")).toBeNull();
  expect(fetcher.mock.calls[0][1].redirect).toBe("error");
  expect(result.status).toBe(409);
  expect(result.headers.get("Cache-Control")).toBe("no-store");
  expect(result.headers.get("X-Request-ID")).toBe("settings-conflict");
});
test("unsupported settings paths and oversized payloads never reach API", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  expect(
    (
      await GET(new Request("https://web.example/api/v1/settings/deploy"), {
        params: Promise.resolve({ path: ["deploy"] }),
      })
    ).status,
  ).toBe(404);
  expect(
    (
      await PUT(
        new Request("https://web.example/api/v1/settings/values", {
          method: "PUT",
          body: "x".repeat(12_289),
        }),
        { params: Promise.resolve({ path: ["values"] }) },
      )
    ).status,
  ).toBe(413);
  expect(fetcher).not.toHaveBeenCalled();
});
test("duplicate session cookies fail closed and network details are not exposed", async () => {
  const fetcher = vi
    .fn()
    .mockRejectedValue(new Error("private-upstream-secret"));
  vi.stubGlobal("fetch", fetcher);
  const response = await GET(
    new Request("https://web.example/api/v1/settings/values", {
      headers: { Cookie: "twf_session=one; twf_session=two" },
    }),
    { params: Promise.resolve({ path: ["values"] }) },
  );
  expect(fetcher.mock.calls[0][1].headers.get("Cookie")).toBeNull();
  expect(response.status).toBe(503);
  expect(await response.text()).not.toContain("private-upstream-secret");
});

test("forwards the generation-fenced generic MCP connect action", async () => {
  const fetcher = vi.fn().mockResolvedValue(
    Response.json({
      id: "83289728-6d31-4dc1-95d5-c53377f82a14",
      provider_id: "tapetide",
      generation: 1,
      state: "CONNECTED",
    }),
  );
  vi.stubGlobal("fetch", fetcher);
  const connectionId = "83289728-6d31-4dc1-95d5-c53377f82a14";
  const result = await POST(
    new Request(
      `https://web.example/api/v1/settings/mcp/connections/${connectionId}/connect`,
      {
        method: "POST",
        headers: {
          Cookie: "twf_session=dev",
          Origin: "https://web.example",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          generation: 0,
          api_key: "disposable-test-token",
        }),
      },
    ),
    {
      params: Promise.resolve({
        path: ["mcp", "connections", connectionId, "connect"],
      }),
    },
  );
  expect(result.status).toBe(200);
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(fetcher.mock.calls[0][0]).toBe(
    `http://api.example/api/v1/settings/mcp/connections/${connectionId}/connect`,
  );
  expect(fetcher.mock.calls[0][1].method).toBe("POST");
});
