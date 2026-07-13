import { eq, sql } from "drizzle-orm";
import { withOrg, creditWallets, creditLedger, type Tx } from "@vortex/db";
import { CreditExhaustedError } from "../../shared/errors.js";

export { CreditExhaustedError };

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
 * the balance independently — the atomic hold lives in budget-hold (Redis);
 * this only guards the single-request case.
 */
export async function assertCredit(
  orgId: string,
  estChargeMicro = 0,
): Promise<void> {
  const balance = await walletBalance(orgId);
  if (balance <= 0 || balance < estChargeMicro) {
    throw new CreditExhaustedError(balance);
  }
}

/**
 * Add credits inside an existing transaction (e.g. the Stripe-webhook tx so a
 * checkout top-up commits atomically with the event-dedupe row).
 */
export async function topupCreditTx(
  tx: Tx,
  orgId: string,
  amountMicro: number,
): Promise<number> {
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
}

/** Add credits (top-up). Returns the new balance. */
export async function topupCredit(
  orgId: string,
  amountMicro: number,
): Promise<number> {
  return withOrg(orgId, (tx) => topupCreditTx(tx, orgId, amountMicro));
}

export type DeductResult = {
  /** false = idempotent replay (this requestId was already charged). */
  deducted: boolean;
  chargeMicro: number;
  /** Wallet balance after the deduction (or current, on replay/zero-charge). */
  balanceMicro: number;
};

/**
 * Deduct managed spend = cost × (1 + markup), in ONE transaction:
 *   1. ledger insert FIRST with ON CONFLICT (request_id) DO NOTHING — the
 *      partial unique index makes retries/replays a no-op;
 *   2. wallet decrement only when the ledger row was actually inserted;
 *   3. never creates a negative wallet — insufficient balance throws
 *      CreditExhaustedError and rolls the ledger row back (hard mode).
 */
export async function deductCredit(a: {
  orgId: string;
  costMicro: number;
  markupBps: number;
  requestId?: string;
}): Promise<DeductResult> {
  const charge = Math.round(a.costMicro * (1 + a.markupBps / 10_000));
  if (charge <= 0) {
    return {
      deducted: false,
      chargeMicro: 0,
      balanceMicro: await walletBalance(a.orgId),
    };
  }
  return withOrg(a.orgId, async (tx) => {
    // 1) idempotency gate: at most one spend ledger entry per requestId
    let insert = tx.insert(creditLedger).values({
      orgId: a.orgId,
      deltaMicro: -charge,
      reason: "spend",
      requestId: a.requestId ?? null,
    });
    if (a.requestId) {
      insert = insert.onConflictDoNothing({
        target: creditLedger.requestId,
        where: sql`${creditLedger.requestId} is not null`,
      }) as typeof insert;
    }
    const inserted = await insert.returning({ id: creditLedger.id });
    if (inserted.length === 0) {
      // replay — already charged; report the existing state
      const [w] = await tx
        .select()
        .from(creditWallets)
        .where(eq(creditWallets.orgId, a.orgId))
        .limit(1);
      return {
        deducted: false,
        chargeMicro: charge,
        balanceMicro: w?.balanceMicro ?? 0,
      };
    }
    // 2) wallet decrement — lock the row, never go negative
    const [w] = await tx
      .select()
      .from(creditWallets)
      .where(eq(creditWallets.orgId, a.orgId))
      .limit(1)
      .for("update");
    const balance = w?.balanceMicro ?? 0;
    if (balance < charge) {
      // rolls back the ledger insert too
      throw new CreditExhaustedError(balance);
    }
    await tx
      .update(creditWallets)
      .set({
        balanceMicro: sql`${creditWallets.balanceMicro} - ${charge}`,
        updatedAt: new Date(),
      })
      .where(eq(creditWallets.orgId, a.orgId));
    return { deducted: true, chargeMicro: charge, balanceMicro: balance - charge };
  });
}
