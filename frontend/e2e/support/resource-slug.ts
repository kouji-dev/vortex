/**
 * Stable, human-readable labels for E2E resources (KBs, conversations) keyed by test title.
 * Bounded cardinality: one row per test, reused across runs until purged — avoids timestamp spam.
 */
export function e2eStableResourceName(prefix: string, testTitle: string): string {
  const slug = testTitle
    .replace(/[^a-zA-Z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ')
    .slice(0, 72)
  return `${prefix}: ${slug || 'test'}`
}
