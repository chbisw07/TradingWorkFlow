import { expect, type Page } from "@playwright/test";

export async function selectBroker(
  page: Page,
  label: "Overview" | "Zerodha" | "Manage Brokers",
) {
  const selector = page.getByRole("combobox", {
    name: "Broker workspace",
    exact: true,
  });
  if (await selector.isVisible()) await selector.selectOption({ label });
  else
    await page
      .getByRole("navigation", { name: "Broker workspace", exact: true })
      .getByRole("link", { name: label, exact: true })
      .click();
}

export async function selectDevelopment(page: Page, label: string) {
  const summary = page.locator(".broker-development > summary");
  await summary.click();
  await page
    .getByRole("navigation", { name: "Development accounts" })
    .getByRole("link", { name: label, exact: true })
    .click();
}

export async function contained(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
}
