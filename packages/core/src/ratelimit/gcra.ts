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
 */
const GCRA_LUA = `
local now = tonumber(ARGV[1])
local T   = tonumber(ARGV[2])
local tau = tonumber(ARGV[3])
local cost= tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])
local incr = T * cost
local tat = redis.call('GET', KEYS[1])
if tat then tat = tonumber(tat) else tat = now end
if tat < now then tat = now end
local new_tat = tat + incr
local allow_at = new_tat - tau
if allow_at > now then
  return {0, math.floor(allow_at - now), 0, math.floor(tat - now)}
end
redis.call('SET', KEYS[1], new_tat, 'PX', ttl)
local backlog = new_tat - now
local remaining = math.floor((tau - backlog) / T)
if remaining < 0 then remaining = 0 end
return {1, 0, remaining, math.floor(backlog)}
`;

type GcraCall = (
  key: string,
  now: number,
  T: number,
  tau: number,
  cost: number,
  ttl: number,
) => Promise<[number, number, number, number]>;

// Register the script once on the singleton client.
(redis as unknown as { defineCommand: (n: string, o: object) => void }).defineCommand(
  "gcra",
  { numberOfKeys: 1, lua: GCRA_LUA },
);
const call = (redis as unknown as { gcra: GcraCall }).gcra.bind(redis);

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

/** Consume `cost` units against a GCRA bucket. */
export async function gcra(key: string, opts: GcraOpts): Promise<GcraResult> {
  const periodMs = opts.periodMs ?? 60_000;
  const cost = opts.cost ?? 1;
  const capacity = opts.burstCapacity ?? opts.limit;
  const T = periodMs / opts.limit; // emission interval
  const tau = T * capacity; // tolerance → burst capacity
  const ttl = Math.ceil(tau) + periodMs;
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
}

/** Namespaced rate-limit key: rl:{scope}:{scopeId}:{unit}. */
export function rlKey(scope: string, scopeId: string, unit: string): string {
  return `rl:${scope}:${scopeId}:${unit}`;
}
