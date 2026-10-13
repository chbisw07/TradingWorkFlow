import { expect, test, type Page } from "@playwright/test";

const energyId = "77777777-7777-4777-8777-777777777777";
const userId = "88888888-8888-4888-8888-888888888888";
const liquidityId = "99999999-9999-4999-8999-999999999999";
const watchlistBase = {
  description: "",
  favorite: false,
  archived: false,
  updated_at: null,
  revision: 1,
  enabled: true,
  availability: "READY",
  pending_reason: null,
  expected_count: null,
  instrument_type_summary: ["EQUITY"],
  source_reference: null,
  source_received_at: null,
  freshness: "CURRENT",
};
const lists = [
  {
    ...watchlistBase,
    id: userId,
    name: "My Core",
    count: 3,
    ownership_kind: "USER",
    read_only: false,
    system_code: null,
  },
  {
    ...watchlistBase,
    id: energyId,
    name: "Nifty Energy",
    count: 10,
    ownership_kind: "SYSTEM",
    read_only: true,
    system_code: "NIFTY_ENERGY",
  },
  {
    ...watchlistBase,
    id: liquidityId,
    name: "F&O Liquidity 50",
    count: 0,
    ownership_kind: "SYSTEM",
    read_only: true,
    enabled: false,
    availability: "UNAVAILABLE",
    system_code: "FNO_LIQUIDITY_50",
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
  },
];

async function signIn(page: Page, baseURL: string, username: string) {
  const login = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: baseURL },
    data: {
      username,
      password: "test-only-browser-password",
    },
  });
  expect(login.ok(), `${login.status()} ${await login.text()}`).toBe(true);
}

