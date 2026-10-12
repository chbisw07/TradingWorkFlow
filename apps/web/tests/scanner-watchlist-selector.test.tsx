import { expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { ScannerWatchlistSelector } from "../src/components/scanner/watchlist-selector";
import type { Watchlist } from "../src/lib/watchlists";

const base = {
  description: "",
  favorite: false,
  archived: false,
  updated_at: null,
  revision: 1,
  enabled: true,
  availability: "READY",
  pending_reason: null,
  expected_count: null,
  instrument_type_summary: [] as Watchlist["instrument_type_summary"],
  source_reference: null,
  source_received_at: null,
  freshness: "CURRENT",
} as const;
const personal = {
  ...base,
  id: "11111111-1111-4111-8111-111111111111",
  name: "My Core",
  count: 4,
  ownership_kind: "USER",
  read_only: false,
  system_code: null,
} as Watchlist;
const builtIn = {
  ...base,
  id: "22222222-2222-4222-8222-222222222222",
  name: "Nifty Pharma",
  count: 20,
  ownership_kind: "SYSTEM",
  read_only: true,
  system_code: "NIFTY_PHARMA",
} as Watchlist;

function Harness() {
  const [selected, setSelected] = useState("");
  return (
    <ScannerWatchlistSelector
      lists={[personal, builtIn]}
      selectedId={selected}
      onSelect={setSelected}
    />
  );
}

test("selection-only popover searches both sections locally and retains built-in lock", () => {
  const fetcher = vi.spyOn(global, "fetch");
  render(<Harness />);
  const trigger = screen.getByRole("button", {
    name: "Watchlist: Choose watchlist",
  });
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("My Watchlists")).toBeVisible();
  expect(screen.getByText("Built-in Watchlists")).toBeVisible();
  expect(screen.getByRole("button", { name: "My Core (4)" })).toBeVisible();
  const builtInOption = screen.getByRole("button", {
    name: "Nifty Pharma, 20 constituents, built-in read-only",
  });
  expect(builtInOption).toHaveTextContent("🔒");
  expect(screen.queryByText(/Create New Watchlist/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Manage Watchlists/)).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /Favorite/ }),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "Search watchlists" }), {
    target: { value: "pHaRmA" },
  });
  expect(
    screen.queryByRole("button", { name: "My Core (4)" }),
  ).not.toBeInTheDocument();
  expect(builtInOption).toBeVisible();
  fireEvent.click(builtInOption);
  expect(
    screen.getByRole("button", { name: /Watchlist: Nifty Pharma/ }),
  ).toHaveTextContent("🔒");
  expect(fetcher).not.toHaveBeenCalled();
  fetcher.mockRestore();
});

test("custom watchlist remains selectable after a local search", () => {
  render(<Harness />);
  fireEvent.click(
    screen.getByRole("button", { name: "Watchlist: Choose watchlist" }),
  );
  fireEvent.change(screen.getByRole("textbox", { name: "Search watchlists" }), {
    target: { value: "core" },
  });
  expect(
    screen.queryByRole("button", { name: /Nifty Pharma/ }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "My Core (4)" }));
  expect(
    screen.getByRole("button", { name: "Watchlist: My Core" }),
  ).toBeVisible();
});

test("keyboard focus can move through lists and Escape returns to trigger", () => {
  render(<Harness />);
  const trigger = screen.getByRole("button", {
    name: "Watchlist: Choose watchlist",
  });
  trigger.focus();
  fireEvent.click(trigger);
  const search = screen.getByRole("textbox", { name: "Search watchlists" });
  expect(search).toHaveFocus();
  fireEvent.keyDown(search, { key: "ArrowDown" });
  expect(screen.getByRole("button", { name: "My Core (4)" })).toHaveFocus();
  fireEvent.keyDown(document.activeElement as Element, { key: "ArrowDown" });
  expect(
    screen.getByRole("button", {
      name: "Nifty Pharma, 20 constituents, built-in read-only",
    }),
  ).toHaveFocus();
  fireEvent.keyDown(document.activeElement as Element, { key: "Escape" });
  expect(trigger).toHaveFocus();
  expect(trigger).toHaveAttribute("aria-expanded", "false");
});
