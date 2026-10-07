import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ScannerWorkspace } from "../src/components/scanner/scanner-workspace";
import { initialConfig, scannerApi } from "../src/lib/scanner";

const catalog = {
  fields: [
    {
      field: "rsi",
      category: "Technical Indicators",
      label: "RSI (14)",
      enabled: true,
    },
    {
      field: "pe_ratio",
      category: "Fundamentals (TapTide)",
      label: "PE ratio",
      enabled: false,
    },
  ],
  templates: [{ name: "RSI Oversold", filters: initialConfig.filters }],
  universes: { CUSTOM: true, WATCHLIST: true, INDEX: false },
  universe_limitation: "No verified constituent source",
};
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
});
afterEach(() => vi.restoreAllMocks());
function mockFetch() {
  return vi.spyOn(global, "fetch").mockImplementation(async (url, init) => {
    const path = String(url);
    if (path.endsWith("/catalog")) return Response.json(catalog);
    if (path.endsWith("/runs") && init?.method === "POST")
      return Response.json({
        id: "run1",
        created_at: "2026-10-06T10:00:00Z",
        config: JSON.parse(String(init.body)),
        counts: {
          requested: 1,
          resolved: 0,
          evaluated: 0,
          not_evaluated: 1,
          matches: 0,
        },
        rows: [
          {
            symbol: "INFY",
            outcome: "NOT_EVALUATED",
            failure: "AUTH_REQUIRED",
          },
        ],
      });
    return Response.json([]);
  });
}
test("fresh Scanner UI separates derivatives and gates unsupported capabilities", async () => {
  mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "PE ratio" });
  expect(screen.getByRole("option", { name: "PE ratio" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Index" }));
  expect(screen.getByText("No verified constituent source")).toBeVisible();
  expect(screen.getByRole("button", { name: "Run Scan" })).toBeDisabled();
  fireEvent.click(screen.getByRole("tab", { name: /Derivatives Scanner/ }));
  expect(
    screen.getByText(/Derivative analytics are not available/),
  ).toBeVisible();
  expect(
    screen.queryByText("Candidates requiring review"),
  ).not.toBeInTheDocument();
});
test("explicit real Dhan payload and acquisition failures never become no-match", async () => {
  const fetch = mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "RSI (14)" });
  fireEvent.change(screen.getByLabelText("NSE symbols"), {
    target: { value: "INFY" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Run Scan" }));
  await screen.findByText(/Some instruments could not be evaluated/);
  const call = fetch.mock.calls.find(
    ([url, init]) => String(url).endsWith("/runs") && init?.method === "POST",
  )!;
  const body = JSON.parse(String(call[1]?.body));
  expect(body.data_mode).toBe("REAL");
  expect(body.provider).toBe("dhan");
  expect(body.universe.symbols).toEqual(["INFY"]);
  expect(body.filters[0]).toEqual(initialConfig.filters[0]);
});
test("filter chips edit conditions and clear all disables execution", async () => {
  mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "RSI (14)" });
  fireEvent.change(screen.getByLabelText("Value or comparison field"), {
    target: { value: "40" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Add Filter/ }));
  expect(
    screen.getByRole("button", { name: "Remove filter 2" }),
  ).toHaveTextContent("40");
  fireEvent.click(screen.getByRole("button", { name: "Remove filter 1" }));
  expect(
    screen.queryByRole("button", { name: "Remove filter 2" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Clear All" }));
  expect(screen.getByRole("button", { name: "Run Scan" })).toBeDisabled();
});
test("scanner tabs support keyboard navigation", async () => {
  mockFetch();
  render(<ScannerWorkspace />);
  fireEvent.click(screen.getByText("＋ Add / edit filter"));
  await screen.findByRole("option", { name: "RSI (14)" });
  const tab = screen.getByRole("tab", { name: /Equity \/ Index Scanner/ });
  tab.focus();
  fireEvent.keyDown(tab, { key: "ArrowRight" });
  await waitFor(() =>
    expect(
      screen.getByRole("tab", { name: /Derivatives Scanner/ }),
    ).toHaveAttribute("aria-selected", "true"),
  );
});
test("typed API failure is surfaced instead of inventing a result", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    Response.json({ error: { message: "Dhan unavailable" } }, { status: 503 }),
  );
  await expect(scannerApi("runs", "POST", initialConfig)).rejects.toThrow(
    "Dhan unavailable",
  );
});
