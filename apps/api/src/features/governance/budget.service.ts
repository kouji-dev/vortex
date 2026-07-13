import { and, eq, gte, lt, sql } from "drizzle-orm";
import { withOrg, teams, memberships, usageRecords } from "@vortex/db";
import {
  redis,
  budgetKey,
  reserveSpend as holdReserve,
  settleSpend as holdSettle,
} from "@vortex/core";
import {
  BudgetExceededError,
  CreditExhaustedError,
} from "../../shared/errors.js";
import { resolveEntitlements } from "../../shared/entitlements.js";
import { requestMemo } from "../../shared/request-context.js";

export { BudgetExceededError };

function currentMonth(): string {
  return new Date().toISOString().slice(0, 7); // YYYY-MM
}

/** Redis base key for managed-credit holds (held counter lives at `:held`). */
function creditHoldKey(orgId: string): string {
  return `credits:${orgId}`;
}

// ── budget levels (member → team → org) ──────────────────────

export type BudgetLevel = {
  scope: "member" | "team" | "org";
  scopeId: string;
  limitMicro: number | null; // null = uncapped (tracked only)
  hard: boolean;
};

/**
 * The budget levels a request bills against, most-specific first:
 *   member cap = memberships.budgetOverrideMicro ?? teams.defaultMemberBudgetMicro
 *   team pool  = teams.budgetMicro ?? plan entitlement teamBudgetMicro
 *   org pool   = plan entitlement orgBudgetMicro
 *
 * Memoized PER REQUEST (not TTL) so a pre-check + its post-commit share one
 * lookup, while every new request still reflects the latest budget config.
 */
export async function resolveLevels(
  orgId: string,
  teamId: string | null,
  memberId?: string | null,
): Promise<BudgetLevel[]> {
  return requestMemo(
    `budget-levels:${orgId}:${teamId ?? "-"}:${memberId ?? "-"}`,
    () => loadLevels(orgId, teamId, memberId ?? null),
  );
}

async function loadLevels(
  orgId: string,
  teamId: string | null,
  memberId: string | null,
): Promise<BudgetLevel[]> {
  const ent = await resolveEntitlements(orgId);
  let team: typeof teams.$inferSelect | undefined;
  let member: typeof memberships.$inferSelect | undefined;
  if (teamId || memberId) {
    await withOrg(orgId, async (tx) => {
      if (teamId) {
        [team] = await tx.select().from(teams).where(eq(teams.id, teamId)).limit(1);
      }
      if (memberId) {
        [member] = await tx
          .select()
          .from(memberships)
          .where(eq(memberships.id, memberId))
          .limit(1);
      }
    });
  }
  const levels: BudgetLevel[] = [];
  if (memberId) {
    levels.push({
      scope: "member",
      scopeId: memberId,
      limitMicro:
        member?.budgetOverrideMicro ?? team?.defaultMemberBudgetMicro ?? null,
      hard: true,
    });
  }
  if (teamId) {
    levels.push({
      scope: "team",
      scopeId: teamId,
      limitMicro: team?.budgetMicro ?? ent.teamBudgetMicro,
      hard: (team?.budgetEnforcement ?? "hard") === "hard",
    });
  }
  levels.push({
    scope: "org",
    scopeId: orgId,
    limitMicro: ent.orgBudgetMicro,
    hard: true,
  });
  return levels;
}

// ── legacy single-pool view (kept for poolSpend/back-compat) ──

export type Pool = {
  scope: "team" | "org";
  scopeId: string;
  limit: number | null;
  hard: boolean;
};

/** The primary pool a request bills against (team when set, else org). */
export async function resolvePool(
  orgId: string,
  teamId: string | null,
): Promise<Pool> {
  const levels = await resolveLevels(orgId, teamId, null);
  const l = levels.find((x) => x.scope === (teamId ? "team" : "org"))!;
  return {
    scope: l.scope as "team" | "org",
    scopeId: l.scopeId,
    limit: l.limitMicro,
    hard: l.hard,
  };
}

// ── reserve / settle (atomic hold in Redis, no read-check race) ─

/**
 * Atomically reserve an estimated spend against member/team/org caps (and,
 * when `creditBalanceMicro` is given, the managed-credit balance). Throws a
 * typed BudgetExceededError / CreditExhaustedError on denial; on success the
 * estimate is held until `settleSpend` (or a 600s TTL) releases it.
 */
