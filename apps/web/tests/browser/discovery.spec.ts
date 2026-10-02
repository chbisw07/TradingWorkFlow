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
  await expect(matches).toContainText("Relative volume");
  await expect(matches).toContainText("Positive 10-day momentum");
  await expect(matches).toContainText("RVOL");
  await expect(matches).toContainText("NSE · EQ");
  await expect(matches).not.toContainText("NSE · INDEX");
  await expect(matches).not.toContainText("HDFCBANK");
  await expect(matches).not.toContainText("BANKNIFTY");
  await expect(page.getByText("Fresh").first()).toBeVisible();
  await page.screenshot({
    path: info.outputPath("workstation-populated.png"),
    fullPage: true,
    animations: "disabled",
  });

  const evidenceTrigger = matches.getByRole("button", {
    name: "View scan evidence chart for RELIANCE",
  });
  await evidenceTrigger.click();
  const evidenceDrawer = page.getByRole("dialog", {
    name: "RELIANCE evidence chart",
  });
  await expect(evidenceDrawer).toBeVisible();
  await expect(
    evidenceDrawer.getByRole("tab", { name: "As scanned" }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(evidenceDrawer.getByText("SYNTHETIC DATA")).toBeVisible();
  await expect(
    evidenceDrawer.getByText("Price evidence", { exact: true }),
  ).toBeVisible();
  await expect(
    evidenceDrawer.getByText("Volume evidence", { exact: true }),
  ).toBeVisible();
  await expect(evidenceDrawer.getByText("Why this matched")).toBeVisible();
  await expect(
    evidenceDrawer.getByText("Relative volume").last(),
  ).toBeVisible();
  expect(
    await evidenceDrawer.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("evidence-chart-open.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.screenshot({
    path: info.outputPath("evidence-chart-viewport.png"),
    animations: "disabled",
  });
  await page.screenshot({
    path: info.outputPath("synthetic-as-scanned.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.keyboard.press("Escape");
  await expect(evidenceDrawer).toHaveCount(0);
  await expect(evidenceTrigger).toBeFocused();

  await expect(
    page.getByRole("button", { name: /Current scan \(2\)/ }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText(/Current scan: 2 · Active queue:/)).toBeVisible();
  await expect(page.getByText(/2 admitted · 0 excluded/).first()).toBeVisible();

  const queueControls = page.locator(".queue-controls");
  await queueControls.locator("summary").click();
  await expect(queueControls.getByLabel("Sort")).toHaveValue("attention");
  await expect(
    queueControls.getByText(
      /Sorted by current relevance model, relevance, lifecycle, freshness, and recency/,
    ),
  ).toBeVisible();
  await queueControls.getByLabel("Search symbol").fill("MCX");
  await expect(queueControls.getByText(/Showing 1 of 2/)).toBeVisible();
  await queueControls.getByRole("button", { name: "Clear filters" }).click();
  await expect(queueControls.getByText(/Showing 2 of 2/)).toBeVisible();
  const controlsBox = await queueControls.boundingBox();
  expect(controlsBox).not.toBeNull();
  expect(controlsBox!.x + controlsBox!.width).toBeLessThanOrEqual(width + 1);
  await page.screenshot({
    path: info.outputPath("queue-filtering.png"),
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
  await expect(
    relianceQueueRow.getByRole("img", {
      name: /Recent observation trend:.*Present/,
    }),
  ).toBeVisible();
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
  await expect(
    detail.getByRole("heading", { name: "Observation history" }),
  ).toBeVisible();
  await expect(detail).toContainText("Last observed");
  await expect(detail).toContainText("Latest comparable scan");
  await expect(
    detail.getByRole("img", { name: /Recent observation trend:.*Present/ }),
  ).toBeVisible();
  expect(
    await detail.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
  ).toBe(true);
  await detail.getByText("Candidate provenance").click();
  await expect(
    detail.getByRole("button", { name: "Copy candidate identifier" }),
  ).toBeVisible();
  await detail.getByText("Provenance details").first().click();
  await expect(
    detail.getByRole("button", { name: "Copy evidence identifier" }).first(),
  ).toBeVisible();
  await expect(
    detail.getByRole("button", { name: "Copy native identifier" }).first(),
  ).toBeVisible();
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
    page.getByRole("heading", { name: /Viewing historical scan/ }),
  ).toBeVisible();
  await page.getByText(/Stored match evidence/).click();
  await expect(
    page.getByRole("table", { name: "Historical scan matches" }),
  ).toContainText("RELIANCE");
  const historicalEvidenceTrigger = page
    .getByRole("table", { name: "Historical scan matches" })
    .getByRole("button", { name: "View scan evidence chart for RELIANCE" });
  await historicalEvidenceTrigger.click();
  const historicalEvidence = page.getByRole("dialog", {
    name: "RELIANCE evidence chart",
  });
  await expect(historicalEvidence).toContainText("AS SCANNED");
  await expect(historicalEvidence).toContainText(/Run [0-9a-f]{8}/);
  await page.screenshot({
    path: info.outputPath("historical-run-evidence-chart.png"),
    fullPage: true,
    animations: "disabled",
  });
  await historicalEvidence
    .getByRole("button", { name: "Close evidence chart" })
    .click();
  const runView = page.getByRole("group", { name: "Historical run view" });
  await expect(
    runView.getByRole("button", { name: "As scanned" }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByRole("table", { name: "Immutable observations from this run" }),
  ).toContainText("Present");
  await runView.getByRole("button", { name: "Current state" }).click();
  await expect(
    page.getByRole("table", { name: "Current candidate state for this run" }),
  ).toContainText("RELIANCE");
  expect(
    await page
      .locator(".historical-scan-view")
      .evaluate((element) => element.scrollWidth <= element.clientWidth + 1),
  ).toBe(true);
  await page.getByRole("button", { name: "Back to latest scan" }).click();
  await expect(
    page.getByRole("heading", { name: "Latest scan result" }),
  ).toBeVisible();
  const useSetup = recentScans
    .getByRole("button", { name: "Use setup" })
    .first();
  await expect(useSetup).toBeVisible();
  await useSetup.click();
  const setupToast = page.getByRole("status", { name: "Setup loaded" });
  await expect(setupToast).toContainText(
    "Historical scan setup loaded. Review before running.",
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

  await page
    .locator('select[aria-describedby="provider-help"]')
    .selectOption("tradingview-synthetic");
  const validationScanResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/v1/discovery/scans" &&
      response.ok(),
  );
  const validationRunButton = page.getByRole("button", { name: "Run scan" });
  await validationRunButton.click();
  await validationScanResponse;
  await expect(validationRunButton).toBeEnabled();
  await expect(
    page.getByRole("heading", { name: "Latest scan result" }),
  ).toBeVisible();
  const validationMatches = page.getByRole("table", {
    name: "Latest normalized scan matches",
  });
  await validationMatches
    .getByRole("button", { name: "View scan evidence chart for RELIANCE" })
    .click();
  const unavailableChart = page.getByRole("dialog", {
    name: "RELIANCE evidence chart",
  });
  await unavailableChart.getByRole("tab", { name: "Current chart" }).click();
  await expect(unavailableChart).toContainText("RETENTION RESTRICTED");
  await expect(unavailableChart).toContainText(
    /As-scanned evidence remains available/,
  );
  await page.screenshot({
    path: info.outputPath("unavailable-current-chart.png"),
    fullPage: true,
    animations: "disabled",
  });
  await unavailableChart
    .getByRole("button", { name: "Close evidence chart" })
    .click();

  await recentScans.getByRole("button", { name: "Archive" }).first().click();
  await expect(
    page.getByRole("status", { name: "Scan history updated" }),
  ).toContainText("Scan archived.");
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
    page.getByRole("status", { name: "Scan history updated" }),
  ).toContainText("Scan restored to recent history.");
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

test("profile-aware pullback evidence renders its exact zone without clutter", async ({
  page,
  baseURL,
}, info) => {
  const width = page.viewportSize()!.width;
  test.skip(
    ![390, 1440].includes(width),
    "Representative mobile and desktop visual validation only",
  );
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
  await page
    .locator('select[aria-describedby="profile-help"]')
    .selectOption("PULLBACK_IN_UPTREND");
  await page.getByLabel("Universe symbols").fill("INFY");
  const runButton = page.getByRole("button", { name: "Run scan" });
  await runButton.click();
  await expect(runButton).toBeEnabled();
  const matches = page.getByRole("table", {
    name: "Latest normalized scan matches",
  });
  await matches
    .getByRole("button", { name: "View scan evidence chart for INFY" })
    .click();
  const chart = page.getByRole("dialog", { name: "INFY evidence chart" });
  await expect(chart).toBeVisible();
  await expect(chart.locator(".chart-pullback-region")).toHaveCount(1);
  await expect(chart).toContainText("Pullback zone upper");
  await expect(chart).toContainText("Pullback zone lower");
  await expect(chart).toContainText("SMA 50");
  await expect(chart).toContainText("SMA 200");
  expect(
    await chart.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("pullback-evidence-chart.png"),
    animations: "disabled",
  });
  expect(errors).toEqual([]);
});
