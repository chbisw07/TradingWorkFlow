import { mkdir } from "node:fs/promises";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, baseURL }, info) => {
  const login = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: baseURL! },
    data: {
      username: `trade-${info.project.name}`,
      password: "test-only-browser-password",
    },
  });
  expect(login.ok()).toBe(true);
  const headers = { Origin: baseURL! };
  const configured = await page.request.post("/api/v1/brokers/accounts", {
    headers,
    data: {
      name: "UX Fixture Broker",
      api_key: `uxkey${info.project.name.replaceAll("-", "")}`,
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
});

test("five workspaces use compact blue-white headers at desktop and mobile widths", async ({
  page,
}) => {
  const width = page.viewportSize()!.width;
  const evidence = "/tmp/twf-ux-blue-white-evidence";
  await mkdir(evidence, { recursive: true });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const [name, route] of [
    ["scanner", "/scanners"],
    ["trade-queue", "/trade/queue"],
    ["trade-positions", "/trade/positions"],
    ["brokers", "/brokers"],
    ["watchlists", "/watchlists"],
    ["options", "/options-analytics"],
  ]) {
    await page.goto(route);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    if (name === "scanner") {
      await expect(page.locator(".sc-page-head")).toHaveCount(0);
      await expect(page.locator(".sc-type-tabs")).toBeVisible();
      await expect(
        page.getByRole("link", { name: "Provider connections" }),
      ).toBeVisible();
    } else if (name.startsWith("trade")) {
      await expect(page.locator(".orders-heading")).toHaveCount(0);
      await expect(
        page.getByRole("navigation", { name: "Trade sections" }),
      ).toBeVisible();
      await expect(page.getByLabel("Instrument account")).toBeVisible();
      await expect(
        page.getByRole("button", { name: "New Order" }),
      ).toBeVisible();
    } else if (name === "brokers") {
      await page
        .getByRole("navigation", { name: "Broker accounts" })
        .getByRole("link", { name: "UX Fixture Broker" })
        .click();
      await expect(page.locator(".broker-account-tabs")).toBeVisible();
      await expect(page.locator(".broker-summary")).toBeVisible();
      await expect(page.locator(".broker-workspace > h1")).toHaveClass(
        /sr-only/,
      );
    } else if (name === "watchlists") {
      await expect(
        page.getByRole("button", { name: /New Watchlist/ }),
      ).toBeVisible();
      await expect(page.locator(".wl-page-head h1")).toHaveCount(0);
    } else {
      await expect(page.locator(".options-title")).toHaveCount(0);
      await expect(page.locator(".options-controls")).toBeVisible();
      await expect(
        page.getByRole("link", { name: "Provider connections" }),
      ).toBeVisible();
    }
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await page.screenshot({
      path: `${evidence}/${width}-${name}.png`,
      animations: "disabled",
    });
  }
  expect(errors).toEqual([]);
});
