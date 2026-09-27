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
    [390, 768, 1024, 1440, 1920, 2560].map((width) => ({
      name: `${browserName}-${width}`,
      use: {
        browserName,
        viewport: { width, height: width < 768 ? 844 : 1080 },
        isMobile: width < 768,
        hasTouch: width <= 1024,
      },
    })),
  ),
  webServer: [
    {
      command: "node tests/browser/auth-test-server.mjs",
      url: "http://127.0.0.1:8100/health",
      reuseExistingServer: false,
    },
    {
      command:
        "TWF_API_ORIGIN=http://127.0.0.1:8100 npm run start -- --hostname 127.0.0.1 --port 3100",
      url: "http://127.0.0.1:3100",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
