import { Hono } from "hono";
import { z } from "zod";
import { eq } from "drizzle-orm";
import { withOrg, subscriptions, plans, organizations } from "@vortex/db";
import { env } from "@vortex/core";
import { requireMember, type AppEnv } from "../../shared/ctx.js";
import { walletBalance, topupCredit } from "./credits.service.js";
import { previewInvoice } from "./invoice.service.js";
import {
  stripeEnabled,
  createCheckout,
  createCreditCheckout,
  createPortal,
  verifyWebhook,
  processStripeEvent,
} from "./billing.service.js";
import { recordBillingFailure } from "./billing-dlq.service.js";
import {
  resolveEntitlements,
  getPlanCatalog,
} from "../../shared/entitlements.js";
import { currentUsage } from "./metering.service.js";

// ── public pricing catalog (/api/pricing) — no auth ──────────
export const pricing = new Hono<AppEnv>();
pricing.get("/", async (c) => {
  return c.json({ plans: await getPlanCatalog() });
});

// ── tenant billing (/api/billing) — owner-managed ────────────
export const billing = new Hono<AppEnv>();
billing.use("*", requireMember);

billing.get("/", async (c) => {
  const { orgId } = c.get("member");
  const row = await withOrg(orgId, async (tx) => {
    const [sub] = await tx
      .select()
      .from(subscriptions)
      .where(eq(subscriptions.orgId, orgId))
      .limit(1);
    return sub ?? null;
  });
  const planList = await withOrg(orgId, (tx) => tx.select().from(plans));
  return c.json({ subscription: row, plans: planList, stripe: stripeEnabled() });
});

// GET /subscription — current plan + entitlements + usage + seats used/limit.
// Powers the settings plan card + billing route.
billing.get("/subscription", async (c) => {
  const { orgId } = c.get("member");
  const ent = await resolveEntitlements(orgId);
  const usage = await currentUsage(orgId);
  return c.json({
    plan: { id: ent.planId, name: ent.planName },
    entitlements: {
      seatsPerOrg: ent.seatsPerOrg,
      servicePerMember: ent.servicePerMember,
      teamBudgetMicro: ent.teamBudgetMicro,
      orgBudgetMicro: ent.orgBudgetMicro,
      rpm: ent.rpm,
      tpm: ent.tpm,
      concurrency: ent.concurrency,
      flags: ent.flags,
    },
    usage,
    seats: { used: usage.seats, limit: ent.seatsPerOrg },
    services: { used: usage.serviceAccounts, limitPerMember: ent.servicePerMember },
    stripe: stripeEnabled(),
  });
});

// GET /invoice — current-period graduated invoice preview (managed only).
billing.get("/invoice", async (c) => {
  const { orgId } = c.get("member");
  return c.json(await previewInvoice(orgId));
});

// ── managed keys: wallet + key mode ──────────────────────────
billing.get("/credits", async (c) => {
  const { orgId } = c.get("member");
  return c.json({ balanceMicro: await walletBalance(orgId) });
});

billing.post("/credits/topup", async (c) => {
  const m = c.get("member");
  if (m.role !== "owner") return c.json({ error: "forbidden" }, 403);
  const { amountMicro } = z
    .object({ amountMicro: z.number().int().positive() })
    .parse(await c.req.json().catch(() => ({})));
  // Managed SaaS: credits are money — purchasing goes through a payment-mode
  // Stripe Checkout; the checkout.session.completed webhook credits the
  // wallet. Only self-hosted/dev may grant credits directly.
  if (env.DEPLOYMENT_MODE === "managed") {
    if (!stripeEnabled()) return c.json({ error: "billing_disabled" }, 400);
    const url = await createCreditCheckout(m.orgId, amountMicro);
    return c.json({ url });
  }
  const balance = await topupCredit(m.orgId, amountMicro);
  return c.json({ balanceMicro: balance });
});

// PATCH /key-mode — switch BYOK | managed | hybrid (+ markup). Owner only.
billing.patch("/key-mode", async (c) => {
  const m = c.get("member");
  if (m.role !== "owner") return c.json({ error: "forbidden" }, 403);
  const body = z
    .object({
      keyMode: z.enum(["byok", "managed", "hybrid"]).optional(),
      markupBps: z.number().int().min(0).max(100_000).optional(),
    })
    .parse(await c.req.json().catch(() => ({})));
  await withOrg(m.orgId, (tx) =>
    tx
      .update(organizations)
      .set({
        ...(body.keyMode && { keyMode: body.keyMode }),
        ...(body.markupBps !== undefined && { markupBps: body.markupBps }),
      })
      .where(eq(organizations.id, m.orgId)),
  );
  return c.json({ ok: true });
});

billing.post("/checkout", async (c) => {
  const m = c.get("member");
  if (m.role !== "owner") return c.json({ error: "forbidden" }, 403);
  if (!stripeEnabled()) return c.json({ error: "billing_disabled" }, 400);
  const { planId } = (await c.req.json().catch(() => ({}))) as {
    planId?: string;
  };
  if (!planId) return c.json({ error: "planId_required" }, 400);
  const url = await createCheckout(m.orgId, planId);
  return c.json({ url });
});

billing.post("/portal", async (c) => {
  const m = c.get("member");
  if (m.role !== "owner") return c.json({ error: "forbidden" }, 403);
  if (!stripeEnabled()) return c.json({ error: "billing_disabled" }, 400);
  const url = await createPortal(m.orgId);
  return c.json({ url });
});

// ── Stripe webhook (no auth, raw body, signature-verified) ───
export const billingWebhook = new Hono();
billingWebhook.post("/", async (c) => {
  const sig = c.req.header("stripe-signature");
  if (!sig) return c.json({ error: "missing_signature" }, 400);
  const raw = await c.req.text();
  let event;
  try {
    event = await verifyWebhook(raw, sig);
  } catch (e) {
    return c.json({ error: (e as Error).message }, 400);
  }
  try {
    await processStripeEvent(event);
    return c.json({ received: true });
  } catch (e) {
    // verified but failed to apply → DLQ retries it; 500 also lets Stripe
    // redeliver (the stripe_events dedupe row makes double-apply impossible).
    await recordBillingFailure(
      "stripe_webhook",
      event as unknown as Record<string, unknown>,
      e,
    );
    return c.json({ error: "processing_failed" }, 500);
  }
});

export const billingRouters: Array<[string, Hono<AppEnv>]> = [
  ["/api/pricing", pricing],
  ["/api/billing", billing],
];
export const webhookRouters: Array<[string, Hono]> = [
  ["/api/stripe-webhook", billingWebhook],
];
