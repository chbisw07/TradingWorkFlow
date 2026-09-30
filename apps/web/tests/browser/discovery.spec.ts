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
  const width = page.viewportSize()!.width;
  await expect(
    page.getByRole("heading", { name: "Evidence-led market discovery" }),
  ).toBeVisible();
  const themeToggle = page.getByRole("button", { name: "Light theme" });
  await themeToggle.click();
  await expect(themeToggle).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByText(/Discovery never authorizes a trade/),
  ).toBeVisible();
  await expect(page.getByText("SYNTHETIC VALIDATION DATA")).toHaveCount(0);
  await expect(page.locator(".data-mode-banner")).toHaveCount(0);
  const statusStrip = page.getByRole("region", {
    name: "Provider and evidence readiness",
  });
  await expect(
    statusStrip.getByRole("heading", {
      name: "Provider and evidence readiness",
    }),
  ).toBeVisible();
  await expect(statusStrip.getByText("Synthetic Data")).toBeVisible();
  await expect(
    statusStrip.getByText("Validation", { exact: true }),
  ).toBeVisible();
  expect(
    await page
      .locator(".discovery-hero")
      .evaluate((element) =>
        element.nextElementSibling?.classList.contains(
          "workspace-status-strip",
        ),
      ),
  ).toBe(true);
  await expect(page.getByText("Ready").first()).toBeVisible();
  await expect(page.getByText(/SPRINT 2/)).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Ready to scan" }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Configure the scan and run it to see results here."),
  ).toBeVisible();
  await expect(
    page.getByText("Select a candidate to inspect evidence and history."),
  ).toHaveCount(0);
  await expect(page.locator(".scan-workstation-grid")).toHaveClass(
    /without-inspector/,
  );
  await expect(page.locator(".scan-workstation-inspector")).toHaveCount(0);
  const emptyGridColumns = await page
    .locator(".scan-workstation-grid")
    .evaluate(
      (element) =>
        getComputedStyle(element).gridTemplateColumns.split(" ").length,
    );
  expect(emptyGridColumns).toBe(width >= 1024 ? 2 : 1);
  await page.screenshot({
    path: info.outputPath("workstation-empty-state.png"),
    fullPage: true,
    animations: "disabled",
  });
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
  await page.screenshot({
    path: info.outputPath("workstation-populated.png"),
    fullPage: true,
    animations: "disabled",
  });

  const discoveryQueue =
    width < 600
      ? page.getByRole("list", { name: "Discovery queue" })
      : page.getByRole("table", { name: "Discovery queue" });
  const relianceQueueRow = discoveryQueue.locator(
    '[data-candidate-symbol="RELIANCE"]',
  );
  await relianceQueueRow.getByRole("button", { name: "Review" }).click();
  const detail = page.getByRole("complementary", { name: "RELIANCE" });
  await expect(page.locator(".scan-workstation-grid")).toHaveClass(
    /has-inspector/,
  );
  await expect(relianceQueueRow).toHaveAttribute("data-selected", "true");
  const selectedGridColumns = await page
    .locator(".scan-workstation-grid")
    .evaluate(
      (element) =>
        getComputedStyle(element).gridTemplateColumns.split(" ").length,
    );
  expect(selectedGridColumns).toBe(width >= 1400 ? 3 : width >= 1024 ? 2 : 1);
  await expect(detail).toContainText(
    "Attention score, not probability of profit",
  );
  await expect(detail).toContainText("Snapshot 1");
  await expect(detail).toContainText("Latest evidence");
  await expect(detail).toContainText("Source time");
  await expect(detail).toContainText("Optional AI explanation");
  await expect(detail).toContainText("Evidence available");
  await expect(detail).toContainText("Within");
  await page.screenshot({
    path: info.outputPath("selected-candidate.png"),
    fullPage: true,
    animations: "disabled",
  });
  const inspectorPosition = await detail.evaluate(
    (element) => getComputedStyle(element).position,
  );
  expect(inspectorPosition).toBe(width >= 1400 ? "sticky" : "static");
  await detail.getByRole("button", { name: "Close candidate review" }).click();
  await expect(detail).toHaveCount(0);
  await expect(page.locator(".scan-workstation-grid")).toHaveClass(
    /without-inspector/,
  );
  await expect(relianceQueueRow).toHaveAttribute("data-selected", "false");
  const restoredGridColumns = await page
    .locator(".scan-workstation-grid")
    .evaluate(
      (element) =>
        getComputedStyle(element).gridTemplateColumns.split(" ").length,
    );
  expect(restoredGridColumns).toBe(width >= 1024 ? 2 : 1);

  const recentScans = page.getByRole("list", {
    name: "Recent discovery scans",
  });
  await expect(recentScans).toContainText("Internal");
  await expect(recentScans).toContainText("symbols");
  await expect(recentScans).toContainText("matches");
  await recentScans.getByText("Actions").first().click();
  const viewHistory = recentScans.getByRole("button", { name: "View" }).first();
  await viewHistory.click();
  await expect(viewHistory).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByRole("heading", { name: "Latest scan summary" }),
  ).toBeVisible();
  const useSetup = recentScans
    .getByRole("button", { name: "Use setup" })
    .first();
  await expect(useSetup).toBeVisible();
  await useSetup.click();
  const setupToast = page.getByRole("status", { name: "Setup loaded" });
  await expect(setupToast).toContainText(
    "Scan setup loaded. Review it before selecting Run scan.",
  );
  expect(
    await setupToast.evaluate((element) => getComputedStyle(element).position),
  ).toBe("fixed");
  await setupToast
    .getByRole("button", { name: "Dismiss notification" })
    .click();
  await expect(setupToast).toHaveCount(0);
  expect(
    await page
      .locator(".discovery-hero")
      .evaluate((element) =>
        element.nextElementSibling?.classList.contains(
          "workspace-status-strip",
        ),
      ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("recent-scan-history.png"),
    fullPage: true,
    animations: "disabled",
  });

  await recentScans.getByRole("button", { name: "Archive" }).first().click();
  await expect(
    page.getByText("Scan archived. It remains available in Past scans."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Past scans" }).click();
  const pastScans = page.getByRole("dialog", { name: "Past scans" });
  await expect(pastScans).toBeVisible();
  await expect(pastScans.getByLabel("Date range")).toBeVisible();
  await expect(pastScans.getByLabel("Provider")).toBeVisible();
  await expect(pastScans.getByLabel("Profile")).toBeVisible();
  await expect(pastScans.getByLabel("Status")).toBeVisible();
  await pastScans.getByLabel("Visibility").selectOption("archived");
  await expect(pastScans.getByText("Archived").first()).toBeVisible();
  await page.screenshot({
    path: info.outputPath("past-scans.png"),
    fullPage: true,
    animations: "disabled",
  });
  await pastScans.getByRole("button", { name: "Restore" }).first().click();
  await expect(
    page.getByText("Scan restored to recent history."),
  ).toBeVisible();
  await pastScans.getByRole("button", { name: "Close past scans" }).click();
  await expect(pastScans).toHaveCount(0);

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
  const candidateLedger =
    width < 600
      ? page.getByRole("list", { name: "Discovery candidates" })
      : page.getByRole("table", { name: "Discovery candidates" });
  await expect(candidateLedger).toContainText("Scan + market context");

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
