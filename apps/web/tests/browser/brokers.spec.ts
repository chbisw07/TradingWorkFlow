import { expect, test } from "@playwright/test";
test("complete broker journey, both themes, responsive tables and disconnect", async ({
  page,
}, testInfo) => {
  const callback = await page.request.get(
    "/brokers/callback?request_token=test-only-marker",
  );
  expect(callback.headers()["referrer-policy"]).toBe("no-referrer");
  expect(callback.headers()["cache-control"]).toContain("no-store");
  await page.goto("/login");
  await page.getByLabel("Username").fill(`broker-${testInfo.project.name}`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-only-browser-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
  await page.goto("/brokers");
  await expect(page.getByText("No broker connected yet")).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Broker accounts" }).getByRole("link"),
  ).toHaveCount(2);
  await page
    .getByRole("link", { name: "Manage Brokers", exact: true })
    .last()
    .click();
  await expect(
    page.getByRole("button", { name: "Coming later", exact: true }),
  ).toHaveCount(4);
  await page.getByRole("link", { name: "Setup", exact: true }).click();
  await page.getByLabel("Connection name").fill("Zerodha – Primary");
  await page.getByLabel("API Key", { exact: true }).fill("testapikey123");
  await page.getByLabel("API Secret", { exact: true }).fill("testsecret123");
  await page.route(
    "https://kite.zerodha.com/connect/login?**",
    async (route) => {
      const url = new URL(route.request().url());
      const state = new URLSearchParams(
        url.searchParams.get("redirect_params") || "",
      ).get("state");
      await route.fulfill({
        status: 302,
        headers: {
          location: `http://127.0.0.1:3100/brokers/callback?status=success&request_token=request123&state=${state}`,
        },
      });
    },
  );
  await page.getByRole("button", { name: "Connect Broker" }).click();
  await expect(page).toHaveURL(/\/brokers\/accounts\/[^/]+\/overview/);
  await expect(
    page
      .getByRole("navigation", { name: "Broker accounts" })
      .getByRole("link", { name: "Zerodha – Primary" }),
  ).toBeVisible();
  for (const theme of ["dark", "light"]) {
    await page.evaluate((theme) => {
      document.documentElement.dataset.theme = theme;
      localStorage.setItem("twf-theme", theme);
    }, theme);
    for (const view of [
      "Overview",
      "Holdings",
      "Positions",
      "Orders",
      "Funds",
      "Instruments",
    ]) {
      await page
        .getByRole("navigation", { name: "Broker functions" })
        .getByRole("link", { name: view, exact: true })
        .click();
      await expect(page).toHaveURL(
        new RegExp(`/accounts/[^/]+/${view.toLowerCase()}$`),
      );
      await expect(
        page.getByRole("heading", { name: view, exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText(
          view === "Instruments"
            ? /READ ONLY · DAILY INSTRUMENT LIST/
            : /LIVE DATA · READ ONLY/,
        ),
      ).toBeVisible();
      if (view === "Instruments") {
        await page
          .getByLabel("Search instruments", { exact: true })
          .fill("HAL");
        await page.getByRole("button", { name: "Search", exact: true }).click();
        await expect(
          page.getByRole("rowheader", { name: /HAL/ }),
        ).toBeVisible();
      }
      if (view === "Holdings") {
        const row = page.getByRole("row", { name: /HAL/ });
        await expect(row.getByRole("cell")).toHaveText([
          "20",
          "100",
          "120",
          "2,400",
          "400",
          "20",
        ]);
      }
      if (view === "Overview") {
        await expect(
          page
            .locator(".broker-summary > div")
            .filter({ hasText: "Holdings value" })
            .locator("strong"),
        ).toHaveText("2,400");
      }
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth,
          ),
        )
        .toBe(true);
      await page.screenshot({
        path: testInfo.outputPath(`${theme}-${view}.png`),
        fullPage: true,
      });
    }
  }
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(
    page.getByText(/NOT CONNECTED · TRADING DISABLED/),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Broker accounts" }).getByRole("link"),
  ).toHaveCount(2);
});
