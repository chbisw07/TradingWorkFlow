import { expect, test } from "@playwright/test";

test("OE-4 policy controls future admissions; persisted AUTO executes and MANUAL waits", async ({
  page,
}, info) => {
  test.setTimeout(120000);
  await page.goto("/login");
  await page.getByLabel("Username").fill(`oe4-${info.project.name}`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-only-browser-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
  const headers = { Origin: "http://127.0.0.1:3100" };
  const configured = await page.request.post("/api/v1/brokers/accounts", {
    headers,
    data: {
      name: "OE-4 Synthetic",
      api_key: `oe4key${info.project.name.replaceAll("-", "")}`,
      api_secret: "testsecret123",
    },
  });
  expect(configured.ok()).toBeTruthy();
  const account = (await configured.json()).id;
  const connection = await page.request.post(
    `/api/v1/brokers/accounts/${account}/connect`,
    { headers, data: {} },
  );
  const url = new URL((await connection.json()).login_url);
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
  async function admit(limitPrice = "100.05") {
    const draft = {
      account_id: account,
      reference: "ZERODHA:NSE:HAL",
      native_token: "1",
      side: "BUY",
      quantity: 1,
      order_type: "LIMIT",
      limit_price: limitPrice,
      product: "CNC",
      validity: "DAY",
    };
    const preview = await page.request.post("/api/v1/twf-orders/preview", {
      headers,
      data: draft,
    });
    expect(preview.ok()).toBeTruthy();
    const created = await page.request.post("/api/v1/twf-orders", {
      headers,
      data: { ...draft, preview_id: (await preview.json()).preview_id },
    });
    expect(created.ok()).toBeTruthy();
    const order = (await created.json()).order;
    const admitted = await page.request.post("/api/v1/twf-queue/admit", {
      headers,
      data: { twf_order_id: order.twf_order_id, broker_account_id: account },
    });
    expect(admitted.ok()).toBeTruthy();
    return admitted.json();
  }
  const q1 = await admit();
  expect(q1.effective_dispatch_mode).toBe("MANUAL");
  await page.goto("/trade?tab=queue");
  await page.getByRole("link", { name: "Execution Queue" }).click();
  page.on("dialog", async (dialog) => {
    if (dialog.message().includes("New Queue entries"))
      expect(dialog.message()).toContain(
        "Existing Queue entries are unchanged.",
      );
    await dialog.accept();
  });
  await page.getByRole("button", { name: "AUTO", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "AUTO", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  const q2 = await admit();
  expect(q2.effective_dispatch_mode).toBe("AUTO");
  await page.getByRole("button", { name: "MANUAL", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "MANUAL", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  const q3 = await admit();
  expect(q3.effective_dispatch_mode).toBe("MANUAL");
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(`/api/v1/twf-queue/${q2.queue_entry_id}`)
          ).json()
        ).queue_state,
    )
    .toBe("DISPATCHED");
  for (const q of [q1, q3]) {
    const persisted = await (
      await page.request.get(`/api/v1/twf-queue/${q.queue_entry_id}`)
    ).json();
    expect(persisted.queue_state).toBe("READY");
    expect(persisted.version).toBe(q.version);
  }
  await page.reload();
  const row = page.getByRole("row").filter({ hasText: q1.public_queue_id });
  await expect(row.getByText("READY FOR DISPATCH")).toBeVisible();
  await row.getByRole("button", { name: "Dispatch", exact: true }).click();
  await expect(row.getByText("DISPATCHED", { exact: true })).toBeVisible();
  const autoRow = page.getByRole("row").filter({ hasText: q2.public_queue_id });
  await expect(
    autoRow.getByRole("button", { name: "Dispatch", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText(q3.public_order_id, { exact: true }),
  ).toBeVisible();
  const waiting = page.getByRole("row").filter({ hasText: q3.public_queue_id });
  await waiting.getByRole("button", { name: "Hold", exact: true }).click();
  await expect(waiting.getByText("HELD", { exact: true })).toBeVisible();
  await waiting.getByRole("button", { name: "Release", exact: true }).click();
  await expect(waiting.getByText("READY FOR DISPATCH")).toBeVisible();
  await waiting.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(waiting.getByText("CANCELLED", { exact: true })).toBeVisible();
  for (const [price, outcome] of [
    ["100.10", "FAILED"],
    ["100.15", "RECONCILIATION_REQUIRED"],
  ]) {
    const q = await admit(price);
    await page.reload();
    const failedRow = page
      .getByRole("row")
      .filter({ hasText: q.public_queue_id });
    await failedRow
      .getByRole("button", { name: "Dispatch", exact: true })
      .click();
    await expect(
      failedRow.getByText(outcome.replaceAll("_", " "), { exact: true }),
    ).toBeVisible();
    await expect(
      failedRow.getByRole("button", { name: "Dispatch", exact: true }),
    ).toHaveCount(0);
    const persisted = await (
      await page.request.get(`/api/v1/twf-queue/${q.queue_entry_id}`)
    ).json();
    expect(persisted.queue_state).toBe(outcome);
    expect(persisted.source_kind).toBe("MANUAL");
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth + 2,
    ),
  ).toBe(false);
  await page.screenshot({
    path: info.outputPath("oe4-queue.png"),
    fullPage: true,
  });
});
