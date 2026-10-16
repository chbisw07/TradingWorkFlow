import { expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { ScannerWatchlistSelector } from "../src/components/scanner/watchlist-selector";
import { watchlistReadinessLabel, type Watchlist } from "../src/lib/watchlists";

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

function Harness({ extra = [] }: { extra?: Watchlist[] }) {
  const [selected, setSelected] = useState("");
  return (
    <ScannerWatchlistSelector
      lists={[personal, builtIn, ...extra]}
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

test("ranked F&O built-ins are discoverable and selection preserves the lock", () => {
  const ranked = [50, 100, 200].map((size) => ({
    ...builtIn,
    id: `00000000-0000-0000-0000-${String(size).padStart(12, "0")}`,
    name: `F&O Liquidity ${size}`,
    count: size,
    system_code: `FNO_LIQUIDITY_${size}`,
    readiness: {
      state: "READY",
      completed_sessions_collected: 3,
      minimum_sessions_required: 3,
      lookback_sessions_target: 20,
      as_of_date: "2026-10-12",
      generated_at: "2026-10-12T10:15:00Z",
      stale: false,
      methodology_version: "v1",
      last_error_category: null,
      last_success_at: "2026-10-12T10:15:00Z",
      earliest_session: "2026-10-08",
      latest_session: "2026-10-12",
      observation_count_used: 3,
    },
  })) as Watchlist[];
  render(<Harness extra={ranked} />);
  fireEvent.click(
    screen.getByRole("button", { name: "Watchlist: Choose watchlist" }),
  );
  fireEvent.change(screen.getByRole("textbox", { name: "Search watchlists" }), {
    target: { value: "liquidity" },
  });
  for (const size of [50, 100, 200]) {
    expect(
      screen.getByRole("button", {
        name: `F&O Liquidity ${size}, ${size} constituents, built-in read-only, ${size} constituents · Ready`,
      }),
    ).toHaveTextContent("🔒");
  }
  fireEvent.click(
    screen.getByRole("button", {
      name: "F&O Liquidity 50, 50 constituents, built-in read-only, 50 constituents · Ready",
    }),
  );
  expect(
    screen.getByRole("button", { name: /Watchlist: F&O Liquidity 50/ }),
  ).toHaveTextContent("🔒");
});

test("ranked readiness labels distinguish building, stale, credentials and provider failure", () => {
  const ranked = {
    ...builtIn,
    id: "00000000-0000-0000-0000-000000000050",
    name: "F&O Liquidity 50",
    system_code: "FNO_LIQUIDITY_50",
    count: 0,
    enabled: false,
    availability: "UNAVAILABLE",
    readiness: {
      state: "BUILDING_HISTORY",
      completed_sessions_collected: 2,
      minimum_sessions_required: 3,
      lookback_sessions_target: 20,
      as_of_date: null,
      generated_at: null,
      stale: false,
      methodology_version: "v1",
      last_error_category: null,
      last_success_at: null,
      earliest_session: null,
      latest_session: null,
      observation_count_used: null,
    },
  } as Watchlist;
  render(<Harness extra={[ranked]} />);
  fireEvent.click(
    screen.getByRole("button", { name: "Watchlist: Choose watchlist" }),
  );
  const item = screen.getByRole("button", {
    name: /F&O Liquidity 50.*Accumulating history/,
  });
  expect(item).toBeDisabled();
  expect(item).toHaveTextContent("Accumulating history · 2/3 sessions");
  expect(
    watchlistReadinessLabel({
      ...ranked,
      readiness: {
        ...ranked.readiness!,
        state: "STALE",
        as_of_date: "2026-10-11",
      },
      count: 50,
      enabled: true,
    }),
  ).toContain("Stale");
  expect(
    watchlistReadinessLabel({
      ...ranked,
      readiness: { ...ranked.readiness!, state: "CREDENTIAL_UNAVAILABLE" },
    }),
  ).toBe("Credentials unavailable");
  expect(
    watchlistReadinessLabel({
      ...ranked,
      readiness: { ...ranked.readiness!, state: "PROVIDER_UNAVAILABLE" },
    }),
  ).toBe("Provider temporarily unavailable · 2/3 sessions");
});
