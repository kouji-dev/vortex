import { and, eq, gte, lt, sql } from "drizzle-orm";
import { withOrg, teams, usageRecords } from "@vortex/db";
import { redis, budgetKey } from "@vortex/core";
import { resolveEntitlements } from "../../shared/entitlements.js";
import { requestMemo } from "../../shared/request-context.js";

export class BudgetExceededError extends Error {
  scope: string;
  constructor(scope: string, message?: string) {
    super(message ?? `budget exceeded: ${scope}`);
    this.name = "BudgetExceededError";
    this.scope = scope;
  }
}

function currentMonth(): string {
  return new Date().toISOString().slice(0, 7); // YYYY-MM
}

export type Pool = {
  scope: "team" | "org";
  scopeId: string;
  limit: number | null;
  hard: boolean;
};

/**
 * The budget pool a request bills against. Team-level when the member has a
 * team (cap = team.budgetMicro ?? plan entitlement), else an org-wide pool at
 * the plan default. Enforced in BOTH managed and self-hosted deployments.
 *
 * Memoized PER REQUEST (not TTL) so a pre-check + its post-commit share one
 * lookup, while every new request still reflects the latest budget config.
 */
export async function resolvePool(
  orgId: string,
  teamId: string | null,
): Promise<Pool> {
  return requestMemo(`pool:${orgId}:${teamId ?? "org"}`, () =>
    loadPool(orgId, teamId),
  );
}

async function loadPool(orgId: string, teamId: string | null): Promise<Pool> {
  const ent = await resolveEntitlements(orgId);
  if (!teamId) {
    return { scope: "org", scopeId: orgId, limit: ent.teamBudgetMicro, hard: true };
  }
  return withOrg(orgId, async (tx) => {
    const [t] = await tx.select().from(teams).where(eq(teams.id, teamId)).limit(1);
    const limit = t?.budgetMicro ?? ent.teamBudgetMicro;
    const hard = (t?.budgetEnforcement ?? "hard") === "hard";
    return { scope: "team", scopeId: teamId, limit, hard };
  });
}

/** Pre-request check. Throws BudgetExceededError on a hard cap. */
export async function assertWithinBudget(a: {
  orgId: string;
  teamId: string | null;
  estimateMicro: number;
}): Promise<void> {
  const pool = await resolvePool(a.orgId, a.teamId);
  if (pool.limit == null || !pool.hard) return;
  const key = budgetKey(a.orgId, pool.scope, pool.scopeId, currentMonth());
  const spent = Number(await redis.get(key)) || 0;
  if (spent + a.estimateMicro > pool.limit) {
    throw new BudgetExceededError(pool.scope, `${pool.scope} monthly budget exceeded`);
  }
}

/** Post-response commit of actual cost to the team/org pool. */
export async function commitSpend(a: {
  orgId: string;
  teamId: string | null;
  actualMicro: number;
}): Promise<void> {
  const pool = await resolvePool(a.orgId, a.teamId);
  const key = budgetKey(a.orgId, pool.scope, pool.scopeId, currentMonth());
  await redis.incrby(key, Math.round(a.actualMicro));
  await redis.expire(key, 60 * 60 * 24 * 40); // ~40d self-clean; reconcile is authoritative
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
    for (const r of rows) {
      const scope = r.teamId ? "team" : "org";
      const scopeId = r.teamId ?? orgId;
      await redis.set(budgetKey(orgId, scope, scopeId, month), Math.round(r.total));
    }
  });
}
