import { defineConfig, devices } from '@playwright/test'

// E2E backend runs on a dedicated port so tests never touch the dev database.
// Start it with:  ./scripts/e2e-up.sh   (from the repo root)
// global-setup rejects E2E_API_URL on port 8000 unless E2E_ALLOW_DEV_API_URL=1.
const E2E_API_PORT = process.env.E2E_API_PORT ?? '8001'
const E2E_FRONTEND_PORT = process.env.E2E_FRONTEND_PORT ?? '5175'
const E2E_API_URL = process.env.E2E_API_URL ?? `http://127.0.0.1:${E2E_API_PORT}`
const E2E_BASE_URL = process.env.E2E_BASE_URL ?? `http://localhost:${E2E_FRONTEND_PORT}`

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // Shared E2E DB + purge hooks: parallel workers race (e.g. memories purge vs sidebar lists).
  // Ingest/chat also hit remote APIs; keep load low.
  // Workers capped at 2 (per user) to limit CPU during E2E runs.
  retries: 0,
  workers: 2,
  globalSetup: './e2e/global-setup.ts',
  globalTeardown: './e2e/global-teardown.ts',
  use: {
    baseURL: E2E_BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // Start Vite on 5175 via scripts/e2e-vite.mjs so `VITE_DEV_API_PROXY_TARGET` is set reliably
  // (Windows often drops env through `pnpm dev`). Do not reuse 5173/5174 dev servers — they
  // may proxy to the wrong API port.
  // Set E2E_BASE_URL to skip webServer (you must point that server at E2E_API_URL yourself).
  // Two local node processes, no backend/DB/Docker:
  //  1. mock-server.mjs — in-memory fake backend (SSR + client both hit it).
  //  2. e2e-vite.mjs    — the Vite SSR dev server, proxying /api → the mock.
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : [
        {
          command: 'node ./e2e/support/mock-server.mjs',
          url: `${E2E_API_URL}/health`,
          reuseExistingServer: false,
          timeout: 30_000,
          env: { MOCK_PORT: E2E_API_PORT },
        },
        {
          command: 'node ./scripts/e2e-vite.mjs',
          url: 'http://localhost:5175',
          reuseExistingServer: false,
          timeout: 120_000,
          env: {
            E2E_API_URL,
            VITE_AUTH_MODE: 'dev',
            VITE_DEV_BEARER_TOKEN: process.env.VITE_DEV_BEARER_TOKEN ?? 'devtoken',
          },
        },
      ],
})
