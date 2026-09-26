import { expect, test } from "@playwright/test";

test("owned synthetic broker rooms and overview recompose in both themes", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  expect((await page.request.get("/api/v1/brokers/overview")).status()).toBe(
    401,
  );
  await page.goto("/login");
  await page.getByLabel("Username").fill(`brokers-${info.project.name}`);
  await page.getByLabel("Password").fill("test-only-browser-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Workspace overview" }),
  ).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Primary navigation" });
  const toggle = nav.getByRole("button", { name: "Workspace navigation" });
  if (await toggle.isVisible()) await toggle.click();
  await nav.getByRole("link", { name: "Brokers", exact: true }).click();
  async function expectContainedAccountLinks() {
    const accounts = page.getByRole("navigation", { name: "Broker accounts" });
    expect(
      await accounts.evaluate((nav) => {
        const bounds = nav.getBoundingClientRect();
        return [...nav.querySelectorAll("a")].every((link) => {
          const box = link.getBoundingClientRect();
          return box.left >= bounds.left - 1 && box.right <= bounds.right + 1;
        });
      }),
    ).toBe(true);
  }
  for (const theme of ["dark", "light"]) {
    if (theme === "light")
      await page.getByRole("button", { name: "Light theme" }).click();
    await expect(
      page.getByRole("heading", { name: "Broker overview" }),
    ).toBeVisible();
    await expect(page.getByText("105", { exact: true })).toBeVisible();
    await expect(page.getByText(/1 unmapped position rows/)).toBeVisible();
    await expectContainedAccountLinks();
    await page.screenshot({
      path: info.outputPath(`brokers-overview-${theme}.png`),
      fullPage: true,
    });
    await page.getByRole("link", { name: "Open Alpha A1 →" }).click();
    await expect(
      page.getByRole("heading", { level: 1, name: "Alpha A1" }),
    ).toBeVisible();
    for (const view of ["Holdings", "Positions", "Orders", "Funds"]) {
      await page
        .getByRole("navigation", { name: "Broker room views" })
        .getByRole("link", { name: view, exact: true })
        .click();
      await expect(
        page.getByRole("heading", { level: 2, name: view, exact: true }),
      ).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    await page
      .getByRole("navigation", { name: "Broker accounts" })
      .getByRole("link", { name: "Alpha A2 SYNTHETIC" })
      .click();
    await expect(
      page.getByRole("heading", { level: 1, name: "Alpha A2" }),
    ).toBeVisible();
    await page
      .getByRole("navigation", { name: "Broker accounts" })
      .getByRole("link", { name: "Beta B1 SYNTHETIC" })
      .click();
    await expect(page.getByText(/Read health: DEGRADED/)).toBeVisible();
    await page
      .getByRole("navigation", { name: "Broker room views" })
      .getByRole("link", { name: "Positions", exact: true })
      .click();
    await expect(
      page.getByText("Unmapped — excluded from canonical netting"),
    ).toBeVisible();
    await expect(page.getByText(/DEGRADED.*STALE.*PARTIAL/)).toBeVisible();
    await expectContainedAccountLinks();
    await page.screenshot({
      path: info.outputPath(`brokers-positions-${theme}.png`),
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page
      .getByRole("navigation", { name: "Broker accounts" })
      .getByRole("link", { name: "Overview", exact: true })
      .click();
  }
  expect(errors).toEqual([]);
});
