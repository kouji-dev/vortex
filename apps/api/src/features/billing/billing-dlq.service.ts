import type Stripe from "stripe";
import { and, eq, isNotNull, lte } from "drizzle-orm";
import { withBypass, withOrg, failedBillingEvents, usageRecords } from "@vortex/db";
import { deductCredit, topupCredit } from "./credits.service.js";
import { processStripeEvent } from "./billing.service.js";
import { settleSpend } from "../governance/budget.service.js";

/**
 * Billing dead-letter queue: money-path work that failed (webhook apply,
 * credit deduction, top-up) is persisted and retried with exponential backoff
 * instead of being silently dropped. All replayed operations are idempotent
 * (stripe_events dedupe row / credit_ledger request_id unique).
 */

const MAX_RETRIES = 10;
const BASE_DELAY_MS = 60_000; // 1m, 2m, 4m, … capped at MAX_DELAY_MS
const MAX_DELAY_MS = 6 * 60 * 60 * 1000; // 6h
const SWEEP_BATCH = 50;

export type BillingFailureKind =
  | "stripe_webhook"
  | "credit_spend"
  | "credit_topup"
  | "spend_settle"
  | "usage_insert";

function backoffAt(retryCount: number): Date {
  const delay = Math.min(BASE_DELAY_MS * 2 ** retryCount, MAX_DELAY_MS);
  return new Date(Date.now() + delay);
}

/**
 * Persist a failed billing operation for retry. Never throws — this is the
 * last line of defense; a failure here is logged and swallowed.
 */
export async function recordBillingFailure(
  kind: BillingFailureKind | string,
  payload: Record<string, unknown>,
  error: unknown,
): Promise<void> {
  const message = error instanceof Error ? error.message : String(error);
  try {
    await withBypass((tx) =>
      tx.insert(failedBillingEvents).values({
        kind,
        payload,
        error: message,
        retryCount: 0,
        nextRetryAt: backoffAt(0),
      }),
    );
  } catch (e) {
    console.error(
      JSON.stringify({
        evt: "billing_dlq_insert_failed",
        kind,
        error: (e as Error).message,
      }),
    );
  }
  console.error(
    JSON.stringify({ evt: "billing_failure", kind, error: message, payload }),
  );
}

async function replay(kind: string, payload: Record<string, unknown>): Promise<void> {
  switch (kind) {
    case "stripe_webhook":
      // stored verified event JSON; processStripeEvent dedupes via stripe_events
      await processStripeEvent(payload as unknown as Stripe.Event);
      return;
    case "credit_spend":
      // idempotent: credit_ledger request_id unique makes retries no-ops
      await deductCredit({
        orgId: String(payload.orgId),
        costMicro: Number(payload.costMicro),
        markupBps: Number(payload.markupBps ?? 0),
        requestId: payload.requestId ? String(payload.requestId) : undefined,
      });
      return;
    case "credit_topup":
      await topupCredit(String(payload.orgId), Number(payload.amountMicro));
      return;
    case "spend_settle":
      // Replays release the (likely expired) hold and INCRBY the actual cost.
      // Redis pools are approximate (reconcile is authoritative), so a rare
      // double-commit after a partial failure is acceptable.
      await settleSpend({
        orgId: String(payload.orgId),
        teamId: payload.teamId ? String(payload.teamId) : null,
        memberId: payload.memberId ? String(payload.memberId) : null,
        actualMicro: Number(payload.actualMicro),
        requestId: String(payload.requestId),
        usedCredits: payload.usedCredits === true,
      });
      return;
    case "usage_insert":
      // Payload is the exact usageRecords row that failed to insert.
      await withOrg(String(payload.orgId), (tx) =>
        tx.insert(usageRecords).values(payload as never),
      );
      return;
    default:
      throw new Error(`unknown_billing_dlq_kind:${kind}`);
  }
}

/** One sweep: replay up to 50 due rows; success deletes, failure backs off. */
export async function retrySweep(): Promise<void> {
  const rows = await withBypass((tx) =>
    tx
      .select()
      .from(failedBillingEvents)
      .where(
        and(
          isNotNull(failedBillingEvents.nextRetryAt),
          lte(failedBillingEvents.nextRetryAt, new Date()),
        ),
      )
      .limit(SWEEP_BATCH),
  );
  for (const row of rows) {
    try {
      await replay(row.kind, row.payload ?? {});
      await withBypass((tx) =>
        tx.delete(failedBillingEvents).where(eq(failedBillingEvents.id, row.id)),
      );
    } catch (e) {
      const retryCount = row.retryCount + 1;
      const dead = retryCount >= MAX_RETRIES;
      await withBypass((tx) =>
        tx
          .update(failedBillingEvents)
          .set({
            retryCount,
            error: (e as Error).message,
            // null nextRetryAt = dead-lettered for good (manual intervention)
            nextRetryAt: dead ? null : backoffAt(retryCount),
          })
          .where(eq(failedBillingEvents.id, row.id)),
      );
      if (dead) {
        console.error(
          JSON.stringify({
            evt: "billing_dlq_dead",
            id: row.id,
            kind: row.kind,
            error: (e as Error).message,
          }),
        );
      }
    }
  }
}

let sweepTimer: NodeJS.Timeout | null = null;

/** Start the 60s DLQ retry sweeper (idempotent). Call from server bootstrap. */
export function startDlqSweep(intervalMs = 60_000): NodeJS.Timeout {
  if (sweepTimer) return sweepTimer;
  sweepTimer = setInterval(() => {
    retrySweep().catch((e) =>
      console.error(
        JSON.stringify({ evt: "billing_dlq_sweep_failed", error: (e as Error).message }),
      ),
    );
  }, intervalMs);
  sweepTimer.unref?.();
  return sweepTimer;
}

/** Stop the sweeper (tests). */
export function stopDlqSweep(): void {
  if (sweepTimer) clearInterval(sweepTimer);
  sweepTimer = null;
}
