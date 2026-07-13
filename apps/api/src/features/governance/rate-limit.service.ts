import { gcra, gcraRefund, rlKey, redis, env } from "@vortex/core";
import { resolveEntitlements } from "../../shared/entitlements.js";

export class RateLimitExceededError extends Error {
  dimension: "rpm" | "tpm" | "concurrency";
  /** Which bucket denied: plan/org-wide or the per-key custom limit. */
  scope: "org" | "key";
  retryAfterMs: number;
  limit: number;
  remaining: number;
  resetMs: number;
  constructor(a: {
    dimension: "rpm" | "tpm" | "concurrency";
    scope: "org" | "key";
    retryAfterMs: number;
    limit: number;
    remaining?: number;
    resetMs?: number;
  }) {
    super(`rate limit exceeded: ${a.dimension} (${a.scope})`);
    this.name = "RateLimitExceededError";
    this.dimension = a.dimension;
    this.scope = a.scope;
    this.retryAfterMs = a.retryAfterMs;
    this.limit = a.limit;
    this.remaining = a.remaining ?? 0;
    this.resetMs = a.resetMs ?? a.retryAfterMs;
  }
}

/** IETF-style headers describing the constraining (RPM) bucket. */
export type LimitHeaders = {
  limit: number;
  remaining: number;
  resetSec: number;
};

/**
 * Pre-request rate check. Plan entitlements (ent.rpm / ent.tpm) are org-wide
 * buckets (rl:org:{orgId}:rpm|tpm); a per-key custom RPM (keyRpm) is a separate
 * bucket (rl:key:{apiKeyId}:rpm). Org buckets are checked first. Throws
 * RateLimitExceededError (carrying bucket scope + remaining/reset) on the first
 * denied bucket. Returns headers for the most constrained RPM bucket checked.
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
  const minRpm = [ent.rpm, a.keyRpm].reduce<number | null>(
    (m, v) => (typeof v === "number" ? (m == null ? v : Math.min(m, v)) : m),
    null,
  );
  let headers: LimitHeaders = { limit: minRpm ?? 0, remaining: 0, resetSec: 0 };

  try {
    // 1) org-wide plan RPM
    if (ent.rpm != null) {
      const r = await gcra(rlKey("org", a.orgId, "rpm"), { limit: ent.rpm });
      headers = {
        limit: ent.rpm,
        remaining: r.remaining,
        resetSec: Math.ceil(r.resetMs / 1000),
      };
      if (!r.allowed)
        throw new RateLimitExceededError({
          dimension: "rpm",
          scope: "org",
          retryAfterMs: r.retryAfterMs,
          limit: ent.rpm,
          remaining: r.remaining,
          resetMs: r.resetMs,
        });
    }
    // 2) org-wide plan TPM (cost = estimated tokens)
    if (ent.tpm != null && a.estTokens > 0) {
      const r = await gcra(rlKey("org", a.orgId, "tpm"), {
        limit: ent.tpm,
        cost: a.estTokens,
      });
      if (!r.allowed)
        throw new RateLimitExceededError({
          dimension: "tpm",
          scope: "org",
          retryAfterMs: r.retryAfterMs,
          limit: ent.tpm,
          remaining: r.remaining,
          resetMs: r.resetMs,
        });
    }
    // 3) per-key custom RPM (separate bucket, checked after the org)
    if (a.keyRpm != null) {
      const r = await gcra(rlKey("key", a.apiKeyId, "rpm"), { limit: a.keyRpm });
      // Report the more constrained RPM bucket in success headers.
      if (ent.rpm == null || r.remaining < headers.remaining) {
        headers = {
          limit: a.keyRpm,
          remaining: r.remaining,
          resetSec: Math.ceil(r.resetMs / 1000),
        };
      }
      if (!r.allowed)
        throw new RateLimitExceededError({
          dimension: "rpm",
          scope: "key",
          retryAfterMs: r.retryAfterMs,
          limit: a.keyRpm,
          remaining: r.remaining,
          resetMs: r.resetMs,
        });
    }
  } catch (e) {
    if (e instanceof RateLimitExceededError) throw e;
    // Redis/GCRA failure → fail open (or closed) per config.
    if (!env.RATE_LIMIT_FAIL_OPEN) {
      throw new RateLimitExceededError({
        dimension: "rpm",
        scope: "org",
        retryAfterMs: 1000,
        limit: minRpm ?? 0,
      });
    }
  }
  return headers;
}

/**
 * Reconcile the actual-vs-estimate token delta into the org-wide TPM bucket.
 * Under-estimate (delta > 0) consumes the difference; over-estimate (delta < 0)
 * refunds it (TAT moves back toward now).
 */
export async function commitTokenDelta(a: {
  orgId: string;
  apiKeyId: string;
  estTokens: number;
  actualTokens: number;
}): Promise<void> {
  const ent = await resolveEntitlements(a.orgId);
  if (ent.tpm == null) return;
  const delta = a.actualTokens - a.estTokens;
  if (delta === 0) return;
  const key = rlKey("org", a.orgId, "tpm");
  try {
    if (delta > 0) {
      await gcra(key, { limit: ent.tpm, cost: delta });
    } else {
      await gcraRefund(key, { limit: ent.tpm, delta: -delta });
    }
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
    // INCR + EXPIRE in one round-trip.
    const res = await redis.multi().incr(key).expire(key, 300).exec();
    const n = Number(res?.[0]?.[1] ?? 0); // safety net against leaked slots
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
