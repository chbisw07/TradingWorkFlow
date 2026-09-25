import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  const response = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: { username: "browser-user", password: "test-only-browser-password" },
  });
  expect(response.ok()).toBe(true);
});

test("themes switch without changing layout and persist across reloads", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await page.goto("/");
  const root = page.locator("html");
  const toggle = page.getByRole("button", { name: "Light theme" });
  await expect(root).toHaveAttribute("data-theme", "dark");
  const initial = await page.getByRole("main").boundingBox();
  await toggle.focus();
  await page.keyboard.press("Space");
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await expect(root).toHaveAttribute("data-theme", "light");
  expect(await page.getByRole("main").boundingBox()).toEqual(initial);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(await root.evaluate((el) => getComputedStyle(el).colorScheme)).toBe(
    "light",
  );
  await page.screenshot({
    path: testInfo.outputPath("light.png"),
    fullPage: true,
  });
  await page.reload();
  await expect(root).toHaveAttribute("data-theme", "light");
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await toggle.click();
  await expect(root).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(root).toHaveAttribute("data-theme", "dark");
  expect(errors).toEqual([]);
});

test("saved light preference is applied before hydration", async ({
  browser,
  baseURL,
}) => {
  const context = await browser.newContext({ javaScriptEnabled: true });
  const page = await context.newPage();
  await page.addInitScript(() => localStorage.setItem("twf-theme", "light"));
  // Block hydration bundles; the head initializer must work independently.
  await page.route("**/_next/static/**/*.js", (route) => route.abort());
  await page.goto(baseURL!);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await context.close();
});
