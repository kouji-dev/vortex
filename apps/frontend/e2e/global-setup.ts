/**
 * Global setup: nothing to wait for.
 *
 * Frontend E2E mocks the entire backend API at the browser
 * (see `e2e/support/api-mock.ts`), so there is no backend to health-check —
 * only the Vite dev server (started by playwright.config `webServer`) is needed.
 */
export default async function globalSetup() {
  // intentionally empty — no backend dependency
}
