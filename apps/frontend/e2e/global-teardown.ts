import { execSync } from 'child_process'

/**
 * Global teardown: drop the E2E database after the full suite finishes.
 * The next `e2e-up.sh` run will recreate it, run migrations, and seed it fresh.
 */
export default async function globalTeardown() {
  const worktreeName = process.env.WORKTREE_NAME ?? ''
  const e2eDbName = process.env.E2E_DB_NAME ?? 'ai_portal_e2e'
  const container = worktreeName
    ? `local-e2e-ai-portal-db-${worktreeName}`
    : 'local-e2e-ai-portal-db'

  console.log(`\n▶ E2E teardown: dropping database '${e2eDbName}'`)
  try {
    // Terminate active backend connections so DROP DATABASE can proceed
    execSync(
      `docker exec ${container} psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${e2eDbName}' AND pid <> pg_backend_pid();" postgres`,
      { stdio: 'pipe' },
    )
    execSync(
      `docker exec ${container} psql -U postgres -c "DROP DATABASE IF EXISTS \\"${e2eDbName}\\";" postgres`,
      { stdio: 'inherit' },
    )
    console.log(`   Database '${e2eDbName}' dropped.`)
  } catch (e) {
    // Non-fatal — the next e2e-up.sh run will reset the DB anyway
    console.warn(
      `   Warning: E2E DB teardown failed (will be reset on next e2e-up.sh):`,
      (e as Error).message,
    )
  }
}
