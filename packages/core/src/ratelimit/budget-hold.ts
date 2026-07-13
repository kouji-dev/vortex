import { redis } from "../redis.js";

/**
 * Budget hold/settle — atomic reserve-then-settle spend accounting in Redis.
 *
 * RESERVE (pre-request): checks `spent + held + estimate` against up to three
 * budget caps (member / team / org) plus an optional credit-balance slot, all
 * in ONE Lua round-trip — no check-then-increment race between concurrent
 * requests. On success it records the estimate as a *hold* (`<pool>:held`) and
 * remembers the per-request estimate under `hold:{requestId}`.
 *
 * SETTLE (post-response): releases the hold (DECRBY `:held` by the reserved
 * estimate) and commits the *actual* cost to the spend pools (INCRBY).
 *
 * Holds self-expire after HOLD_TTL_SEC so a crashed request can only inflate
 * the held counter for a bounded window; the reconcile job remains the
 * authority for the spend pools themselves.
 */

const HOLD_TTL_SEC = 600; // orphaned holds evaporate after 10 min
const POOL_TTL_SEC = 60 * 60 * 24 * 40; // ~40d self-clean; reconcile is authoritative

// KEYS: [1]=member pool, [2]=team pool, [3]=org pool ('' = level absent),
//       [4]=credit key ('' = no credit slot), [5]=hold:{requestId}
// ARGV: [1]=estimate, [2]=hold ttl sec, [3..5]=member/team/org limit (-1 = no cap),
//       [6]=credit balance (-1 = no credit slot)
// Returns {1, 0} on success, {0, scopeIndex} on denial (1=member 2=team 3=org 4=credit).
const RESERVE_LUA = `
local est = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local credit = tonumber(ARGV[6])
for i = 1, 3 do
  local limit = tonumber(ARGV[i + 2])
  if KEYS[i] ~= '' and limit >= 0 then
    local spent = tonumber(redis.call('GET', KEYS[i]) or '0')
    local held = tonumber(redis.call('GET', KEYS[i] .. ':held') or '0')
    if spent + held + est > limit then
      return {0, i}
    end
  end
end
if KEYS[4] ~= '' and credit >= 0 then
  local held = tonumber(redis.call('GET', KEYS[4] .. ':held') or '0')
  if held + est > credit then
    return {0, 4}
  end
end
for i = 1, 3 do
  if KEYS[i] ~= '' then
    redis.call('INCRBY', KEYS[i] .. ':held', est)
    redis.call('EXPIRE', KEYS[i] .. ':held', ttl)
  end
end
if KEYS[4] ~= '' then
  redis.call('INCRBY', KEYS[4] .. ':held', est)
  redis.call('EXPIRE', KEYS[4] .. ':held', ttl)
end
redis.call('SET', KEYS[5], est, 'EX', ttl)
return {1, 0}
`;

// KEYS: same layout as RESERVE. ARGV: [1]=actual cost, [2]=pool ttl sec.
// Releases the hold (if still present) and commits actual spend to the pools.
const SETTLE_LUA = `
local actual = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local est = redis.call('GET', KEYS[5])
if est then est = tonumber(est) else est = -1 end
for i = 1, 3 do
  if KEYS[i] ~= '' then
    if est >= 0 then
      local h = redis.call('DECRBY', KEYS[i] .. ':held', est)
      if h <= 0 then redis.call('DEL', KEYS[i] .. ':held') end
    end
    if actual ~= 0 then
      redis.call('INCRBY', KEYS[i], actual)
      redis.call('EXPIRE', KEYS[i], ttl)
    end
  end
end
if KEYS[4] ~= '' and est >= 0 then
  local h = redis.call('DECRBY', KEYS[4] .. ':held', est)
  if h <= 0 then redis.call('DEL', KEYS[4] .. ':held') end
end
redis.call('DEL', KEYS[5])
return 1
`;

type ReserveCall = (
  memberKey: string,
  teamKey: string,
  orgKey: string,
  creditKey: string,
  holdKey: string,
  est: number,
  ttl: number,
  memberLimit: number,
  teamLimit: number,
  orgLimit: number,
  creditBalance: number,
) => Promise<[number, number]>;

type SettleCall = (
  memberKey: string,
  teamKey: string,
  orgKey: string,
  creditKey: string,
  holdKey: string,
  actual: number,
  poolTtl: number,
) => Promise<number>;

// Register the scripts once on the singleton client (gcra.ts pattern).
const client = redis as unknown as {
  defineCommand: (n: string, o: object) => void;
  budgetReserve: ReserveCall;
  budgetSettle: SettleCall;
};
client.defineCommand("budgetReserve", { numberOfKeys: 5, lua: RESERVE_LUA });
client.defineCommand("budgetSettle", { numberOfKeys: 5, lua: SETTLE_LUA });
const reserveCall = client.budgetReserve.bind(redis);
const settleCall = client.budgetSettle.bind(redis);

export type HoldScope = "member" | "team" | "org" | "credit";

/** A budget level to hold against: pool key + cap (null = tracked, uncapped). */
export type BudgetHoldSlot = { key: string; limitMicro: number | null };

export type ReserveSpendResult =
  | { allowed: true }
  | { allowed: false; scope: HoldScope };

/** Redis key that remembers one request's reserved estimate. */
export function holdKey(requestId: string): string {
  return `hold:${requestId}`;
}

const SCOPE_BY_INDEX: Record<number, HoldScope> = {
  1: "member",
  2: "team",
  3: "org",
  4: "credit",
};

/**
 * Atomically reserve `estMicro` against up to three budget pools and an
 * optional credit balance. Denied → nothing is held anywhere.
 */
export async function reserveSpend(a: {
  requestId: string;
  estMicro: number;
  member?: BudgetHoldSlot | null;
  team?: BudgetHoldSlot | null;
  org?: BudgetHoldSlot | null;
  /** Credit slot: deny when held + est would exceed the current balance. */
  credit?: { key: string; balanceMicro: number } | null;
  ttlSec?: number;
}): Promise<ReserveSpendResult> {
  const est = Math.max(0, Math.round(a.estMicro));
  const [allowed, deniedIndex] = await reserveCall(
    a.member?.key ?? "",
    a.team?.key ?? "",
    a.org?.key ?? "",
    a.credit?.key ?? "",
    holdKey(a.requestId),
    est,
    a.ttlSec ?? HOLD_TTL_SEC,
    a.member?.limitMicro ?? -1,
    a.team?.limitMicro ?? -1,
    a.org?.limitMicro ?? -1,
    a.credit ? Math.max(0, Math.round(a.credit.balanceMicro)) : -1,
  );
  if (allowed === 1) return { allowed: true };
  return { allowed: false, scope: SCOPE_BY_INDEX[deniedIndex] ?? "org" };
}

/**
 * Release a request's hold and commit its actual cost to the spend pools.
 * Safe when the hold already expired (only the INCRBY of actual applies).
 */
export async function settleSpend(a: {
  requestId: string;
  actualMicro: number;
  memberKey?: string | null;
  teamKey?: string | null;
  orgKey?: string | null;
  creditKey?: string | null;
  poolTtlSec?: number;
}): Promise<void> {
  await settleCall(
    a.memberKey ?? "",
    a.teamKey ?? "",
    a.orgKey ?? "",
    a.creditKey ?? "",
    holdKey(a.requestId),
    Math.round(a.actualMicro),
    a.poolTtlSec ?? POOL_TTL_SEC,
  );
}
