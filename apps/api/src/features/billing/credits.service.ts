import { eq, sql } from "drizzle-orm";
import { withOrg, creditWallets, creditLedger } from "@vortex/db";

/** Managed-mode credit balance hit zero. Maps to HTTP 402. */
export class CreditExhaustedError extends Error {
  constructor() {
    super("managed credits exhausted");
    this.name = "CreditExhaustedError";
  }
}

/** Current wallet balance in micro-USD (0 if no wallet). */
export async function walletBalance(orgId: string): Promise<number> {
  return withOrg(orgId, async (tx) => {
    const [w] = await tx
      .select()
      .from(creditWallets)
      .where(eq(creditWallets.orgId, orgId))
      .limit(1);
    return w?.balanceMicro ?? 0;
  });
}

/**
 * Pre-request gate for managed keys: reject when the wallet can't cover this
 * request's estimated charge (defaults to "any positive balance"). Bounds
 * per-request overspend to estimate error. NOTE: concurrent requests each read
 * the balance independently — a true hold/reservation would need an atomic
 * decrement; this only guards the single-request case.
 */
export async function assertCredit(
  orgId: string,
  estChargeMicro = 0,
): Promise<void> {
  const balance = await walletBalance(orgId);
  if (balance <= 0 || balance < estChargeMicro) throw new CreditExhaustedError();
}

/** Add credits (top-up). Returns the new balance. */
export async function topupCredit(
  orgId: string,
  amountMicro: number,
): Promise<number> {
  return withOrg(orgId, async (tx) => {
    await tx
      .insert(creditWallets)
      .values({ orgId, balanceMicro: amountMicro })
      .onConflictDoUpdate({
        target: creditWallets.orgId,
        set: {
          balanceMicro: sql`${creditWallets.balanceMicro} + ${amountMicro}`,
          updatedAt: new Date(),
        },
      });
    await tx
      .insert(creditLedger)
      .values({ orgId, deltaMicro: amountMicro, reason: "topup" });
    const [w] = await tx
      .select()
      .from(creditWallets)
      .where(eq(creditWallets.orgId, orgId))
      .limit(1);
    return w?.balanceMicro ?? 0;
  });
}

/** Deduct managed spend = cost × (1 + markup). Records a ledger entry. */
export async function deductCredit(a: {
  orgId: string;
  costMicro: number;
  markupBps: number;
  requestId?: string;
}): Promise<void> {
  const charge = Math.round(a.costMicro * (1 + a.markupBps / 10_000));
  if (charge <= 0) return;
  await withOrg(a.orgId, async (tx) => {
    await tx
      .insert(creditWallets)
      .values({ orgId: a.orgId, balanceMicro: -charge })
      .onConflictDoUpdate({
        target: creditWallets.orgId,
        set: {
          balanceMicro: sql`${creditWallets.balanceMicro} - ${charge}`,
          updatedAt: new Date(),
        },
      });
    await tx.insert(creditLedger).values({
      orgId: a.orgId,
      deltaMicro: -charge,
      reason: "spend",
      requestId: a.requestId ?? null,
    });
  });
}
