/**
 * Purge all application data from the E2E database after the test run.
 * Truncates every table except alembic_version and catalog_models so the
 * next run starts clean while keeping the schema and static seed data.
 */
export default async function globalTeardown() {
  const apiBase = (process.env.E2E_API_URL ?? 'http://127.0.0.1:8001').replace(/\/$/, '')
  try {
    const res = await fetch(`${apiBase}/api/e2e/purge`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${process.env.E2E_BEARER_TOKEN ?? 'devtoken'}` },
    })
    if (res.ok) {
      console.log('\n✔ E2E database purged.')
    } else {
      console.warn(`\n⚠ E2E purge returned ${res.status} — skipped.`)
    }
  } catch {
    console.warn('\n⚠ E2E purge skipped (backend not reachable).')
  }
}
