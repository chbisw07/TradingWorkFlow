import { expect, test } from "@playwright/test";

test("Scan & Discover presents a responsive evidence workstation with route-level navigation", async ({
  page,
  baseURL,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const login = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: baseURL! },
    data: {
      username: "discovery-" + info.project.name,
      password: "test-only-browser-password",
    },
  });
  expect(login.ok()).toBe(true);

  await page.goto("/scanners");
  await expect(
    page.getByRole("heading", { name: "Evidence-led market discovery" }),
  ).toBeVisible();
  const themeToggle = page.getByRole("button", { name: "Light theme" });
  await themeToggle.click();
  await expect(themeToggle).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByText(/Discovery never authorizes a trade/),
  ).toBeVisible();
  await expect(page.getByText("SYNTHETIC VALIDATION DATA")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Provider status" }),
  ).toBeVisible();
  await expect(page.getByText("SYNTHETIC DATA").first()).toBeVisible();
  await expect(page.getByText("VALIDATION / SYNTHETIC")).toBeVisible();
  await expect(page.getByText("READY").first()).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Recent scans" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Candidates requiring review" }),
  ).toBeVisible();

  await page
    .getByLabel("Universe symbols")
    .fill("RELIANCE, MCX, HDFCBANK, INFY, BSE, NIFTY, BANKNIFTY");
  await page.getByRole("button", { name: "Run scan" }).click();
  await expect(
    page.getByRole("heading", { name: "Latest scan result" }),
  ).toBeVisible();
  const matches = page.getByRole("table", {
    name: "Latest normalized scan matches",
  });
  await expect(matches).toContainText("Relative volume elevated");
  await expect(matches).toContainText("RVOL");
  await expect(matches).toContainText("NSE · EQ");
  await expect(matches).toContainText("NSE · INDEX");
  await expect(matches).not.toContainText("HDFCBANK");
  await expect(matches).not.toContainText("BANKNIFTY");
  await expect(page.getByText("Fresh").first()).toBeVisible();

  const relianceQueueRow = page
    .getByRole("table", { name: "Discovery queue" })
    .getByRole("row")
    .filter({ hasText: "RELIANCE" });
  await relianceQueueRow.getByRole("button", { name: "Review" }).click();
  const detail = page.getByRole("complementary", { name: "RELIANCE" });
  await expect(detail).toContainText(
    "Attention score, not probability of profit",
  );
  await expect(detail).toContainText("Snapshot 1");
  await expect(detail).toContainText("Latest evidence");
  await expect(detail).toContainText("Source time");
  await expect(detail).toContainText("Optional AI explanation");
  await detail.getByRole("button", { name: "Close candidate review" }).click();
  await page.screenshot({
    path: info.outputPath("scan-workstation.png"),
    fullPage: true,
    animations: "disabled",
  });

  const navigation = page.getByRole("navigation", {
    name: "Primary navigation",
  });
  const candidateLink = navigation.getByRole("link", { name: "Candidates" });
  if (!(await candidateLink.isVisible())) {
    await navigation
      .getByRole("button", { name: "Workspace navigation" })
      .click();
  }
  await candidateLink.click();
  await expect(page).toHaveURL(/\/candidates$/);
  await expect(
    page.getByRole("heading", { name: "Candidate ledger" }),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Discovery candidates" }),
  ).toContainText("Scan + market context");

  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("candidate-ledger.png"),
    fullPage: true,
    animations: "disabled",
  });
  expect(errors).toEqual([]);
});
