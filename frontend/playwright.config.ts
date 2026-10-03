import { defineConfig } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// A new private directory per test invocation; never use the everyday database.
const database = join(mkdtempSync(join(tmpdir(), "yanji-e2e-")), "e2e.sqlite3");
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30000,
  expect: { timeout: 7000 },
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { browserName: "chromium", viewport: { width: 1440, height: 1000 } },
    },
    {
      name: "mobile",
      use: {
        browserName: "chromium",
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: [
    {
      command:
        "../backend/.venv/bin/python ../backend/tests/mock_model_server.py --port 8099",
      url: "http://127.0.0.1:8099",
      reuseExistingServer: false,
    },
    {
      command: "../backend/.venv/bin/python ../backend/run.py",
      url: "http://127.0.0.1:8001/api/v1/health/ready",
      reuseExistingServer: false,
      env: {
        EDUTOY_DB_PATH: database,
        EDUTOY_AI_KEY_PATH: database + ".key",
        EDUTOY_PORT: "8001",
        EDUTOY_ORIGINS: "http://127.0.0.1:5174",
      },
    },
    {
      command: "npm run dev -- --port 5174 --strictPort",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
      env: { EDUTOY_API_TARGET: "http://127.0.0.1:8001" },
    },
  ],
});
