import { and, eq, inArray } from "drizzle-orm";
import {
  withBypass,
  organizations,
  subscriptions,
  contracts,
  plans,
  planEntitlements,
  pricingTiers,
} from "@vortex/db";
import { ttlMemo } from "@vortex/core";

/** Effective governance limits for an org. `null` field = unlimited. */
export type Entitlements = {
  planId: string;
  planName: string | null;
  seatsPerOrg: number | null;
  servicePerMember: number | null;
  teamBudgetMicro: number | null;
  rpm: number | null;
  tpm: number | null;
  concurrency: number | null;
  flags: Record<string, unknown>;
  hasContract: boolean;
};

const DEFAULT_PLAN_ID = "plan_free";
const TTL_MS = 30_000;

/** Resolve org → active contract ?? active subscription ?? org.planId ?? Free. */
async function loadEntitlements(orgId: string): Promise<Entitlements> {
  return withBypass(async (tx) => {
    const [org] = await tx
      .select()
      .from(organizations)
      .where(eq(organizations.id, orgId))
      .limit(1);
    const [sub] = await tx
      .select()
      .from(subscriptions)
      .where(
        and(
          eq(subscriptions.orgId, orgId),
          inArray(subscriptions.status, ["active", "trialing"]),
        ),
      )
      .limit(1);
    const [contract] = await tx
      .select()
      .from(contracts)
      .where(and(eq(contracts.orgId, orgId), eq(contracts.status, "active")))
      .limit(1);

    const planId = sub?.planId ?? org?.planId ?? DEFAULT_PLAN_ID;
    const [ent] = await tx
      .select()
      .from(planEntitlements)
      .where(eq(planEntitlements.planId, planId))
      .limit(1);
    const [plan] = await tx
      .select()
      .from(plans)
      .where(eq(plans.id, planId))
      .limit(1);

    // Contract seat commit raises the org seat ceiling.
    const seatsPerOrg =
      contract?.seatCommit != null ? contract.seatCommit : ent?.seatsPerOrg ?? null;

    return {
      planId,
      planName: plan?.name ?? null,
      seatsPerOrg,
      servicePerMember: ent?.servicePerMember ?? null,
      teamBudgetMicro: ent?.teamBudgetMicro ?? null,
      rpm: ent?.rpm ?? null,
      tpm: ent?.tpm ?? null,
      concurrency: ent?.concurrency ?? null,
      flags: (ent?.flags as Record<string, unknown>) ?? {},
      hasContract: !!contract,
    } satisfies Entitlements;
  });
}

/** Resolve entitlements for an org (30s TTL, stampede-safe). */
export const resolveEntitlements = ttlMemo(TTL_MS, loadEntitlements);

/** Drop a cached org (call after plan/subscription/contract changes). */
export function invalidateEntitlements(orgId: string): void {
  resolveEntitlements.invalidate(orgId);
}

export type PlanCatalogEntry = {
  planId: string;
  name: string;
  priceMicro: number | null;
  entitlements: {
    seatsPerOrg: number | null;
    servicePerMember: number | null;
    teamBudgetMicro: number | null;
    rpm: number | null;
    tpm: number | null;
    concurrency: number | null;
    flags: Record<string, unknown>;
  };
  tiers: {
    meter: string;
    upToQty: number | null;
    unitPriceMicro: number;
  }[];
};

/** Public pricing catalog: every plan + its entitlements + graduated tiers. */
export async function getPlanCatalog(): Promise<PlanCatalogEntry[]> {
  return withBypass(async (tx) => {
    const planRows = await tx.select().from(plans);
    const entRows = await tx.select().from(planEntitlements);
    const tierRows = await tx
      .select()
      .from(pricingTiers)
      .where(eq(pricingTiers.scopeType, "plan"));

    return planRows.map((p) => {
      const ent = entRows.find((e) => e.planId === p.id);
      return {
        planId: p.id,
        name: p.name,
        priceMicro: p.priceMicro ?? null,
        entitlements: {
          seatsPerOrg: ent?.seatsPerOrg ?? null,
          servicePerMember: ent?.servicePerMember ?? null,
          teamBudgetMicro: ent?.teamBudgetMicro ?? null,
          rpm: ent?.rpm ?? null,
          tpm: ent?.tpm ?? null,
          concurrency: ent?.concurrency ?? null,
          flags: (ent?.flags as Record<string, unknown>) ?? {},
        },
        tiers: tierRows
          .filter((t) => t.scopeId === p.id)
          .map((t) => ({
            meter: t.meter,
            upToQty: t.upToQty ?? null,
            unitPriceMicro: t.unitPriceMicro,
          })),
      } satisfies PlanCatalogEntry;
    });
  });
}
