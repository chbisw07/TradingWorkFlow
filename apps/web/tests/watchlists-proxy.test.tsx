// @vitest-environment node
import { afterEach, expect, test, vi } from "vitest";
import { GET, POST } from "../src/app/api/v1/watchlists/[[...path]]/route";
vi.mock("../src/lib/auth-server", () => ({
  apiOrigin: () => "http://api.example",
}));
afterEach(() => vi.unstubAllGlobals());
const id = "00000000-0000-0000-0000-000000000001";
test("watchlists proxy preserves owner session, strips unrelated credentials and cannot execute", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(() => Promise.resolve(Response.json([])));
  vi.stubGlobal("fetch", fetcher);
  const response = await POST(
    new Request("https://web.example/api/v1/watchlists", {
      method: "POST",
      headers: {
        Cookie: "twf_session=valid-session; other=private",
        Authorization: "not-forwarded",
        Origin: "https://web.example",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name: "Core" }),
    }),
    { params: Promise.resolve({}) },
  );
  expect(response.status).toBe(200);
  const [url, options] = fetcher.mock.calls[0];
  expect(url).toBe("http://api.example/api/v1/watchlists");
  expect([...options.headers.keys()].sort()).toEqual([
    "content-type",
    "cookie",
    "origin",
  ]);
  expect(options.headers.get("cookie")).toBe("twf_session=valid-session");
  expect(response.headers.get("Cache-Control")).toBe("no-store");
  for (const action of ["submit", "confirm", "dispatch", "delete"]) {
    const blocked = await POST(
      new Request(`https://web.example/api/v1/watchlists/${id}/${action}`, {
        method: "POST",
      }),
      { params: Promise.resolve({ path: [id, action] }) },
    );
    expect(blocked.status).toBe(404);
  }
  expect(fetcher).toHaveBeenCalledTimes(1);
});
test("watchlist export preserves CSV content and input stays bounded", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response("canonical_symbol\nNSE:RELIANCE"));
  vi.stubGlobal("fetch", fetcher);
  const response = await GET(
    new Request(`https://web.example/api/v1/watchlists/${id}/export`),
    { params: Promise.resolve({ path: [id, "export"] }) },
  );
  expect(response.headers.get("content-type")).toBe("text/csv");
  expect(await response.text()).toContain("NSE:RELIANCE");
  const large = await POST(
    new Request("https://web.example/api/v1/watchlists", {
      method: "POST",
      body: "x".repeat(40001),
    }),
    { params: Promise.resolve({}) },
  );
  expect(large.status).toBe(413);
  expect(fetcher).toHaveBeenCalledTimes(1);
});
