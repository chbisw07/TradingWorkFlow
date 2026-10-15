import { expect, test } from "@playwright/test";

test("Trade shares its instrument account and New Order flow across all tabs", async ({
  page,
}, info) => {
  test.setTimeout(120000);
  await page.goto("/login");
  await page.getByLabel("Username").fill(`trade-${info.project.name}`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-only-browser-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
  const headers = { Origin: "http://127.0.0.1:3100" };
  const configured = await page.request.post("/api/v1/brokers/accounts", {
    headers,
    data: {
      name: "Trade Instrument Account",
      api_key: `tradekey${info.project.name.replaceAll("-", "")}`,
      api_secret: "testsecret123",
    },
  });
  expect(configured.ok()).toBeTruthy();
  const account = (await configured.json()).id as string;
  const connect = await page.request.post(
    `/api/v1/brokers/accounts/${account}/connect`,
    {
      headers,
      data: {},
    },
  );
  expect(connect.ok()).toBeTruthy();
  const url = new URL((await connect.json()).login_url);
  const state = new URLSearchParams(
    url.searchParams.get("redirect_params")!,
  ).get("state");
  const callback = await page.request.post("/api/v1/brokers/callback", {
    headers,
    data: { state, request_token: `trade-request-${info.project.name}` },
  });
  expect(callback.ok()).toBeTruthy();

  await page.goto("/trade/orders");
  const tabs = page.getByRole("navigation", { name: "Trade sections" });
  const selector = page.getByRole("combobox", { name: "Instrument account" });
  await expect(selector).toHaveValue(account);
  for (const [label, path] of [
    ["Orders", "/trade/orders"],
    ["Execution Queue", "/trade/queue"],
    ["Positions", "/trade/positions"],
  ] as const) {
    await tabs.getByRole("link", { name: label, exact: true }).click();
    await expect(page).toHaveURL(path);
    await expect(selector).toHaveValue(account);
    await expect(tabs.getByRole("link", { name: label })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await page.getByRole("button", { name: "+ New Order" }).click();
    const ticket = page.getByRole("dialog");
    await expect(
      ticket.getByRole("heading", { name: "Select Instrument" }),
    ).toBeVisible();
    await ticket.getByRole("button", { name: "Close order ticket" }).click();
    await expect(ticket).toBeHidden();
    if (label === "Positions") {
      await expect(
        page.getByRole("region", { name: "Positions table" }),
      ).toBeVisible();
      await expect(
        page.getByRole("row", { name: /Totals/ }).getByRole("cell"),
      ).toHaveText(["-997.5", "30", "-967.5"]);
    }
    await expect(
      page.getByText("Service connections", { exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByText("Selected context", { exact: true }),
    ).toHaveCount(0);
    await expect(page.getByText("System console", { exact: true })).toHaveCount(
      0,
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth + 2,
      ),
    ).toBe(false);
  }
  await page.screenshot({
    path: info.outputPath("trade-positions.png"),
    fullPage: true,
  });
  await tabs.getByRole("link", { name: "Orders", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL("/trade/orders");
  await page.reload();
  await expect(selector).toHaveValue(account);
  await expect(
    page.locator(".primary-nav a[href='/trade/orders']").first(),
  ).toHaveText("Trade");
  await page.goto("/positions");
  await expect(page).toHaveURL("/trade/positions");
  await page.goto("/orders");
  await expect(page).toHaveURL("/trade/orders");
});
