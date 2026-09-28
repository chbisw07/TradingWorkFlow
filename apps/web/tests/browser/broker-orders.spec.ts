import { expect, test } from "@playwright/test";
test("manual equity, futures and options with exact contracts, preview and broker truth", async ({
  page,
}, info) => {
  test.setTimeout(120000);
  await page.goto("/login");
  await page.getByLabel("Username").fill(`order-${info.project.name}`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-only-browser-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
  // Setup uses same-origin API and the synthetic provider transport only.
  const headers = { Origin: "http://127.0.0.1:3100" };
  const configured = await page.request.post("/api/v1/brokers/accounts", {
    headers,
    data: {
      name: "Manual Trading",
      api_key: `testkey${info.project.name.replaceAll("-", "")}`,
      api_secret: "testsecret123",
    },
  });
  expect(configured.ok()).toBeTruthy();
  const account = (await configured.json()).id;
  const connect = await page.request.post(
    `/api/v1/brokers/accounts/${account}/connect`,
    { headers, data: {} },
  );
  const url = new URL((await connect.json()).login_url);
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
  await page.goto(`/brokers/accounts/${account}/orders`);
  for (const theme of ["dark", "light"]) {
    await page.evaluate((t) => {
      document.documentElement.dataset.theme = t;
      localStorage.setItem("twf-theme", t);
    }, theme);
    for (const asset of ["equity", "futures", "options"]) {
      await page
        .getByRole("button", { name: "+ New Order", exact: true })
        .click();
      const dialog = page.getByRole("dialog");
      await dialog
        .getByRole("radio", {
          name:
            asset === "equity"
              ? "Equity"
              : asset === "futures"
                ? "Futures"
                : "Options",
          exact: true,
        })
        .check();
      if (asset === "equity") {
        const nse = dialog.getByRole("radio", { name: "NSE", exact: true });
        await expect(nse).toBeChecked();
        await expect(
          dialog.getByText("Search for a stock to continue."),
        ).toBeVisible();
        await dialog.getByLabel("Search stock").fill("reliance");
        const cards = dialog.locator(".order-choice");
        await expect(cards).toHaveCount(4);
        await expect(cards.first().locator("strong")).toHaveText("RELIANCE");
        for (const card of await cards.all())
          await expect(card).toContainText("NSE · Equity");
        for (const query of [
          "REL",
          "RELI",
          "Reliance Industries",
          "Reliance Industries Ltd",
          "  Reliance---  Industries  ",
          "ind rel",
        ]) {
          const result = page.waitForResponse((r) => {
            const url = new URL(r.url());
            return (
              url.pathname.endsWith("/order-entry/choices") &&
              url.searchParams.get("q") === query
            );
          });
          await dialog.getByLabel("Search stock").fill(query);
          expect((await (await result).json()).instruments[0].reference).toBe(
            "ZERODHA:NSE:RELIANCE",
          );
          await expect(cards.first().locator("strong")).toHaveText("RELIANCE");
        }
        await dialog.getByLabel("Search stock").fill("reliance");
        await expect(cards).toHaveCount(4);
        // Native radio keyboard navigation must work as well as pointer input.
        await nse.focus();
        await page.keyboard.press("ArrowRight");
        await expect(
          dialog.getByRole("radio", { name: "BSE", exact: true }),
        ).toBeChecked();
        await expect(cards).toHaveCount(1);
        await expect(cards.first()).toContainText("BSE · Equity");
        await dialog.getByRole("radio", { name: "Both", exact: true }).check();
        await expect(cards).toHaveCount(5);
        await expect(cards.nth(0).locator("strong")).toHaveText("RELIANCE");
        await expect(cards.nth(1).locator("strong")).toHaveText("RELIANCE");
        await expect(cards.nth(0)).toContainText("BSE · Equity");
        await expect(cards.nth(1)).toContainText("NSE · Equity");
        await expect(cards.nth(0)).toContainText("RELIANCE INDUSTRIES");
        await expect(dialog.getByText(/^Token /)).toHaveCount(0);
        await page.screenshot({
          path: info.outputPath(`${theme}-equity-selection.png`),
        });
        await expect(cards.first().getByTestId("reference-ltp")).toContainText(
          "₹",
        );
        // Pick the BSE row: exact identity must survive the shared web proxy.
        const capResponse = page.waitForResponse(
          (r) =>
            r.url().includes("/order-entry/capabilities?") &&
            r.url().includes("native_token=12"),
        );
        await cards
          .first()
          .getByRole("button", { name: "Buy RELIANCE", exact: true })
          .click();
        expect((await (await capResponse).json()).instrument.reference).toBe(
          "ZERODHA:BSE:RELIANCE",
        );
      } else {
        await expect(
          dialog
            .getByLabel("Underlying")
            .getByRole("option", { name: "RELIANCE", exact: true }),
        ).toBeAttached();
        await dialog
          .getByRole("combobox", { name: "Underlying", exact: true })
          .selectOption("RELIANCE");
        await expect(dialog.getByLabel("Expiry").locator("option")).toHaveCount(
          3,
        );
        const expiries = await dialog
          .getByLabel("Expiry")
          .locator("option")
          .allTextContents();
        expect(expiries.slice(1)).toEqual([...expiries.slice(1)].sort());
        await expect(dialog.locator(".order-choice")).toHaveCount(0);
        await dialog.getByLabel("Expiry").selectOption({ index: 1 });
        if (asset === "options") {
          await expect(
            dialog.getByLabel("Option type").locator("option"),
          ).toHaveCount(3);
          await dialog.getByLabel("Option type").selectOption("CE");
          await expect(
            dialog.getByLabel("Strike").locator("option"),
          ).toHaveCount(3);
          await expect(
            dialog.getByLabel("Strike").locator("option"),
          ).toHaveText(["Select strike", "1400", "1500"]);
          await expect(dialog.locator(".order-choice")).toHaveCount(0);
          await dialog.getByLabel("Option type").selectOption("PE");
          await expect(
            dialog.getByLabel("Strike").locator("option"),
          ).toHaveText(["Select strike", "1300"]);
          await dialog.getByLabel("Option type").selectOption("CE");
          await expect(
            dialog.getByLabel("Strike").locator("option"),
          ).toHaveCount(3);
          await dialog.getByLabel("Strike").selectOption("1400");
        }
        await expect(
          dialog.getByRole("group", { name: "Exchange" }),
        ).toHaveCount(0);
        await expect(dialog.locator(".order-choice")).toHaveCount(1);
        await page.screenshot({
          path: info.outputPath(`${theme}-${asset}-selection.png`),
        });
        await dialog
          .getByRole("button", {
            name: asset === "futures" ? "Buy RELIANCEFUT1" : "Buy RELIANCECE1",
            exact: true,
          })
          .click();
        await dialog.getByLabel("Lots", { exact: true }).fill("2");
        await expect(dialog.getByText("500", { exact: true })).toBeVisible();
      }
      const bounds = await dialog.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.width).toBeLessThanOrEqual(480);
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(
        page.viewportSize()!.width,
      );
      const price = dialog.getByLabel("Price (₹)", { exact: true });
      const ltp = dialog.getByTestId("reference-ltp");
      await expect(ltp).toContainText("₹");
      await expect(price).not.toHaveValue("");
      const launchPrice = await price.inputValue();
      const firstLtp = await ltp.textContent();
      await expect(ltp).not.toHaveText(firstLtp!);
      await expect(ltp).toContainText("₹");
      await expect(price).toHaveValue(launchPrice);
      await dialog
        .getByRole("button", { name: "Set Price", exact: true })
        .click();
      await expect(price).not.toHaveValue(launchPrice);
      await price.fill("100.05");
      const editedAt = await ltp.textContent();
      await expect(ltp).not.toHaveText(editedAt!);
      await expect(price).toHaveValue("100.05");
      await expect(dialog.getByLabel("Stop Loss Price")).toBeDisabled();
      await expect(dialog.getByLabel("Take Profit Percent")).toBeDisabled();
      await expect(
        dialog.getByRole("button", { name: "Buy", exact: true }),
      ).toHaveAttribute("aria-pressed", "true");
      await page.screenshot({
        path: info.outputPath(`${theme}-${asset}-ticket.png`),
        fullPage: false,
      });
      await dialog.getByRole("button", { name: "Preview Buy" }).click();
      await expect(
        dialog.getByRole("button", { name: "Confirm Buy" }),
      ).toBeVisible();
      await page.screenshot({
        path: info.outputPath(`${theme}-${asset}-preview.png`),
        fullPage: false,
      });
      await dialog.getByRole("button", { name: "Confirm Buy" }).click();
      await expect(
        dialog.getByRole("heading", { name: "Order Submitted", exact: true }),
      ).toBeVisible();
      await dialog
        .getByRole("button", { name: "Refresh broker status" })
        .click();
      await expect(dialog.getByText("OPEN", { exact: true })).toBeVisible();
      await page.screenshot({
        path: info.outputPath(`${theme}-${asset}-result.png`),
        fullPage: false,
      });
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        )
        .toBeTruthy();
      await dialog.getByRole("link", { name: "View in Orders" }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
    }
  }
  await page.reload();
  await page.getByText(/Recent manual submissions/).click();
  await page.getByRole("button", { name: "Check submission" }).first().click();
  await expect(
    page.getByRole("heading", { name: "Order Submitted" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close order ticket" }).click();
  // A broker-pending modification belongs in Open without rewriting its status.
  await page.route(
    (url) => url.pathname === `/api/v1/brokers/accounts/${account}/orders`,
    async (route) => {
      const response = await route.fetch();
      const snapshot = await response.json();
      expect(snapshot.data.length).toBeGreaterThan(0);
      await route.fulfill({
        response,
        json: {
          ...snapshot,
          data: [
            ...snapshot.data,
            {
              ...snapshot.data[0],
              id: "filter-pending-order",
              instrument: {
                ...snapshot.data[0].instrument,
                symbol: "FILTER-PENDING",
                reference: "ZERODHA:NSE:FILTER-PENDING",
              },
              status: "MODIFY VALIDATION PENDING",
            },
          ],
        },
      });
    },
  );
  await page.reload();
  const pending = page.getByRole("row").filter({
    has: page.getByRole("rowheader", { name: /FILTER-PENDING/ }),
  });
  const filters = page.getByRole("group", { name: "Order filter" });
  for (const filter of [
    "All",
    "Open",
    "Completed",
    "Cancelled",
    "Rejected",
    "All",
  ]) {
    await filters.getByRole("button", { name: filter, exact: true }).click();
    if (filter === "All" || filter === "Open") {
      await expect(pending).toBeVisible();
      await expect(
        pending.getByRole("cell", {
          name: "MODIFY VALIDATION PENDING",
          exact: true,
        }),
      ).toBeVisible();
    } else {
      await expect(pending).toHaveCount(0);
    }
  }
  await page
    .getByRole("navigation", { name: "Broker functions" })
    .getByRole("link", { name: "Instruments", exact: true })
    .click();
  await expect(
    page
      .getByRole("row")
      .filter({
        has: page.getByRole("rowheader", { name: /ZERODHA:NFO:EXPIRED/ }),
      })
      .getByRole("button"),
  ).toHaveCount(0);
  const hal = page
    .getByRole("row")
    .filter({ has: page.getByRole("rowheader", { name: /ZERODHA:NSE:HAL/ }) });
  await hal.getByRole("button", { name: "Sell", exact: true }).click();
  await expect(
    page.getByRole("dialog").getByRole("button", { name: "Sell", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page
    .getByRole("dialog")
    .getByLabel("Price (₹)", { exact: true })
    .fill("100.05");
  await page.getByRole("button", { name: "Preview Sell" }).click();
  await expect(
    page.getByRole("button", { name: "Confirm Sell" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    hal.getByRole("button", { name: "Sell", exact: true }),
  ).toBeFocused();
});
