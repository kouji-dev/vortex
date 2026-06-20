/**
 * Global teardown: nothing to clean up.
 *
 * Frontend E2E uses an in-browser API mock — no backend, no E2E database — so
 * there is nothing to drop. (The store is per-page and disposed with the test.)
 */
export default async function globalTeardown() {
  // intentionally empty — no backend / DB to tear down
}
