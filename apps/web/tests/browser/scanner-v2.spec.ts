import { expect, test } from "@playwright/test";

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
  await page.addInitScript(() => localStorage.setItem("twf-theme", "light"));
  let dispatches = 0;
  page.on("request", (r) => {
    if (/\/(confirm|dispatch|submit)$/.test(r.url())) dispatches++;
  });
  await page.goto("/scanners");
  await expect(
    page.getByRole("heading", { name: "Scanners", exact: true }),
  ).toBeVisible();
  if (page.viewportSize()!.width <= 800)
    await page.locator(".sc-builder > details > summary").click();
  await page.getByRole("button", { name: "Watchlist", exact: true }).click();
  await page.getByLabel("Watchlist", { exact: true }).selectOption(list.id);
  await expect(page.locator(".sc-members")).toContainText("RELIANCE");
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
  await expect(page.locator(".sc-counts")).toContainText("matches 3", {
    timeout: 30000,
  });
  await expect(page.locator(".sc-reason").first()).toContainText(
    "1/1 technical · Context +0 Mixed · Final 80",
  );
  await expect(page.locator(".sc-table thead")).toContainText("Sector");
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
  await page.getByRole("button", { name: "Why?", exact: true }).first().click();
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
  if (page.viewportSize()!.width < 1200)
    await page.getByLabel("Close dialog").click();
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
  if (page.viewportSize()!.width < 1200)
    await page.getByLabel("Close dialog").click();
  await page.getByRole("button", { name: "Save Scan", exact: false }).click();
  await page.getByLabel("Scan name", { exact: true }).fill("My RSI");
  await page
    .getByRole("button", { name: "Save configuration", exact: true })
    .click();
  await expect(page.locator("#sc-saved")).toContainText("My RSI");
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
  if (page.viewportSize()!.width < 1200)
    await expect(
      page.getByRole("dialog", { name: "Result analysis" }),
    ).toBeVisible();
  const surface =
    page.viewportSize()!.width < 1200
      ? page.getByRole("dialog")
      : page.locator(".sc-inspector");
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
  await expect(page.locator("#sc-saved")).toContainText("My RSI");
  await page
    .locator("#sc-history")
    .getByRole("button", { name: "View", exact: true })
    .first()
    .click();
  await expect(page.locator(".sc-table")).toContainText("RELIANCE");
  await page
    .getByRole("tab", { name: "Derivatives Scanner", exact: false })
    .click();
  await expect(
    page.getByText("Derivative analytics are not available in this version.", {
      exact: false,
    }),
  ).toBeVisible();
  expect(dispatches).toBe(0);
});
