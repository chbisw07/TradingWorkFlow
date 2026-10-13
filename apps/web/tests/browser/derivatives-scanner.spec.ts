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
              oi_percentile: 90,
              oi_chain_median: 250000,
              oi_vs_chain_median: 2,
              oi_change_percent: 4.1666667,
              oi_change_percentile: 80,
              relative_oi_cohort_size: 22,
              oi_interpretation: {
                label: "Call long buildup",
                inferred: true,
                confidence: "MEDIUM",
                freshness: "SOURCE_TIME_UNAVAILABLE",
                window_start: "2026-10-10T09:45:00Z",
                window_end: "2026-10-10T10:00:00Z",
                window_seconds: 900,
                premium_change_percent: 12.4,
                oi_window_change_percent: 4.2,
                underlying_change_percent: 0.8,
                iv_change_points: null,
                reason: "Observed snapshot-to-snapshot premium and OI moves",
              },
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
  await expect(page.getByLabel("Derivatives selection actions")).toContainText(
    "0 selected",
  );
  await expect(page.locator(".derivative-scanner .sc-grid")).not.toHaveClass(
    /has-detail/,
  );
  await expect(
    page.locator(".derivative-scanner .sc-context-panel"),
  ).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath("derivatives-clean-builder.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Market Movers" }).click();
  await expect(page.locator(".sc-context-panel")).toContainText("TapTide");
  await page.screenshot({
    path: info.outputPath("derivatives-market-movers-panel.png"),
    fullPage: true,
  });
  await page.getByLabel("Close panel").click();
  await expect(page.locator(".derivative-scanner .sc-grid")).not.toHaveClass(
    /has-detail/,
  );
  await page.locator(".derivative-filter-editor > summary").click();
  const fieldOptions = page
    .getByRole("combobox", { name: "Field" })
    .locator("option");
  await expect(fieldOptions).toHaveCount(24);
  await expect(page.getByRole("combobox", { name: "Field" })).toHaveValue("");
  await expect(page.getByRole("radio", { name: "Both" })).toBeChecked();
  await page.getByRole("radio", { name: "Both" }).focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByRole("radio", { name: "PE" })).toBeChecked();
  await expect(
    page
      .getByRole("combobox", { name: "Field" })
      .locator('option[value="option_type"]'),
  ).toHaveCount(0);
  await expect(page.locator(".derivative-active-bar")).not.toContainText(
    "Single-leg NSE options · Dhan market data",
  );
  await expect(
    page.getByRole("button", { name: "Add / update filter" }),
  ).toBeDisabled();
  const chipStyle = await page
    .locator(".derivative-active-bar > button")
    .first()
    .evaluate((node) => ({
      background: getComputedStyle(node).backgroundColor,
      border: getComputedStyle(node).borderColor,
      color: getComputedStyle(node).color,
    }));
  expect(chipStyle).toEqual({
    background: "rgb(234, 244, 255)",
    border: "rgb(138, 184, 230)",
    color: "rgb(23, 63, 104)",
  });
  await page.getByRole("radio", { name: "CE" }).check();
  for (const label of ["Field", "Comparison"]) {
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
  await expect(page.getByRole("radio", { name: "CE" })).toBeChecked();
  await expect(page.locator(".derivative-active-bar")).toContainText(
    "Option Type: CE",
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
  await page.getByRole("button", { name: "Custom underlyings" }).click();
  await page.getByLabel("NSE underlyings").fill("NIFTY, NIFTY");
  await expect(
    page.getByRole("button", { name: "Reset Option Type CE to Both" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Run Scan" }).click();
  const compact = info.project.use.viewport!.width <= 600;
  const results = page.locator(
    compact ? ".derivative-mobile-cards" : ".derivative-table-wrap",
  );
  await expect(results).toContainText("Call long buildup");
  await expect(
    results.getByRole("link", { name: "Open NIFTY in Options Analytics" }),
  ).toHaveAttribute("href", "/options-analytics?underlying=NIFTY");
  if (!compact) {
    for (const label of [
      "OI",
      "OI Pctl",
      "ΔOI",
      "ΔOI %",
      "OI Interpretation (Inferred)",
    ]) {
      await expect(
        page.getByRole("columnheader", { name: label, exact: true }),
      ).toBeVisible();
    }
    await expect(
      page.getByRole("columnheader", { name: "Spot", exact: true }),
    ).toHaveCount(0);
  }
  await expect(page.getByLabel("Derivatives selection actions")).toContainText(
    "0 selected",
  );
  await expect(
    page.locator(".derivative-scanner .sc-center").locator(".derivative-bulk"),
  ).toBeVisible();
  await expect(
    page.locator(".derivative-scanner .sc-center").locator(".derivative-bulk"),
  ).toHaveCount(1);
  await expect(page.locator(".derivative-scanner .sc-grid")).not.toHaveClass(
    /has-detail/,
  );
  await expect(
    page.locator(".derivative-scanner .sc-center"),
  ).not.toContainText("Saved Scans");
  await page.screenshot({
    path: info.outputPath("derivatives-results-full-width.png"),
    fullPage: true,
  });
  await page
    .getByRole("checkbox", { name: `Select ${contract.display_symbol}` })
    .first()
    .check();
  await expect(page.getByLabel("Derivatives selection actions")).toContainText(
    "1 selected",
  );
  await expect(
    page
      .getByLabel("Derivatives selection actions")
      .getByRole("link", { name: "Open in Options Analytics" }),
  ).toHaveAttribute("href", /contract_id=NFO%3ANIFTY/);
  if (compact) await expect(results).toContainText("NIFTY 25,000 CE");
  const resultCard = page.locator(".derivative-results");
  const layout = async () =>
    page.evaluate(() => {
      const card = document.querySelector(".derivative-results")!;
      const bar = document.querySelector(".derivative-bulk")!;
      const cardRect = card.getBoundingClientRect();
      const barRect = bar.getBoundingClientRect();
      return {
        resultHeight: cardRect.height,
        barTop: barRect.top + window.scrollY,
      };
    });
  const beforeColumns = await layout();
  const columnsButton = resultCard.getByRole("button", { name: "Columns" });
  await columnsButton.click();
  await expect(columnsButton).toHaveAttribute("aria-expanded", "true");
  const columnsPopup = page.getByRole("group", {
    name: "Visible result columns",
  });
  await expect(columnsPopup).toBeVisible();
  for (const label of [
    "OI Pctl",
    "OI vs Median",
    "ΔOI %",
    "ΔOI Percentile",
    "OI Interpretation (Inferred)",
  ]) {
    await expect(
      columnsPopup.getByRole("checkbox", { name: label }),
    ).toBeVisible();
  }
  const popupBox = await columnsPopup.boundingBox();
  expect(popupBox).not.toBeNull();
  expect(popupBox!.x).toBeGreaterThanOrEqual(0);
  expect(popupBox!.x + popupBox!.width).toBeLessThanOrEqual(
    page.viewportSize()!.width + 1,
  );
  expect(popupBox!.y).toBeGreaterThanOrEqual(0);
  expect(popupBox!.y + popupBox!.height).toBeLessThanOrEqual(
    page.viewportSize()!.height + 1,
  );
  const openedColumns = await layout();
  expect(openedColumns.resultHeight).toBeCloseTo(beforeColumns.resultHeight, 0);
  expect(openedColumns.barTop).toBeCloseTo(beforeColumns.barTop, 0);
  await page.screenshot({
    path: info.outputPath("derivatives-columns-popup.png"),
    fullPage: true,
  });
  if (compact) {
    const viewport = page.viewportSize()!;
    await page.setViewportSize({ width: viewport.width, height: 360 });
    await expect
      .poll(() =>
        columnsPopup.evaluate(
          (element) => element.scrollHeight > element.clientHeight,
        ),
      )
      .toBe(true);
    const shortBox = await columnsPopup.boundingBox();
    expect(shortBox!.y).toBeGreaterThanOrEqual(0);
    expect(shortBox!.y + shortBox!.height).toBeLessThanOrEqual(361);
    await page.setViewportSize(viewport);
  }
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
  await page.keyboard.press("Escape");
  await expect(columnsButton).toHaveAttribute("aria-expanded", "false");
  await expect(columnsPopup).toHaveCount(0);
  await expect(columnsButton).toBeFocused();
  await columnsButton.click();
  await expect(
    page.getByRole("checkbox", { name: "Vol/Median" }),
  ).toBeChecked();
  await page.locator(".derivative-builder h2").click();
  await expect(columnsButton).toHaveAttribute("aria-expanded", "false");
  await expect(await layout()).toEqual(beforeColumns);
  await expect(page.getByLabel("Selected option contract")).toHaveCount(0);
  if (!compact) {
    const badge = page.locator(".derivative-oi-badge").first();
    await badge.focus();
    await expect(badge).toBeFocused();
    await expect(badge).toHaveAttribute(
      "aria-label",
      /OI interpretation, inferred: Call long buildup.*Premium \+12\.4%/,
    );
  }
  const why = page.getByRole("button", { name: "Why?" });
  await why.focus();
  await page.keyboard.press("Enter");
  const detail = page.getByLabel("Selected option contract");
  await expect(detail).toContainText(id);
  await expect(page.locator(".derivative-scanner .sc-grid")).toHaveClass(
    /has-detail/,
  );
  await expect(detail).toContainText("Liquidity / Activity");
  await expect(detail).toContainText("OI Interpretation (Inferred)");
  await expect(detail).toContainText("Premium change");
  await expect(detail).toContainText("+12.4%");
  await expect(detail).toContainText("900 seconds");
  await expect(detail).toContainText("SOURCE_TIME_UNAVAILABLE");
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
  const withPanel = await layout();
  await columnsButton.click();
  await expect(columnsPopup).toBeVisible();
  const withPanelOpen = await layout();
  expect(withPanelOpen.resultHeight).toBeCloseTo(withPanel.resultHeight, 0);
  expect(withPanelOpen.barTop).toBeCloseTo(withPanel.barTop, 0);
  await page.screenshot({
    path: info.outputPath("derivatives-columns-with-panel.png"),
    fullPage: true,
  });
  await page.keyboard.press("Escape");
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
  await page.getByRole("button", { name: "Custom underlyings" }).click();
  await page.getByLabel("NSE underlyings").fill("NIFTY");
  await page.getByRole("radio", { name: "PE" }).check();
  await expect(page.locator(".derivative-active-bar")).toContainText(
    "Option Type: PE",
  );
  await page.getByRole("button", { name: "Run Scan" }).click();
  const resultActions = page
    .locator(".derivative-scanner .derivative-row-actions:visible")
    .first();
  const detail = page.getByLabel("Selected option contract");
  for (const side of ["Buy", "Sell"] as const) {
    const action = resultActions.getByRole("button", {
      name: `${side} ${canonical.display_symbol}`,
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
  await resultActions.getByRole("button", { name: "Why?" }).click();
  await expect(detail).toContainText(canonical.canonical_id);
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
  await page.locator(".derivative-filter-editor > summary").click();
  const field = page.getByRole("combobox", { name: "Field" });
  const comparison = page.getByRole("combobox", { name: "Comparison" });
  await expect(field.locator("option")).toHaveCount(24);
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
  await expect(
    page.getByRole("button", { name: "Remove Volume Percentile >= 70" }),
  ).toHaveCSS("background-color", "rgb(220, 238, 255)");
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
  for (const [key, comparisonValue, numericValue] of [
    ["oi_percentile", ">=", "80"],
    ["oi_vs_chain_median", ">=", "2"],
    ["oi_change_percent", ">=", "10"],
    ["oi_change_percentile", ">=", "80"],
  ]) {
    await field.selectOption(key);
    await comparison.selectOption(comparisonValue);
    await page.getByRole("spinbutton", { name: "Value" }).fill(numericValue);
    await expect(page.locator(".derivative-active-bar")).not.toContainText(
      key === "oi_percentile"
        ? "OI Percentile >= 80%"
        : "Change in OI Percentile >= 80%",
    );
    await page.getByRole("button", { name: "Add / update filter" }).click();
  }
  await expect(
    page.getByRole("button", { name: "Remove OI Percentile >= 80% filter" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Remove Change in OI % >= 10% filter" }),
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
  await page.getByRole("button", { name: "Custom underlyings" }).click();
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
  await page.getByRole("radio", { name: "CE" }).check();
  await page.getByRole("radio", { name: "Both" }).check();
  await expect(page.locator(".derivative-active-bar")).toContainText(
    "Option Type: Both",
  );
  const clearAll = page.getByRole("button", { name: "Clear All" });
  await expect(clearAll).toHaveCSS("background-color", "rgb(255, 241, 242)");
  await expect(clearAll).toHaveCSS("color", "rgb(147, 37, 53)");
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
      { field: "oi_percentile", operator: ">=", value: 80 },
      { field: "oi_vs_chain_median", operator: ">=", value: 2 },
      { field: "oi_change_percent", operator: ">=", value: 10 },
      { field: "oi_change_percentile", operator: ">=", value: 80 },
      { field: "underlying_trend", operator: "equals", value: "Up" },
      { field: "option_type", operator: "equals", value: "BOTH" },
    ],
  });
  await page.getByRole("button", { name: /Scan History ▾/ }).click();
  await page.getByRole("menuitem", { name: "Recent Scans" }).click();
  await expect(page.locator(".sc-context-panel")).toContainText("Recent Scans");
  await page.screenshot({
    path: info.outputPath("derivatives-recent-scans-panel.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: /Scan History ▾/ }).click();
  await page
    .getByRole("menuitem", { name: "Scan History", exact: true })
    .click();
  await expect(page.locator(".sc-context-panel")).toContainText("Scan History");
  await page.screenshot({
    path: info.outputPath("derivatives-scan-history-panel.png"),
    fullPage: true,
  });
  await page
    .locator(".sc-context-panel")
    .getByRole("button", { name: "View", exact: true })
    .click();
  await expect(
    page.getByText(
      "No contracts matched these filters. No result was invented.",
    ),
  ).toBeVisible();
  await page.getByRole("radio", { name: "CE" }).check();
  page.once("dialog", (dialog) => void dialog.accept("Typed O4"));
  await page.getByRole("button", { name: /Save Scan ▾/ }).click();
  await page.getByRole("menuitem", { name: /Save Scan/ }).click();
  expect(savedConfig).toMatchObject({
    filters: expect.arrayContaining([
      { field: "option_type", operator: "equals", value: "CE" },
      { field: "oi_percentile", operator: ">=", value: 80 },
      { field: "oi_vs_chain_median", operator: ">=", value: 2 },
      { field: "oi_change_percent", operator: ">=", value: 10 },
      { field: "oi_change_percentile", operator: ">=", value: 80 },
    ]),
  });
  await page.getByRole("button", { name: "My Scans" }).click();
  await expect(page.getByRole("button", { name: "Use setup" })).toBeVisible();
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(page.locator(".derivative-active-bar")).not.toContainText(
    "Moneyness",
  );
  await page.getByRole("button", { name: "My Scans" }).click();
  await page.getByRole("button", { name: "Use setup" }).click();
  await expect(page.getByRole("radio", { name: "CE" })).toBeChecked();
  await expect(page.locator(".derivative-active-bar")).toContainText(
    "Option Type: CE",
  );
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
  await page.getByRole("button", { name: "Clear All" }).click();
  await expect(page.getByRole("radio", { name: "Both" })).toBeChecked();
  await expect(page.locator(".derivative-active-bar")).toContainText(
    "Underlyings: NIFTY",
  );
  await expect(page.locator(".derivative-active-bar")).toContainText(
    "Expiry: Nearest active",
  );
  await expect(page.locator(".derivative-active-bar")).toContainText(
    "±10 strikes",
  );
  await expect(page.locator(".derivative-active-bar")).not.toContainText(
    "Volume vs Chain Median",
  );
  await page.getByRole("tab", { name: /Equity \/ Index Scanner/ }).click();
  await expect(page.locator(".derivative-active-bar")).toHaveCount(0);
  await expect(page.locator(".sc-context-panel")).toHaveCount(0);
  await page.getByRole("tab", { name: /Derivatives Scanner/ }).click();
  await expect(page.locator(".derivative-active-bar")).not.toContainText(
    "Volume Percentile >= 70",
  );
});

test("legacy Option Type setup, two-row selection and canonical underlying links", async ({
  page,
  baseURL,
}, info) => {
  const login = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: baseURL! },
    data: {
      username: "browser-user",
      password: "test-only-browser-password",
    },
  });
  expect(login.ok()).toBe(true);
  const legacyConfig = {
    name: "Legacy puts",
    scanner_type: "DERIVATIVES",
    data_mode: "REAL",
    provider: "dhan",
    universe: { source: "CUSTOM", symbols: ["NIFTY", "HDFCBANK"] },
    expiry_mode: "NEAREST",
    exact_expiry: null,
    strike_window: 10,
    filters: [{ field: "option_type", operator: "not_equals", value: "CE" }],
    version: "1",
  };
  const makeRow = (underlying: string, strike: string) => {
    const exact = {
      ...contract,
      canonical_id: `NFO:${underlying}:${expiry}:${strike}:PE`,
      underlying_symbol: underlying,
      strike,
      option_type: "PE",
      display_symbol: `${underlying} 30 Dec 2099 ${strike} PE`,
    };
    return {
      contract: exact,
      underlying,
      spot: strike,
      expiry,
      dte: 7,
      strike,
      option_type: "PE",
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
      observed: { option_type: "PE" },
      provenance,
      outcome: "MATCH",
      diagnostics: [
        {
          filter: legacyConfig.filters[0],
          observed: "PE",
          threshold: "CE",
          passed: true,
          reason: "Option Type not_equals CE",
        },
      ],
      missing_evidence: [],
      warnings: [],
      reason: "1/1 active filters matched",
    };
  };
  let posted: Record<string, unknown> | null = null;
  await page.route("**/api/v1/scanner/derivatives/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/catalog")) return route.continue();
    if (path.endsWith("/saved"))
      return route.fulfill({
        json: [
          {
            id: "33333333-3333-4333-8333-333333333333",
            config: legacyConfig,
            archived: false,
            updated_at: "2026-10-11T10:00:00Z",
          },
        ],
      });
    if (path.endsWith("/runs") && route.request().method() === "GET")
      return route.fulfill({ json: [] });
    if (path.endsWith("/runs") && route.request().method() === "POST") {
      posted = route.request().postDataJSON();
      return route.fulfill({
        json: {
          id: "44444444-4444-4444-8444-444444444444",
          created_at: "2026-10-11T10:00:00Z",
          config: posted,
          counts: {
            requested: 2,
            resolved: 2,
            chains_evaluated: 2,
            contracts_evaluated: 2,
            not_evaluated: 0,
            matches: 2,
          },
          underlyings: [
            { symbol: "NIFTY", outcome: "EVALUATED", failure: null },
            { symbol: "HDFCBANK", outcome: "EVALUATED", failure: null },
          ],
          rows: [makeRow("NIFTY", "25000"), makeRow("HDFCBANK", "700")],
        },
      });
    }
    return route.continue();
  });
  await page.goto("/scanners");
  await page.getByRole("tab", { name: /Derivatives Scanner/ }).click();
  await page.getByRole("button", { name: "My Scans" }).click();
  await page.getByRole("button", { name: "Use setup" }).click();
  await page.locator(".derivative-filter-editor > summary").click();
  await expect(page.getByRole("radio", { name: "PE" })).toBeChecked();
  await expect(page.locator(".derivative-active-bar")).toContainText(
    "Option Type: PE",
  );
  await expect(
    page
      .getByRole("combobox", { name: "Field" })
      .locator('option[value="option_type"]'),
  ).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath("derivatives-builder-option-type.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Run Scan" }).click();
  expect(posted).toMatchObject({
    filters: [{ field: "option_type", operator: "not_equals", value: "CE" }],
  });
  const compact = info.project.use.viewport!.width <= 600;
  const results = page.locator(
    compact ? ".derivative-mobile-cards" : ".derivative-table-wrap",
  );
  for (const underlying of ["NIFTY", "HDFCBANK"]) {
    await expect(
      results.getByRole("link", {
        name: `Open ${underlying} in Options Analytics`,
      }),
    ).toHaveAttribute("href", `/options-analytics?underlying=${underlying}`);
  }
  await page
    .getByRole("checkbox", { name: "Select NIFTY 30 Dec 2099 25000 PE" })
    .first()
    .check();
  await page
    .getByRole("checkbox", { name: "Select HDFCBANK 30 Dec 2099 700 PE" })
    .first()
    .check();
  await expect(page.getByLabel("Derivatives selection actions")).toContainText(
    "2 selected",
  );
  await page.screenshot({
    path: info.outputPath("derivatives-two-selected-action-bar.png"),
    fullPage: true,
  });
  await results.getByRole("button", { name: "Why?" }).first().click();
  await expect(page.getByLabel("Derivatives selection actions")).toContainText(
    "2 selected",
  );
  await page.getByLabel("Close panel").click();
  await page
    .getByRole("checkbox", { name: "Select NIFTY 30 Dec 2099 25000 PE" })
    .first()
    .uncheck();
  await expect(page.getByLabel("Derivatives selection actions")).toContainText(
    "1 selected",
  );
  await results
    .getByRole("link", {
      name: "Open HDFCBANK in Options Analytics",
    })
    .click();
  await expect(page).toHaveURL(/\/options-analytics\?underlying=HDFCBANK$/);
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
  await page.locator(".derivative-filter-editor > summary").click();
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
  await expect(field.locator("option")).toHaveCount(24);
  await expect(field).toBeEnabled();
  await expect(
    page.getByText("Derivatives filter catalog could not be loaded."),
  ).toHaveCount(0);
});
