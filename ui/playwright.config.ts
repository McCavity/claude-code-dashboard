import { defineConfig } from "@playwright/test";

const PORT = process.env.CC_E2E_PORT ?? "8765";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  // We expect the dashboard server to already be running when these
  // tests execute (e.g. via `cc start`). Tests assert against the live
  // SQLite DB so an empty environment is fine — empty states are part
  // of what we verify.
});
