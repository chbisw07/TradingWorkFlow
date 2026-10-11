import { expect, test } from "@playwright/test";
import { chainFixture } from "../fixtures/option-chain";

const expiry = "2099-12-30";
const id = `NFO:NIFTY:${expiry}:25000:CE`;
const contract = {
  canonical_id: id,
  exchange: "NFO",
  segment: "NFO-OPT",
  underlying_symbol: "NIFTY",
  underlying_type: "INDEX",
  expiry,
  strike: "25000",
  option_type: "CE",
  lot_size: 65,
  display_symbol: "NIFTY 30 Dec 2099 25000 CE",
  tick_size: "0.05",
  is_active: true,
};
const market = {
  ltp: "125",
  bid: "124",
  ask: "126",
  spread: "2",
  spread_percent: "1.6",
  volume: "100000",
  open_interest: "500000",
  change_in_open_interest: "20000",
  implied_volatility: null,
  delta: null,
  theta: null,
};
const provenance = {
  provider: "dhan",
  market_source: "option-chain",
  received_at: "2026-10-10T10:00:00Z",
  source_time: null,
  freshness: "SOURCE_TIME_UNAVAILABLE",
  cached: false,
};

test("O4 bounded scanner, explanation and exact Analytics handoff", async ({
  page,
  baseURL,
}, info) => {
  test.setTimeout(90000);
  const headers = { Origin: baseURL! };
  const login = await page.request.post("/api/v1/auth/login", {
    headers,
    data: {
      username: "discovery-" + info.project.name,
      password: "test-only-browser-password",
    },
  });
  expect(login.ok()).toBe(true);
  await page.route("**/api/v1/scanner/derivatives/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/catalog")) return route.continue();
    if (path.endsWith("/saved")) return route.fulfill({ json: [] });
    if (path.endsWith("/runs") && route.request().method() === "GET")
      return route.fulfill({ json: [] });
    if (path.endsWith("/runs") && route.request().method() === "POST") {
      const config = route.request().postDataJSON();
      expect(config.scanner_type).toBe("DERIVATIVES");
      expect(config.universe.symbols).toEqual(["NIFTY"]);
      expect(config.filters).toEqual([
        { field: "option_type", operator: "equals", value: "CE" },
      ]);
      return route.fulfill({
        json: {
          id: "00000000-0000-0000-0000-000000000001",
          created_at: "2026-10-10T10:00:00Z",
          config,
          counts: {
            requested: 1,
            resolved: 1,
            chains_evaluated: 1,
            contracts_evaluated: 1,
            not_evaluated: 0,
            matches: 1,
          },
          underlyings: [
            { symbol: "NIFTY", outcome: "EVALUATED", failure: null },
          ],
          rows: [
            {
              contract,
              underlying: "NIFTY",
              spot: "25000",
              expiry,
              dte: 7,
              strike: "25000",
              option_type: "CE",
              moneyness: "ATM",
              strike_distance_percent: 0,
              market,
              volume_percentile: 92,
              volume_chain_median: 20000,
              volume_vs_chain_median: 5,
              volume_oi_percent: 20,
              relative_volume_cohort_size: 22,
              technical: {},
              instrument_metadata: null,
              observed: { option_type: "CE" },
              provenance,
              outcome: "MATCH",
              diagnostics: [
                {
                  filter: config.filters[0],
                  observed: "CE",
                  threshold: "CE",
                  passed: true,
                  reason: "Option Type equals CE",
                },
              ],
              missing_evidence: [],
              warnings: [],
              reason: "1/1 active filters matched",
            },
          ],
        },
      });
    }
    return route.continue();
  });
  await page.route("**/api/v1/options/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/underlyings"))
      return route.fulfill({ json: ["NIFTY"] });
    if (path.endsWith("/expiries")) return route.fulfill({ json: [expiry] });
    if (path.endsWith("/chain"))
      return route.fulfill({
        json: {
          underlying: "NIFTY",
          spot: "25000",
          expiry,
          dte: 7,
          as_of: "2026-10-10T10:00:00Z",
          atm_strike: "25000",
          rows: [
            {
              strike: "25000",
              is_atm: true,
              distance_from_spot: "0",
              distance_percent: "0",
              ce: {
                contract,
                moneyness: "ATM",
                market,
                availability: "AVAILABLE",
                warnings: [],
              },
              pe: null,
            },
          ],
          status: "COMPLETE",
          capabilities: {
            provider: "dhan",
            contracts: "SUPPORTED",
            quotes: "SUPPORTED",
            bid_ask: "SUPPORTED",
            volume: "SUPPORTED",
            open_interest: "SUPPORTED",
            oi_change: "SUPPORTED",
            iv: "UNSUPPORTED",
            greeks: "UNSUPPORTED",
          },
          provenance,
          warnings: [],
          missing_capabilities: [],
        },
      });
    return route.continue();
  });
  await page.addInitScript(() => localStorage.setItem("twf-theme", "light"));
  await page.goto("/scanners");
  await page.getByRole("tab", { name: /Derivatives Scanner/ }).click();
  await expect(
    page.getByRole("tabpanel", { name: "Derivatives Scanner" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Market Movers" }).click();
  await expect(page.locator(".sc-context-panel")).toContainText("TapTide");
  await page.screenshot({
    path: info.outputPath("derivatives-market-movers-panel.png"),
    fullPage: true,
  });
  await page.getByLabel("Close panel").click();
  const fieldOptions = page
    .getByRole("combobox", { name: "Field" })
    .locator("option");
  await expect(fieldOptions).toHaveCount(21);
  await expect(page.getByRole("combobox", { name: "Field" })).toHaveValue("");
  await expect(
    page.getByRole("button", { name: "Add / update filter" }),
  ).toBeDisabled();
  await page
    .getByRole("combobox", { name: "Field" })
    .selectOption("option_type");
  for (const label of ["Field", "Comparison", "Value"]) {
    const bounds = await page
      .getByRole("combobox", { name: label })
      .boundingBox();
    expect(bounds, `${label} should be rendered`).not.toBeNull();
    expect(bounds!.x, `${label} left edge`).toBeGreaterThanOrEqual(0);
    expect(
      bounds!.x + bounds!.width,
      `${label} right edge`,
    ).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
  }
  await expect(page.getByRole("combobox", { name: "Comparison" })).toHaveValue(
    "equals",
  );
  await expect(
    page.getByText("Derivatives filter catalog could not be loaded."),
  ).toHaveCount(0);
  await expect(
    page.getByText("maximum 5; excess selection is rejected", { exact: false }),
  ).toBeVisible();
  await expect(page.locator(".derivative-active-bar")).not.toContainText(
    "Moneyness",
  );
  await page.getByLabel("NSE underlyings").fill("NIFTY, NIFTY");
  await expect(
    page.getByRole("button", { name: "Add / update filter" }),
  ).toBeEnabled();
  await page.getByRole("combobox", { name: "Value" }).selectOption("CE");
  await page.getByRole("button", { name: "Add / update filter" }).click();
  await expect(
    page.getByRole("button", { name: "Remove Option Type equals CE" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Run Scan" }).click();
  const compact = info.project.use.viewport!.width <= 600;
  const results = page.locator(
    compact ? ".derivative-mobile-cards" : ".derivative-table-wrap",
  );
  await expect(results).toContainText("1/1 active filters matched");
  if (compact) await expect(results).toContainText("NIFTY 25,000 CE");
  await page.locator(".derivative-columns summary").click();
  await page.getByRole("checkbox", { name: "Bid", exact: true }).check();
  if (!compact)
    await expect(page.getByRole("columnheader", { name: "Bid" })).toBeVisible();
  await page.getByRole("checkbox", { name: "Bid", exact: true }).uncheck();
  await page.getByRole("checkbox", { name: "Vol/Median" }).check();
  await page.getByRole("checkbox", { name: "Vol/OI %" }).check();
  if (!compact) {
    await expect(
      page.getByRole("columnheader", { name: "Vol Pctl" }),
    ).toBeVisible();
    await expect(
      page.getByRole("columnheader", { name: "Vol/Median" }),
    ).toBeVisible();
    await expect(
      page.getByRole("columnheader", { name: "Vol/OI %" }),
    ).toBeVisible();
  }
  await page.locator(".derivative-columns summary").click();
  await expect(page.getByLabel("Selected option contract")).toHaveCount(0);
  const why = page.getByRole("button", { name: "Why?" });
  await why.focus();
  await page.keyboard.press("Enter");
  const detail = page.getByLabel("Selected option contract");
  await expect(detail).toContainText(id);
  await expect(detail).toContainText("Liquidity / Activity");
  for (const [label, expected] of [
    ["Volume percentile", "92"],
    ["Chain median volume", "20,000"],
    ["Volume vs median", "5x"],
    ["Volume / OI", "20%"],
  ]) {
    await expect(
      detail
        .locator("dt")
        .filter({ hasText: label })
        .locator("xpath=following-sibling::dd[1]"),
    ).toHaveText(expected);
  }
  await expect(detail).toContainText("22 valid CE + PE volumes");
  await expect(detail).toContainText("Observed: CE");
  await page.screenshot({
    path: info.outputPath(`o4-${info.project.name}.png`),
    fullPage: true,
  });
  await detail.getByRole("link", { name: "Open in Options Analytics" }).click();
  await expect(page).toHaveURL(
    /\/options-analytics\?underlying=NIFTY&expiry=2099-12-30/,
  );
  await expect(
    page.getByText("25,000 CE", { exact: false }).first(),
  ).toBeVisible();
});

test("O4 exact canonical contract reaches Broker V2 Buy and Sell previews", async ({
  page,
}, info) => {
  test.setTimeout(120000);
  const headers = { Origin: "http://127.0.0.1:3100" };
  await page.goto("/login");
  await page.getByLabel("Username").fill(`o4-broker-${info.project.name}`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-only-browser-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
  const created = await page.request.post("/api/v1/brokers/accounts", {
    headers,
    data: {
      name: "O4 preview",
      api_key: `o4${info.project.name.replaceAll("-", "")}`,
      api_secret: "testsecret123",
    },
  });
  expect(created.ok()).toBeTruthy();
  const account = (await created.json()).id;
  const connected = await page.request.post(
    `/api/v1/brokers/accounts/${account}/connect`,
    { headers, data: {} },
  );
  expect(connected.ok()).toBeTruthy();
  const url = new URL((await connected.json()).login_url);
  const state = new URLSearchParams(
    url.searchParams.get("redirect_params")!,
  ).get("state");
  expect(
    (
      await page.request.post("/api/v1/brokers/callback", {
        headers,
        data: { state, request_token: "request123" },
      })
    ).ok(),
  ).toBeTruthy();
  const choices = await page.request.get(
    `/api/v1/brokers/accounts/${account}/order-entry/choices?asset=options&underlying=NIFTY`,
  );
  expect(choices.ok()).toBeTruthy();
  const expiry = ((await choices.json()).expiries as string[])[0];
  const fixture = chainFixture("NIFTY", expiry);
  const leg = fixture.rows.find((r) => r.strike === "25000")!.pe!;
  const canonical = leg.contract;
  let historical = false;
  let confirms = 0;
  await page.route("**/order-entry/intents/*/confirm", async (route) => {
    confirms++;
    await route.abort();
  });
  await page.route("**/api/v1/scanner/derivatives/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/catalog"))
      return route.fulfill({
        json: {
          max_underlyings: 5,
          fields: [
            {
              field: "option_type",
              category: "Contract",
              label: "Option Type",
              kind: "enum",
              values: ["BOTH", "CE", "PE"],
              operators: ["equals", "not_equals"],
            },
          ],
        },
      });
    if (path.endsWith("/saved")) return route.fulfill({ json: [] });
    if (path.endsWith("/runs") && route.request().method() === "GET")
      return route.fulfill({ json: [] });
    if (path.endsWith("/runs") && route.request().method() === "POST") {
      const config = route.request().postDataJSON();
      expect(config.filters).toEqual([
        { field: "option_type", operator: "equals", value: "PE" },
      ]);
      const displayedContract = historical
        ? {
            ...canonical,
            canonical_id: canonical.canonical_id.replace(expiry, "2020-01-01"),
            expiry: "2020-01-01",
            last_trading_date: "2020-01-01",
          }
        : canonical;
      return route.fulfill({
        json: {
          id: "00000000-0000-0000-0000-000000000002",
          created_at: "2026-10-10T10:00:00Z",
          config,
          counts: {
            requested: 1,
            resolved: 1,
            chains_evaluated: 1,
            contracts_evaluated: 1,
            not_evaluated: 0,
            matches: 1,
          },
          underlyings: [
            { symbol: "NIFTY", outcome: "EVALUATED", failure: null },
          ],
          rows: [
            {
              contract: displayedContract,
              underlying: "NIFTY",
              spot: fixture.spot,
              expiry: displayedContract.expiry,
              dte: fixture.dte,
              strike: "25000",
              option_type: "PE",
              moneyness: "ATM",
              strike_distance_percent: 0,
              market: leg.market,
              availability: "AVAILABLE",
              technical: {},
              instrument_metadata: null,
              observed: { option_type: "PE" },
              provenance: fixture.provenance,
              outcome: "MATCH",
              missing_evidence: [],
              warnings: [],
              diagnostics: [
                {
                  filter: config.filters[0],
                  observed: "PE",
                  threshold: "PE",
                  passed: true,
                  reason: "Option Type equals PE",
                },
              ],
              reason: "1/1 active filters matched",
            },
          ],
        },
      });
    }
    return route.continue();
  });
  await page.goto("/scanners");
  await page.getByRole("tab", { name: /Derivatives Scanner/ }).click();
  await page.getByLabel("NSE underlyings").fill("NIFTY");
  await page
    .getByRole("combobox", { name: "Field" })
    .selectOption("option_type");
  await expect(page.getByRole("combobox", { name: "Value" })).toBeVisible();
  await page.getByRole("combobox", { name: "Value" }).selectOption("PE");
  await page.getByRole("button", { name: "Add / update filter" }).click();
  await page.getByRole("button", { name: "Run Scan" }).click();
  await page.getByRole("button", { name: "Why?" }).click();
  const detail = page.getByLabel("Selected option contract");
  await expect(detail).toContainText(canonical.canonical_id);
  for (const side of ["Buy", "Sell"] as const) {
    const action = detail.getByRole("button", {
      name: `${side} · Broker V2 preview`,
    });
    await expect(action).toBeEnabled();
    await action.click();
    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByRole("heading", { name: "Order Ticket" }),
    ).toBeVisible();
    await dialog
      .getByRole("combobox", { name: "Order type" })
      .selectOption("LIMIT");
    await dialog.getByLabel("Price (₹)").fill("147.05");
    const responsePromise = page.waitForResponse(
      (r) =>
        r.url().endsWith("/option-preview") && r.request().method() === "POST",
    );
    await dialog.getByRole("button", { name: `Preview ${side}` }).click();
    const response = await responsePromise;
    expect(response.ok()).toBeTruthy();
    expect(response.request().postDataJSON().contract).toEqual({
      exchange: "NFO",
      underlying_symbol: "NIFTY",
      expiry,
      strike: "25000",
      option_type: "PE",
    });
    expect((await response.json()).option_contract.canonical_id).toBe(
      canonical.canonical_id,
    );
    await expect(
      dialog.getByRole("heading", { name: "Preview", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: info.outputPath(`o4-${side.toLowerCase()}-preview.png`),
      fullPage: true,
    });
    await dialog.getByRole("button", { name: "Close order ticket" }).click();
  }
  historical = true;
  await page.getByRole("button", { name: "Run Scan" }).click();
  await page.getByRole("button", { name: "Why?" }).click();
  await expect(detail).toContainText("2020-01-01");
  await expect(
    detail.getByRole("button", { name: "Buy · Broker V2 preview" }),
  ).toBeDisabled();
  await expect(
    detail.getByRole("button", { name: "Sell · Broker V2 preview" }),
  ).toBeDisabled();
  expect(confirms).toBe(0);
});

test("O4 real catalog drives typed filters, saved setup, and scan payload", async ({
  page,
  baseURL,
}, info) => {
  test.setTimeout(90000);
  const login = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: baseURL! },
    data: {
      username: "discovery-" + info.project.name,
      password: "test-only-browser-password",
    },
  });
  expect(login.ok()).toBe(true);
  let submitted: Record<string, unknown> | null = null;
  let savedConfig: Record<string, unknown> | null = null;
  let lastRun: Record<string, unknown> | null = null;
  await page.route("**/api/v1/scanner/derivatives/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (path.endsWith("/catalog")) return route.continue();
    if (path.endsWith("/saved") && method === "GET")
      return route.fulfill({ json: [] });
    if (path.endsWith("/saved") && method === "POST") {
      const payload = route.request().postDataJSON();
      savedConfig = payload.config;
      return route.fulfill({
        json: {
          id: "11111111-1111-4111-8111-111111111111",
          config: savedConfig,
          archived: false,
          updated_at: "2026-10-11T10:00:00Z",
        },
      });
    }
    if (path.endsWith("/runs") && method === "GET")
      return route.fulfill({ json: [] });
    if (path.endsWith("/runs") && method === "POST") {
      submitted = route.request().postDataJSON();
      lastRun = {
        id: "22222222-2222-4222-8222-222222222222",
        created_at: "2026-10-11T10:00:00Z",
        config: submitted,
        counts: {
          requested: 1,
          resolved: 1,
          chains_evaluated: 1,
          contracts_evaluated: 1,
          not_evaluated: 0,
          matches: 0,
        },
        underlyings: [{ symbol: "NIFTY", outcome: "EVALUATED", failure: null }],
        rows: [],
      };
      return route.fulfill({ json: lastRun });
    }
    if (path.endsWith("/22222222-2222-4222-8222-222222222222"))
      return route.fulfill({ json: lastRun });
    return route.continue();
  });
  await page.goto("/scanners");
  await page.getByRole("tab", { name: /Derivatives Scanner/ }).click();
  const field = page.getByRole("combobox", { name: "Field" });
  const comparison = page.getByRole("combobox", { name: "Comparison" });
  await expect(field.locator("option")).toHaveCount(21);
  await field.selectOption("moneyness");
  await expect(comparison).toHaveValue("equals");
  await page.getByRole("checkbox", { name: "ITM" }).uncheck();
  await page.getByRole("checkbox", { name: "ATM" }).check();
  await page.getByRole("button", { name: "Add / update filter" }).click();
  await expect(
    page.getByRole("button", { name: "Remove Moneyness equals ATM" }),
  ).toBeVisible();
  await field.selectOption("dte");
  await expect(comparison.locator("option")).toHaveCount(6);
  await comparison.selectOption(">=");
  await page.getByRole("spinbutton", { name: "Value" }).fill("3");
  await page.getByRole("button", { name: "Add / update filter" }).click();
  await expect(
    page.getByRole("button", { name: "Remove DTE >= 3" }),
  ).toBeVisible();
  await field.selectOption("volume");
  await comparison.selectOption(">=");
  await page.getByRole("spinbutton", { name: "Value" }).fill("100000");
  await page.getByRole("button", { name: "Add / update filter" }).click();
  await field.selectOption("spread_percent");
  await comparison.selectOption("<=");
  await page.getByRole("spinbutton", { name: "Value" }).fill("2");
  await page.getByRole("button", { name: "Add / update filter" }).click();
  await field.selectOption("volume_percentile");
  await comparison.selectOption(">=");
  await page.getByRole("spinbutton", { name: "Value" }).fill("70");
  await page.getByRole("button", { name: "Add / update filter" }).click();
  await expect(
    page.getByRole("button", { name: "Remove Volume Percentile >= 70" }),
  ).toBeVisible();
  await field.selectOption("volume_vs_chain_median");
  await page.getByRole("spinbutton", { name: "Value" }).fill("1.5");
  await page.getByRole("button", { name: "Add / update filter" }).click();
  await expect(
    page.getByRole("button", { name: "Remove Volume vs Chain Median >= 1.5x" }),
  ).toBeVisible();
  await field.selectOption("volume_oi_percent");
  await page.getByRole("spinbutton", { name: "Value" }).fill("20");
  await page.getByRole("button", { name: "Add / update filter" }).click();
  await expect(
    page.getByRole("button", { name: "Remove Volume / OI % >= 20%" }),
  ).toBeVisible();
  await field.selectOption("underlying_trend");
  await expect(comparison.locator("option")).toHaveCount(2);
  await page.getByRole("combobox", { name: "Value" }).selectOption("Up");
  await page.getByRole("button", { name: "Add / update filter" }).click();
  await expect(
    page.getByRole("button", {
      name: "Remove Underlying Trend vs SMA20 equals Up",
    }),
  ).toBeVisible();
  await page.getByLabel("NSE underlyings").fill("NIFTY");
  await expect(page.locator(".derivative-active-bar")).toContainText(
    "Moneyness",
  );
  await expect(page.locator(".derivative-active-bar")).toContainText(
    "Volume Percentile",
  );
  await expect(page.locator(".derivative-builder")).not.toContainText(
    "Active filters",
  );
  await page.screenshot({
    path: info.outputPath("derivatives-horizontal-active-chips.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Run Scan" }).click();
  await expect(
    page.getByText(
      "No contracts matched these filters. No result was invented.",
    ),
  ).toBeVisible();
  expect(submitted).toMatchObject({
    scanner_type: "DERIVATIVES",
    data_mode: "REAL",
    provider: "dhan",
    filters: [
      { field: "moneyness", operator: "equals", value: ["ATM"] },
      { field: "dte", operator: ">=", value: 3 },
      { field: "volume", operator: ">=", value: 100000 },
      { field: "spread_percent", operator: "<=", value: 2 },
      { field: "volume_percentile", operator: ">=", value: 70 },
      { field: "volume_vs_chain_median", operator: ">=", value: 1.5 },
      { field: "volume_oi_percent", operator: ">=", value: 20 },
      { field: "underlying_trend", operator: "equals", value: "Up" },
    ],
  });
  await page.getByRole("button", { name: /Scan History ▾/ }).click();
  await page.getByRole("menuitem", { name: "Recent Scans" }).click();
  await page
    .locator(".sc-context-panel")
    .getByRole("button", { name: "View", exact: true })
    .click();
  await expect(
    page.getByText(
      "No contracts matched these filters. No result was invented.",
    ),
  ).toBeVisible();
  page.once("dialog", (dialog) => void dialog.accept("Typed O4"));
  await page.getByRole("button", { name: "Save Scan" }).click();
  await page.getByRole("button", { name: "My Scans" }).click();
  await expect(page.getByRole("button", { name: "Use setup" })).toBeVisible();
  await page.getByRole("button", { name: "Reset" }).click();
  await expect(page.locator(".derivative-active-bar")).not.toContainText(
    "Moneyness",
  );
  await page.getByRole("button", { name: "My Scans" }).click();
  await page.getByRole("button", { name: "Use setup" }).click();
  await expect(
    page.getByRole("button", { name: "Remove DTE >= 3" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Remove Volume Percentile >= 70" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Remove Volume vs Chain Median >= 1.5x" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Remove Volume / OI % >= 20%" }),
  ).toBeVisible();
  await field.selectOption("dte");
  await expect(comparison.locator("option")).toHaveCount(6);
  await page.getByRole("button", { name: "Remove DTE >= 3" }).click();
  await expect(
    page.getByRole("button", { name: "Remove DTE >= 3" }),
  ).toHaveCount(0);
});

test("O4 catalog failure shows a retryable error without empty controls", async ({
  page,
  baseURL,
}, info) => {
  const login = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: baseURL! },
    data: {
      username: "discovery-" + info.project.name,
      password: "test-only-browser-password",
    },
  });
  expect(login.ok()).toBe(true);
  let attempts = 0;
  await page.route("**/api/v1/scanner/derivatives/catalog", async (route) => {
    attempts += 1;
    if (attempts === 1)
      return route.fulfill({
        status: 404,
        json: { error: { message: "Not found" } },
      });
    if (attempts === 2)
      return route.fulfill({
        json: { fields: [], max_underlyings: 5 },
      });
    return route.continue();
  });
  await page.goto("/scanners");
  await page.getByRole("tab", { name: /Derivatives Scanner/ }).click();
  await expect(
    page.getByText("Derivatives filter catalog could not be loaded."),
  ).toBeVisible();
  const field = page.getByRole("combobox", { name: "Field" });
  await expect(field).toBeDisabled();
  await expect(field).toContainText("Filters unavailable");
  await expect(page.getByText("Not found", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(
    page.getByText("No derivative filters available."),
  ).toBeVisible();
  await expect(field).toBeDisabled();
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(field.locator("option")).toHaveCount(21);
  await expect(field).toBeEnabled();
  await expect(
    page.getByText("Derivatives filter catalog could not be loaded."),
  ).toHaveCount(0);
});
