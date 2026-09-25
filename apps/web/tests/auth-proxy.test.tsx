// @vitest-environment node
import { afterEach, expect, test, vi } from "vitest";
import { GET, POST } from "../src/app/api/v1/auth/[action]/route";

vi.mock("../src/lib/auth-server", () => ({
  apiOrigin: () => "http://api.example",
}));
afterEach(() => vi.unstubAllGlobals());

test.each([
  ["twf_session=abc-_123", "twf_session=abc-_123"],
  ["__Host-twf_session=prod-_123", "__Host-twf_session=prod-_123"],
  [
    "preference=dark; twf_session=abc; analytics=private; other=secret",
    "twf_session=abc",
  ],
  [
    'broken; invalid=%ZZ; =bad; twf_session=Ab%2FC==; bad="unterminated',
    "twf_session=Ab%2FC==",
  ],
  ["twf_session=dev; __Host-twf_session=prod", "__Host-twf_session=prod"],
  ["__Host-twf_session=prod; twf_session=dev", "__Host-twf_session=prod"],
  ["preference=dark; analytics=private", null],
  ["", null],
  ["twf_session=one; twf_session=two", null],
  ["__Host-twf_session=one; __Host-twf_session=two; twf_session=dev", null],
  ["twf_session=bad value", null],
])("filters cookies safely: %s", async (cookie, expected) => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ id: "test-user" }));
  vi.stubGlobal("fetch", fetcher);
  await GET(
    new Request("https://web.example/api/v1/auth/me", {
      headers: { Cookie: cookie, "X-Unrelated": "private" },
    }),
    { params: Promise.resolve({ action: "me" }) },
  );
  expect(fetcher).toHaveBeenCalledOnce();
  const headers: Headers = fetcher.mock.calls[0][1].headers;
  expect(headers.get("Cookie")).toBe(expected);
  expect(headers.has("X-Unrelated")).toBe(false);
});

test.each([
  ["login", 200],
  ["logout", 200],
  ["me", 200],
  ["login", 429],
])(
  "preserves %s status %s, body and safe headers only",
  async (action, status) => {
    const body =
      status === 429
        ? '{"error":{"code":"HTTP_429","message":"Too Many Requests","request_id":"test-id","details":null}}'
        : action === "logout"
          ? '{"logged_out":true}'
          : '{"id":"test-user","username":"alice","display_name":"Alice"}';
    const cookies =
      action === "me" || status === 429
        ? []
        : [
            `twf_session=${action === "logout" ? "" : "test-only-token"}; HttpOnly; Path=/; SameSite=Strict`,
          ];
    const upstream = new Response(body, {
      status,
      headers: {
        "X-Request-ID": "test-id",
        "X-Internal-Secret": "never-forward",
        ...(status === 429 ? { "Retry-After": "60" } : {}),
      },
    });
    for (const cookie of cookies) upstream.headers.append("Set-Cookie", cookie);
    const fetcher = vi.fn().mockResolvedValue(upstream);
    vi.stubGlobal("fetch", fetcher);
    const request = new Request(`https://web.example/api/v1/auth/${action}`, {
      method: action === "me" ? "GET" : "POST",
      headers: {
        Cookie: "unrelated=private; twf_session=test-only-token",
        Origin: "https://web.example",
        "Content-Type": "application/json",
      },
      ...(action === "login"
        ? { body: '{"username":"alice","password":"test-only-password"}' }
        : {}),
    });
    const response = await (action === "me" ? GET : POST)(request, {
      params: Promise.resolve({ action }),
    });
    expect(fetcher.mock.calls[0][0]).toBe(
      `http://api.example/api/v1/auth/${action}`,
    );
    expect(fetcher.mock.calls[0][1].headers.get("Cookie")).toBe(
      "twf_session=test-only-token",
    );
    expect(fetcher.mock.calls[0][1].headers.get("Origin")).toBe(
      "https://web.example",
    );
    expect(response.status).toBe(status);
    expect(await response.text()).toBe(body);
    expect(response.headers.get("X-Request-ID")).toBe("test-id");
    expect(response.headers.get("Retry-After")).toBe(
      status === 429 ? "60" : null,
    );
    expect(response.headers.getSetCookie()).toEqual(cookies);
    expect(response.headers.has("X-Internal-Secret")).toBe(false);
    expect(response.headers.get("Cache-Control")).toBe("no-store");
  },
);
