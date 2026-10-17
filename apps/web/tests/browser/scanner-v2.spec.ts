import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";

test("Scanner V2 editable filters, durable runs, Watchlist handoff and responsive review", async ({
  page,
  baseURL,
}, info) => {
  test.setTimeout(90000);
  const headers = { Origin: baseURL! };
  expect(
    (
      await page.request.post("/api/v1/auth/login", {
        headers,
        data: {
          username: "discovery-" + info.project.name,
          password: "test-only-browser-password",
        },
      })
    ).ok(),
  ).toBe(true);
  const list = await (
    await page.request.post("/api/v1/watchlists", {
      headers,
      data: { name: "Scanner Core" },
    })
  ).json();
  const ids: string[] = [];
  for (const symbol of ["RELIANCE", "INFY", "NIFTY"]) {
    const instruments = await (
      await page.request.get("/api/v1/watchlists/instruments?q=" + symbol)
    ).json();
    ids.push(
      instruments.find(
        (i: { instrument: { symbol: string } }) =>
          i.instrument.symbol === symbol,
      ).instrument.instrument_id,
    );
  }
  await page.request.post(`/api/v1/watchlists/${list.id}/items`, {
    headers,
    data: { instrument_ids: ids },
  });
  const configured = await page.request.post("/api/v1/brokers/accounts", {
    headers,
    data: {
      name: "Scanner Equity Preview",
      api_key: `scannerkey${info.project.name.replaceAll("-", "")}`,
      api_secret: "testsecret123",
    },
  });
  expect(configured.ok()).toBe(true);
  const brokerId = (await configured.json()).id;
  const connect = await page.request.post(
    `/api/v1/brokers/accounts/${brokerId}/connect`,
    { headers, data: {} },
  );
  expect(connect.ok()).toBe(true);
  const loginUrl = new URL((await connect.json()).login_url);
  const state = new URLSearchParams(
    loginUrl.searchParams.get("redirect_params")!,
  ).get("state");
  expect(
    (
      await page.request.post("/api/v1/brokers/callback", {
        headers,
        data: { state, request_token: "request123" },
      })
    ).ok(),
  ).toBe(true);
  await page.addInitScript(() => localStorage.setItem("twf-theme", "light"));
  let dispatches = 0;
  page.on("request", (r) => {
    if (/\/(confirm|dispatch|submit)$/.test(r.url())) dispatches++;
  });
  await page.goto("/scanners");
  await expect(
    page.getByRole("heading", { name: "Scanners", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".sc-bottom")).toHaveCount(0);
  await expect(page.locator(".sc-context-panel")).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath("scanner-clean-workspace.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Market Movers" }).click();
  await expect(page.locator(".sc-context-panel")).toContainText("TapTide");
  await page.screenshot({
    path: info.outputPath("scanner-market-movers-panel.png"),
    fullPage: true,
  });
  await page.getByLabel("Close Market Movers").click();
  await page.getByRole("button", { name: /Scan History ▾/ }).click();
  await expect(
    page.getByRole("button", { name: /Scan History ▾/ }),
  ).toHaveAttribute("aria-expanded", "true");
  await page.screenshot({
    path: info.outputPath("scanner-history-menu.png"),
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: /Scan History ▾/ }),
  ).toHaveAttribute("aria-expanded", "false");
  await page.getByRole("button", { name: /Scan History ▾/ }).click();
  await page.getByRole("menuitem", { name: "Recent Scans" }).click();
  await expect(page.locator(".sc-context-panel")).toContainText("Recent Scans");
  await page.screenshot({
    path: info.outputPath("scanner-recent-scans-panel.png"),
    fullPage: true,
  });
  await page.getByLabel("Close panel").click();
  await page.getByRole("button", { name: /Scan History ▾/ }).click();
  await page.getByRole("menuitem", { name: "Scan History" }).click();
  await expect(page.locator(".sc-context-head")).toContainText("Scan History");
  await page.getByLabel("Close panel").click();
  await expect(page.locator(".sc-grid")).not.toHaveClass(/has-detail/);
  if (page.viewportSize()!.width <= 800)
    await page.locator(".sc-builder > details > summary").click();
  await page
    .getByRole("button", { name: "Watchlist: Choose watchlist" })
    .click();
  await page.getByRole("button", { name: "Scanner Core (3)" }).click();
  await expect(page.locator(".sc-universe-summary")).toContainText(
    "Scanner Core",
  );
  await page.locator(".sc-context-builder > summary").click();
  await expect(
    page.getByRole("button", { name: "Ranking", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByText(
      "Only explicit predicates in Hard filter mode can reject a technical match.",
      { exact: false },
    ),
  ).toBeVisible();
  await page
    .getByLabel("Scan Templates", { exact: true })
    .selectOption("Momentum");
  await page.getByRole("button", { name: "Clear All", exact: true }).click();
  await page.locator(".sc-editor > summary").click();
  await page.getByLabel("Field", { exact: true }).selectOption("rsi");
  await expect(page.getByLabel("Compare to", { exact: true })).toHaveValue(
    "value",
  );
  await expect(
    page
      .getByLabel("Compare to", { exact: true })
      .locator('option[value="field"]'),
  ).toHaveCount(0);
  await expect(page.getByLabel("Value", { exact: true })).toHaveAttribute(
    "type",
    "number",
  );

  await page.getByLabel("Field", { exact: true }).selectOption("high20");
  await page.getByLabel("Compare to", { exact: true }).selectOption("field");
  const comparison = page.getByLabel("Comparison field", { exact: true });
  await expect(comparison.locator('option[value="sma20"]')).toHaveCount(1);
  await expect(comparison.locator('option[value="sma50"]')).toHaveCount(1);
  await expect(comparison.locator('option[value="rsi"]')).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath("scanner-typed-field-comparison.png"),
    fullPage: true,
  });

  await page.getByLabel("Field", { exact: true }).selectOption("supertrend");
  await expect(page.getByLabel("Operator", { exact: true })).toHaveValue(
    "equals",
  );
  await expect(page.getByLabel("Value", { exact: true })).toHaveValue("Up");
  await expect(page.getByLabel("Value", { exact: true })).toHaveAttribute(
    "aria-label",
    "Value",
  );

  await page.getByLabel("Field", { exact: true }).selectOption("rsi");
  await page.getByLabel("Operator", { exact: true }).selectOption(">");
  await page.getByLabel("Value", { exact: true }).fill("0");
  await page.getByRole("button", { name: "Add Filter", exact: false }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: info.outputPath("scanner-filters-light.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Run Scan", exact: true }).click();
  const scanCounts = page.getByLabel("Scan run counts");
  await expect(scanCounts.locator(".derivative-count-card")).toHaveCount(5, {
    timeout: 30000,
  });
  await expect(scanCounts.locator(".derivative-count-matches")).toContainText(
    "3",
  );
  await expect(scanCounts.locator(".derivative-count-matches svg")).toHaveCount(
    1,
  );
  const symbolLink = page.locator(".sc-table .sc-symbol").first();
  await expect(symbolLink).toHaveCSS("color", "rgb(8, 120, 239)");
  await expect(symbolLink).toHaveCSS("cursor", "pointer");
  await symbolLink.focus();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Shift+Tab");
  await expect(symbolLink).toBeFocused();
  await expect(symbolLink).toHaveCSS("outline-style", "solid");
  const trendColors = await page.locator(".sc-grid").evaluate((grid) => {
    const sample = document.createElement("span");
    grid.append(sample);
    const color = (tone: string) => {
      sample.className = `derivative-trend derivative-trend-${tone}`;
      return getComputedStyle(sample).color;
    };
    const colors = [color("up"), color("down"), color("neutral")];
    sample.remove();
    return colors;
  });
  expect(trendColors).toEqual([
    "rgb(18, 98, 62)",
    "rgb(157, 38, 56)",
    "rgb(69, 86, 107)",
  ]);
  await page.screenshot({
    path: info.outputPath("scanner-results-unified.png"),
  });
  await expect(page.locator(".sc-reason").first()).toContainText(
    "RSI (14) > 0",
  );
  await page.getByRole("button", { name: "Run Evidence" }).click();
  const runEvidence = page.getByLabel("Scanner contextual panel");
  await expect(runEvidence).toContainText("Data source & mode");
  await expect(runEvidence).toContainText("Evaluation diagnostics");
  await runEvidence.getByText(/Per-symbol diagnostics/).click();
  await expect(runEvidence).toContainText("RELIANCE");
  await page.screenshot({ path: info.outputPath("scanner-run-evidence.png") });
  await runEvidence.getByRole("button", { name: "Close panel" }).click();
  const equityResults = page.locator(".sc-results");
  const equityHeight = await equityResults.evaluate(
    (element) => element.getBoundingClientRect().height,
  );
  const equityColumns = equityResults.getByRole("button", { name: "Columns" });
  await equityColumns.click();
  await expect(equityColumns).toHaveAttribute("aria-expanded", "true");
  const optionalColumns = page.getByRole("group", {
    name: "Visible result columns",
  });
  await expect(optionalColumns).toBeVisible();
  await optionalColumns.getByRole("checkbox", { name: "Relevance" }).check();
  if (page.viewportSize()!.width > 600) {
    await expect(
      equityResults.getByRole("columnheader", { name: "Relevance" }),
    ).toBeVisible();
  } else {
    await expect(
      equityResults.locator('td[data-label="Relevance"]'),
    ).toHaveCount(3);
  }
  await optionalColumns.getByRole("checkbox", { name: "Relevance" }).uncheck();
  expect(
    await equityResults.evaluate(
      (element) => element.getBoundingClientRect().height,
    ),
  ).toBeCloseTo(equityHeight, 0);
  await page.keyboard.press("Escape");
  await expect(equityColumns).toHaveAttribute("aria-expanded", "false");
  const relianceRow = page
    .locator(".sc-table tbody tr")
    .filter({ hasText: "RELIANCE" });
  const indexRow = page
    .locator(".sc-table tbody tr")
    .filter({ hasText: "NIFTY" });
  await expect(
    relianceRow.getByRole("button", { name: "Buy RELIANCE" }),
  ).toBeEnabled();
  await expect(
    relianceRow.getByRole("button", { name: "Sell RELIANCE" }),
  ).toBeEnabled();
  await expect(
    indexRow.getByRole("button", { name: "Buy NIFTY" }),
  ).toBeDisabled();
  await expect(
    indexRow.getByRole("button", { name: "Sell NIFTY" }),
  ).toBeDisabled();
  for (const [action, side] of [
    ["Buy", "BUY"],
    ["Sell", "SELL"],
  ] as const) {
    await relianceRow
      .getByRole("button", { name: `${action} RELIANCE` })
      .click();
    const ticket = page.getByRole("dialog");
    await expect(
      ticket.getByRole("heading", { name: "Order Ticket" }),
    ).toBeVisible();
    await expect(
      ticket.getByRole("button", { name: action, exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await expect(ticket).toContainText("RELIANCE");
    await expect(ticket).toContainText("NSE");
    const price = ticket.getByLabel("Price (₹)", { exact: true });
    if (await price.count()) await price.fill("100.05");
    await ticket.getByRole("button", { name: `Preview ${action}` }).click();
    await expect(
      ticket.getByRole("button", { name: "Create TWF Order" }),
    ).toBeVisible();
    await expect(ticket.locator(".order-preview")).toContainText(
      `${side} RELIANCE`,
    );
    await page.screenshot({
      path: info.outputPath(`scanner-${action.toLowerCase()}-preview.png`),
    });
    await ticket.getByLabel("Close order ticket").click();
    await expect(ticket).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Watchlist: Scanner Core" }),
    ).toBeVisible();
    await expect(page.locator(".sc-grid")).not.toHaveClass(/has-detail/);
    await expect(
      page.getByRole("button", { name: "Remove filter 1" }),
    ).toBeVisible();
  }
  expect(dispatches).toBe(0);
  await expect(page.locator(".sc-table thead")).toContainText("Sector");
  await expect(page.locator(".sc-table thead")).toContainText("Reason");
  await expect(page.locator(".sc-reason").first()).not.toContainText(
    "Final 80",
  );
  await expect(page.locator(".sc-table tbody")).toContainText("Energy");
  await expect(page.locator(".sc-table tbody")).toContainText("Technology");
  await expect(page.locator(".sc-inspector")).toHaveCount(0);
  await expect(page.locator(".sc-grid")).not.toHaveClass(/has-detail/);
  const resultsWidthWithoutDetail = await page
    .locator(".sc-center")
    .evaluate((element) => element.getBoundingClientRect().width);
  await page.screenshot({
    path: info.outputPath("scanner-metadata-table.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Market Movers" }).click();
  await expect(page.locator(".sc-context-panel")).toContainText("TapTide");
  await page.getByRole("button", { name: "Why?", exact: true }).first().click();
  await expect(page.locator(".sc-context-panel")).toHaveCount(1);
  await expect(page.locator(".sc-context-head")).toContainText(
    "Instrument Analysis",
  );
  await expect(page.locator(".sc-grid")).toHaveClass(/has-detail/);
  if (page.viewportSize()!.width >= 1200) {
    const resultsWidthWithDetail = await page
      .locator(".sc-center")
      .evaluate((element) => element.getBoundingClientRect().width);
    expect(resultsWidthWithDetail).toBeLessThan(
      resultsWidthWithoutDetail - 100,
    );
  }
  const analysis = page.locator(
    '[aria-label="Deterministic candidate analysis"]:visible',
  );
  await expect(analysis).toBeVisible();
  const sector = analysis.getByRole("region", {
    name: "Sector Context",
    exact: true,
  });
  await expect(sector).toContainText("Technology");
  await expect(sector).toContainText("NIFTY IT");
  await expect(sector).toContainText("5D vs NIFTY");
  await expect(sector).toContainText("Completed daily bars");
  await sector.getByText("Sector data details", { exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(
    sector.getByText("Identity source: Instrument Metadata"),
  ).toBeVisible();
  await page.keyboard.press("Enter");
  await sector.screenshot({
    path: info.outputPath("scanner-sector-evidence.png"),
  });

  await expect(
    analysis.getByText("Technical score", { exact: true }),
  ).toBeVisible();
  await expect(analysis.getByText("Missing evidence")).toBeVisible();
  await expect(
    analysis.getByText(
      "Technical score is the V1 deterministic match baseline, not a probability.",
    ),
  ).toBeVisible();
  await analysis.getByText("Provenance and freshness").click();
  await expect(analysis.getByText(/unavailable/).first()).toBeVisible();
  await page.screenshot({
    path: info.outputPath("scanner-analysis-light.png"),
    fullPage: page.viewportSize()!.width >= 1200,
  });
  await page.getByLabel("Close panel").click();
  await page
    .locator(".sc-table tbody tr")
    .filter({ hasText: "RELIANCE" })
    .getByRole("button", { name: "Why?", exact: true })
    .click();
  await expect(sector).toContainText("NIFTY OIL & GAS");
  await expect(sector).toContainText("Completed daily bars · available");
  await expect(sector).not.toContainText("INSTRUMENT_NOT_FOUND");
  await sector.screenshot({
    path: info.outputPath("scanner-sector-oil-gas-evidence.png"),
  });
  await page.getByLabel("Close panel").click();
  await page.getByRole("button", { name: "Save Scan", exact: false }).click();
  await page.getByLabel("Scan name", { exact: true }).fill("My RSI");
  await page
    .getByRole("button", { name: "Save configuration", exact: true })
    .click();
  await page.getByRole("button", { name: "My Scans" }).click();
  await expect(page.locator(".sc-context-panel")).toContainText("My RSI");
  await page.getByLabel("Select RELIANCE", { exact: true }).check();
  await page
    .getByRole("button", { name: "Add Selected to Watchlist", exact: false })
    .click();
  await page.getByRole("button", { name: "Add results", exact: true }).click();
  const persisted = await (
    await page.request.get("/api/v1/watchlists/" + list.id)
  ).json();
  expect(persisted.count).toBe(3);
  await page.getByRole("button", { name: "Add All", exact: true }).click();
  await page.getByRole("button", { name: "Add results", exact: true }).click();
  await page
    .locator(".sc-table .sc-symbol")
    .filter({ hasText: "RELIANCE" })
    .click();
  const surface = page.locator(".sc-inspector");
  await expect(surface).toBeVisible();
  await expect(
    surface.getByText("As scanned · completed daily bars", { exact: true }),
  ).toBeVisible();
  const metadata = surface.getByRole("region", {
    name: "Instrument metadata",
  });
  await expect(metadata).toContainText("Energy");
  await expect(metadata).toContainText("Oil & Gas Exploration");
  await expect(metadata).toContainText("₹20 L Cr");
  await expect(metadata).toContainText("NIFTY OIL & GAS");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: info.outputPath("scanner-detail-light.png"),
    fullPage: page.viewportSize()!.width >= 1200,
  });
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  await expect(
    surface.getByRole("button", { name: "Clear selection" }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("scanner-detail-dark.png"),
    fullPage: page.viewportSize()!.width >= 1200,
  });
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "light";
  });
  await surface.getByRole("button", { name: "Clear selection" }).click();
  await expect(page.locator(".sc-inspector")).toHaveCount(0);
  await expect(page.locator(".sc-grid")).not.toHaveClass(/has-detail/);
  const resultsWidthAfterClear = await page
    .locator(".sc-center")
    .evaluate((element) => element.getBoundingClientRect().width);
  expect(
    Math.abs(resultsWidthAfterClear - resultsWidthWithoutDetail),
  ).toBeLessThan(2);
  await page.screenshot({
    path: info.outputPath("scanner-cleared-light.png"),
    fullPage: true,
  });
  await expect(page.locator(".wl-toast")).toBeHidden({ timeout: 7000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: info.outputPath("scanner-results-light.png"),
    fullPage: true,
  });
  const width = page.viewportSize()!.width;
  const overflowDiagnostics = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          selector: [
            element.tagName.toLowerCase(),
            element.id && "#" + element.id,
            ...Array.from(element.classList).map((name) => "." + name),
          ]
            .filter(Boolean)
            .join(""),
          left: Math.round(rect.left),
          right: Math.round(rect.right),
          width: Math.round(rect.width),
          text: element.textContent?.trim().slice(0, 80),
          ariaLabel: element.getAttribute("aria-label"),
          parentClass: element.parentElement?.className,
        };
      })
      .filter((item) => item.right > window.innerWidth + 1 || item.left < -1)
      .slice(0, 20),
  );
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
    JSON.stringify(overflowDiagnostics),
  ).toBeLessThanOrEqual(width);
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  await page.waitForTimeout(250);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: info.outputPath("scanner-dark.png"),
    fullPage: true,
  });
  await page.reload();
  await page.getByRole("button", { name: "My Scans" }).click();
  await expect(page.locator(".sc-context-panel")).toContainText("My RSI");
  await page.getByRole("button", { name: /Scan History ▾/ }).click();
  await page.getByRole("menuitem", { name: "Recent Scans" }).click();
  await page
    .locator(".sc-context-panel")
    .getByRole("button", { name: "View", exact: true })
    .first()
    .click();
  await expect(page.locator(".sc-table")).toContainText("RELIANCE");
  await page
    .getByRole("tab", { name: "Derivatives Scanner", exact: false })
    .click();
  await expect(
    page.getByRole("tabpanel", { name: "Derivatives Scanner" }),
  ).toContainText("Select an underlying watchlist or enter Custom underlyings");
  await page.getByRole("tab", { name: /Equity \/ Index Scanner/ }).click();
  await expect(page.locator(".sc-table")).toContainText("RELIANCE");
  const chartApiRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/scanner/"))
      chartApiRequests.push(request.url());
  });
  const renderStart = Date.now();
  await page.getByRole("button", { name: "Charts", exact: true }).click();
  const chartCards = page.locator(".sc-chart-card");
  await expect(chartCards).toHaveCount(3);
  const initialRenderMs = Date.now() - renderStart;
  await expect(
    chartCards.first().locator(".sc-candle-chart svg"),
  ).toBeVisible();
  const columns = await page
    .locator(".sc-chart-grid")
    .evaluate(
      (element) =>
        getComputedStyle(element).gridTemplateColumns.split(" ").length,
    );
  const resultsWidth = await page
    .locator(".sc-results")
    .evaluate((element) => parseFloat(getComputedStyle(element).width));
  expect(columns).toBe(resultsWidth >= 1220 ? 3 : resultsWidth >= 800 ? 2 : 1);
  await page.screenshot({
    path: info.outputPath(`scanner-charts-${width}.png`),
    fullPage: width >= 1024,
  });
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  await expect(chartCards.first()).toHaveCSS(
    "background-color",
    "rgb(18, 29, 41)",
  );
  await page.screenshot({
    path: info.outputPath(`scanner-charts-dark-${width}.png`),
  });
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "light";
  });
  const relianceCard = chartCards.filter({ hasText: "RELIANCE" });
  const rangeStart = Date.now();
  await relianceCard
    .getByRole("button", { name: "RELIANCE 6M chart range" })
    .click();
  await expect(
    relianceCard.getByRole("img", { name: /RELIANCE 6M candlestick/ }),
  ).toBeVisible();
  const rangeSwitchMs = Date.now() - rangeStart;
  await page.screenshot({
    path: info.outputPath(`scanner-charts-range-${width}.png`),
  });
  const selectionStart = Date.now();
  await relianceCard.getByRole("button", { name: "Why?" }).click();
  await expect(page.locator(".sc-context-panel")).toContainText("RELIANCE");
  const selectionMs = Date.now() - selectionStart;
  expect(chartApiRequests).toHaveLength(0);
  await writeFile(
    info.outputPath("scanner-chart-performance.json"),
    JSON.stringify(
      {
        width,
        initialRenderMs,
        rangeSwitchMs,
        selectionMs,
        scannerRequests: chartApiRequests.length,
      },
      null,
      2,
    ),
  );
  await page.screenshot({
    path: info.outputPath(`scanner-charts-selected-${width}.png`),
  });
  await page.getByRole("tab", { name: "Overview" }).click();
  await expect(
    page.locator(".sc-context-panel .sc-candle-chart svg"),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath(`scanner-charts-analysis-${width}.png`),
  });
  await page.getByLabel("Close panel").click();
  await relianceCard.getByRole("button", { name: "Buy RELIANCE" }).click();
  const chartTicket = page.getByRole("dialog");
  await expect(
    chartTicket.getByRole("heading", { name: "Order Ticket" }),
  ).toBeVisible();
  await chartTicket.getByRole("button", { name: "Preview Buy" }).click();
  await page.screenshot({
    path: info.outputPath(`scanner-charts-broker-preview-${width}.png`),
  });
  await chartTicket.getByLabel("Close order ticket").click();
  await page.getByRole("button", { name: "Table", exact: true }).click();
  await expect(page.locator(".sc-table")).toContainText("RELIANCE");
  expect(dispatches).toBe(0);
});
