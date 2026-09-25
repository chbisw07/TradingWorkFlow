// @vitest-environment node
import { afterEach, expect, test, vi } from "vitest";
import { GET, PUT } from "../src/app/api/v1/settings/[...path]/route";
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
          body: "x".repeat(4097),
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
