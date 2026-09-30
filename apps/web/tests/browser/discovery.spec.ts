import { expect, test } from "@playwright/test";

test("Scan & Discover runs a bounded internal scan and exposes normalized evidence history", async ({
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
  await expect(
    page.getByText(/Discovery never authorizes a trade/),
  ).toBeVisible();
  await expect(
    page.getByText("TradingView exact-batch validation"),
  ).toBeVisible();
  await page.getByRole("textbox").fill("RELIANCE, TCS");
  await page.getByRole("button", { name: "Run scan" }).click();
  await expect(
    page.getByRole("heading", { name: "Latest scan result" }),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Latest normalized scan matches" }),
  ).toContainText("Relative volume");
  await page.getByRole("button", { name: "Review" }).first().click();
  const detail = page.getByRole("complementary", { name: "RELIANCE" });
  await expect(detail).toContainText(
    "Attention score, not probability of profit",
  );
  await expect(detail).toContainText("Snapshot 1");
  await expect(detail).toContainText("Latest evidence");
  await expect(detail).toContainText("Source time");
  await expect(detail).toContainText("Optional AI explanation");
  await detail.getByRole("button", { name: "Close candidate review" }).click();
  await page.getByRole("button", { name: /Candidates/ }).click();
  await expect(
    page.getByRole("heading", { name: "Candidate ledger" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("scan-discover.png"),
    fullPage: true,
    animations: "disabled",
  });
  expect(errors).toEqual([]);
});
