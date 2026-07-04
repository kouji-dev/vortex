import { drizzle } from "drizzle-orm/postgres-js";
import { sql } from "drizzle-orm";
import postgres from "postgres";
import * as schema from "./schema.js";

export type DbSchema = typeof schema;

// the app connects as the NON-superuser role so RLS applies (see drizzle/rls.sql)
const url =
  process.env.APP_DATABASE_URL ??
  process.env.DATABASE_URL ??
  "postgres://vortex_app:vortex_app@localhost:5433/vortex";

// single pooled connection; RLS is enforced via per-transaction session vars
export const queryClient = postgres(url, { max: 10 });
export const db = drizzle(queryClient, { schema, casing: "snake_case" });

export type Db = typeof db;
export type Tx = Parameters<Parameters<Db["transaction"]>[0]>[0];

/**
 * Run tenant-scoped work: sets `app.current_org` for the transaction so Postgres
 * RLS policies filter every row to this org. Use for ALL tenant request handling.
 */
export async function withOrg<T>(
  orgId: string,
  cb: (tx: Tx) => Promise<T>,
): Promise<T> {
  return db.transaction(async (tx) => {
    await tx.execute(sql`select set_config('app.current_org', ${orgId}, true)`);
    return cb(tx);
  });
}

/**
 * Run cross-tenant / provisioning / platform work that must bypass RLS.
 * Only for auth, org provisioning, and the platform super-admin surface.
 */
export async function withBypass<T>(cb: (tx: Tx) => Promise<T>): Promise<T> {
  return db.transaction(async (tx) => {
    await tx.execute(sql`select set_config('app.bypass_rls', 'on', true)`);
    return cb(tx);
  });
}
