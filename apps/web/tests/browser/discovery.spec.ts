import { expect, test } from "@playwright/test";

async function signIn(
  page: import("@playwright/test").Page,
  baseURL: string,
  project: string,
) {
  const login = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: baseURL },
    data: {
      username: `discovery-${project}`,
      password: "test-only-browser-password",
    },
  });
  expect(login.ok()).toBe(true);
}

test("Discovery navigation opens the current responsive candidate ledger", async ({
  page,
  baseURL,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await signIn(page, baseURL!, info.project.name);

  await page.goto("/scanners");
  await expect(
    page.getByRole("heading", { name: "Scanners", exact: true }),
  ).toBeVisible();
  if (page.viewportSize()!.width < 1200) {
    await page
      .getByRole("button", { name: "Workspace navigation", exact: true })
      .click();
  }
  await page.getByRole("link", { name: "Discovery", exact: true }).click();

  await expect(page).toHaveURL("/candidates");
  await expect(
    page.getByRole("heading", { name: "Discovery candidate review" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Candidate ledger" }),
  ).toBeVisible();
  await expect(
    page.getByRole("complementary", { name: "Candidate inspector" }),
  ).toContainText("Select a candidate to inspect evidence and history.");
  await expect(page.locator(".scan-control-panel")).toHaveCount(0);
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await page.screenshot({
    path: info.outputPath("candidate-ledger.png"),
    fullPage: true,
    animations: "disabled",
  });
  expect(errors).toEqual([]);
});

test("candidate ledger exposes truthful empty evidence without legacy scan controls", async ({
  page,
  baseURL,
}, info) => {
  test.skip(
    page.viewportSize()!.width < 1200,
    "The first journey covers the compact candidate ledger; this verifies the desktop two-panel state.",
  );
  await signIn(page, baseURL!, info.project.name);
  await page.goto("/candidates");

  await expect(
    page.getByRole("heading", { name: "No candidates to review" }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Run a bounded scan or change the selected universe. No missing evidence is inferred.",
    ),
  ).toBeVisible();
  await expect(page.getByLabel("Candidate inspector")).toContainText(
    "Evidence and history",
  );
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Candidate ledger" }),
  ).toBeVisible();
  await expect(
    page.locator('select[aria-describedby="profile-help"]'),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth + 2,
    ),
  ).toBe(false);
});
