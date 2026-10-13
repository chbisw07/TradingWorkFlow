import { expect, test } from "@playwright/test";

test("O4 templates are visible, editable recipes and never auto-run", async ({
  page,
  baseURL,
}, info) => {
  test.setTimeout(90_000);
  const login = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: baseURL! },
    data: {
      username: `discovery-${info.project.name}`,
      password: "test-only-browser-password",
    },
  });
  expect(login.ok()).toBe(true);
  const templateResponse = await page.request.get(
    "/api/v1/scanner/derivatives/templates",
  );
  expect(templateResponse.ok(), await templateResponse.text()).toBe(true);
  let submitted: Record<string, unknown> | null = null;
  await page.route("**/api/v1/scanner/derivatives/runs", async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    return route.fulfill({
      json: {
        id: "22222222-2222-4222-8222-222222222222",
        created_at: "2026-10-12T10:00:00Z",
        config: submitted,
        counts: {
          requested: 1,
          resolved: 1,
          chains_evaluated: 1,
          contracts_evaluated: 0,
          not_evaluated: 0,
          matches: 0,
        },
        underlyings: [{ symbol: "NIFTY", outcome: "EVALUATED", failure: null }],
        rows: [],
      },
    });
  });
  await page.addInitScript(() => localStorage.setItem("twf-theme", "light"));
  await page.goto("/scanners");
  await page.getByRole("tab", { name: /Derivatives Scanner/ }).click();
  await expect(page.locator(".derivative-predicate-chip")).toHaveCount(0);
  await page.getByRole("button", { name: /Scan Templates/ }).click();
  for (const group of ["Intraday", "Positional", "My Templates"])
    await expect(page.getByRole("region", { name: group })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("template-menu.png"),
    fullPage: true,
  });
  await page
    .getByRole("menuitem", { name: /Intraday — Liquid ATM Options/ })
    .click();
  for (const part of [
    "Volume Percentile >= 70%",
    "OI Percentile >= 70%",
    "Spread % <= 2%",
    "Moneyness equals ATM",
  ])
    await expect(page.locator(".derivative-active-bar")).toContainText(part);
  expect(submitted).toBeNull();
  await page.screenshot({
    path: info.outputPath("template-loaded.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: /Scan Templates/ }).click();
  await page
    .getByRole("menuitem", { name: /Positional — Bullish Call Setup/ })
    .click();
  for (const part of [
    "DTE >= 7",
    "Underlying Trend vs SMA20 equals Up",
    "Option Type: CE",
  ])
    await expect(page.locator(".derivative-active-bar")).toContainText(part);
  await page.locator(".derivative-filter-editor > summary").click();
  await page
    .getByRole("combobox", { name: "Field" })
    .selectOption("volume_percentile");
  await page.getByRole("combobox", { name: "Comparison" }).selectOption(">=");
  await page.getByRole("spinbutton", { name: "Value" }).fill("77");
  await page.getByRole("button", { name: "Add / update filter" }).click();
  await expect(page.locator(".derivative-active-bar")).toContainText(
    "Volume Percentile >= 77%",
  );
  await page.screenshot({
    path: info.outputPath("template-edited.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: /Save Scan ▾/ }).click();
  await expect(page.getByRole("menuitem", { name: /Save Scan/ })).toBeVisible();
  await page.screenshot({
    path: info.outputPath("save-chooser.png"),
    fullPage: true,
  });
  await page.getByRole("menuitem", { name: "Save as Template" }).click();
  const dialog = page.getByRole("dialog", { name: "Save as Template" });
  await expect(dialog).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("save-dialog.png"),
    fullPage: true,
  });
  const name = `Test positional ${info.project.name}`;
  await dialog.getByRole("textbox", { name: "Name" }).fill(name);
  await dialog.getByRole("button", { name: "Save Template" }).click();
  await expect(dialog).toBeHidden();
  expect(submitted).toBeNull();
  await page.reload();
  await page.getByRole("tab", { name: /Derivatives Scanner/ }).click();
  await page.getByRole("button", { name: /Scan Templates/ }).click();
  await expect(
    page.getByRole("menuitem", { name: new RegExp(name) }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("my-templates.png"),
    fullPage: true,
  });
  await page.getByRole("menuitem", { name: new RegExp(name) }).click();
  await expect(page.locator(".derivative-active-bar")).toContainText(
    "Volume Percentile >= 77%",
  );
  expect(submitted).toBeNull();
  await page.locator(".derivative-filter-editor > summary").click();
  await page
    .getByRole("combobox", { name: "Field" })
    .selectOption("volume_percentile");
  await page.getByRole("combobox", { name: "Comparison" }).selectOption(">=");
  await page.getByRole("spinbutton", { name: "Value" }).fill("79");
  await page.getByRole("button", { name: "Add / update filter" }).click();
  await page.getByRole("button", { name: /Save Scan ▾/ }).click();
  await page.getByRole("menuitem", { name: "Save as Template" }).click();
  const updateDialog = page.getByRole("dialog", { name: "Save as Template" });
  await updateDialog
    .getByRole("checkbox", { name: /Update loaded My Template/ })
    .check();
  await updateDialog.getByRole("button", { name: "Save Template" }).click();
  await expect(updateDialog).toBeHidden();
  await page.getByRole("button", { name: "Custom underlyings" }).click();
  await page.getByLabel("NSE underlyings").fill("NIFTY");
  await page.getByRole("button", { name: "Run Scan" }).click();
  await expect.poll(() => submitted).not.toBeNull();
  expect(submitted).toMatchObject({
    origin_template_name: name,
    filters: expect.arrayContaining([
      { field: "volume_percentile", operator: ">=", value: 79 },
    ]),
  });
  await page.getByRole("button", { name: /Scan Templates/ }).click();
  const renamed = `${name} renamed`;
  page.once("dialog", (prompt) => void prompt.accept(renamed));
  await page.getByRole("button", { name: `Rename ${name}` }).click();
  await page.getByRole("button", { name: /Scan Templates/ }).click();
  await expect(
    page.getByRole("menuitem", { name: new RegExp(renamed) }),
  ).toBeVisible();
  page.once("dialog", (confirmation) => void confirmation.accept());
  await page.getByRole("button", { name: `Delete ${renamed}` }).click();
  await page.getByRole("button", { name: /Scan Templates/ }).click();
  await expect(
    page.getByRole("menuitem", { name: new RegExp(name) }),
  ).toHaveCount(0);
});

test("an obsolete template is rejected without dropping rules or running", async ({
  page,
  baseURL,
}, info) => {
  const login = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: baseURL! },
    data: {
      username: `discovery-${info.project.name}`,
      password: "test-only-browser-password",
    },
  });
  expect(login.ok()).toBe(true);
  let posts = 0;
  await page.route("**/api/v1/scanner/derivatives/runs", async (route) => {
    if (route.request().method() === "POST") posts++;
    return route.fulfill({ json: [] });
  });
  await page.route("**/api/v1/scanner/derivatives/templates", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    const payload = await response.json();
    payload.user.push({
      template_id: "11111111-1111-4111-8111-111111111111",
      name: "Old incompatible template",
      scanner_type: "DERIVATIVES",
      instrument_scope: "OPTIONS",
      horizon: "GENERAL",
      source: "USER",
      description: "Old rule no longer in catalog",
      template_schema_version: 0,
      recipe: {
        scanner_type: "DERIVATIVES",
        instrument_scope: "OPTIONS",
        expiry_mode: "NEAREST",
        exact_expiry: null,
        strike_window: 10,
        watchlist_id: null,
        predicates: [{ field: "removed_field", operator: ">=", value: 1 }],
      },
    });
    await route.fulfill({ json: payload });
  });
  await page.addInitScript(() => localStorage.setItem("twf-theme", "light"));
  await page.goto("/scanners");
  await page.getByRole("tab", { name: /Derivatives Scanner/ }).click();
  await page.getByRole("button", { name: /Scan Templates/ }).click();
  await page
    .getByRole("menuitem", { name: /Old incompatible template/ })
    .click();
  await expect(page.locator(".wl-error[role=alert]")).toContainText(
    "Template incompatible",
  );
  await expect(page.locator(".derivative-predicate-chip")).toHaveCount(0);
  expect(posts).toBe(0);
});
