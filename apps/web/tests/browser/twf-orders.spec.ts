import { expect, test } from "@playwright/test";

test("OE-2 reuses selection, ticket and preview for Equity, Futures and Options, then stops at READY", async ({
  page,
}, info) => {
  test.setTimeout(120000);
  await page.goto("/login");
  await page.getByLabel("Username").fill(`oe2-${info.project.name}`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-only-browser-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
  const headers = { Origin: "http://127.0.0.1:3100" };
  const configured = await page.request.post("/api/v1/brokers/accounts", {
    headers,
    data: {
      name: "OE-2 Instrument Account",
      api_key: `oe2key${info.project.name.replaceAll("-", "")}`,
      api_secret: "testsecret123",
    },
  });
  expect(configured.ok()).toBeTruthy();
  const account = (await configured.json()).id;
  const connect = await page.request.post(
    `/api/v1/brokers/accounts/${account}/connect`,
    { headers, data: {} },
  );
  expect(connect.ok()).toBeTruthy();
  const url = new URL((await connect.json()).login_url);
  const state = new URLSearchParams(
    url.searchParams.get("redirect_params")!,
  ).get("state");
  expect(
    (
      await page.request.post("/api/v1/brokers/callback", {
        headers,
        data: { state, request_token: `order-request-${info.project.name}` },
      })
    ).ok(),
  ).toBeTruthy();
  await page.goto("/orders");
  await expect(page.getByRole("heading", { name: "TWF Orders" })).toBeVisible();
  for (const asset of ["Equity", "Futures", "Options"] as const) {
    await page.getByRole("button", { name: "+ New Order" }).click();
    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByRole("heading", { name: "Select Instrument" }),
    ).toBeVisible();
    await dialog.getByRole("radio", { name: asset, exact: true }).check();
    if (asset === "Equity") {
      await dialog.getByLabel("Search stock").fill("HAL");
      await dialog
        .getByRole("button", { name: "Buy HAL", exact: true })
        .click();
      await dialog.getByLabel("Quantity").fill("2");
    } else {
      await dialog
        .getByRole("combobox", { name: "Underlying", exact: true })
        .selectOption("NIFTY");
      await dialog
        .getByRole("combobox", { name: "Expiry", exact: true })
        .selectOption({ index: 1 });
      if (asset === "Options") {
        await dialog
          .getByRole("combobox", { name: "Option type", exact: true })
          .selectOption("CE");
        await dialog
          .getByRole("combobox", { name: "Strike", exact: true })
          .selectOption("25000");
      }
      await dialog
        .getByRole("button", {
          name: asset === "Futures" ? "Buy NIFTYFUT1" : "Buy NIFTYCE1",
        })
        .click();
      await dialog.getByLabel("Lots").fill("1");
    }
    await expect(
      dialog.getByRole("heading", { name: "Order Ticket" }),
    ).toBeVisible();
    await dialog.getByLabel("Order type").selectOption("LIMIT");
    await dialog.getByLabel("Price (₹)").fill("100.05");
    await dialog.getByRole("button", { name: "Preview Buy" }).click();
    await expect(
      dialog.getByText(/No broker order will be submitted/),
    ).toBeVisible();
    await expect(
      dialog.getByText("MANUAL", { exact: false }).first(),
    ).toBeVisible();
    if (asset !== "Options") {
      const code = asset === "Equity" ? "PREVIEW_MISMATCH" : "PREVIEW_EXPIRED";
      const rejectCreate = async (route: import("@playwright/test").Route) => {
        if (route.request().method() === "POST")
          await route.fulfill({
            status: 409,
            contentType: "application/json",
            body: JSON.stringify({
              error: { code, message: "Preview again." },
            }),
          });
        else await route.continue();
      };
      await page.route("**/api/v1/twf-orders", rejectCreate);
      await dialog.getByRole("button", { name: "Create TWF Order" }).click();
      await expect(dialog.getByText(/Please review again/)).toBeVisible();
      await expect(
        dialog.getByRole("button", { name: "Preview Buy" }),
      ).toBeVisible();
      await page.unroute("**/api/v1/twf-orders", rejectCreate);
      await dialog.getByRole("button", { name: "Preview Buy" }).click();
      await expect(
        dialog.getByRole("button", { name: "Create TWF Order" }),
      ).toBeVisible();
    }
    await dialog.getByRole("button", { name: "Create TWF Order" }).click();
    await expect(
      dialog.getByRole("heading", { name: "TWF Order Created" }),
    ).toBeVisible();
    await expect(
      dialog.getByText("READY", { exact: false }).first(),
    ).toBeVisible();
    await dialog.getByRole("link", { name: "View Order Details" }).click();
    await expect(
      page.getByRole("heading", { name: "Order Details" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "History" }).click();
    await expect(
      page.getByText("ORDER_CREATED", { exact: false }),
    ).toBeVisible();
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Order Details" }),
    ).toBeVisible();
    await expect(
      page.getByText("READY", { exact: true }).first(),
    ).toBeVisible();
  }
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 2,
  );
  expect(overflow).toBe(false);
});
