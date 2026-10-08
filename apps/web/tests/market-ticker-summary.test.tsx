import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MarketTickerSummary } from "../src/components/shell/market-ticker-summary";

function item(
  code: string,
  value: number | null,
  change: number | null,
  freshness = "CURRENT",
  available = true,
) {
  return {
    code,
    display_name: code,
    value,
    change_percent: change,
    source: available ? "dhan" : null,
    source_time: available ? "2026-10-08T05:00:00Z" : null,
    freshness,
    availability: available ? "AVAILABLE" : "UNAVAILABLE",
  };
}

function payload(overrides = {}) {
  return {
    nifty: item("NIFTY", 24998.75, 0.42),
    banknifty: item("BANKNIFTY", 52316.2, -0.58),
    india_vix: item("INDIA VIX", 13.25, 0),
    refresh_after_seconds: 300,
    ...overrides,
  };
}

function respond(value: object) {
  return Promise.resolve(
    new Response(JSON.stringify(value), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

test("shows honest loading placeholders, then all normalized values and signed changes", async () => {
  let resolve!: (response: Response) => void;
  const fetcher = vi.fn(
    () =>
      new Promise<Response>((done) => {
        resolve = done;
      }),
  );
  vi.stubGlobal("fetch", fetcher);
  render(<MarketTickerSummary />);
  expect(screen.getByLabelText("NIFTY value —")).toBeVisible();
  expect(screen.getByLabelText("BANKNIFTY value —")).toBeVisible();
  expect(screen.getByLabelText("INDIA VIX value —")).toBeVisible();
  resolve(
    new Response(JSON.stringify(payload()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  expect(
    await screen.findByLabelText("NIFTY one day change +0.42%"),
  ).toHaveClass("positive");
  expect(screen.getByLabelText("BANKNIFTY one day change -0.58%")).toHaveClass(
    "negative",
  );
  expect(screen.getByLabelText("INDIA VIX one day change 0.00%")).toHaveClass(
    "neutral",
  );
  expect(screen.getByLabelText("NIFTY value 24,998.75")).toBeVisible();
  expect(fetcher).toHaveBeenCalledTimes(1);
});

test("one unavailable item does not blank successful peers", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      respond(
        payload({
          india_vix: item("INDIA VIX", null, null, "UNKNOWN", false),
        }),
      ),
    ),
  );
  render(<MarketTickerSummary />);
  expect(await screen.findByLabelText("NIFTY value 24,998.75")).toBeVisible();
  expect(screen.getByLabelText("INDIA VIX value —")).toBeVisible();
  expect(screen.getByLabelText("INDIA VIX change unavailable")).toBeVisible();
});

test("stale state is visible and accessible", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      respond(
        payload({
          nifty: item("NIFTY", 24998.75, 0.42, "STALE"),
        }),
      ),
    ),
  );
  render(<MarketTickerSummary />);
  expect(await screen.findByLabelText("NIFTY data is stale")).toHaveTextContent(
    "Stale",
  );
});

test("rerender does not duplicate the shell request", async () => {
  const fetcher = vi.fn(() => respond(payload()));
  vi.stubGlobal("fetch", fetcher);
  const view = render(<MarketTickerSummary />);
  await screen.findByLabelText("NIFTY value 24,998.75");
  view.rerender(<MarketTickerSummary />);
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
});
