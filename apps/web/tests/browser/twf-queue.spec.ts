import { expect, test } from "@playwright/test";

test("OE-3 admits one READY order and audits Hold/Release without broker submission", async ({
  page,
}, info) => {
  test.setTimeout(120000);
  await page.goto("/login");
  await page.getByLabel("Username").fill(`queue-${info.project.name}`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-only-browser-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
  const headers = { Origin: "http://127.0.0.1:3100" };
  const configured = await page.request.post("/api/v1/brokers/accounts", {
    headers,
    data: {
      name: "OE-3 Instrument Account",
      api_key: `queuekey${info.project.name.replaceAll("-", "")}`,
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
        data: { state, request_token: `queue-request-${info.project.name}` },
      })
    ).ok(),
  ).toBeTruthy();

  await page.goto("/orders");
  await expect(page.getByRole("heading", { name: "TWF Orders" })).toBeVisible();
  await page.getByRole("button", { name: "+ New Order" }).click();
  const ticket = page.getByRole("dialog");
  await ticket.getByRole("radio", { name: "Equity", exact: true }).check();
  await ticket.getByLabel("Search stock").fill("HAL");
  await ticket.getByRole("button", { name: "Buy HAL", exact: true }).click();
  await ticket.getByLabel("Quantity").fill("2");
  await ticket.getByLabel("Order type").selectOption("LIMIT");
  await ticket.getByLabel("Price (₹)").fill("100.05");
  await ticket.getByRole("button", { name: "Preview Buy" }).click();
  await ticket.getByRole("button", { name: "Create TWF Order" }).click();
  await expect(
    ticket.getByRole("heading", { name: "TWF Order Created" }),
  ).toBeVisible();
  await ticket.getByRole("link", { name: "View Order Details" }).click();
  const orderDetail = page.locator("aside[aria-label='Order details']");
  const orderId = (await orderDetail
    .locator(".orders-detail-summary small")
    .textContent())!.trim();
  await expect(orderDetail.locator(".twf-order-state")).toHaveText("READY");
  await page.getByRole("button", { name: "Close order details" }).click();
  await page.getByRole("button", { name: "Add to Queue" }).click();
  const confirmation = page.getByRole("dialog", { name: "Add to TWF Queue" });
  await expect(confirmation).toBeVisible();
  await expect(confirmation.getByText(orderId)).toBeVisible();
  await expect(
    confirmation.getByText(/does not submit an order to the broker/),
  ).toBeVisible();
  await expect(
    confirmation.getByRole("button", { name: "Add to Queue" }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(confirmation).toBeHidden();
  await page.getByRole("button", { name: "Add to Queue" }).click();
  await confirmation.getByRole("button", { name: "Add to Queue" }).click();
  await expect(
    page.getByRole("heading", { name: "TWF Queue", exact: true }),
  ).toBeVisible();
  const queueDetail = page.locator("aside[aria-label='Queue details']");
  await expect(
    queueDetail.getByRole("heading", { name: "Queue Details" }),
  ).toBeVisible();
  await expect(queueDetail.locator(".twf-order-state")).toHaveText("READY");
  const queueId = (await queueDetail
    .locator(".orders-detail-summary small")
    .textContent())!.trim();
  const replay = await page.request.post("/api/v1/twf-queue/admit", {
    headers,
    data: { twf_order_id: orderId },
  });
  expect(replay.ok()).toBeTruthy();
  expect((await replay.json()).queue_entry_id).toBe(queueId);
  await expect(
    page.locator("section[aria-label='TWF Queue'] tbody tr"),
  ).toHaveCount(1);
  await queueDetail.getByRole("button", { name: "Queue History" }).click();
  await expect(queueDetail.getByText(/QUEUE_ADMITTED/)).toBeVisible();
  await queueDetail.getByRole("button", { name: "Hold" }).click();
  await expect(queueDetail.locator(".twf-order-state")).toHaveText("HELD");
  await expect(queueDetail.getByText(/QUEUE_HELD/)).toBeVisible();
  await queueDetail.getByRole("button", { name: "Release" }).click();
  await expect(queueDetail.locator(".twf-order-state")).toHaveText("READY");
  await expect(queueDetail.getByText(/QUEUE_RELEASED/)).toBeVisible();
  await page.reload();
  await page.getByRole("link", { name: "Execution Queue" }).click();
  await expect(
    page.locator("section[aria-label='TWF Queue'] tbody tr"),
  ).toHaveCount(1);
  await page
    .getByRole("button", { name: `View Queue entry ${queueId}` })
    .click();
  await page.getByRole("button", { name: "TWF Order", exact: true }).click();
  await page.getByRole("button", { name: "View exact TWF Order" }).click();
  await expect(
    page.locator("aside[aria-label='Order details'] .twf-order-state"),
  ).toHaveText("QUEUED");
  await page.getByRole("button", { name: "History" }).click();
  await expect(page.getByText(/STATE_TRANSITIONED/).last()).toBeVisible();
  await expect(page.getByText(/READY → QUEUED/)).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 2,
    ),
  ).toBe(false);
});

