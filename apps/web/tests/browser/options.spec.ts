import { writeFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { chainFixture } from "../fixtures/option-chain";

test("canonical chain, CE/PE Broker preview, partial data and responsive layout", async ({
  page,
}, info) => {
  test.setTimeout(120000);
  await page.goto("/login");
  await page.getByLabel("Username").fill(`broker-${info.project.name}`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-only-browser-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
  const headers = { Origin: "http://127.0.0.1:3100" };
  const configured = await page.request.post("/api/v1/brokers/accounts", {
    headers,
    data: {
      name: "Options execution",
      api_key: `o3${info.project.name.replaceAll("-", "")}`,
      api_secret: "testsecret123",
    },
  });
  expect(configured.ok()).toBeTruthy();
  const account = (await configured.json()).id;
  const connected = await page.request.post(
    `/api/v1/brokers/accounts/${account}/connect`,
    { headers, data: {} },
  );
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
  const catalog = await page.request.get(
    `/api/v1/brokers/accounts/${account}/order-entry/choices?asset=options&underlying=NIFTY`,
  );
  const expiries = (await catalog.json()).expiries as string[];
  let partial = false;
  let failed = false;
  let chainCalls = 0;
  let confirms = 0;
  await page.route("**/order-entry/intents/*/confirm", async (route) => {
    confirms++;
    await route.abort();
  });
  // Only market-chain input is mocked. Canonical mapping, ticket and preview use
  // the real TWF API with its isolated synthetic broker transport. Never live orders.
  await page.route("**/api/v1/options/**", async (route) => {
    const request = new URL(route.request().url());
    if (failed) {
      await route.fulfill({
        status: 503,
        json: { error: { code: "provider_unavailable" } },
      });
      return;
    }
    if (request.pathname.endsWith("underlyings")) {
      await route.fulfill({ json: ["NIFTY", "BANKNIFTY", "HDFCBANK"] });
      return;
    }
    if (request.pathname.endsWith("expiries")) {
      await route.fulfill({ json: expiries });
      return;
    }
    chainCalls++;
    await route.fulfill({
      json: chainFixture(
        request.searchParams.get("underlying")!,
        request.searchParams.get("expiry")!,
        partial,
      ),
    });
  });
  if (info.project.use.viewport!.width < 1200)
    await page
      .getByRole("button", { name: "Workspace navigation", exact: true })
      .click();
  await page
    .getByRole("link", { name: "Options Analytics", exact: true })
    .click();
  await expect(page).toHaveURL("/options-analytics");
  const start = Date.now();
  await page.getByRole("button", { name: "NIFTY", exact: true }).click();
  const compact = info.project.use.viewport!.width < 768;
  const table = page.getByRole("table", {
    name: compact ? "Compact option chain" : "Calls and puts option chain",
  });
  await expect(table).toBeVisible();
  const initialMs = Date.now() - start;
  await expect(
    page.getByText("Provider source time unavailable", { exact: true }),
  ).toBeVisible();
  const timings: Record<string, number> = { initial_fixture_ms: initialMs };
  const switchStart = Date.now();
  await page.getByLabel("Expiry", { exact: true }).selectOption(expiries[1]);
  await expect(
    page.getByRole("button", { name: "Refresh", exact: true }),
  ).toBeEnabled();
  timings.expiry_fixture_ms = Date.now() - switchStart;
  await page.getByLabel("Expiry", { exact: true }).selectOption(expiries[0]);
  await expect(
    page.getByRole("button", { name: "Refresh", exact: true }),
  ).toBeEnabled();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBeTruthy();
  for (const [side, action] of [
    ["CE", "Buy"],
    ["PE", "Sell"],
  ]) {
    if (compact)
      await page
        .getByRole("button", {
          name: side === "CE" ? "Calls" : "Puts",
          exact: true,
        })
        .click();
    const select = table.getByRole("button", {
      name: `Select NIFTY 25000 ${side}`,
    });
    await select.focus();
    await page.keyboard.press("Enter");
    await expect(select).toHaveAttribute("aria-pressed", "true");
    const begun = Date.now();
    await page
      .getByRole("button", { name: `${action} ${side}`, exact: true })
      .click();
    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByRole("heading", { name: "Order Ticket", exact: true }),
    ).toBeVisible();
    await expect(
      dialog.getByRole("combobox", { name: "Order type", exact: true }),
    ).toBeEnabled();
    await dialog
      .getByRole("combobox", { name: "Order type", exact: true })
      .selectOption("LIMIT");
    await dialog.getByLabel("Price (₹)", { exact: true }).fill("147.05");
    const responsePromise = page.waitForResponse(
      (r) =>
        r.url().endsWith("/option-preview") && r.request().method() === "POST",
    );
    await dialog
      .getByRole("button", { name: `Preview ${action}`, exact: true })
      .click();
    const response = await responsePromise;
    expect(response.ok()).toBeTruthy();
    const payload = response.request().postDataJSON();
    expect(payload.contract).toEqual({
      exchange: "NFO",
      underlying_symbol: "NIFTY",
      expiry: expiries[0],
      strike: "25000",
      option_type: side,
    });
    const intent = await response.json();
    expect(intent.option_contract.canonical_id).toBe(
      `NFO:NIFTY:${expiries[0]}:25000:${side}`,
    );
    expect(intent.option_contract.lot_size).toBe(65);
    expect(intent.status).toBe("PREVIEWED");
    await expect(
      dialog.getByRole("heading", { name: "Preview", exact: true }),
    ).toBeVisible();
    timings[`${action.toLowerCase()}_preview_ms`] = Date.now() - begun;
    await page.screenshot({
      path: info.outputPath(`preview-${side}.png`),
      fullPage: true,
      animations: "disabled",
    });
    // Explicitly stop at preview. Never click Confirm.
    await dialog.getByRole("button", { name: "Close order ticket" }).click();
  }
  const refreshStart = Date.now();
  partial = true;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(
    page.getByText(
      "Partial chain. Available contracts and values are retained.",
      { exact: true },
    ),
  ).toBeVisible();
  timings.refresh_fixture_ms = Date.now() - refreshStart;
  await expect(page.getByLabel("Expiry", { exact: true })).toHaveValue(
    expiries[0],
  );
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    document.documentElement.dataset.theme = "light";
  });
  await page.waitForTimeout(200);
  await page.screenshot({
    path: info.outputPath("chain-light.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  await page.waitForTimeout(200);
  await page.screenshot({
    path: info.outputPath("chain-dark.png"),
    fullPage: true,
    animations: "disabled",
  });
  expect(chainCalls).toBe(4);
  failed = true;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(
    page.locator(".options-workspace").getByRole("alert"),
  ).toContainText("Dhan market data unavailable");
  expect(confirms).toBe(0);
  await writeFile(
    info.outputPath("fixture-timings.json"),
    JSON.stringify(timings),
  );
  await info.attach("fixture-timings", {
    body: JSON.stringify(timings),
    contentType: "application/json",
  });
});
