import { Redis } from "ioredis";
import { env } from "./config/env.js";

// Singleton ioredis client for the whole process.
export const redis = new Redis(env.REDIS_URL, {
  maxRetriesPerRequest: null,
});

/**
 * Org-scoped monthly spend counter key for a budget pool.
 * `scope` is "member" | "team" | "org"; `month` is a period token, e.g. "2026-07".
 */
export function budgetKey(
  orgId: string,
  scope: "member" | "team" | "org",
  scopeId: string,
  month: string,
): string {
  return `spend:${orgId}:${scope}:${scopeId}:${month}`;
}
