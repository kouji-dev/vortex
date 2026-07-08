import { and, eq } from "drizzle-orm";
import {
  withBypass,
  withOrg,
  contracts,
  pricingTiers,
  usageRollups,
} from "@vortex/db";
import { env } from "@vortex/core";
import { resolveEntitlements } from "../../shared/entitlements.js";

export type Tier = { upToQty: number | null; unitPriceMicro: number };

/**
 * Graduated (tiered) charge for `quantity` units. Each tier prices only the
 * units that fall inside its band; `upToQty: null` is the final unbounded tier.
 * Unit price steps down with volume → "dynamically affordable".
 */
export function computeGraduatedCharge(tiers: Tier[], quantity: number): number {
  const sorted = [...tiers].sort(
    (a, b) => (a.upToQty ?? Infinity) - (b.upToQty ?? Infinity),
  );
  let lower = 0;
  let total = 0;
  for (const t of sorted) {
    const upper = t.upToQty ?? Infinity;
    const inTier = Math.max(0, Math.min(quantity, upper) - lower);
    total += inTier * t.unitPriceMicro;
    lower = upper;
    if (quantity <= upper) break;
  }
  return Math.round(total);
}

export type InvoiceLine = {
  meter: string;
  quantity: number;
  amountMicro: number;
};

export type InvoicePreview =
  | { enabled: false; reason: string }
  | {
      enabled: true;
      planId: string;
      baseMicro: number;
      lines: InvoiceLine[];
      totalMicro: number;
    };

/**
 * Preview the current-period invoice from usage_rollups × graduated pricing.
 * Billing plane is MANAGED ONLY — returns disabled otherwise.
 */
export async function previewInvoice(orgId: string): Promise<InvoicePreview> {
  if (env.DEPLOYMENT_MODE !== "managed") {
    return { enabled: false, reason: "billing_disabled_self_hosted" };
  }
  const ent = await resolveEntitlements(orgId);
  const month = new Date().toISOString().slice(0, 7);

  const { tierRows, contract } = await withBypass(async (tx) => {
    const [contractRow] = await tx
      .select()
      .from(contracts)
      .where(and(eq(contracts.orgId, orgId), eq(contracts.status, "active")))
      .limit(1);
    const scopeType = contractRow ? "contract" : "plan";
    const scopeId = contractRow ? contractRow.id : ent.planId;
    const tiers = await tx
      .select()
      .from(pricingTiers)
      .where(
        and(
          eq(pricingTiers.scopeType, scopeType),
          eq(pricingTiers.scopeId, scopeId),
        ),
      );
    return { tierRows: tiers, contract: contractRow };
  });

  const rollups = await withOrg(orgId, (tx) =>
    tx.select().from(usageRollups).where(eq(usageRollups.period, month)),
  );
  const qtyByMeter = new Map(rollups.map((r) => [r.meter, r.value]));

  // Group tiers by meter and price each metered quantity.
  const meters = [...new Set(tierRows.map((t) => t.meter))];
  const lines: InvoiceLine[] = meters.map((meter) => {
    const tiers = tierRows
      .filter((t) => t.meter === meter)
      .map((t) => ({ upToQty: t.upToQty ?? null, unitPriceMicro: t.unitPriceMicro }));
    const quantity = qtyByMeter.get(meter) ?? 0;
    return { meter, quantity, amountMicro: computeGraduatedCharge(tiers, quantity) };
  });

  // Only the contract's committed base belongs on the usage invoice. A plan's
  // flat monthly fee is billed separately by Stripe (subscription) — including
  // plan.priceMicro here would double-charge it.
  const baseMicro = contract?.baseMicro ?? 0;
  const totalMicro =
    baseMicro + lines.reduce((s, l) => s + l.amountMicro, 0);

  return { enabled: true, planId: ent.planId, baseMicro, lines, totalMicro };
}
