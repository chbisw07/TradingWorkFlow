// @vitest-environment node
import { afterEach, expect, test, vi } from "vitest";
import { GET, PATCH, POST } from "../src/app/api/v1/scanner/[[...path]]/route";

vi.mock("../src/lib/auth-server", () => ({
  apiOrigin: () => "http://api.example",
}));
afterEach(() => vi.unstubAllGlobals());

const id = "11111111-1111-4111-8111-111111111111";
const context = (path: string[]) => ({ params: Promise.resolve({ path }) });
const request = (path: string, method = "GET") =>
  new Request("https://web.example/api/v1/scanner/" + path, {
    method,
    headers: {
      Cookie: "other=private; twf_session=dev-session",
      Authorization: "secret",
      Origin: "https://web.example",
    },
  });

test("O4 catalog and owner-scoped routes forward through the scanner proxy", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(() =>
      Promise.resolve(Response.json({ fields: [{ field: "dte" }] })),
    );
  vi.stubGlobal("fetch", fetcher);
  for (const [method, path] of [
    ["GET", "derivatives/catalog"],
    ["GET", "derivatives/saved"],
    ["GET", "derivatives/runs"],
    ["GET", `derivatives/runs/${id}`],
    ["POST", "derivatives/saved"],
    ["POST", "derivatives/runs"],
    ["PATCH", `derivatives/saved/${id}`],
  ]) {
    const route = path.split("/");
    const handler = method === "GET" ? GET : method === "POST" ? POST : PATCH;
    const response = await handler(request(path, method), context(route));
    expect(response.status, `${method} ${path}`).toBe(200);
    expect(fetcher.mock.lastCall?.[0]).toBe(
      "http://api.example/api/v1/scanner/" + path,
    );
    expect(fetcher.mock.lastCall?.[1].headers.get("Cookie")).toBe(
      "twf_session=dev-session",
    );
    expect(fetcher.mock.lastCall?.[1].headers.get("Authorization")).toBeNull();
  }
  expect(fetcher).toHaveBeenCalledTimes(7);
});

test("scanner proxy rejects unlisted O4 paths without an upstream call", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  for (const path of [
    "derivatives/secret",
    "derivatives/runs/not-an-id",
    `derivatives/runs/${id}/delete`,
  ]) {
    expect((await GET(request(path), context(path.split("/")))).status).toBe(
      404,
    );
  }
  expect(fetcher).not.toHaveBeenCalled();
});
