/**
 * Global teardown runs after the full E2E suite.
 * Tests use unique timestamped names for isolation — no database purge needed.
 */
export default async function globalTeardown() {
  // No-op: E2E tests are isolated by unique names (e.g. `E2E Isolated ${Date.now()}`).
  // Do not add API-based purge or seed calls here — E2E interactions must go through the UI.
}
