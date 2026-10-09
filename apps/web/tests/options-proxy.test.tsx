// @vitest-environment node
import { afterEach, expect, test, vi } from "vitest";
import { GET } from "../src/app/api/v1/options/[...path]/route";
import { POST } from "../src/app/api/v1/brokers/[...path]/route";
vi.mock("../src/lib/auth-server", () => ({
  apiOrigin: () => "http://api.example",
}));
afterEach(() => vi.unstubAllGlobals());
test("chain proxy forwards only session, bounded queries and no-store semantics", async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ rows: [] }));
  vi.stubGlobal("fetch", fetcher);
  const response = await GET(
    new Request(
      "https://web.example/api/v1/options/chain?underlying=NIFTY&expiry=2026-10-13&around_atm=10",
      {
        headers: {
          Cookie: `other=secret; twf_session=${"a".repeat(43)}`,
          Authorization: "private",
        },
      },
    ),
    { params: Promise.resolve({ path: ["chain"] }) },
  );
  expect(response.status).toBe(200);
  expect(response.headers.get("Cache-Control")).toBe("no-store");
  expect(fetcher.mock.calls[0][1].headers.get("Authorization")).toBeNull();
  expect(fetcher.mock.calls[0][1].headers.get("Cookie")).toBe(
    `twf_session=${"a".repeat(43)}`,
  );
  expect(
    (
      await GET(new Request("https://web.example/api/v1/options/secret"), {
        params: Promise.resolve({ path: ["secret"] }),
      })
    ).status,
  ).toBe(404);
  expect(
    (
      await GET(
        new Request(
          "https://web.example/api/v1/options/chain?q=" + "a".repeat(1100),
        ),
        { params: Promise.resolve({ path: ["chain"] }) },
      )
    ).status,
  ).toBe(414);
  expect(fetcher).toHaveBeenCalledTimes(1);
});
test.each(["option-capabilities", "option-preview"])(
  "Broker proxy permits exact canonical %s only",
  async (action) => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({}));
    vi.stubGlobal("fetch", fetcher);
    const path = [
      "accounts",
      "11111111-1111-4111-8111-111111111111",
      "order-entry",
      action,
    ];
    const body = {
      contract: {
        exchange: "NFO",
        underlying_symbol: "NIFTY",
        expiry: "2026-10-13",
        strike: "22650",
        option_type: "PE",
      },
    };
    const r = await POST(
      new Request("https://web.example/api/v1/brokers/" + path.join("/"), {
        method: "POST",
        headers: {
          Origin: "https://web.example",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      }),
      { params: Promise.resolve({ path }) },
    );
    expect(r.status).toBe(200);
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual(body);
  },
);
