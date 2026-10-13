import { expect, test } from "@playwright/test";

test("O5 Futures stays in Derivatives workspace with explicit filters and icon counts", async ({
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
  await page.route("**/api/v1/scanner/movers", (route) =>
    route.fulfill({
      json: {
        state: "READY",
        coverage: "PARTIAL",
        freshness: "Snapshot",
        rows: [
          {
            symbol: "RELIANCE",
            provider: "TapTide",
            tool: "get_market_movers",
            bucket: "top_gainers",
            metrics: { change: 1.2, volume: 1000 },
            reasons: [],
          },
        ],
      },
    }),
  );
  await page.route("**/api/v1/scanner/derivatives/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/futures/catalog"))
      return route.fulfill({
        json: {
          max_underlyings: 50,
          fields: [
            {
              field: "volume",
              category: "Price & Liquidity",
              label: "Volume",
              kind: "integer",
              minimum: 0,
              operators: [">", ">=", "<", "<=", "equals", "between"],
            },
          ],
          expiry_modes: ["NEAREST", "EXACT"],
        },
      });
    if (path.endsWith("/templates"))
      return route.fulfill({ json: { built_in: [], user: [] } });
    if (
      path.endsWith("/saved") ||
      (path.endsWith("/runs") && route.request().method() === "GET")
    )
      return route.fulfill({ json: [] });
    if (path.endsWith("/futures/runs") && route.request().method() === "POST") {
      const config = route.request().postDataJSON();
      expect(config.instrument_scope).toBe("FUTURES");
      expect(config.universe.symbols).toEqual(["NIFTY"]);
      expect(config.filters).toEqual([
        { field: "volume", operator: ">=", value: 100 },
      ]);
      return route.fulfill({
        json: {
          id: "00000000-0000-0000-0000-000000000501",
          created_at: "2026-10-13T09:00:00Z",
          config,
          counts: {
            requested: 1,
            resolved: 1,
            contracts_evaluated: 1,
            not_evaluated: 0,
            matches: 1,
          },
          underlyings: [{ symbol: "NIFTY", outcome: "MATCH", failure: null }],
          rows: [
            {
              contract: {
                canonical_id: "NSE:FUTIDX:NIFTY:2099-12-30:NIFTYFUT",
                exchange: "NSE",
                underlying_symbol: "NIFTY",
                instrument_type: "FUTIDX",
                expiry: "2099-12-30",
                trading_symbol: "NIFTYFUT",
                provider_native_id: "NSE_FNO:101",
                lot_size: 65,
                tick_size: "0.05",
              },
              underlying: "NIFTY",
              expiry: "2099-12-30",
              dte: 100,
              quote: {
                last_price: "25000",
                open: "24900",
                volume: "1000",
                open_interest: "5000",
                provider_source_time: "2026-10-13T09:00:00Z",
                received_at: "2026-10-13T09:00:00Z",
              },
              spot_quote: {
                last_price: "24980",
                provider_source_time: "2026-10-13T09:00:00Z",
              },
              observed: {
                ltp: 25000,
                change_percent: 0.5,
                volume: 1000,
                volume_percentile: 100,
                open_interest: 5000,
                oi_percentile: 100,
                change_in_open_interest: null,
                oi_change_percent: null,
                basis_abs: 20,
                basis_percent: 0.08,
                underlying_trend: "Up",
                interpretation: null,
              },
              volume_percentile: 100,
              relative_volume_cohort_size: 5,
              oi_percentile: 100,
              relative_oi_cohort_size: 5,
              basis_reason: "Same batch",
              spot_change_percent: 0.2,
              comparison_window: null,
              futures_interpretation: {
                label: "Insufficient evidence",
                inferred: true,
                reason: "No prior OI",
              },
              source_time: "2026-10-13T09:00:00Z",
              received_at: "2026-10-13T09:00:00Z",
              outcome: "MATCH",
              diagnostics: [
                {
                  filter: config.filters[0],
                  observed: 1000,
                  threshold: 100,
                  passed: true,
                  reason: "Volume >= 100",
                },
              ],
              missing_evidence: [],
              reason: "1/1 active filters matched",
            },
          ],
        },
      });
    }
    return route.continue();
  });
  await page.addInitScript(() => localStorage.setItem("twf-theme", "light"));
  await page.goto("/scanners");
  await page.getByRole("tab", { name: /Derivatives Scanner/ }).click();
  await expect(page.getByRole("group", { name: "Instrument" })).toBeVisible();
  await page.getByRole("button", { name: "Futures", exact: true }).focus();
  await page.keyboard.press("Enter");
  const future = page.getByRole("tabpanel", { name: "Futures Scanner" });
  await expect(future).toBeVisible();
  await expect(
    future
      .getByLabel("Active Futures scan configuration")
      .getByText("Volume", { exact: false }),
  ).toHaveCount(0);
  await future.getByLabel("NSE underlyings").fill("NIFTY");
  await future.getByLabel("Field").selectOption("volume");
  await future.getByLabel("Value").fill("100");
  await future.getByRole("button", { name: "Add / update filter" }).click();
  await future.getByRole("button", { name: "Run Scan" }).click();
  await expect(future.locator("small", { hasText: "1 matches" })).toBeVisible();
  await expect(future.locator(".derivative-count-card")).toHaveCount(5);
  await expect(future.locator(".derivative-count-icon svg")).toHaveCount(5);
  await expect(
    future.getByRole("columnheader", { name: "Spot Direction" }),
  ).toHaveCount(1);
  await expect(future.locator(".derivative-trend-up").first()).toContainText(
    "▲ Up",
  );
  await page.screenshot({ path: info.outputPath("futures-results.png") });
  await future.getByRole("button", { name: "Why?" }).click();
  await expect(
    future.getByText("Passed · Volume >= 100", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Options", exact: true }).click();
  await expect(
    page.getByRole("tabpanel", { name: "Derivatives Scanner" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Futures", exact: true }).click();
  await expect(future.locator("small", { hasText: "1 matches" })).toBeVisible();
  await page.getByRole("button", { name: "Market Movers" }).click();
  await future.getByRole("button", { name: "Load movers" }).click();
  await expect(future.getByRole("button", { name: "RELIANCE" })).toBeVisible();
  await future.getByRole("button", { name: "RELIANCE" }).click();
  await expect(future.getByLabel("NSE underlyings")).toHaveValue("RELIANCE");
});
