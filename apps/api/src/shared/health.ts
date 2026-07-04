import { Hono } from "hono";
import { sql } from "drizzle-orm";
import { db } from "@vortex/db";
import { env, redis } from "@vortex/core";

export const health = new Hono();

health.get("/", async (c) => {
  const checks: Record<string, "ok" | "down"> = { db: "down", redis: "down" };
  try {
    await db.execute(sql`select 1`);
    checks.db = "ok";
  } catch {
    /* down */
  }
  try {
    await redis.ping();
    checks.redis = "ok";
  } catch {
    /* down */
  }
  const ok = Object.values(checks).every((v) => v === "ok");
  return c.json(
    { status: ok ? "ok" : "degraded", tenancyMode: env.TENANCY_MODE, checks },
    ok ? 200 : 503,
  );
});
