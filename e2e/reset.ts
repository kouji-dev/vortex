import postgres from "postgres";
import Redis from "ioredis";

// Owner connection (bypasses RLS) — clears human members + their keys/usage so
// each test's first signup provisions as owner of the seeded single org.
const URL =
  process.env.DATABASE_URL ?? "postgres://vortex:vortex@localhost:5433/vortex";
const REDIS_URL = process.env.REDIS_URL ?? "redis://localhost:6380";

export async function resetTenants(): Promise<void> {
  const sql = postgres(URL, { max: 1 });
  try {
    // orgs created by multi-tenant (billing) tests — keep only the oldest org,
    // the one the single-tenant server bound to at boot (cascades wipe their
    // teams/members/keys/wallets/subscriptions).
    await sql`delete from organizations where id not in (select id from organizations order by created_at asc limit 1)`;
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
    // billing plane state (multi-server tests)
    await sql`delete from stripe_events`;
    await sql`delete from failed_billing_events`;
    await sql`delete from managed_provider_keys`;
    await sql`delete from provider_credentials`;
    await sql`delete from subscriptions`;
    await sql`delete from credit_ledger`;
    await sql`delete from credit_wallets`;
    await sql`update plans set stripe_price_id = null`;
    // teams created by tests: keep only the seeded (oldest) team per org and
    // restore its defaults (tests rename it / tweak budgets)
    await sql`delete from teams where id not in (select distinct on (org_id) id from teams order by org_id, created_at asc, id asc)`;
    await sql`update teams set name = 'Default', budget_micro = null, budget_enforcement = 'hard', default_member_budget_micro = 500000000`;
    // reset org to defaults (Free plan, BYOK) so entitlements resolve cleanly
    await sql`update organizations set plan_id = null, key_mode = 'byok', markup_bps = 0, status = 'active'`;
  } finally {
    await sql.end();
  }
}

/**
 * Flush Redis so rate-limit buckets, budget pools and credit holds never leak
 * between tests (single-tenant tests reuse one org, so buckets WOULD leak).
 */
export async function resetRedis(): Promise<void> {
  const redis = new Redis(REDIS_URL, { lazyConnect: true });
  try {
    await redis.connect();
    await redis.flushall();
  } finally {
    redis.disconnect();
  }
}

/** Standard per-test reset: tenant tables + Redis buckets. */
export async function resetAll(): Promise<void> {
  await resetTenants();
  await resetRedis();
}
