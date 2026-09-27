import { test, expect } from "@playwright/test";

test("Zerodha setup, cross-site callback, read-only binding, catalog pagination, disconnect and reauth", async ({
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
  await page
    .getByRole("link", { name: "Instrument Search", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Instrument Search", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Refresh catalog", exact: true })
    .click();
  await expect(
    page.getByText("34 matching instruments", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Search instruments", { exact: true }).fill("HAL");
  await page.getByLabel("Segment", { exact: true }).fill("NFO-OPT");
  await page.getByLabel("Expiry", { exact: true }).fill("2026-10-29");
  await page.getByLabel("Strike", { exact: true }).fill("4500");
  await page
    .getByRole("combobox", { name: "Contract kind", exact: true })
    .selectOption("CE");
  await page.getByRole("button", { name: "Search catalog" }).click();
  await expect(
    page.getByRole("heading", { name: "HAL26OCT4500CE", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("1 matching instruments", { exact: true }),
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
    await page.screenshot({
      path: info.outputPath(`catalog-${theme}.png`),
      fullPage: true,
      animations: "disabled",
    });
  }
  await page
    .getByRole("combobox", { name: "Contract kind", exact: true })
    .selectOption("PE");
  await page.getByRole("button", { name: "Search catalog" }).click();
  await expect(
    page.getByRole("heading", { name: "HAL26OCT4500PE", exact: true }),
  ).toBeVisible();
  await test.step("pagination retains A after B reuses native tokens", async () => {
    await page.getByLabel("Search instruments", { exact: true }).fill("PAGE");
    for (const label of ["Segment", "Expiry", "Strike"])
      await page.getByLabel(label, { exact: true }).fill("");
    await page
      .getByRole("combobox", { name: "Contract kind", exact: true })
      .selectOption("");
    const nextResponse = () =>
      page.waitForResponse(
        (response) =>
          response.url().includes("/instruments?") &&
          response.request().method() === "GET",
      );
    let response = nextResponse();
    await page.getByRole("button", { name: "Search catalog" }).click();
    const first = await (await response).json();
    const versionA = first.catalog.version;
    expect(first.instruments).toHaveLength(25);
    expect(
      first.instruments.every((row: { symbol: string }) =>
        row.symbol.startsWith("PAGEA"),
      ),
    ).toBe(true);
    await expect(
      page.getByRole("heading", { name: "PAGEA00", exact: true }),
    ).toBeVisible();
    const publication = page.waitForResponse(
      (response) =>
        response.url().endsWith("/refresh") &&
        response.request().method() === "POST",
    );
    response = nextResponse();
    await page
      .getByRole("button", { name: "Refresh catalog", exact: true })
      .click();
    expect((await publication).status()).toBe(200);
    expect((await (await response).json()).catalog.version).toBe(versionA);
    response = nextResponse();
    await page.getByRole("button", { name: "Next", exact: true }).click();
    const next = await response;
    expect(new URL(next.url()).searchParams.get("version")).toBe(versionA);
    const second = await next.json();
    expect(second.catalog.version).toBe(versionA);
    expect(second.instruments).toHaveLength(5);
    expect(
      [...first.instruments, ...second.instruments].map((row) => row.symbol),
    ).toEqual(
      Array.from(
        { length: 30 },
        (_, i) => `PAGEA${String(i).padStart(2, "0")}`,
      ),
    );
    await expect(
      page.getByRole("heading", { name: "PAGEA25", exact: true }),
    ).toBeVisible();
    response = nextResponse();
    await page.getByRole("button", { name: "Previous", exact: true }).click();
    const previous = await response;
    expect(new URL(previous.url()).searchParams.get("version")).toBe(versionA);
    expect((await previous.json()).instruments).toEqual(first.instruments);
    await expect(
      page.getByRole("heading", { name: "PAGEA00", exact: true }),
    ).toBeVisible();
    await page.getByLabel("Search instruments", { exact: true }).fill("PAGEB");
    await page.getByLabel("Exchange", { exact: true }).fill("NSE");
    response = nextResponse();
    await page.getByRole("button", { name: "Search catalog" }).click();
    const fresh = await response;
    expect(new URL(fresh.url()).searchParams.has("version")).toBe(false);
    const current = await fresh.json();
    expect(current.catalog.version).not.toBe(versionA);
    expect(current.instruments[0].native_id).toBe(
      first.instruments[0].native_id,
    );
    expect(current.instruments[0].symbol).toBe("PAGEB00");
    await expect(
      page.getByRole("heading", { name: "PAGEB00", exact: true }),
    ).toBeVisible();
  });
  await page.getByRole("link", { name: "Brokers / connection" }).click();
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
