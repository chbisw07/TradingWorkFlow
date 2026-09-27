import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { InstrumentSearch } from "../src/components/brokers/instrument-search";
import { GET, POST } from "../src/app/api/v1/broker-catalog/[...path]/route";

const id = "00000000-0000-0000-0000-000000000001";
const catalog = {
  account_label: "My Zerodha",
  provider_id: "zerodha",
  version: id,
  freshness: "FRESH",
  completeness: "COMPLETE",
  row_count: 1,
  fetched_at: "2026-09-27T00:00:00Z",
  verified_at: "2026-09-27T00:00:00Z",
  source_at: null,
  failure_code: null,
  refreshing: false,
  can_refresh: true,
  attempt_rejected_rows: 0,
};
const item = {
  id,
  native_id: "3",
  exchange_id: "13",
  symbol: "HAL26OCT4500CE",
  name: "HAL",
  exchange: "NFO",
  segment: "NFO-OPT",
  instrument_type: "CE",
  expiry: "2026-10-29",
  strike: "4500.00000000",
  derivative_kind: "CE",
  lot_size: 150,
  tick_size: "0.05000000",
  provider_id: "zerodha",
  catalog_version: id,
  fingerprint: "abc",
  canonical_id: null,
};
const result = {
  catalog,
  instruments: [item],
  matched: 1,
  limit: 25,
  offset: 0,
};
afterEach(() => vi.unstubAllGlobals());

test("instrument identity, provenance and read-only safety remain visible", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(result)));
  render(<InstrumentSearch accountId={id} />);
  expect(
    await screen.findByRole("rowheader", { name: new RegExp(item.symbol) }),
  ).toBeVisible();
  for (const text of [
    "LIVE DATA · READ ONLY",
    "TRADING DISABLED",
    "NFO-OPT",
    "2026-10-29",
    "4500",
    "150",
    "0.05",
  ])
    expect(
      screen.getAllByText(
        new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
      ).length,
    ).toBeGreaterThan(0);
  expect(screen.getByText("4500", { exact: true })).toBeVisible();
  expect(screen.getByText("0.05", { exact: true })).toBeVisible();
  expect(
    screen.getByText(/Unmapped · native identity retained/),
  ).not.toBeVisible();
  fireEvent.click(screen.getByText("Instrument details", { exact: true }));
  expect(screen.getByText(/Unmapped · native identity retained/)).toBeVisible();
  expect(
    screen.queryByRole("button", { name: /order/i }),
  ).not.toBeInTheDocument();
});

test("text and derivative filters reach the bounded typed search endpoint", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(() => Promise.resolve(Response.json(result)));
  vi.stubGlobal("fetch", fetcher);
  render(<InstrumentSearch accountId={id} />);
  await screen.findByRole("rowheader", { name: new RegExp(item.symbol) });
  for (const [label, value] of [
    ["Search instruments", "HAL"],
    ["Underlying / name", "HAL"],
    ["Segment", "NFO-OPT"],
    ["Expiry", "2026-10-29"],
    ["Strike", "4500"],
    ["Contract kind", "CE"],
  ])
    fireEvent.change(screen.getByLabelText(label, { exact: true }), {
      target: { value },
    });
  fireEvent.submit(screen.getByRole("form", { name: "Instrument filters" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  const url = new URL(fetcher.mock.calls[1][0], "https://twf.test");
  expect(Object.fromEntries(url.searchParams)).toEqual({
    limit: "25",
    text: "HAL",
    name: "HAL",
    segment: "NFO-OPT",
    expiry: "2026-10-29",
    strike: "4500",
    derivative_kind: "CE",
  });
});

for (const state of ["STALE", "UNAVAILABLE", "UNKNOWN"])
  test(`catalog ${state} and empty state are honest`, async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json({
          ...result,
          instruments: [],
          matched: 0,
          catalog: {
            ...catalog,
            version: state === "STALE" ? id : null,
            freshness: state,
            failure_code: state === "UNAVAILABLE" ? "AUTH_REQUIRED" : "TIMEOUT",
            can_refresh: false,
          },
        }),
      ),
    );
    render(<InstrumentSearch accountId={id} />);
    expect(await screen.findByText(state, { exact: true })).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Refresh catalog" }),
    ).toBeDisabled();
    expect(
      screen.getByText(
        state === "STALE"
          ? "No instruments match these filters."
          : "No catalog is available yet. Connect Zerodha and refresh the catalog.",
      ),
    ).toBeVisible();
    if (state === "UNAVAILABLE")
      expect(
        screen.getByText(/Authentication required to refresh/),
      ).toBeVisible();
  });

