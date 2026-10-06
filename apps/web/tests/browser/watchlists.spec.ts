import { expect, test } from "@playwright/test";

test("persistent Watchlists, instrument detail, CSV, notes, archive and responsive shell", async ({
  page,
  baseURL,
}, info) => {
  const login = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: baseURL! },
    data: {
      username: `watchlist-${info.project.name}`,
      password: "test-only-browser-password",
    },
  });
  expect(login.ok()).toBe(true);
  test.setTimeout(90000);
  const headers = { Origin: baseURL! };
  const configured = await page.request.post("/api/v1/brokers/accounts", {
    headers,
    data: {
      name: "Watchlist Broker",
      api_key: `watchkey${info.project.name.replaceAll("-", "")}`,
      api_secret: "testsecret123",
    },
  });
  expect(configured.ok()).toBe(true);
  const accountId = (await configured.json()).id;
  const connect = await page.request.post(
    `/api/v1/brokers/accounts/${accountId}/connect`,
    { headers, data: {} },
  );
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
  let submissions = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      /\/(confirm|submit|dispatch)$/.test(new URL(request.url()).pathname)
    )
      submissions++;
  });
  // Only market overlays are simulated; collection actions use the real API and database.
  await page.route("**/api/v1/watchlists/*/quotes", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(
      /\/quotes$/,
      "",
    );
    const detail = await (await page.request.get(path)).json();
    await route.fulfill({
      json: {
        provider: "dhan",
        error: null,
        quotes: detail.items.map(
          (item: { instrument: unknown }, i: number) => ({
            instrument: item.instrument,
            provider: "dhan",
            last_price: String(1500 + i * 100),
            previous_close: "1480",
            open: "1490",
            high: "1510",
            low: "1475",
            volume: "230000",
            received_at: new Date().toISOString(),
            provider_source_time: null,
          }),
        ),
      },
    });
  });
  let historicalCalls = 0;
  await page.route("**/api/v1/watchlists/*/items/*/chart?*", (route) => {
    historicalCalls += 1;
    return route.fulfill({
      json: {
        provider: "dhan",
        interval: "1d",
        metrics: {
          rsi14: 64.2,
          trend: "Up",
          average_volume20: 10100,
          as_of: "2026-09-22T00:00:00Z",
          basis: "Completed daily bars; Wilder RSI(14); close versus SMA(20)",
        },
        error: null,
        bars: Array.from({ length: 22 }, (_, i) => ({
          timestamp: new Date(Date.UTC(2026, 8, i + 1)).toISOString(),
          open: 1480 + i,
          high: 1486 + i,
          low: 1475 + i,
          close: 1483 + i + Math.sin(i) * 3,
          volume: 10000 + i * 10,
        })),
      },
    });
  });
  await page.goto("/watchlists");
  await page.getByRole("button", { name: "New Watchlist" }).click();
  const dialog = page.getByRole("dialog", { name: "New Watchlist" });
  await dialog.getByLabel("Name", { exact: true }).focus();
  await page.keyboard.press("Shift+Tab");
  await expect(
    dialog.getByRole("button", { name: "Close dialog" }),
  ).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  expect(
    await dialog.evaluate((element) =>
      element.contains(document.activeElement),
    ),
  ).toBe(true);
  await dialog.getByLabel("Name", { exact: true }).fill("My Core");
  await dialog
    .getByLabel("Description")
    .fill("Core watchlist for active trading opportunities.");
  await dialog.getByRole("button", { name: "Save watchlist" }).click();
  await expect(page.getByRole("heading", { name: "My Core" })).toBeVisible();
  await page.getByRole("button", { name: "Add Symbols" }).click();
  const add = page.getByRole("dialog", { name: "Add Symbols" });
  await add.getByLabel("Search instruments").fill("RELIANCE");
  await add.getByRole("button", { name: "Add RELIANCE", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "RELIANCE added" }),
  ).toBeVisible();
  await add.getByRole("button", { name: "Close dialog" }).click();
  await page
    .getByRole("button", { name: "Import", exact: false })
    .first()
    .click();
  const imp = page.getByRole("dialog", { name: "Import CSV" });
  await imp
    .getByLabel("CSV content")
    .fill(
      "canonical_symbol\nNSE:INFY\nNSE:NIFTY\nNSE:NIFTY99DECFUT\nNSE:NIFTY99DEC25000CE\nNSE:RELIANCE\nNSE:UNKNOWN\n",
    );
  await imp.getByRole("button", { name: "Import symbols" }).click();
  await expect(
    imp.getByText("Added 4 · Duplicates 1 · Unresolved 1"),
  ).toBeVisible();
  await imp.getByRole("button", { name: "Close dialog" }).click();
  await expect(
    page.getByRole("button", { name: "All 5", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Search symbols in this list").fill("INFY");
  await expect(page.locator(".wl-table tbody tr")).toHaveCount(1);
  await page.getByLabel("Search symbols in this list").fill("");
  await page.getByRole("button", { name: "Options 1", exact: true }).click();
  await expect(page.locator(".wl-table tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: "All 5", exact: true }).click();
  await page.getByRole("button", { name: "New Watchlist" }).click();
  await page
    .getByRole("dialog")
    .getByLabel("Name", { exact: true })
    .fill("Momentum");
  await page.getByRole("button", { name: "Save watchlist" }).click();
  await expect(page.getByRole("heading", { name: /^Momentum/ })).toBeVisible();
  const navigator = page.getByRole("navigation", { name: "My watchlists" });
  await navigator.getByRole("button", { name: /My Core/ }).click();
  await page.getByLabel("Select INFY", { exact: true }).check();
  await page.getByLabel("Target watchlist").selectOption({ label: "Momentum" });
  await page.getByRole("button", { name: "Copy", exact: true }).click();
  await expect(
    navigator.getByRole("button", { name: /Momentum/ }),
  ).toContainText("1 symbols");
  await navigator.getByRole("button", { name: /Momentum/ }).click();
  await expect(page.locator(".wl-table tbody tr")).toHaveCount(1);
  await navigator.getByRole("button", { name: /My Core/ }).click();
  await expect(page.locator(".wl-table tbody tr")).toHaveCount(5);
  await expect(page.locator('.wl-table tbody svg[role="img"]')).toHaveCount(5);
  await expect(page.locator(".wl-table tbody tr").first()).toContainText(
    "64.2",
  );
  await page.reload();
  await expect(page.locator('.wl-table tbody svg[role="img"]')).toHaveCount(5);
  await expect(page.locator(".wl-table tbody tr").first()).toContainText(
    "64.2",
  );
  await page.screenshot({
    path: info.outputPath("watchlists-hard-reload-unselected.png"),
    fullPage: true,
  });
  const callsBeforeSelection = historicalCalls;
  await page.getByRole("button", { name: "RELIANCE", exact: true }).click();
  const mobile = page.viewportSize()!.width < 1200;
  const panel = mobile
    ? page.getByRole("dialog", { name: "RELIANCE details" })
    : page.getByRole("complementary", { name: "Selected instrument" });
  await expect(panel.getByRole("img", { name: /Price chart/ })).toBeVisible();
  if (page.viewportSize()!.width > 390) {
    await expect(
      page
        .locator(".wl-table tbody tr")
        .filter({ hasText: "RELIANCE" })
        .getByRole("img", { name: /Quick chart, 22 completed bars/ }),
    ).toBeVisible();
  }
  expect(historicalCalls).toBe(callsBeforeSelection);
  await expect(
    page.getByText("Chart unavailable", { exact: true }),
  ).toHaveCount(0);
  await panel.getByRole("button", { name: "1M", exact: true }).click();
  await expect(panel.getByRole("img", { name: /Price chart/ })).toBeVisible();
  expect(historicalCalls).toBe(callsBeforeSelection);
  await expect(
    panel.getByRole("button", { name: "Buy", exact: true }),
  ).toBeEnabled();
  await panel.getByLabel("Quantity").fill("2");
  await panel.getByRole("button", { name: "Buy", exact: true }).click();
  const ticket = page.locator("dialog.order-dialog");
  await expect(ticket.getByLabel("Quantity", { exact: true })).toHaveValue("2");
  await ticket.getByLabel("Price (₹)", { exact: true }).fill("1500");
  await ticket
    .getByRole("button", { name: "Preview Buy", exact: true })
    .click();
  await expect(
    ticket.getByRole("button", { name: "Confirm Buy", exact: true }),
  ).toBeVisible();
  await ticket.getByRole("button", { name: "Close order ticket" }).click();
  expect(submissions).toBe(0);
  if (mobile) await panel.evaluate((element) => (element.scrollTop = 0));
  for (const theme of ["light", "dark"]) {
    await page.evaluate((theme) => {
      localStorage.setItem("twf-theme", theme);
      document.documentElement.dataset.theme = theme;
    }, theme);
    await page.waitForTimeout(250); // Allow the shell's theme transition to finish before visual capture.
    await page.screenshot({
      path: info.outputPath(`watchlists-${theme}-detail.png`),
      fullPage: !mobile,
    });
  }
  if (mobile) await panel.getByRole("button", { name: "Close dialog" }).click();
  await page.getByLabel("Watchlist note").fill("Review after earnings.");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(
    page.getByText("Review after earnings.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Edit watchlist" }).click();
  await page
    .getByRole("dialog")
    .getByLabel("Name", { exact: true })
    .fill("My Core Updated");
  await page.getByRole("button", { name: "Save watchlist" }).click();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "My Core Updated" }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export (CSV)", exact: false })
    .click();
  expect((await download).suggestedFilename()).toBe("watchlist.csv");
  await page.getByLabel("Select INFY", { exact: true }).check();
  await page.getByRole("button", { name: "Remove selected" }).click();
  await expect(
    page.getByRole("button", { name: "All 4", exact: true }),
  ).toBeVisible();
  await page.locator(".wl-detail-head summary").click();
  await page
    .getByRole("button", { name: "Move to Trash", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Move to Trash" })
    .click();
  await page
    .getByRole("button", { name: "Trash", exact: false })
    .last()
    .click();
  await page
    .getByRole("navigation", { name: "My watchlists" })
    .getByRole("button", { name: /My Core Updated/ })
    .click();
  await page.locator(".wl-detail-head summary").click();
  await page.getByRole("button", { name: "Restore watchlist" }).click();
  await page
    .getByRole("button", { name: "Active watchlists", exact: false })
    .click();
  await expect(
    page
      .getByRole("navigation", { name: "My watchlists" })
      .getByRole("button", { name: /My Core Updated/ }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  for (const theme of ["light", "dark"]) {
    await page.evaluate((theme) => {
      document.documentElement.dataset.theme = theme;
    }, theme);
    await page.waitForTimeout(250); // Allow the shell's theme transition to finish before visual capture.
    await page.screenshot({
      path: info.outputPath(`watchlists-${theme}-list.png`),
      fullPage: true,
    });
  }
});
