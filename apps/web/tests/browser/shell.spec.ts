import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, baseURL }) => {
  const response = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: baseURL! },
    data: { username: "browser-user", password: "test-only-browser-password" },
  });
  expect(response.ok()).toBe(true);
});

test("shell recomposes with reachable regions, keyboard controls and no page overflow", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Workspace overview" }),
  ).toBeVisible();
  await expect(
    page.getByText("TWF-1.1 Frontend Shell", { exact: true }),
  ).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Primary navigation" });
  const toggle = page.getByRole("button", { name: "Workspace navigation" });
  const width = page.viewportSize()!.width;
  if (width < 700) {
    await expect(
      nav.getByRole("link", { name: "Home", exact: true }),
    ).toBeHidden();
    await toggle.tap();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
  }
  await expect(
    nav.getByRole("link", { name: "Home", exact: true }),
  ).toBeVisible();
  await expect(nav.getByRole("button", { name: /coming later/ })).toHaveCount(
    8,
  );
  await expect(
    nav.getByRole("button", { name: "Orders — coming later" }),
  ).toBeDisabled();
  if (width < 700) {
    await nav.getByRole("link", { name: "Home", exact: true }).focus();
    await page.keyboard.press("Escape");
    await expect(toggle).toBeFocused();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
  }
  const main = await page.getByRole("main").boundingBox();
  const context = page.getByRole("complementary", {
    name: "Workspace context",
  });
  const contextBox = await context.boundingBox();
  if (width >= 1200)
    expect(contextBox!.x).toBeGreaterThanOrEqual(main!.x + main!.width);
  else expect(contextBox!.y).toBeGreaterThanOrEqual(main!.y + main!.height);
  await context.scrollIntoViewIfNeeded();
  await expect(
    context.getByRole("button", { name: "Check service status" }),
  ).toBeVisible();
  await expect(
    context.getByText("Configured services have not been checked."),
  ).toBeVisible();
  const collapse = page.getByRole("button", { name: "Collapse console" });
  await collapse.scrollIntoViewIfNeeded();
  await collapse.focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("region", { name: "System console content" }),
  ).toBeHidden();
  await page.getByRole("button", { name: "Expand console" }).click();
  await expect(
    page.getByRole("region", { name: "System console content" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: testInfo.outputPath("shell.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("skip link, reduced motion, and localized panel overflow work", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to workspace" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
  const theme = await page.evaluate(() => ({
    motion: parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue(
        "--motion-fast",
      ),
    ),
    scheme: getComputedStyle(document.documentElement).colorScheme,
    focus: getComputedStyle(document.querySelector("main")!).outlineStyle,
  }));
  expect(theme).toEqual({ motion: 0, scheme: "dark", focus: "solid" });
  const body = page.getByRole("region", { name: "Workspace activity content" });
  await body.evaluate((element) => {
    const oversized = document.createElement("div");
    oversized.style.width = "3000px";
    oversized.style.height = "900px";
    oversized.textContent = "Future virtualized surface sizing probe";
    element.appendChild(oversized);
  });
  const sizing = await body.evaluate((element) => ({
    localOverflow: element.scrollWidth > element.clientWidth,
    pageOverflow: document.documentElement.scrollWidth > window.innerWidth,
  }));
  expect(sizing).toEqual({ localOverflow: true, pageOverflow: false });
});

test("unknown routes retain the shell and offer recovery", async ({ page }) => {
  const response = await page.goto("/missing-shell-view");
  // Next.js streams authenticated layouts; a streamed not-found response is 200.
  expect([200, 404]).toContain(response?.status());
  await expect(page.locator('meta[name="robots"]').first()).toHaveAttribute(
    "content",
    "noindex",
  );
  await expect(
    page.getByRole("heading", { name: "Page not found" }),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Primary navigation" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Back to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Workspace overview" }),
  ).toBeVisible();
});
