import { expect, test } from "@playwright/test";

const builtinId = "77777777-7777-4777-8777-777777777777";
const userId = "88888888-8888-4888-8888-888888888888";
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
  instrument_type_summary: ["EQUITY"],
  source_reference: null,
  source_received_at: null,
  freshness: "CURRENT",
};
const personal = {
  ...base,
  id: userId,
  name: "My Core",
  count: 4,
  ownership_kind: "USER",
  read_only: false,
  system_code: null,
};
const builtIn = {
  ...base,
  id: builtinId,
  name: "Nifty Pharma",
  count: 20,
  ownership_kind: "SYSTEM",
  read_only: true,
  system_code: "NIFTY_PHARMA",
};

test("unified watchlist-first scanner clean, popover and built-in states", async ({
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
  await page.route("**/api/v1/watchlists", async (route) => {
    if (route.request().method() === "GET")
      await route.fulfill({ json: [personal, builtIn] });
    else await route.continue();
  });
  await page.route(`**/api/v1/watchlists/${userId}`, async (route) => {
    await route.fulfill({
      json: {
        ...personal,
        items: Array.from({ length: 4 }, (_, index) => ({
          instrument: {
            instrument_id: `11111111-1111-4111-8111-${String(index + 1).padStart(12, "0")}`,
            symbol: `CORE${index + 1}`,
          },
          kind: "EQUITY",
        })),
      },
    });
  });
  await page.route(
    `**/api/v1/scanner/derivatives/watchlists/${userId}/optionable`,
    async (route) => {
      await route.fulfill({
        json: {
          watchlist_id: userId,
          members: 4,
          optionable: 1,
          symbols: ["CORE1"],
          max_underlyings: 5,
        },
      });
    },
  );
  await page.route(`**/api/v1/watchlists/${builtinId}`, async (route) => {
    await route.fulfill({
      json: {
        ...builtIn,
        items: Array.from({ length: 20 }, (_, index) => ({
          instrument: {
            instrument_id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
            symbol: `PHARMA${index + 1}`,
          },
          kind: "EQUITY",
        })),
      },
    });
  });
  await page.route(
    `**/api/v1/scanner/derivatives/watchlists/${builtinId}/optionable`,
    async (route) => {
      await route.fulfill({
        json: {
          watchlist_id: builtinId,
          members: 20,
          optionable: 2,
          symbols: ["PHARMA1", "PHARMA2"],
          max_underlyings: 5,
        },
      });
    },
  );
  await page.goto("/scanners");
  await page.getByRole("button", { name: "Light theme" }).click();
  await expect(page.locator(".sc-category").first()).toHaveCount(1);
  await expect(
    page.getByRole("heading", { name: "Ready to scan" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Watchlist: Choose watchlist" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Remove filter 1/ }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Index", exact: true }),
  ).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath("equity-clean.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Watchlist: Choose watchlist" })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Select Watchlist" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: /Nifty Pharma, 20 constituents, built-in read-only/,
    }),
  ).toBeVisible();
  await expect(page.getByText(/Create New Watchlist/)).toHaveCount(0);
  await expect(page.getByText(/Manage Watchlists/)).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /Favorite My Core/ }),
  ).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath("equity-watchlists-open.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "My Core (4)" }).click();
  await expect(page.locator(".sc-universe-summary")).toContainText(
    "4 of 4 constituents selected",
  );
  await page.getByRole("button", { name: "Watchlist: My Core" }).click();
  await page
    .getByRole("button", {
      name: /Nifty Pharma, 20 constituents, built-in read-only/,
    })
    .click();
  await expect(page.locator(".sc-universe-summary")).toContainText(
    "20 constituents selected",
  );
  await expect(
    page.getByRole("button", { name: /Watchlist: Nifty Pharma/ }),
  ).toContainText("🔒");
  await page.screenshot({
    path: info.outputPath("equity-built-in-selected.png"),
    fullPage: true,
  });
  await page.getByRole("tab", { name: /Derivatives Scanner/ }).click();
  await expect(
    page.getByRole("heading", { name: "Ready to scan" }),
  ).toBeVisible();
  await expect(page.locator(".derivative-active-bar")).not.toContainText(
    "Volume Percentile",
  );
  await page.screenshot({
    path: info.outputPath("derivatives-clean.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Watchlist: Choose watchlist" })
    .click();
  await expect(page.getByText(/Create New Watchlist/)).toHaveCount(0);
  await expect(page.getByText(/Manage Watchlists/)).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath("derivatives-watchlists-open.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "My Core (4)" }).click();
  await expect(page.locator(".sc-universe-summary")).toContainText(
    "1 optionable",
  );
  await page.getByRole("button", { name: "Watchlist: My Core" }).click();
  await page
    .getByRole("button", {
      name: /Nifty Pharma, 20 constituents, built-in read-only/,
    })
    .click();
  await expect(page.locator(".sc-universe-summary")).toContainText(
    "2 optionable",
  );
  await expect(page.locator(".sc-universe-summary")).toContainText(
    "2 selected",
  );
  await page.screenshot({
    path: info.outputPath("derivatives-built-in-selected.png"),
    fullPage: true,
  });
});
