import { defineConfig, devices } from "@playwright/test";

const PORT = 3100;
const baseURL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chrome",
      // The installed Google Chrome: nothing is downloaded.
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
  ],
  // The static export served like S3 (next start cannot serve an export).
  // `npm run test:e2e` builds out/ first.
  webServer: {
    command: `node e2e/static-server.mjs out ${PORT}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
