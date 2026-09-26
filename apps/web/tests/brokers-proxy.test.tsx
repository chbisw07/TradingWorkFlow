// @vitest-environment node
import { afterEach, expect, test, vi } from "vitest";
import { GET as handler } from "../src/app/api/v1/brokers/[...path]/route";
const GET = (request: Request) =>
  handler(request, { params: Promise.resolve({ path: ["overview"] }) });
vi.mock("../src/lib/auth-server", () => ({
  apiOrigin: () => "http://api.example",
}));
afterEach(() => vi.unstubAllGlobals());

test("service proxy sends only the selected session and safe correlation to the TWF API", async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ services: [] }));
  vi.stubGlobal("fetch", fetcher);
  const response = await GET(
    new Request("https://web.example/api/v1/brokers/overview?endpoint=evil", {
      headers: {
        Cookie: "other=secret; twf_session=dev; __Host-twf_session=prod",
        "X-Request-ID": "service-42",
        Authorization: "secret",
        "X-User-ID": "other-user",
      },
    }),
  );
  const [url, options] = fetcher.mock.calls[0];
  expect(url).toBe("http://api.example/api/v1/brokers/overview");
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
    new Request("https://web.example/api/v1/brokers/overview", {
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
      message: "Broker observations unavailable",
      request_id: response.headers.get("X-Request-ID"),
      details: null,
    },
  });
  expect(result.error.request_id).toBe(response.headers.get("X-Request-ID"));
  expect(result.error.request_id.length).toBeLessThanOrEqual(64);
  expect(JSON.stringify(result)).not.toContain("private-secret");
});

test("proxy rejects command and arbitrary path routing before contacting API", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  for (const path of [
    ["connect"],
    ["accounts", "../auth/me"],
    ["accounts", "not-an-id"],
    ["orders"],
  ]) {
    const result = await handler(
      new Request("https://web.example/api/v1/brokers/test"),
      { params: Promise.resolve({ path }) },
    );
    expect(result.status).toBe(404);
  }
  expect(fetcher).not.toHaveBeenCalled();
});
