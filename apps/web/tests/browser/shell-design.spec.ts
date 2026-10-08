import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, baseURL }) => {
  const login = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: baseURL! },
    data: { username: "browser-user", password: "test-only-browser-password" },
  });
  expect(login.ok()).toBe(true);
});

test("approved shell wraps real workspaces in light and dark at every width", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const width = page.viewportSize()!.width;
  for (const theme of ["light", "dark"]) {
    await page.addInitScript(
      (theme) => localStorage.setItem("twf-theme", theme),
      theme,
    );
    for (const route of ["scanners", "brokers", "settings"]) {
      await page.goto("/" + route);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await expect(
        page.getByRole("search", { name: "Global symbol search" }),
      ).toBeVisible();
      await expect(
        page.getByLabel("Search symbol — coming later"),
      ).toBeDisabled();
      await expect(page.getByLabel("Market summary")).toBeVisible();
      await expect(
        page.getByLabel("NIFTY value 24,998.75", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByLabel("BANKNIFTY value 52,316.20", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByLabel("INDIA VIX value 13.25", { exact: true }),
      ).toBeVisible();
      await expect(page.locator(".user-menu > summary")).toHaveAttribute(
        "aria-label",
        "User menu: Browser Trader",
      );
      if (route === "scanners")
        await expect(
          page.getByRole("button", { name: /^Run scan$/i }),
        ).toBeVisible();
      if (route === "brokers")
        await expect(
          page
            .getByRole("link", { name: "Manage Brokers", exact: true })
            .last(),
        ).toBeVisible();
      if (route === "settings")
        await expect(
          page.getByRole("heading", { name: "Dhan market data", exact: true }),
        ).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({
        path: info.outputPath(`${theme}-${route}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await page.screenshot({
        path: `/tmp/twf-shell-evidence/after-${width}-${theme}-${route}.png`,
        animations: "disabled",
      });
      if (width >= 1200) {
        await expect(page.locator(".desktop-sidebar")).toBeVisible();
        expect(
          (await page.locator(".desktop-sidebar").boundingBox())!.width,
        ).toBe(202);
        expect(
          (await page.locator(".top-bar").boundingBox())!.height,
        ).toBeLessThanOrEqual(70);
      }
    }
  }
  expect(errors).toEqual([]);
});

test("grouped navigation, mobile focus trap, user menu, planned routes and Settings deep links work", async ({
  page,
}) => {
  await page.goto("/scanners");
  const mobile = page.viewportSize()!.width < 1200;
  const toggle = page.getByRole("button", { name: "Workspace navigation" });
  async function navigation() {
    if (mobile) await toggle.click();
    return page.locator(
      mobile ? ".navigation-drawer nav" : ".desktop-sidebar nav",
    );
  }
  let nav = await navigation();
  await expect(nav.getByRole("heading")).toHaveText([
    "WORKSPACE",
    "TOOLS",
    "INSIGHTS",
    "SETTINGS",
  ]);
  await expect(nav.getByRole("link")).toHaveCount(17);
  await expect(
    nav.getByRole("link", { name: "Scanners", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  if (mobile) {
    await expect(
      page.getByRole("dialog", { name: "Workspace navigation" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Close navigation" }).focus();
    await page.keyboard.press("Shift+Tab");
    await expect(
      nav.getByRole("link", { name: "Advanced", exact: true }),
    ).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("button", { name: "Close navigation" }),
    ).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(toggle).toBeFocused();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    nav = await navigation();
  }
  await nav.getByRole("link", { name: "Market Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Market Overview", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Coming later", { exact: true }).last(),
  ).toBeVisible();
  await page.locator(".user-menu > summary").click();
  await page
    .locator(".user-menu-content")
    .getByRole("link", { name: "Brokers", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Brokers", exact: true }),
  ).toBeVisible();
  for (const [label, hash] of [
    ["Integrations", "integrations"],
    ["Advanced", "advanced"],
    ["Preferences", "preferences"],
  ]) {
    nav = await navigation();
    await nav.getByRole("link", { name: label, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/settings#${hash}$`));
    const target = page.locator("#" + hash);
    await expect(target).toBeInViewport();
    if (hash === "advanced") {
      await expect(target.locator("..")).toHaveAttribute("open", "");
      await expect(target).toBeFocused();
    } else await expect(target).toBeFocused();
    if (hash === "integrations") {
      await expect(
        target.getByRole("heading", { name: "Dhan market data" }),
      ).toBeVisible();
      await expect(
        target.getByRole("heading", { name: "TapTide" }),
      ).toBeVisible();
      await expect(
        target.getByRole("link", { name: "Manage broker connections" }),
      ).toHaveAttribute("href", "/brokers");
    }
  }
  // Direct entry and reload also reopen the advanced section after async settings load.
  await page.goto("/settings#advanced");
  await expect(page.locator("#advanced").locator("..")).toHaveAttribute(
    "open",
    "",
  );
  await page.reload();
  await expect(page.locator("#advanced")).toBeFocused();
});

test("Brokers supports direct entry, refresh and a Scanners round trip", async ({
  page,
}) => {
  const mobile = page.viewportSize()!.width < 1200;
  async function navigation() {
    if (mobile)
      await page.getByRole("button", { name: "Workspace navigation" }).click();
    return page.locator(
      mobile ? ".navigation-drawer nav" : ".desktop-sidebar nav",
    );
  }
  async function activeStyle(label: string) {
    const nav = await navigation();
    const link = nav.getByRole("link", { name: label, exact: true });
    await expect(link).toHaveAttribute("aria-current", "page");
    return link.evaluate(async (element) => {
      await Promise.all(
        element.getAnimations().map((animation) => animation.finished),
      );
      const style = getComputedStyle(element);
      return {
        background: style.backgroundColor,
        color: style.color,
        shadow: style.boxShadow,
      };
    });
  }
  const response = await page.goto("/brokers");
  expect(response!.ok()).toBe(true);
  await expect(
    page.getByRole("heading", { name: "Brokers", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Manage Brokers", exact: true }).last(),
  ).toBeVisible();
  const brokerStyle = await activeStyle("Brokers");
  if (mobile)
    await page.getByRole("button", { name: "Close navigation" }).click();
  const reload = await page.reload();
  expect(reload!.ok()).toBe(true);
  await expect(page).toHaveURL(/\/brokers$/);
  await expect(
    page.getByRole("heading", { name: "Brokers", exact: true }),
  ).toBeVisible();
  let nav = await navigation();
  await nav.getByRole("link", { name: "Scanners", exact: true }).click();
  await expect(page).toHaveURL(/\/scanners$/);
  await expect(page.getByRole("button", { name: /^Run scan$/i })).toBeVisible();
  expect(await activeStyle("Scanners")).toEqual(brokerStyle);
  nav = page.locator(
    mobile ? ".navigation-drawer nav" : ".desktop-sidebar nav",
  );
  await expect(
    nav.getByRole("link", { name: "Brokers", exact: true }),
  ).toHaveAttribute("href", "/brokers");
  await nav.getByRole("link", { name: "Brokers", exact: true }).click();
  await expect(page).toHaveURL(/\/brokers$/);
  await expect(
    page.getByRole("heading", { name: "Brokers", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Manage Brokers", exact: true }).last(),
  ).toBeVisible();
  expect(await activeStyle("Brokers")).toEqual(brokerStyle);
});
