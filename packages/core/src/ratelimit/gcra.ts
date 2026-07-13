import { redis } from "../redis.js";

/**
 * GCRA (Generic Cell Rate Algorithm) — atomic token-bucket rate limiting.
 * One Redis round-trip, no check-then-increment race, smooth sustained rate +
 * burst capacity, exact retry-after. `cost` lets one script serve both RPM
 * (cost = 1) and TPM (cost = tokens).
 *
 * State per key = TAT (theoretical arrival time, ms). A request of `cost` units
 * advances TAT by cost·T; it is admitted iff the new TAT is within τ of now.
 * Capacity ≈ τ/T; sustained rate = 1 unit per T.
 *
 * Oversized requests (cost·T > τ, i.e. cost > burst capacity) can never fit the
 * standard admission test, which would otherwise 429 them forever. They are
 * admitted iff the bucket is idle (TAT ≤ now) and then push TAT to now + cost·T,
 * so the debt drains before anything else is admitted. While backlogged they get
 * retryAfter = TAT - now (time until the bucket is idle again).
 */
export const GCRA_LUA = `
local now = tonumber(ARGV[1])
local T   = tonumber(ARGV[2])
local tau = tonumber(ARGV[3])
local cost= tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])
local incr = T * cost
local tat = redis.call('GET', KEYS[1])
if tat then tat = tonumber(tat) else tat = now end
if tat < now then tat = now end
if incr > tau then
  -- oversized: admit only on an idle bucket, no clamping of the debt
  if tat > now then
    return {0, math.floor(tat - now), 0, math.floor(tat - now)}
  end
  local new_tat = now + incr
  local px = math.max(ttl, math.ceil(new_tat - now) + 1000)
  redis.call('SET', KEYS[1], new_tat, 'PX', px)
  return {1, 0, 0, math.floor(new_tat - now)}
end
local new_tat = tat + incr
local allow_at = new_tat - tau
if allow_at > now then
  return {0, math.floor(allow_at - now), 0, math.floor(tat - now)}
end
local px = math.max(ttl, math.ceil(new_tat - now) + 1000)
redis.call('SET', KEYS[1], new_tat, 'PX', px)
local backlog = new_tat - now
local remaining = math.floor((tau - backlog) / T)
if remaining < 0 then remaining = 0 end
return {1, 0, remaining, math.floor(backlog)}
`;

/**
 * Refund `delta` units into a GCRA bucket (actual usage < estimate):
 * TAT = max(now, TAT - delta·T). Preserves the key's remaining TTL.
 */
export const GCRA_REFUND_LUA = `
local now   = tonumber(ARGV[1])
local T     = tonumber(ARGV[2])
local delta = tonumber(ARGV[3])
local ttl   = tonumber(ARGV[4])
local tat = redis.call('GET', KEYS[1])
if not tat then return 0 end
tat = tonumber(tat)
local new_tat = tat - (delta * T)
if new_tat < now then new_tat = now end
local px = redis.call('PTTL', KEYS[1])
if not px or px <= 0 then px = ttl end
redis.call('SET', KEYS[1], new_tat, 'PX', px)
return 1
`;

type GcraCall = (
  key: string,
  now: number,
  T: number,
  tau: number,
  cost: number,
  ttl: number,
) => Promise<[number, number, number, number]>;

type GcraRefundCall = (
  key: string,
  now: number,
  T: number,
  delta: number,
  ttl: number,
) => Promise<number>;

type ScriptClient = {
  defineCommand: (name: string, opts: { numberOfKeys: number; lua: string }) => void;
};

export type GcraResult = {
  allowed: boolean;
  retryAfterMs: number;
  remaining: number;
  resetMs: number;
};

export type GcraOpts = {
  limit: number; // units per period
  periodMs?: number; // default 60_000 (per minute)
  cost?: number; // default 1
  burstCapacity?: number; // token-bucket capacity; default = limit
};

export type GcraRefundOpts = {
  limit: number; // units per period (defines the emission interval)
  periodMs?: number; // default 60_000
  delta: number; // units to give back (positive)
};

export type BoundGcra = {
  gcra: (key: string, opts: GcraOpts) => Promise<GcraResult>;
  gcraRefund: (key: string, opts: GcraRefundOpts) => Promise<void>;
};

function derive(limit: number, periodMs: number, burstCapacity?: number) {
  const T = periodMs / limit; // emission interval
  const tau = T * (burstCapacity ?? limit); // tolerance → burst capacity
  const ttl = Math.ceil(tau) + periodMs;
  return { T, tau, ttl };
}

/**
 * Register the GCRA scripts on an ioredis-compatible client and return bound
 * callables. The module-level `gcra`/`gcraRefund` use the singleton client;
 * tests bind their own (e.g. ioredis-mock).
 */
export function bindGcra(client: unknown): BoundGcra {
  const c = client as ScriptClient & Record<string, unknown>;
  if (typeof c.gcra !== "function") {
    c.defineCommand("gcra", { numberOfKeys: 1, lua: GCRA_LUA });
  }
  if (typeof c.gcraRefund !== "function") {
    c.defineCommand("gcraRefund", { numberOfKeys: 1, lua: GCRA_REFUND_LUA });
  }
  const call = (c as unknown as { gcra: GcraCall }).gcra.bind(c);
  const callRefund = (
    c as unknown as { gcraRefund: GcraRefundCall }
  ).gcraRefund.bind(c);

  return {
    async gcra(key, opts) {
      const periodMs = opts.periodMs ?? 60_000;
      const cost = opts.cost ?? 1;
      const { T, tau, ttl } = derive(opts.limit, periodMs, opts.burstCapacity);
      const now = Date.now();
      const [allowed, retryAfterMs, remaining, resetMs] = await call(
        key,
        now,
        T,
        tau,
        cost,
        ttl,
      );
      return {
        allowed: allowed === 1,
        retryAfterMs,
        remaining,
        resetMs,
      };
    },
    async gcraRefund(key, opts) {
      const periodMs = opts.periodMs ?? 60_000;
      if (opts.delta <= 0) return;
      const { T, ttl } = derive(opts.limit, periodMs);
      await callRefund(key, Date.now(), T, opts.delta, ttl);
    },
  };
}

const bound = bindGcra(redis);

/** Consume `cost` units against a GCRA bucket. */
export const gcra = bound.gcra;

/** Give back over-estimated units: TAT = max(now, TAT - delta·T). */
export const gcraRefund = bound.gcraRefund;

/** Namespaced rate-limit key: rl:{scope}:{scopeId}:{unit}. */
export function rlKey(scope: string, scopeId: string, unit: string): string {
  return `rl:${scope}:${scopeId}:${unit}`;
}
