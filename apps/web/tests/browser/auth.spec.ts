import { expect, test } from "@playwright/test";

test("anonymous redirect, invalid login, authenticated identity, logout and replay protection", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await expect(
    page.getByRole("navigation", { name: "Primary navigation" }),
  ).toHaveCount(0);
  await page.getByLabel("Username").fill("browser-user");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator(".login-error[role=alert]")).toContainText(
    "Check your username and password",
  );
  await page.screenshot({
    path: testInfo.outputPath("login-dark.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Light theme" }).click();
  await page.screenshot({
    path: testInfo.outputPath("login-light.png"),
    fullPage: true,
  });
  await page.getByLabel("Password").fill("test-only-browser-password");
  await page.getByLabel("Password").press("Enter");
  await expect(
    page.getByRole("heading", { name: "Workspace overview" }),
  ).toBeVisible();
  await expect(page.getByText("Browser Trader", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const cookies = await page.context().cookies();
  const session = cookies.find((cookie) => cookie.name === "twf_session")!;
  expect(session.httpOnly).toBe(true);
  expect(session.sameSite).toBe("Strict");
  await page.reload();
  await expect(page.getByText("Browser Trader", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.context().addCookies([session]);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  expect(errors).toEqual([]);
});
