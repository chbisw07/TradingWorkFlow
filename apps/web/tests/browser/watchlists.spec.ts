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
    const period =
      new URL(route.request().url()).searchParams.get("period") || "1M";
    const count = (
      { "1D": 75, "1W": 5, "1M": 22, "3M": 66, "1Y": 252 } as Record<
        string,
        number
      >
    )[period];
    return route.fulfill({
      json: {
        provider: "dhan",
        interval: period === "1D" ? "5m" : "1d",
        metrics: {
          rsi14: 64.2,
          trend: "Up",
          average_volume20: 10100,
          atr14: 24.5,
          atr_percent: 1.64,
          high_52w: 1700,
          low_52w: 1200,
          high_52w_distance_percent: 11.76,
          low_52w_distance_percent: 25,
          history_coverage_sessions: 252,
          as_of: "2026-09-22T00:00:00Z",
          basis: "Completed daily bars; Wilder RSI(14); close versus SMA(20)",
        },
        error: null,
        bars: Array.from({ length: count }, (_, i) => ({
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
  let referenceCalls = 0;
  await page.route("**/api/v1/watchlists/*/items/*/reference", (route) => {
    referenceCalls++;
    return route.fulfill({
      json: {
        provider: "tapetide",
        tool: "get_stock_quote",
        state: "AVAILABLE",
        market_cap_inr: "16482632200000",
        pe_ratio: "22.06",
        high_52_week: "1611.8",
        low_52_week: "1160.8",
        received_at: new Date().toISOString(),
        source_time: new Date().toISOString(),
        freshness: "CURRENT",
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
  const instrumentSearch = add.getByLabel("Search instruments");
  const instrumentType = add.getByLabel("Instrument type");
  for (const [symbol, kind] of [
    ["RELIANCE", "EQUITY"],
    ["INFY", "EQUITY"],
    ["NIFTY", "INDEX"],
  ] as const) {
    await instrumentType.selectOption(kind);
    await instrumentSearch.fill(symbol);
    const addButton = add.getByRole("button", {
      name: `Add ${symbol}`,
      exact: true,
    });
    await expect(addButton).toBeVisible();
    if (symbol === "NIFTY") await instrumentSearch.press("Enter");
    else await addButton.click();
    await expect(add).toBeVisible();
    await expect(add.getByRole("status")).toContainText(`Added ${symbol}`);
    await expect(instrumentSearch).toHaveValue("");
    await expect(instrumentSearch).toBeFocused();
    await expect(instrumentType).toHaveValue(kind);
  }
  await instrumentType.selectOption("EQUITY");
  await instrumentSearch.fill("RELIANCE");
  await expect(
    add.getByRole("button", { name: "RELIANCE already added" }),
  ).toBeDisabled();
  if (info.project.name.match(/390|1440|2560/)) {
    await page.screenshot({
      path: info.outputPath("watchlists-rapid-entry.png"),
      fullPage: true,
    });
  }
  await instrumentType.selectOption("FUTURE");
  await instrumentSearch.fill("NIFTY99DECFUT");
  await page.route("**/api/v1/watchlists/*/items", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 503,
        json: {
          error: { message: "Instrument service temporarily unavailable." },
        },
      });
    } else {
      await route.continue();
    }
  });
  await add
    .getByRole("button", { name: "Add NIFTY99DECFUT", exact: true })
    .click();
  await expect(add).toBeVisible();
  await expect(add.getByRole("alert")).toContainText(
    "Instrument service temporarily unavailable.",
  );
  await expect(instrumentSearch).toHaveValue("NIFTY99DECFUT");
  await page.unroute("**/api/v1/watchlists/*/items");
  await page.keyboard.press("Escape");
  await expect(add).not.toBeVisible();
  await page.getByRole("button", { name: "Add Symbols" }).click();
  await expect(add).toBeVisible();
  await add.getByRole("button", { name: "Done" }).click();
  await expect(add).not.toBeVisible();
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
    imp.getByText("Added 2 · Duplicates 3 · Unresolved 1"),
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
  for (const header of [
    "Market Cap Category",
    "Market Cap",
    "ATR %",
    "52W High Distance",
    "52W Low Distance",
  ])
    await expect(
      page.getByRole("columnheader", {
        name: header,
        exact: true,
        includeHidden: true,
      }),
    ).toHaveCount(1);
  await expect(page.locator(".wl-table tbody")).toContainText("1.64%");
  await expect(page.locator(".wl-table tbody")).toContainText("11.76%");
  await expect(page.locator(".wl-table tbody")).toContainText("25.00%");
  await page.screenshot({
    path: info.outputPath("watchlists-market-metrics.png"),
    fullPage: true,
  });
  await page.reload();
  await expect(page.locator('.wl-table tbody svg[role="img"]')).toHaveCount(5);
  await expect(page.locator(".wl-table tbody tr").first()).toContainText(
    "64.2",
  );
  await page.screenshot({
    path: info.outputPath("watchlists-hard-reload-unselected.png"),
    fullPage: true,
  });
  await expect(
    page.getByRole("columnheader", {
      name: "1D %",
      exact: true,
      includeHidden: true,
    }),
  ).toHaveCount(1);
  // Narrow layouts intentionally hide optional sparkline columns, not their semantics.
  await expect(
    page.getByRole("columnheader", {
      name: "Quick Chart (1M)",
      includeHidden: true,
      exact: true,
    }),
  ).toHaveCount(1);
  const rowBefore = await page
    .locator(".wl-table tbody tr")
    .first()
    .textContent();
  const callsBeforeSelection = historicalCalls;
  await page.getByRole("button", { name: "RELIANCE", exact: true }).click();
  const mobile = page.viewportSize()!.width < 1200;
  const panel = mobile
    ? page.getByRole("dialog", { name: "RELIANCE details" })
    : page.getByRole("complementary", { name: "Selected instrument" });
  await expect(page.locator(".wl-table thead")).toContainText("Sector");
  await expect(page.locator(".wl-table tbody")).toContainText("Energy");
  const metadata = panel.getByRole("region", { name: "Instrument metadata" });
  await expect(metadata).toContainText("Energy");
  await expect(metadata).toContainText("Oil & Gas Exploration");
  await expect(metadata).toContainText("₹20 L Cr");
  await expect(metadata).toContainText("NIFTY OIL & GAS");
  await page.screenshot({
    path: info.outputPath("watchlists-metadata-detail.png"),
    fullPage: !mobile,
  });
  await expect(panel.getByRole("img", { name: /Price chart/ })).toBeVisible();
  if (page.viewportSize()!.width > 900) {
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
    panel.getByRole("region", { name: "Reference / fundamentals" }),
  ).toContainText("22.06");
  await expect(
    panel.getByRole("tab", { name: "Chart", exact: true }),
  ).toHaveCount(0);
  await expect(panel.getByRole("tab")).toHaveText([
    "Overview",
    "Option Chain",
    "News",
  ]);
  await expect(
    panel.getByRole("region", { name: "Price / market data" }),
  ).toContainText("2.30 L");
  await expect(
    panel.getByRole("region", { name: "Price / market data" }),
  ).toContainText("10.10 K");
  await expect(
    panel.getByRole("region", { name: "Reference / fundamentals" }),
  ).toContainText("₹16.48 L Cr");
  const disclosure = panel.locator(".wl-data-details summary");
  await expect(disclosure).toHaveAttribute("aria-expanded", "false");
  await expect(panel.getByText(/Reference data · TapTide/)).not.toBeVisible();
  await disclosure.focus();
  await page.keyboard.press("Enter");
  await expect(disclosure).toHaveAttribute("aria-expanded", "true");
  await expect(panel.getByText(/Reference data · TapTide/)).toBeVisible();
  await expect(
    panel.getByText("Market data · Dhan · quote / OHLCV snapshot"),
  ).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(disclosure).toHaveAttribute("aria-expanded", "false");
  const returns = new Set<string>();
  for (const period of ["1D", "1W", "1M", "3M", "1Y"]) {
    await panel.getByRole("button", { name: period, exact: true }).click();
    await expect(panel.getByRole("img", { name: /Price chart/ })).toBeVisible();
    await expect(panel.locator(".wl-price small")).toContainText(period + " ");
    const value = await panel.locator(".wl-price small").innerText();
    expect(value).not.toContain("—");
    returns.add(value);
    await expect(panel.getByLabel("Period change basis")).toContainText(
      period === "1D" ? "Previous trading session close" : "close to close",
    );
    expect(await page.locator(".wl-table tbody tr").first().textContent()).toBe(
      rowBefore,
    );
  }
  expect(returns.size).toBe(5);
  expect(historicalCalls).toBe(callsBeforeSelection + 4);
  await panel.getByRole("button", { name: "1M", exact: true }).click();
  await expect(panel.getByRole("img", { name: /Price chart/ })).toBeVisible();
  expect(historicalCalls).toBe(callsBeforeSelection + 4);
  expect(referenceCalls).toBe(1);
  await panel
    .getByRole("region", { name: "Reference / fundamentals" })
    .screenshot({
      path: info.outputPath("tapetide-reference-available-detail.png"),
    });
  await page.screenshot({
    path: info.outputPath("tapetide-reference-available.png"),
    fullPage: true,
  });
  await page.route("**/api/v1/watchlists/*/items/*/reference", (route) =>
    route.fulfill({
      json: {
        provider: "tapetide",
        tool: "get_stock_quote",
        state: "UNAVAILABLE",
        market_cap_inr: null,
        pe_ratio: null,
        high_52_week: null,
        low_52_week: null,
        received_at: new Date().toISOString(),
        source_time: null,
        freshness: "UNAVAILABLE",
      },
    }),
  );
  // A full reload clears the component cache; the selected instrument is reopened.
  await page.reload();
  await page
    .locator(".wl-table tbody tr")
    .first()
    .getByRole("button", { name: "RELIANCE", exact: true })
    .click();
  await expect(
    panel.getByText(/TapTide reference data is temporarily unavailable/),
  ).toBeVisible();
  await expect(panel.getByRole("img", { name: /Price chart/ })).toBeVisible();
  await panel
    .getByRole("region", { name: "Reference / fundamentals" })
    .screenshot({
      path: info.outputPath("tapetide-reference-unavailable-detail.png"),
    });
  await page.screenshot({
    path: info.outputPath("tapetide-reference-unavailable.png"),
    fullPage: true,
  });
  await expect(
    panel.getByRole("region", { name: "Instrument metadata" }),
  ).toContainText("Energy");
  await panel.getByRole("tab", { name: "Overview" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(panel.getByRole("tab", { name: "Option Chain" })).toBeFocused();
  await expect(panel.getByText("Option chain coming later")).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await expect(panel.getByRole("tab", { name: "News" })).toBeFocused();
  await expect(
    panel.getByRole("heading", { name: "Company news" }),
  ).toBeVisible();
  await page.keyboard.press("Home");
  await expect(panel.getByRole("tab", { name: "Overview" })).toBeFocused();
  await expect(panel.getByRole("img", { name: /Price chart/ })).toBeVisible();
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
  const remove = page.getByRole("button", {
    name: "Remove INFY from My Core Updated",
    exact: true,
  });
  await expect(remove).toBeVisible();
  const removeBox = await remove.boundingBox();
  expect(removeBox!.x).toBeGreaterThanOrEqual(0);
  expect(removeBox!.x + removeBox!.width).toBeLessThanOrEqual(
    page.viewportSize()!.width,
  );
  await expect(remove).toHaveAttribute(
    "title",
    "Remove INFY from My Core Updated",
  );
  page.once("dialog", (dialog) => dialog.dismiss());
  await remove.focus();
  await page.keyboard.press("Enter");
  await expect(remove).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await remove.focus();
  await page.keyboard.press("Space");
  await expect(
    page.getByRole("button", { name: "All 4", exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator(".wl-activity")
      .filter({ hasText: "REMOVED" })
      .filter({ hasText: "INFY" }),
  ).toBeVisible();
  await navigator.getByRole("button", { name: /Momentum/ }).click();
  await expect(page.getByLabel("Select INFY", { exact: true })).toBeVisible();
  await navigator.getByRole("button", { name: /My Core Updated/ }).click();
  await expect(
    page.getByRole("button", { name: "Trash", exact: true }),
  ).toBeVisible();
  if (info.project.name.match(/1440|1920|2560/)) {
    const navBox = await page.locator(".wl-navigator").boundingBox();
    const mainBox = await page.locator(".wl-main").boundingBox();
    expect(
      Math.abs(navBox!.y + navBox!.height - mainBox!.y - mainBox!.height),
    ).toBeLessThan(2);
  }
  await page
    .getByRole("button", {
      name: "Move My Core Updated to Trash",
      exact: true,
    })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Move to Trash" })
    .click();
  await expect(
    navigator.getByRole("button", { name: /My Core Updated/ }),
  ).not.toBeVisible();
  await expect(page.getByRole("status")).toContainText(
    "My Core Updated moved to Trash.",
  );
  await expect(
    page.getByRole("heading", { name: "Trash", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Select My Core Updated")).toBeVisible();
  const restoreMe = await (
    await page.request.post("/api/v1/watchlists", {
      headers,
      data: { name: "Restore Me" },
    })
  ).json();
  const deleteMe = await (
    await page.request.post("/api/v1/watchlists", {
      headers,
      data: { name: "Delete Me" },
    })
  ).json();
  for (const id of [restoreMe.id, deleteMe.id]) {
    expect(
      (
        await page.request.patch(`/api/v1/watchlists/${id}`, {
          headers,
          data: { archived: true },
        })
      ).ok(),
    ).toBe(true);
  }
  await page
    .getByRole("button", { name: "Active watchlists", exact: false })
    .click();
  await page.getByRole("button", { name: "Trash", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Trash", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Select My Core Updated").check();
  await page.getByLabel("Select Restore Me").check();
  await expect(page.getByText("2 selected", { exact: true })).toBeVisible();
  if (info.project.name.match(/390|1440|2560/)) {
    await page.screenshot({
      path: info.outputPath("watchlists-trash-selection.png"),
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "Restore selected" }).click();
  await expect(page.getByLabel("Select My Core Updated")).not.toBeVisible();
  await expect(page.getByLabel("Select Restore Me")).not.toBeVisible();

  await page.getByLabel("Select Delete Me").check();
  await page
    .getByRole("button", { name: "Delete selected permanently" })
    .click();
  const permanent = page.getByRole("dialog", {
    name: "Permanently delete 1 watchlist?",
  });
  await expect(permanent.getByText("This cannot be undone.")).toBeVisible();
  await permanent.getByRole("button", { name: "Close dialog" }).click();
  await expect(page.getByLabel("Select Delete Me")).toBeVisible();
  await page
    .getByRole("button", { name: "Delete selected permanently" })
    .click();
  await permanent.getByRole("button", { name: "Delete permanently" }).click();
  await expect(page.getByLabel("Select Delete Me")).not.toBeVisible();
  await page
    .getByRole("button", { name: "Active watchlists", exact: false })
    .click();
  const activeNavigator = page.getByRole("navigation", {
    name: "My watchlists",
  });
  await expect(
    activeNavigator.getByRole("button", { name: /My Core Updated/ }),
  ).toBeVisible();
  await expect(
    activeNavigator.getByRole("button", { name: /Restore Me/ }),
  ).toBeVisible();
  await expect(
    activeNavigator.getByRole("button", { name: /Momentum/ }),
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
