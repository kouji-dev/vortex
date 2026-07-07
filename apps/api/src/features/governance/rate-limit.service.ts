import { gcra, rlKey, redis, env } from "@vortex/core";
import { resolveEntitlements } from "../../shared/entitlements.js";

export class RateLimitExceededError extends Error {
  dimension: "rpm" | "tpm" | "concurrency";
  retryAfterMs: number;
  limit: number;
  constructor(
    dimension: "rpm" | "tpm" | "concurrency",
    retryAfterMs: number,
    limit: number,
  ) {
    super(`rate limit exceeded: ${dimension}`);
    this.name = "RateLimitExceededError";
    this.dimension = dimension;
    this.retryAfterMs = retryAfterMs;
    this.limit = limit;
  }
}

/** IETF-style headers describing the constraining (RPM) bucket. */
export type LimitHeaders = {
  limit: number;
  remaining: number;
  resetSec: number;
};

/** Smallest of the defined values (null = unlimited on that axis). */
function minDefined(...vals: (number | null | undefined)[]): number | null {
  const nums = vals.filter((v): v is number => typeof v === "number");
  return nums.length ? Math.min(...nums) : null;
}

/**
 * Pre-request rate check. Enforces RPM (cost 1) and TPM (cost = estimated
 * tokens) as GCRA buckets, most-restrictive of {plan entitlement, key custom}.
 * Throws RateLimitExceededError on the first denied bucket.
 * Returns headers for the RPM bucket (or a no-limit sentinel).
 *
 * Fail-open: on a Redis error the request is allowed (RATE_LIMIT_FAIL_OPEN).
 */
export async function checkRateLimits(a: {
  orgId: string;
  apiKeyId: string;
  keyRpm: number | null;
  estTokens: number;
}): Promise<LimitHeaders> {
  const ent = await resolveEntitlements(a.orgId);
  const rpm = minDefined(ent.rpm, a.keyRpm);
  let headers: LimitHeaders = { limit: rpm ?? 0, remaining: 0, resetSec: 0 };

  try {
    if (rpm != null) {
      const r = await gcra(rlKey("key", a.apiKeyId, "rpm"), { limit: rpm });
      headers = {
        limit: rpm,
        remaining: r.remaining,
        resetSec: Math.ceil(r.resetMs / 1000),
      };
      if (!r.allowed) throw new RateLimitExceededError("rpm", r.retryAfterMs, rpm);
    }
    if (ent.tpm != null && a.estTokens > 0) {
      const r = await gcra(rlKey("key", a.apiKeyId, "tpm"), {
        limit: ent.tpm,
        cost: a.estTokens,
      });
      if (!r.allowed) throw new RateLimitExceededError("tpm", r.retryAfterMs, ent.tpm);
    }
  } catch (e) {
    if (e instanceof RateLimitExceededError) throw e;
    // Redis/GCRA failure → fail open (or closed) per config.
    if (!env.RATE_LIMIT_FAIL_OPEN) {
      throw new RateLimitExceededError("rpm", 1000, rpm ?? 0);
    }
  }
  return headers;
}

/** Reconcile the actual-vs-estimate token delta into the TPM bucket. */
export async function commitTokenDelta(a: {
  orgId: string;
  apiKeyId: string;
  estTokens: number;
  actualTokens: number;
}): Promise<void> {
  const ent = await resolveEntitlements(a.orgId);
  if (ent.tpm == null) return;
  const delta = a.actualTokens - a.estTokens;
  if (delta <= 0) return; // conservative: never refund
  try {
    await gcra(rlKey("key", a.apiKeyId, "tpm"), {
      limit: ent.tpm,
      cost: delta,
    });
  } catch {
    /* best-effort */
  }
}

export type ConcurrencySlot = { ok: boolean; release: () => Promise<void> };

/** Acquire one in-flight slot; release() on completion (idempotent). */
export async function acquireConcurrency(
  orgId: string,
  apiKeyId: string,
): Promise<ConcurrencySlot> {
  const ent = await resolveEntitlements(orgId);
  if (ent.concurrency == null) return { ok: true, release: async () => {} };
  const key = rlKey("key", apiKeyId, "conc");
  try {
    const n = await redis.incr(key);
    await redis.expire(key, 300); // safety net against leaked slots
    if (n > ent.concurrency) {
      await redis.decr(key);
      return { ok: false, release: async () => {} };
    }
    let released = false;
    return {
      ok: true,
      release: async () => {
        if (released) return;
        released = true;
        await redis.decr(key).catch(() => {});
      },
    };
  } catch {
    // fail open on Redis error
    return { ok: true, release: async () => {} };
  }
}
