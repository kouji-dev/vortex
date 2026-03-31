import { defineConfig, devices } from '@playwright/test'

// E2E backend runs on a dedicated port so tests never touch the dev database.
// Start it with:  ./scripts/e2e-up.sh   (from the repo root)
const E2E_API_URL = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
const E2E_BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:5174'

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  globalSetup: './e2e/global-setup.ts',
  globalTeardown: './e2e/global-teardown.ts',
  use: {
    baseURL: E2E_BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // Start the Vite dev server on port 5174 (separate from the normal dev port 5173)
  // so E2E tests always hit the E2E backend and never reuse a dev server
  // that proxies to the wrong database.
  // Set E2E_BASE_URL to an already-running server on 5174 to skip this.
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: 'pnpm dev --port 5174',
        url: 'http://localhost:5174',
        reuseExistingServer: false,
        timeout: 60_000,
        env: {
          VITE_DEV_API_PROXY_TARGET: E2E_API_URL,
        },
      },
})
