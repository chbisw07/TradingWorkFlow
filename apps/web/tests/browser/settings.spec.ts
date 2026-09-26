import { expect, test } from "@playwright/test";
test("personal settings persist, profiles apply, stale edits conflict and both themes recompose", async ({
  page,
  baseURL,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const login = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: baseURL! },
    data: {
      username: "settings-" + info.project.name,
      password: "test-only-browser-password",
    },
  });
  expect(login.ok()).toBe(true);
  await page.goto("/settings");
  await expect(
    page.getByRole("heading", { name: "Settings", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Setup density").selectOption("compact");
  await page.getByLabel("Default analysis horizon").selectOption("15d");
  await page
    .getByRole("button", { name: "Save and apply preferences" })
    .click();
  await expect(page.getByText("Preferences saved and applied.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Setup density")).toHaveValue("compact");
  await expect(page.getByLabel("Default analysis horizon")).toHaveValue("15d");
  const conflict = await page.request.put("/api/v1/settings/values", {
    headers: { Origin: baseURL! },
    data: { revision: 0, values: {} },
  });
  expect(conflict.status()).toBe(409);
  await page.getByLabel("Profile name").fill("Desk");
  await page
    .getByRole("button", { name: "Create profile", exact: true })
    .click();
  await expect(page.getByRole("button", { name: "Apply Desk" })).toBeVisible();
  await page
    .getByRole("button", { name: "Reset preferences to defaults" })
    .click();
  await expect(page.getByText("Defaults restored.")).toBeVisible();
  await page.getByRole("button", { name: "Apply Desk" }).click();
  await expect(page.getByText(/Profile applied/)).toBeVisible();
  await expect(page.getByLabel("Setup density")).toHaveValue("compact");
  for (const theme of ["dark", "light"]) {
    if (theme === "light")
      await page.getByRole("button", { name: "Light theme" }).click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: info.outputPath("settings-" + theme + ".png"),
      fullPage: true,
      animations: "disabled",
    });
  }
  await page.getByRole("button", { name: "Deactivate profile" }).click();
  await expect(page.getByText(/Profile detached/)).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/login$/);
  expect((await page.request.get("/api/v1/settings/values")).status()).toBe(
    401,
  );
  expect(errors).toEqual([]);
});
