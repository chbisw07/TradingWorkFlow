// @vitest-environment node
import { afterEach, expect, test, vi } from "vitest";
import { GET } from "../src/app/api/v1/services/route";
vi.mock("../src/lib/auth-server", () => ({
  apiOrigin: () => "http://api.example",
}));
afterEach(() => vi.unstubAllGlobals());

test("service proxy sends only the selected session and safe correlation to the TWF API", async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ services: [] }));
  vi.stubGlobal("fetch", fetcher);
  const response = await GET(
    new Request("https://web.example/api/v1/services?endpoint=evil", {
      headers: {
        Cookie: "other=secret; twf_session=dev; __Host-twf_session=prod",
        "X-Request-ID": "service-42",
        Authorization: "secret",
        "X-User-ID": "other-user",
      },
    }),
  );
  const [url, options] = fetcher.mock.calls[0];
  expect(url).toBe("http://api.example/api/v1/services");
  expect([...options.headers.keys()].sort()).toEqual([
    "cookie",
    "x-request-id",
  ]);
  expect(options.headers.get("cookie")).toBe("__Host-twf_session=prod");
  expect(options.redirect).toBe("error");
  expect(response.headers.get("X-Request-ID")).toBe("service-42");
  expect(response.headers.get("Cache-Control")).toBe("no-store");
});

test("duplicate cookies fail closed and local errors use a safe correlated envelope", async () => {
  const fetcher = vi.fn().mockRejectedValue(new Error("private-secret"));
  vi.stubGlobal("fetch", fetcher);
  const response = await GET(
    new Request("https://web.example/api/v1/services", {
      headers: {
        Cookie: "twf_session=one; twf_session=two",
        "X-Request-ID": "x".repeat(65),
      },
    }),
  );
  expect(fetcher.mock.calls[0][1].headers.get("cookie")).toBeNull();
  expect(response.status).toBe(503);
  const result = await response.json();
  expect(result).toEqual({
    error: {
      code: "SERVICE_UNAVAILABLE",
      message: "Service status unavailable",
      request_id: response.headers.get("X-Request-ID"),
      details: null,
    },
  });
  expect(result.error.request_id).toBe(response.headers.get("X-Request-ID"));
  expect(result.error.request_id.length).toBeLessThanOrEqual(64);
  expect(JSON.stringify(result)).not.toContain("private-secret");
});