test("expired sessions produce a safe search error", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
  );
  render(<InstrumentSearch accountId={id} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Your session expired",
  );
});

test("catalog proxy restricts routes and query, preserves session and origin", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(() => Promise.resolve(Response.json(result)));
  vi.stubGlobal("fetch", fetcher);
  const params = {
    params: Promise.resolve({ path: ["accounts", id, "instruments"] }),
  };
  expect(
    (
      await GET(
        new Request("http://localhost/api?text=HAL&limit=25", {
          headers: { Cookie: `twf_session=${"a".repeat(43)}; other=private` },
        }),
        params,
      )
    ).status,
  ).toBe(200);
  expect(fetcher.mock.calls[0][0]).toContain(
    `/accounts/${id}/instruments?text=HAL&limit=25`,
  );
  expect(fetcher.mock.calls[0][1].headers.get("Cookie")).toBe(
    `twf_session=${"a".repeat(43)}`,
  );
  expect(
    (await GET(new Request("http://localhost/api?token=private"), params))
      .status,
  ).toBe(422);
  expect(
    (
      await GET(new Request("http://localhost/api"), {
        params: Promise.resolve({ path: ["orders"] }),
      })
    ).status,
  ).toBe(404);
  const post = await POST(
    new Request("http://localhost/api", {
      method: "POST",
      headers: { Origin: "http://localhost" },
    }),
    { params: Promise.resolve({ path: ["accounts", id, "refresh"] }) },
  );
  expect(post.status).toBe(200);
  expect(fetcher.mock.calls[1][1].headers.get("Origin")).toBe(
    "http://localhost",
  );
});

test("active search pins Next, Previous and refresh; query, filter and account reset it", async () => {
  const newer = "00000000-0000-0000-0000-000000000002";
  let activeVersion = id;
  const requests: URL[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        activeVersion = newer;
        return Response.json({ ...catalog, version: newer });
      }
      const url = new URL(input, "https://twf.test");
      requests.push(url);
      const version = url.searchParams.get("version") || activeVersion;
      const offset = Number(url.searchParams.get("offset") || 0);
      return Response.json({
        ...result,
        catalog: { ...catalog, version },
        matched: 30,
        offset,
        instruments: [
          {
            ...item,
            catalog_version: version,
            symbol: `${version === id ? "A" : "B"}-${offset}`,
          },
        ],
      });
    }),
  );
  const view = render(<InstrumentSearch accountId={id} />);
  await screen.findByRole("rowheader", { name: /A-0/ });
  expect(requests.at(-1)!.searchParams.has("version")).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Refresh catalog" }));
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests.at(-1)!.searchParams.get("version")).toBe(id);
  await screen.findByRole("rowheader", { name: /A-0/ });
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByRole("rowheader", { name: /A-25/ });
  expect(requests.at(-1)!.searchParams.get("version")).toBe(id);
  expect(requests.at(-1)!.searchParams.get("offset")).toBe("25");
  fireEvent.click(screen.getByRole("button", { name: "Previous" }));
  await screen.findByRole("rowheader", { name: /A-0/ });
  expect(requests.at(-1)!.searchParams.get("version")).toBe(id);
  expect(requests.at(-1)!.searchParams.get("offset")).toBe("0");
  for (const [label, value] of [
    ["Search instruments", "HAL"],
    ["Segment", "NFO-OPT"],
  ]) {
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("rowheader", { name: /-25/ });
    fireEvent.change(screen.getByLabelText(label, { exact: true }), {
      target: { value },
    });
    fireEvent.submit(screen.getByRole("form", { name: "Instrument filters" }));
    await screen.findByRole("rowheader", { name: /B-0/ });
    expect(requests.at(-1)!.searchParams.has("version")).toBe(false);
    expect(requests.at(-1)!.searchParams.has("offset")).toBe(false);
  }
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByRole("rowheader", { name: /B-25/ });
  expect(requests.at(-1)!.searchParams.get("version")).toBe(newer);
  view.rerender(<InstrumentSearch accountId={newer} />);
  await screen.findByRole("rowheader", { name: /B-0/ });
  expect(requests.at(-1)!.pathname).toContain(`/accounts/${newer}/`);
  expect(Object.fromEntries(requests.at(-1)!.searchParams)).toEqual({
    limit: "25",
  });
});