test("Queue operator can page older rows and return to newest", async ({
  page,
}, info) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill(`queue-${info.project.name}`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-only-browser-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
  const row = (id: string, state: "READY" | "HELD") => ({
    queue_entry_id: id,
    twf_order_id: `order-${id}`,
    queue_state: state,
    version: 1,
    admitted_at: "2026-10-15T10:00:00Z",
    order: {
      state: "QUEUED",
      instrument: { symbol: `SYM-${id}`, asset_class: "EQUITY" },
      terms: { side: "BUY", quantity: 1, order_type: "LIMIT" },
    },
  });
  let rejectNextCursor = false;
  await page.route("**/api/v1/twf-queue?*", async (route) => {
    const params = new URL(route.request().url()).searchParams;
    if (params.has("cursor") && rejectNextCursor) {
      rejectNextCursor = false;
      await route.fulfill({
        status: 400,
        json: {
          error: { code: "INVALID_CURSOR", message: "raw backend detail" },
        },
      });
      return;
    }
    const data = params.has("cursor")
      ? { items: [row("a", "READY")], next_cursor: null, has_more: false }
      : params.get("state") === "HELD"
        ? { items: [row("b", "HELD")], next_cursor: null, has_more: false }
        : {
            items: [row("c", "READY"), row("b", "HELD")],
            next_cursor: "opaque-cursor",
            has_more: true,
          };
    await route.fulfill({ json: data });
  });
  await page.goto("/trade/queue");
  const queue = page.locator("section[aria-label='TWF Queue']");
  await expect(queue.locator("tbody tr")).toHaveCount(2);
  await expect(queue.getByText("SYM-c")).toBeVisible();
  await queue.getByRole("button", { name: "Load older" }).click();
  await expect(queue.locator("tbody tr")).toHaveCount(3);
  await queue.getByRole("button", { name: "Back to newest" }).click();
  await expect(queue.locator("tbody tr")).toHaveCount(2);
  await queue.getByRole("button", { name: "Held" }).click();
  await expect(queue.locator("tbody tr")).toHaveCount(1);
  await expect(queue.getByText("SYM-b")).toBeVisible();
  await queue.getByRole("button", { name: "All" }).click();
  await expect(queue.locator("tbody tr")).toHaveCount(2);
  rejectNextCursor = true;
  await queue.getByRole("button", { name: "Load older" }).click();
  await expect(queue.locator("tbody tr")).toHaveCount(2);
  await expect(queue.getByText("SYM-c")).toBeVisible();
  await expect(page.locator(".broker-notice[role=alert]")).toContainText(
    "Queue page expired. Returned to newest entries.",
  );
  await expect(page.getByText("raw backend detail")).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 2,
    ),
  ).toBe(false);
});
