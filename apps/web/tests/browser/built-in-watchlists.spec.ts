import { expect, test } from "@playwright/test";

test("built-in watchlists are read-only, copyable and responsive", async ({
  page,
  baseURL,
}, info) => {
  test.setTimeout(90_000);
  const headers = { Origin: baseURL! };
  const login = await page.request.post("/api/v1/auth/login", {
    headers,
    data: {
      username: `builtin-${info.project.name}`,
      password: "test-only-browser-password",
    },
  });
  expect(login.ok()).toBe(true);
  const target = await page.request.post("/api/v1/watchlists", {
    headers,
    data: { name: "Built-in Target" },
  });
  expect(target.ok()).toBe(true);

  await page.goto("/watchlists");
  const systemNavigation = page.getByRole("navigation", {
    name: "Built-in watchlists",
  });
  await expect(systemNavigation).toBeVisible();
  await expect(systemNavigation.getByRole("button")).toHaveCount(10);
  await expect(
    systemNavigation.getByRole("button", { name: /F&O 50/ }),
  ).toBeDisabled();
  await expect(
    systemNavigation.getByRole("button", { name: /F&O 100/ }),
  ).toBeDisabled();
  await systemNavigation.getByRole("button", { name: /Nifty Energy/ }).click();
  await page.getByLabel("Group by", { exact: true }).selectOption("SECTOR");
  await expect(
    page.getByRole("button", { name: "Energy (1)", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Technology (1)", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("built-in-watchlists-grouped.png"),
    fullPage: true,
  });
  await systemNavigation.getByRole("button", { name: /Nifty Bank/ }).click();

  await expect(page.getByRole("heading", { name: /Nifty Bank/ })).toBeVisible();
  expect(
    await page.getByLabel("Read-only built-in Watchlist").count(),
  ).toBeGreaterThanOrEqual(2);
  await expect(page.getByText("EQ", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Import/ })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: /Move Nifty Bank to Trash/ }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /Remove .* from Nifty Bank/ }),
  ).toHaveCount(0);
  await expect(page.getByText(/Official constituent source/)).toBeVisible();
  await expect(page.getByText(/Constituents received/)).toBeVisible();

  await page.getByLabel("Select RELIANCE", { exact: true }).check();
  await page.getByRole("button", { name: "Add Selected to Watchlist" }).click();
  const selectedDialog = page.getByRole("dialog", {
    name: "Add selected to a custom watchlist",
  });
  await expect(selectedDialog).toContainText("Add 1 selected constituent");
  await selectedDialog.getByLabel("Copy destination").selectOption({
    label: "Built-in Target",
  });
  await selectedDialog.getByRole("button", { name: "Add selected" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Added 1 symbol to the custom watchlist.",
  );

  await page.getByRole("button", { name: "Add all to Watchlist" }).click();
  const allDialog = page.getByRole("dialog", {
    name: "Add all to a custom watchlist",
  });
  await expect(allDialog).toContainText("Add all 2 constituents");
  await allDialog.getByLabel("New watchlist name").fill("Nifty Bank Copy");
  await allDialog.getByRole("button", { name: "Add all" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Added 2 symbols to the custom watchlist.",
  );

  const personalNavigation = page.getByRole("navigation", {
    name: "My watchlists",
  });
  await personalNavigation
    .getByRole("button", { name: /Nifty Bank Copy/ })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove INFY from Nifty Bank Copy" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Move Nifty Bank Copy to Trash" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Trash", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Trash", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Select Nifty Bank")).toHaveCount(0);
  await page.getByRole("button", { name: /Active watchlists/ }).click();
  await systemNavigation.getByRole("button", { name: /Nifty Bank/ }).click();

  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  for (const selector of [".wl-navigator", ".wl-main"]) {
    const box = await page.locator(selector).boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: info.outputPath("built-in-watchlists.png"),
    fullPage: true,
  });
});
