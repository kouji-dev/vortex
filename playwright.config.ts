import { defineConfig } from "@playwright/test";

// Spins up the mock provider + the API (gateway pointed at the mock), then runs
// the API/gateway E2E suite. `pnpm test:e2e`.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  webServer: [
    {
      command: "node e2e/mock-provider.mjs",
      url: "http://localhost:9099/models",
      reuseExistingServer: true,
      timeout: 20_000,
    },
    {
      command: "node --import tsx apps/api/src/server.ts",
      url: "http://localhost:8080/health",
      reuseExistingServer: true,
      timeout: 40_000,
      env: {
        OPENAI_BASE_URL: "http://localhost:9099",
        OPENAI_API_KEY: "test-mock",
        TENANCY_MODE: "single",
      },
    },
  ],
});
