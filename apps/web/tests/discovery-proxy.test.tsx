// @vitest-environment node
import { afterEach, expect, test, vi } from "vitest";
import { GET, POST, PUT } from "../src/app/api/v1/discovery/[...path]/route";

vi.mock("../src/lib/auth-server", () => ({
  apiOrigin: () => "http://api.example",
}));
afterEach(() => vi.unstubAllGlobals());

test("discovery proxy allowlists routes and forwards only session, origin and content type", async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ items: [] }));
  vi.stubGlobal("fetch", fetcher);
  const response = await POST(
    new Request("https://web.example/api/v1/discovery/scans", {
      method: "POST",
      headers: {
        Cookie:
          "private=other; twf_session=dev-session; __Host-twf_session=prod-session",
        Origin: "https://web.example",
        "Content-Type": "application/json",
        Authorization: "secret",
      },
      body: JSON.stringify({ universe: ["TCS"] }),
    }),
    { params: Promise.resolve({ path: ["scans"] }) },
  );
  const [url, options] = fetcher.mock.calls[0];
  expect(url).toBe("http://api.example/api/v1/discovery/scans");
  expect([...options.headers.keys()].sort()).toEqual([
    "content-type",
    "cookie",
    "origin",
  ]);
  expect(options.headers.get("cookie")).toBe("__Host-twf_session=prod-session");
  expect(options.redirect).toBe("error");
  expect(response.headers.get("Cache-Control")).toBe("no-store");
});

test("discovery proxy allows owner-scoped read-only scan detail", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(
      Response.json({ summary: {}, matches: [], market_context: null }),
    );
  vi.stubGlobal("fetch", fetcher);
  const runId = "70000000-0000-0000-0000-000000000001";
  const response = await GET(
    new Request(`https://web.example/api/v1/discovery/scans/${runId}`),
    { params: Promise.resolve({ path: ["scans", runId] }) },
  );
  expect(response.status).toBe(200);
  expect(fetcher).toHaveBeenCalledWith(
    `http://api.example/api/v1/discovery/scans/${runId}`,
    expect.objectContaining({ method: "GET", cache: "no-store" }),
  );
});

test("discovery proxy forwards only bounded scan archive and restore mutations", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(() =>
      Promise.resolve(Response.json({ archived_at: null })),
    );
  vi.stubGlobal("fetch", fetcher);
  const runId = "70000000-0000-0000-0000-000000000001";

  for (const action of ["archive", "restore"]) {
    const response = await POST(
      new Request(
        `https://web.example/api/v1/discovery/scans/${runId}/${action}`,
        {
          method: "POST",
          headers: { Origin: "https://web.example" },
        },
      ),
      { params: Promise.resolve({ path: ["scans", runId, action] }) },
    );
    expect(response.status).toBe(200);
  }

  expect(fetcher.mock.calls.map((call) => call[0])).toEqual([
    `http://api.example/api/v1/discovery/scans/${runId}/archive`,
    `http://api.example/api/v1/discovery/scans/${runId}/restore`,
  ]);
  const rejected = await POST(
    new Request(`https://web.example/api/v1/discovery/scans/${runId}/delete`, {
      method: "POST",
    }),
    { params: Promise.resolve({ path: ["scans", runId, "delete"] }) },
  );
  expect(rejected.status).toBe(404);
  expect(fetcher).toHaveBeenCalledTimes(2);
});

test("discovery proxy rejects unsupported routes and oversized input", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  expect(
    (
      await GET(new Request("https://web.example/api/v1/discovery/admin"), {
        params: Promise.resolve({ path: ["admin"] }),
      })
    ).status,
  ).toBe(404);
  expect(
    (
      await PUT(
        new Request("https://web.example/api/v1/discovery/settings", {
          method: "PUT",
          body: "x".repeat(16_385),
        }),
        { params: Promise.resolve({ path: ["settings"] }) },
      )
    ).status,
  ).toBe(413);
  expect(fetcher).not.toHaveBeenCalled();
});

test("discovery proxy fails safely without exposing network details", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockRejectedValue(new Error("private-upstream")),
  );
  const response = await GET(
    new Request("https://web.example/api/v1/discovery/status"),
    { params: Promise.resolve({ path: ["status"] }) },
  );
  expect(response.status).toBe(503);
  expect(await response.text()).not.toContain("private-upstream");
});