export async function reserveSpend(a: {
  orgId: string;
  teamId: string | null;
  memberId?: string | null;
  estimateMicro: number;
  requestId: string;
  /** Current managed-credit balance; omit/null to skip the credit slot. */
  creditBalanceMicro?: number | null;
}): Promise<void> {
  const levels = await resolveLevels(a.orgId, a.teamId, a.memberId ?? null);
  const month = currentMonth();
  const slot = (scope: BudgetLevel["scope"]) => {
    const l = levels.find((x) => x.scope === scope);
    if (!l) return null;
    return {
      key: budgetKey(a.orgId, l.scope, l.scopeId, month),
      // soft pools are tracked but never deny
      limitMicro: l.hard ? l.limitMicro : null,
    };
  };
  const res = await holdReserve({
    requestId: a.requestId,
    estMicro: a.estimateMicro,
    member: slot("member"),
    team: slot("team"),
    org: slot("org"),
    credit:
      a.creditBalanceMicro != null
        ? { key: creditHoldKey(a.orgId), balanceMicro: a.creditBalanceMicro }
        : null,
  });
  if (res.allowed) return;
  if (res.scope === "credit") {
    throw new CreditExhaustedError(a.creditBalanceMicro ?? 0);
  }
  const l = levels.find((x) => x.scope === res.scope);
  const spent = l
    ? Number(await redis.get(budgetKey(a.orgId, l.scope, l.scopeId, month))) || 0
    : 0;
  throw new BudgetExceededError(res.scope, l?.limitMicro ?? 0, spent);
}

/**
 * Release a request's hold and commit the actual cost to every level's spend
 * pool. Pass `usedCredits` when the reserve included the credit slot.
 */
export async function settleSpend(a: {
  orgId: string;
  teamId: string | null;
  memberId?: string | null;
  actualMicro: number;
  requestId: string;
  usedCredits?: boolean;
}): Promise<void> {
  const levels = await resolveLevels(a.orgId, a.teamId, a.memberId ?? null);
  const month = currentMonth();
  const key = (scope: BudgetLevel["scope"]) => {
    const l = levels.find((x) => x.scope === scope);
    return l ? budgetKey(a.orgId, l.scope, l.scopeId, month) : null;
  };
  await holdSettle({
    requestId: a.requestId,
    actualMicro: a.actualMicro,
    memberKey: key("member"),
    teamKey: key("team"),
    orgKey: key("org"),
    creditKey: a.usedCredits ? creditHoldKey(a.orgId) : null,
  });
}

// ── compatible wrappers (no hold; superseded by reserve/settle) ─

/** Pre-request check. Throws BudgetExceededError on a hard cap. */
export async function assertWithinBudget(a: {
  orgId: string;
  teamId: string | null;
  estimateMicro: number;
}): Promise<void> {
  const levels = await resolveLevels(a.orgId, a.teamId, null);
  const month = currentMonth();
  for (const l of levels) {
    if (l.limitMicro == null || !l.hard) continue;
    const key = budgetKey(a.orgId, l.scope, l.scopeId, month);
    const spent = Number(await redis.get(key)) || 0;
    if (spent + a.estimateMicro > l.limitMicro) {
      throw new BudgetExceededError(l.scope, l.limitMicro, spent);
    }
  }
}

/** Post-response commit of actual cost to every applicable pool. */
export async function commitSpend(a: {
  orgId: string;
  teamId: string | null;
  actualMicro: number;
}): Promise<void> {
  const levels = await resolveLevels(a.orgId, a.teamId, null);
  const month = currentMonth();
  for (const l of levels) {
    const key = budgetKey(a.orgId, l.scope, l.scopeId, month);
    await redis.incrby(key, Math.round(a.actualMicro));
    await redis.expire(key, 60 * 60 * 24 * 40); // ~40d self-clean; reconcile is authoritative
  }
}

/** Current spend for a team (or org pool) this month (micro-USD). */
export async function poolSpend(
  orgId: string,
  teamId: string | null,
): Promise<number> {
  const pool = await resolvePool(orgId, teamId);
  const key = budgetKey(orgId, pool.scope, pool.scopeId, currentMonth());
  return Number(await redis.get(key)) || 0;
}

/** Re-sum usage_records → authoritative Redis counters for the month. */
export async function reconcileMonth(
  orgId: string,
  month = currentMonth(),
): Promise<void> {
  const start = new Date(`${month}-01T00:00:00.000Z`);
  const end = new Date(start);
  end.setUTCMonth(end.getUTCMonth() + 1);
  await withOrg(orgId, async (tx) => {
    const rows = await tx
      .select({
        teamId: usageRecords.teamId,
        total: sql<number>`coalesce(sum(${usageRecords.costMicro}),0)`,
      })
      .from(usageRecords)
      .where(
        and(
          gte(usageRecords.createdAt, start),
          lt(usageRecords.createdAt, end),
        ),
      )
      .groupBy(usageRecords.teamId);
    let orgTotal = 0;
    for (const r of rows) {
      orgTotal += Number(r.total);
      if (r.teamId) {
        await redis.set(
          budgetKey(orgId, "team", r.teamId, month),
          Math.round(Number(r.total)),
        );
      }
    }
    // org pool aggregates ALL usage (team + non-team)
    await redis.set(budgetKey(orgId, "org", orgId, month), Math.round(orgTotal));
  });
}
