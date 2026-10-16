import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { QueueWorkspace } from "../src/components/orders/queue-workspace";
import type { TWFQueueEntry } from "../src/lib/twf-queue";

const entry = (id: string, state: "READY" | "HELD") =>
  ({
    queue_entry_id: id,
    twf_order_id: `order-${id}`,
    queue_state: state,
    version: 1,
    admitted_at: "2026-10-15T10:00:00Z",
    order: {
      instrument: { symbol: `SYM-${id}`, asset_class: "EQUITY" },
      terms: { side: "BUY", quantity: 1, order_type: "LIMIT" },
    },
  }) as TWFQueueEntry;

afterEach(() => vi.unstubAllGlobals());

test("Queue opens newest, loads older without duplicates, and returns to newest", async () => {
  const fetcher = vi.fn(async (url: string) => {
    const params = new URL(url, "http://localhost").searchParams;
    if (params.get("cursor"))
      return Response.json({
        items: [entry("b", "HELD"), entry("a", "READY")],
        next_cursor: null,
        has_more: false,
      });
    if (params.get("state") === "READY")
      return Response.json({
        items: [entry("c", "READY"), entry("a", "READY")],
        next_cursor: null,
        has_more: false,
      });
    return Response.json({
      items: [entry("c", "READY"), entry("b", "HELD")],
      next_cursor: "opaque-cursor",
      has_more: true,
    });
  });
  vi.stubGlobal("fetch", fetcher);
  render(
    <QueueWorkspace
      selectedId={null}
      onSelect={vi.fn()}
      onViewOrder={vi.fn()}
      refreshKey={0}
    />,
  );
  const table = () => within(screen.getByRole("table"));
  await waitFor(() => expect(table().getAllByRole("row")).toHaveLength(3));
  expect(table().getByText("SYM-c")).toBeInTheDocument();
  expect(table().getByText("SYM-b")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Load older" }));
  await waitFor(() => expect(table().getAllByRole("row")).toHaveLength(4));
  expect(table().getAllByText("SYM-b")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Back to newest" }));
  await waitFor(() => expect(table().getAllByRole("row")).toHaveLength(3));
  fireEvent.click(screen.getByRole("button", { name: "Ready" }));
  await waitFor(() => expect(table().getByText("SYM-a")).toBeInTheDocument());
  expect(table().queryByText("SYM-b")).not.toBeInTheDocument();
  expect(
    fetcher.mock.calls.some(([url]) => String(url).includes("state=READY")),
  ).toBe(true);
});

test("invalid older-page cursor returns to newest without exposing server detail", async () => {
  let newestLoads = 0;
  const fetcher = vi.fn(async (url: string) => {
    const params = new URL(url, "http://localhost").searchParams;
    if (params.has("cursor")) {
      return Response.json(
        { error: { code: "INVALID_CURSOR", message: "raw backend detail" } },
        { status: 400 },
      );
    }
    newestLoads += 1;
    return Response.json({
      items: [entry(newestLoads === 1 ? "old" : "new", "READY")],
      next_cursor: newestLoads === 1 ? "expired-cursor" : null,
      has_more: newestLoads === 1,
    });
  });
  vi.stubGlobal("fetch", fetcher);
  render(
    <QueueWorkspace
      selectedId={null}
      onSelect={vi.fn()}
      onViewOrder={vi.fn()}
      refreshKey={0}
    />,
  );
  await screen.findByText("SYM-old");
  fireEvent.click(screen.getByRole("button", { name: "Load older" }));
  await screen.findByText("SYM-new");
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Queue page expired. Returned to newest entries.",
  );
  expect(screen.queryByText("SYM-old")).not.toBeInTheDocument();
  expect(screen.queryByText("raw backend detail")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Load older" }),
  ).not.toBeInTheDocument();
});
