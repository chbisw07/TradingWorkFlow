import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 2,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: (["chromium", "webkit"] as const).flatMap((browserName) =>
    [390, 768, 1024, 1440, 1920, 2560].flatMap((width) =>
      [false, true].map((brokerAuth) => ({
        name: `${brokerAuth ? "broker-auth-" : ""}${browserName}-${width}`,
        ...(brokerAuth
          ? { testMatch: "**/broker-auth.spec.ts" }
          : { testIgnore: "**/broker-auth.spec.ts" }),
        use: {
          browserName,
          baseURL: `http://127.0.0.1:${3100 + (browserName === "webkit" ? 1 : 0) + (brokerAuth ? 2 : 0)}`,
          viewport: { width, height: width < 768 ? 844 : 1080 },
          isMobile: width < 768,
          hasTouch: width <= 1024,
        },
      })),
    ),
  ),
  // Each engine/suite owns a DB and unchanged production login budget.
  // Auth coverage must not consume the frozen shell suite's per-peer budget.
  webServer: [0, 1, 2, 3].flatMap((index) => [
    {
      command: `node tests/browser/auth-test-server.mjs ${8100 + index} ${3100 + index}`,
      url: `http://127.0.0.1:${8100 + index}/health`,
      reuseExistingServer: false,
    },
    {
      command: `TWF_API_ORIGIN=http://127.0.0.1:${8100 + index} npm run start -- --hostname 127.0.0.1 --port ${3100 + index}`,
      url: `http://127.0.0.1:${3100 + index}`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ]),
});
