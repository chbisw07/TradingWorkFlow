import { test, expect } from "@playwright/test";

test("Zerodha setup, cross-site callback, read-only binding, disconnect and reauth", async ({
  page,
  browserName,
}, info) => {
  const width = info.project.use.viewport!.width;
  const apiPort = browserName === "chromium" ? 8102 : 8103;
  let expired = false;
  let callbackCookie: string | undefined;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/v1/broker-auth/callback")
      callbackCookie = request.headers()["cookie"] || "";
  });
  await page.route(
    "https://kite.zerodha.com/connect/login?*",
    async (route) => {
      const login = new URL(route.request().url());
      const state = new URLSearchParams(
        login.searchParams.get("redirect_params")!,
      ).get("state")!;
      await route.fulfill({
        status: 200,
        contentType: "text/html",
        body: `<html><body><a href="http://localhost:${apiPort}/fixture/kite-login?state=${state}&expired=${expired}">Continue broker authentication</a></body></html>`,
      });
    },
  );
  await page.goto("/login");
  await page.getByLabel("Username").fill(`zerodha-${browserName}-${width}`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-only-browser-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Workspace overview" }),
  ).toBeVisible();
  await page.goto("/brokers");
  await expect(
    page.getByRole("heading", { name: "Zerodha connection", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Add Zerodha account" }).click();
  await page.getByText("Configure Zerodha", { exact: true }).click();
  await page
    .getByLabel("API key / app identifier")
    .fill(`app-${browserName}-${width}`);
  await page
    .getByLabel("API secret", { exact: true })
    .fill("browser-api-secret");
  await page.getByRole("button", { name: "Save configuration" }).click();
  await expect(page.getByLabel("API secret", { exact: true })).toHaveValue("");
  await expect(
    page.getByRole("button", { name: "Connect Zerodha", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Connect Zerodha", exact: true })
    .click();
  await page
    .getByRole("link", { name: "Continue broker authentication" })
    .click();
  await expect(page).toHaveURL(/\/broker-auth\/complete$/);
  await expect(page.getByRole("status")).toContainText(
    "Provider account verified",
  );
  expect(callbackCookie).toBeDefined();
  expect(callbackCookie).not.toContain("twf_session=");
  expect(page.url()).not.toContain("request_token");
  await page.getByRole("link", { name: "Return to Brokers" }).click();
  await expect(page.getByText("CONNECTED", { exact: true })).toBeVisible();
  await expect(
    page.getByText("LIVE DATA · READ ONLY", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Development / Synthetic" }),
  ).toBeVisible();
  for (const theme of ["light", "dark"]) {
    await page.evaluate((value) => {
      document.documentElement.dataset.theme = value;
    }, theme);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await expect(
      page.getByRole("button", { name: "Disconnect from TWF" }),
    ).toBeVisible();
    await page.screenshot({
      path: info.outputPath(`zerodha-${theme}.png`),
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "Disconnect from TWF" }).click();
  await expect(page.getByText("DISCONNECTED", { exact: true })).toBeVisible();
  expired = true;
  await page
    .getByRole("button", { name: "Connect Zerodha", exact: true })
    .click();
  await page
    .getByRole("link", { name: "Continue broker authentication" })
    .click();
  await expect(page).toHaveURL(/\/broker-auth\/complete$/);
  await expect(page.getByRole("status")).toContainText("could not be verified");
  await page.getByRole("link", { name: "Return to Brokers" }).click();
  await expect(
    page.getByRole("button", { name: "Reauthenticate with Zerodha" }),
  ).toBeEnabled();
});