test("Futures uses shared catalogs after an auxiliary failure and keeps Custom/Watchlist state distinct", async ({
  page,
  baseURL,
}, info) => {
  test.setTimeout(90000);
  await signIn(page, baseURL!, `discovery-${info.project.name}`);
  const headers = { Origin: baseURL! };
  const createFutures = await page.request.post(
    "/api/v1/scanner/derivatives/templates",
    {
      headers,
      data: {
        template_schema_version: 1,
        name: "My Futures Activity",
        horizon: "INTRADAY",
        description: "Explicit Futures recipe",
        recipe: {
          scanner_type: "DERIVATIVES",
          instrument_scope: "FUTURES",
          expiry_mode: "NEAREST",
          strike_window: 10,
          predicates: [
            { field: "volume_percentile", operator: ">=", value: 75 },
          ],
        },
      },
    },
  );
  expect(createFutures.ok()).toBe(true);
  const createOptions = await page.request.post(
    "/api/v1/scanner/derivatives/templates",
    {
      headers,
      data: {
        template_schema_version: 1,
        name: "My Options Activity",
        horizon: "INTRADAY",
        description: "Explicit Options recipe",
        recipe: {
          scanner_type: "DERIVATIVES",
          instrument_scope: "OPTIONS",
          expiry_mode: "NEAREST",
          strike_window: 10,
          predicates: [
            { field: "option_type", operator: "equals", value: "CE" },
          ],
        },
      },
    },
  );
  expect(createOptions.ok()).toBe(true);
  const actualCatalog = await page.request.get(
    "/api/v1/scanner/derivatives/templates",
  );
  expect(actualCatalog.ok()).toBe(true);
  const actual = await actualCatalog.json();
  expect(
    actual.built_in.filter(
      (item: { instrument_scope: string }) =>
        item.instrument_scope === "FUTURES",
    ),
  ).toHaveLength(8);
  await page.route("**/api/v1/watchlists", async (route) => {
    if (route.request().method() === "GET")
      await route.fulfill({ json: lists });
    else await route.continue();
  });
  await page.route("**/api/v1/scanner/derivatives/saved", async (route) => {
    if (route.request().method() === "GET")
      await route.fulfill({
        status: 503,
        json: { error: { message: "Unavailable" } },
      });
    else await route.continue();
  });
  await page.route(
    `**/api/v1/scanner/derivatives/futures/watchlists/${energyId}/eligible`,
    (route) =>
      route.fulfill({
        json: {
          watchlist_id: energyId,
          members: 10,
          eligible: 4,
          excluded: [
            "NOFUT1",
            "NOFUT2",
            "NOFUT3",
            "NOFUT4",
            "NOFUT5",
            "NOFUT6",
          ],
          symbols: ["RELIANCE", "HDFCBANK", "INFY", "TCS"],
          max_underlyings: 50,
        },
      }),
  );
  const submitted: Array<{
    universe: { source: string; symbols: string[]; watchlist_id?: string };
    filters: { field: string }[];
  }> = [];
  await page.route("**/api/v1/scanner/derivatives/futures/runs", (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const config = route.request().postDataJSON();
    submitted.push(config);
    const watchlist = config.universe.source === "WATCHLIST";
    return route.fulfill({
      json: {
        id: "00000000-0000-4000-8000-000000000555",
        created_at: "2026-10-13T09:00:00Z",
        config,
        counts: {
          requested: config.universe.symbols.length,
          resolved: config.universe.symbols.length,
          contracts_evaluated: watchlist ? 4 : 0,
          not_evaluated: watchlist ? 0 : 3,
          matches: 0,
        },
        rows: [],
        underlyings: [],
      },
    });
  });
  await page.goto("/scanners");
  await page.getByRole("tab", { name: /Derivatives Scanner/ }).click();
  await page.getByRole("button", { name: /Scan Templates/ }).click();
  const optionsMenu = page.getByRole("menu", { name: "Scan Templates" });
  await expect(
    optionsMenu.getByRole("menuitem", { name: /Liquid ATM Options/ }),
  ).toBeVisible();
  await expect(
    optionsMenu.getByRole("menuitem", { name: "My Options Activity" }),
  ).toBeVisible();
  await expect(optionsMenu.getByText("Futures Momentum Long")).toHaveCount(0);
  await expect(optionsMenu.getByText("My Futures Activity")).toHaveCount(0);
  await optionsMenu.press("Escape");
  await page.getByRole("button", { name: "Futures", exact: true }).click();
  const future = page.getByRole("tabpanel", { name: "Futures Scanner" });
  await expect(
    future.getByText("Enter custom underlyings or choose a watchlist."),
  ).toBeVisible();
  await future.getByLabel("NSE underlyings").fill("NIFTY, RELIANCE, HDFCBANK");
  await expect(
    future.getByText(/Custom underlyings are selected/),
  ).toBeVisible();
  await expect(
    future.getByText("Choose a watchlist from the toolbar above."),
  ).toHaveCount(0);
  await future.getByRole("button", { name: "Watchlist", exact: true }).click();
  await expect(
    future.getByText("Choose a watchlist from the toolbar above."),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Watchlist: Choose watchlist" })
    .click();
  const picker = page.getByRole("dialog", { name: "Select Watchlist" });
  await expect(picker.getByText("My Watchlists 1")).toBeVisible();
  await expect(picker.getByText("Built-in Watchlists 2")).toBeVisible();
  await expect(
    picker.getByRole("button", { name: "My Core (3)" }),
  ).toBeVisible();
  await expect(
    picker.getByRole("button", {
      name: /F&O Liquidity 50.*Building liquidity history/,
    }),
  ).toBeDisabled();
  await picker
    .getByRole("button", {
      name: /Nifty Energy, 10 constituents, built-in read-only/,
    })
    .click();
  await expect(future.getByText("4/10 futures eligible")).toBeVisible();
  await expect(future.getByText("6 excluded")).toBeVisible();
  await expect(
    future.getByLabel("Active Futures scan configuration"),
  ).toContainText("Nifty Energy");
  await page.getByRole("button", { name: /Scan Templates/ }).click();
  const futuresMenu = page.getByRole("menu", { name: "Scan Templates" });
  await expect(
    futuresMenu.getByRole("menuitem", {
      name: /Intraday — Futures Momentum Long/,
    }),
  ).toBeVisible();
  await expect(
    futuresMenu.getByRole("menuitem", {
      name: /Positional — Futures Trend Long/,
    }),
  ).toBeVisible();
  await expect(
    futuresMenu.getByRole("menuitem", { name: "My Futures Activity" }),
  ).toBeVisible();
  await expect(futuresMenu.getByText("My Options Activity")).toHaveCount(0);
  await futuresMenu
    .getByRole("menuitem", { name: /Intraday — Futures Momentum Long/ })
    .click();
  await expect(
    future.getByLabel("Active Futures scan configuration"),
  ).toContainText("Nifty Energy");
  await expect(
    future.getByLabel("Active Futures scan configuration"),
  ).toContainText("Volume Percentile");
  await expect(
    future.getByLabel("Active Futures scan configuration"),
  ).toContainText("OI Percentile");
  await expect(
    future.getByLabel("Active Futures scan configuration"),
  ).toContainText("Spot 1D Direction");
  expect(submitted).toHaveLength(0);
  await future.getByRole("button", { name: "Run Scan" }).click();
  await expect(
    future.getByText("No contracts matched these filters."),
  ).toBeVisible();
  expect(submitted[0].universe).toEqual({
    source: "WATCHLIST",
    watchlist_id: energyId,
    symbols: ["RELIANCE", "HDFCBANK", "INFY", "TCS"],
  });
  await future.getByRole("button", { name: "Custom", exact: true }).click();
  await expect(
    future.getByText(/Custom underlyings are selected/),
  ).toBeVisible();
  await page.getByRole("button", { name: /Scan Templates/ }).click();
  await page
    .getByRole("menu", { name: "Scan Templates" })
    .getByRole("menuitem", { name: "My Futures Activity" })
    .click();
  await expect(
    future.getByLabel("Active Futures scan configuration"),
  ).toContainText("NIFTY, RELIANCE, HDFCBANK");
  await expect(
    future.getByLabel("Active Futures scan configuration"),
  ).toContainText("Volume Percentile >= 75");
  expect(submitted).toHaveLength(1);
  await future.getByRole("button", { name: "Run Scan" }).click();
  await expect(
    future.getByText(
      "Contracts could not be evaluated because required evidence was unavailable.",
    ),
  ).toBeVisible();
  expect(submitted[1].universe.source).toBe("CUSTOM");
  expect(submitted[1].universe.symbols).toEqual([
    "NIFTY",
    "RELIANCE",
    "HDFCBANK",
  ]);
  if (info.project.name === "chromium-1440") {
    page.once("dialog", (dialog) => void dialog.accept("Saved Futures Parity"));
    await page.getByRole("button", { name: /Save Scan ▾/ }).click();
    await page.getByRole("menuitem", { name: /Save Scan/ }).click();
    await expect(future.getByText("Futures scan saved.")).toBeVisible();
    await page.getByRole("button", { name: "My Scans" }).click();
    await expect(future.getByText("Saved Futures Parity")).toBeVisible();
  }
  await page.getByRole("button", { name: "Options", exact: true }).click();
  await expect(
    page.getByRole("tabpanel", { name: "Derivatives Scanner" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Futures", exact: true }).click();
  await expect(future.getByLabel("NSE underlyings")).toHaveValue(
    "NIFTY, RELIANCE, HDFCBANK",
  );
});

test("Futures catalog failures are visible and do not become false zero counts", async ({
  page,
  baseURL,
}, info) => {
  test.skip(
    info.project.name !== "chromium-1440",
    "One representative viewport",
  );
  await signIn(page, baseURL!, `watchlist-${info.project.name}`);
  await page.route("**/api/v1/watchlists", (route) =>
    route.fulfill({ status: 503, json: { error: { message: "Unavailable" } } }),
  );
  await page.route("**/api/v1/scanner/derivatives/templates", (route) =>
    route.fulfill({ status: 503, json: { error: { message: "Unavailable" } } }),
  );
  await page.goto("/scanners");
  await page.getByRole("tab", { name: /Derivatives Scanner/ }).click();
  await page.getByRole("button", { name: "Futures", exact: true }).click();
  await page.getByRole("button", { name: /Watchlists unavailable/ }).click();
  const picker = page.getByRole("dialog", { name: "Select Watchlist" });
  await expect(picker.getByRole("alert")).toContainText(
    "Watchlists unavailable",
  );
  await expect(picker.getByText("My Watchlists 0")).toHaveCount(0);
  await page.getByRole("button", { name: /Scan Templates/ }).click();
  const menu = page.getByRole("menu", { name: "Scan Templates" });
  await expect(menu.getByRole("alert")).toContainText(
    "Scan templates unavailable",
  );
  await expect(menu.getByText("Intraday")).toHaveCount(0);
});
