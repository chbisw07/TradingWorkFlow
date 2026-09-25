import { expect, test } from "@playwright/test";

test("authenticated service status is labeled synthetic and fits both themes", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  expect((await page.request.get("/api/v1/services")).status()).toBe(401);
  expect(
    (
      await page.request.post("/api/v1/auth/login", {
        headers: { Origin: "http://127.0.0.1:3100" },
        data: {
          username: "browser-user",
          password: "test-only-browser-password",
        },
      })
    ).ok(),
  ).toBe(true);
  await page.clock.setFixedTime(new Date("2026-09-25T12:00:00Z"));
  await page.goto("/");
  const panel = page.getByRole("region", {
    name: "Service connections",
    exact: true,
  });
  for (const theme of ["dark", "light"]) {
    if (theme === "light")
      await page.getByRole("button", { name: "Light theme" }).click();
    await panel.getByRole("button", { name: "Check service status" }).click();
    await expect(panel.getByText(/Synthetic fixture/)).toHaveCount(4);
    await expect(
      panel.getByText("Available · fresh", { exact: true }),
    ).toHaveCount(1);
    await expect(
      panel.getByText("Available · stale", { exact: true }),
    ).toHaveCount(1);
    await expect(panel.getByText("Unavailable", { exact: true })).toHaveCount(
      1,
    );
    await expect(
      panel.getByText("Unknown · fresh", { exact: true }),
    ).toHaveCount(1);
    await expect(
      panel.getByText("Source: twf-fixture", { exact: true }),
    ).toHaveCount(4);
    await expect(
      panel.locator('time[datetime="2026-09-25T11:50:00.000Z"]'),
    ).toBeVisible();
    await expect(panel.getByText("Available", { exact: true })).toHaveCount(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(
      await panel
        .getByRole("region", { name: "Service connections content" })
        .evaluate((element) => element.scrollWidth <= element.clientWidth),
    ).toBe(true);
    await panel.scrollIntoViewIfNeeded();
    await expect(panel).toBeVisible();
  }
  expect(errors).toEqual([]);
});
