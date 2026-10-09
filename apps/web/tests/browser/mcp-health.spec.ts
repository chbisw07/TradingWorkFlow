import { expect, test } from "@playwright/test";

test("TapTide health and operation accounting stay separate", async ({
  page,
  baseURL,
}, info) => {
  const login = await page.request.post("/api/v1/auth/login", {
    headers: { Origin: baseURL! },
    data: {
      username: `settings-${info.project.name}`,
      password: "test-only-browser-password",
    },
  });
  expect(login.ok()).toBe(true);
  let degraded = false;
  await page.route("**/api/v1/settings/mcp/connections", (route) =>
    route.fulfill({
      json: [
        {
          id: "11111111-1111-1111-1111-111111111111",
          provider_id: "tapetide",
          display_name: "TapTide",
          enabled: true,
          generation: 5,
          state: "CONNECTED",
          health: degraded ? "DEGRADED" : "AVAILABLE",
          error: degraded ? "TOOL_FAILED" : null,
          tools: Array.from({ length: 55 }, (_, i) => ({
            name: `fixture_tool_${i}`,
          })),
          operations_pending: 0,
          unresolved_cleanup_count: degraded ? 1 : 0,
          recovery_required: degraded,
          cleanup_pending: false,
          last_success_at: "2026-10-09T12:55:13Z",
          last_failure_at: degraded ? "2026-10-09T12:55:41Z" : null,
          last_failure_kind: degraded ? "TOOL_FAILED" : null,
        },
      ],
    }),
  );
  for (const state of ["available", "degraded"]) {
    degraded = state === "degraded";
    await page.goto("/settings#integrations");
    if (degraded) await page.reload();
    const card = page.locator(".settings-integration-card").filter({
      has: page.getByRole("heading", { name: "TapTide", exact: true }),
    });
    await expect(card.getByText(/Active operations: 0/)).toBeVisible();
    await expect(
      card.getByText("State: Connected", { exact: false }),
    ).toBeVisible();
    if (degraded) {
      await expect(card.getByText("Unresolved cleanup: 1")).toBeVisible();
      await expect(card.getByText(/Last failure: Tool failed/)).toBeVisible();
      await expect(card.getByText("Error", { exact: true })).toHaveCount(0);
    } else {
      await expect(card.getByText("Ready", { exact: true })).toBeVisible();
      await expect(card.getByText(/Unresolved cleanup/)).toHaveCount(0);
    }
    await card.scrollIntoViewIfNeeded();
    await card.screenshot({
      path: info.outputPath(`tapetide-${state}-card.png`),
    });
    await page.screenshot({
      path: info.outputPath(`tapetide-${state}.png`),
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});
