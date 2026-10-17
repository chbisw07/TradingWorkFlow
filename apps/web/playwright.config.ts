import { defineConfig } from "@playwright/test";

const browserEnvironment = { ...process.env };

// VS Code's Snap launcher points GIO at modules built against the core20
// runtime. Playwright WebKit then loads that older glibc in its network
// process and fails every navigation before application code runs.
delete browserEnvironment.GIO_MODULE_DIR;

export default defineConfig({
  testDir: "./tests/browser",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 2,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3100",
    launchOptions: { env: browserEnvironment },
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
      url: "http://127.0.0.1:8100/ready",
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
