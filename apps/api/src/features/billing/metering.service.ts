import { and, count, gte, lt, sql } from "drizzle-orm";
import { withOrg, usageRecords, usageRollups, memberships } from "@vortex/db";

function currentMonth(): string {
  return new Date().toISOString().slice(0, 7); // YYYY-MM
}

export type UsageSummary = {
  period: string;
  requests: number;
  inputTokens: number;
  outputTokens: number;
  costMicro: number;
  seats: number;
  serviceAccounts: number;
};

const METERS = [
  "requests",
  "input_tokens",
  "output_tokens",
  "cost_micro",
  "seats",
  "service_accounts",
] as const;

/**
 * Aggregate usage_records for the month into a summary and upsert the per-meter
 * usage_rollups (price-tracking source of truth). Runs in BOTH deployments.
 */
export async function rollupOrg(
  orgId: string,
  month = currentMonth(),
): Promise<UsageSummary> {
  const start = new Date(`${month}-01T00:00:00.000Z`);
  const end = new Date(start);
  end.setUTCMonth(end.getUTCMonth() + 1);

  const summary = await withOrg(orgId, async (tx) => {
    const [agg] = await tx
      .select({
        requests: sql<number>`count(*)`,
        inputTokens: sql<number>`coalesce(sum(${usageRecords.promptTokens}),0)`,
        outputTokens: sql<number>`coalesce(sum(${usageRecords.completionTokens}),0)`,
        costMicro: sql<number>`coalesce(sum(${usageRecords.costMicro}),0)`,
      })
      .from(usageRecords)
      .where(
        and(gte(usageRecords.createdAt, start), lt(usageRecords.createdAt, end)),
      );
    const memberCounts = await tx
      .select({ type: memberships.type, n: count() })
      .from(memberships)
      .groupBy(memberships.type);
    const byType = (t: string) =>
      Number(memberCounts.find((r) => r.type === t)?.n ?? 0);
    return {
      requests: Number(agg?.requests ?? 0),
      inputTokens: Number(agg?.inputTokens ?? 0),
      outputTokens: Number(agg?.outputTokens ?? 0),
      costMicro: Number(agg?.costMicro ?? 0),
      seats: byType("human"),
      serviceAccounts: byType("technical"),
    };
  });

  const values: Record<(typeof METERS)[number], number> = {
    requests: summary.requests,
    input_tokens: summary.inputTokens,
    output_tokens: summary.outputTokens,
    cost_micro: summary.costMicro,
    seats: summary.seats,
    service_accounts: summary.serviceAccounts,
  };

  await withOrg(orgId, (tx) =>
    tx
      .insert(usageRollups)
      .values(METERS.map((meter) => ({ orgId, period: month, meter, value: values[meter] })))
      .onConflictDoUpdate({
        target: [usageRollups.orgId, usageRollups.period, usageRollups.meter],
        set: { value: sql`excluded.value`, updatedAt: new Date() },
      }),
  );

  return { period: month, ...summary };
}

/** Current-month usage summary (recomputes + persists rollups). */
export async function currentUsage(orgId: string): Promise<UsageSummary> {
  return rollupOrg(orgId);
}
