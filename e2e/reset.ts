import postgres from "postgres";

// Owner connection (bypasses RLS) — clears human members + their keys/usage so
// each test's first signup provisions as owner of the seeded single org.
const URL =
  process.env.DATABASE_URL ?? "postgres://vortex:vortex@localhost:5433/vortex";

export async function resetTenants(): Promise<void> {
  const sql = postgres(URL, { max: 1 });
  try {
    await sql`delete from usage_records`;
    await sql`delete from api_keys`;
    await sql`delete from audit_logs`;
    await sql`delete from app_access`;
    // service accounts + their apps created during a test (keep seeded system app)
    await sql`delete from apps where kind = 'service'`;
    await sql`delete from memberships where type = 'human'`;
    await sql`delete from memberships where type = 'technical' and id not in (select technical_member_id from apps where technical_member_id is not null)`;
    await sql`delete from sessions`;
    await sql`delete from accounts`;
    await sql`delete from users`;
    // clear any team-budget override a prior test left behind
    await sql`update teams set budget_micro = null`;
    // reset org to defaults (Free plan, BYOK) so entitlements resolve cleanly
    await sql`update organizations set plan_id = null, key_mode = 'byok', markup_bps = 0`;
  } finally {
    await sql.end();
  }
}
