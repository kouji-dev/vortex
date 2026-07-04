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
    await sql`delete from memberships where type = 'human'`;
    await sql`delete from sessions`;
    await sql`delete from accounts`;
    await sql`delete from users`;
  } finally {
    await sql.end();
  }
}
