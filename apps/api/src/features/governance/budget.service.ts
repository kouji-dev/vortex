import { and, eq, gte, lt, sql } from "drizzle-orm";
import { withOrg, memberships, teams, usageRecords } from "@vortex/db";
import { redis, spendKey } from "@vortex/core";

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

/** Effective monthly ceiling for a member = override ?? team default. */
async function effectiveLimit(
  orgId: string,
  memberId: string,
): Promise<{ limit: number | null; hard: boolean }> {
  return withOrg(orgId, async (tx) => {
    const [m] = await tx
      .select()
      .from(memberships)
      .where(eq(memberships.id, memberId))
      .limit(1);
    if (!m) return { limit: null, hard: false };
    let teamDefault: number | null = null;
    let hard = true;
    if (m.teamId) {
      const [t] = await tx
        .select()
        .from(teams)
        .where(eq(teams.id, m.teamId))
        .limit(1);
      if (t) {
        teamDefault = t.defaultMemberBudgetMicro ?? null;
        hard = t.budgetEnforcement === "hard";
      }
    }
    const limit = m.budgetOverrideMicro ?? teamDefault;
    return { limit, hard };
  });
}

/** Pre-request check. Throws BudgetExceededError on a hard cap. (Called by the gateway.) */
export async function assertWithinBudget(a: {
  orgId: string;
  memberId: string;
  estimateMicro: number;
}): Promise<void> {
  const { limit, hard } = await effectiveLimit(a.orgId, a.memberId);
  if (limit == null || !hard) return;
  const key = spendKey(a.orgId, a.memberId, currentMonth());
  const spent = Number(await redis.get(key)) || 0;
  if (spent + a.estimateMicro > limit) {
    throw new BudgetExceededError("member", "member monthly budget exceeded");
  }
}

/** Post-response commit of actual cost. (Called by the gateway.) */
export async function commitSpend(a: {
  orgId: string;
  memberId: string;
  actualMicro: number;
}): Promise<void> {
  const key = spendKey(a.orgId, a.memberId, currentMonth());
  await redis.incrby(key, Math.round(a.actualMicro));
  await redis.expire(key, 60 * 60 * 24 * 40); // ~40d self-clean; reconcile is authoritative
}

/** Current spend for a member this month (micro-USD). */
export async function memberSpend(
  orgId: string,
  memberId: string,
): Promise<number> {
  const key = spendKey(orgId, memberId, currentMonth());
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
        memberId: usageRecords.memberId,
        total: sql<number>`coalesce(sum(${usageRecords.costMicro}),0)`,
      })
      .from(usageRecords)
      .where(
        and(
          gte(usageRecords.createdAt, start),
          lt(usageRecords.createdAt, end),
        ),
      )
      .groupBy(usageRecords.memberId);
    for (const r of rows) {
      if (!r.memberId) continue;
      await redis.set(spendKey(orgId, r.memberId, month), Math.round(r.total));
    }
  });
}
