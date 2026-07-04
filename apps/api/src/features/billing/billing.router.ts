import { Hono } from "hono";
import { eq } from "drizzle-orm";
import { withOrg, subscriptions, plans } from "@vortex/db";
import { requireMember, type AppEnv } from "../../shared/ctx.js";
import {
  stripeEnabled,
  createCheckout,
  createPortal,
  handleWebhook,
} from "./billing.service.js";

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
  try {
    await handleWebhook(raw, sig);
    return c.json({ received: true });
  } catch (e) {
    return c.json({ error: (e as Error).message }, 400);
  }
});

export const billingRouters: Array<[string, Hono<AppEnv>]> = [
  ["/api/billing", billing],
];
export const webhookRouters: Array<[string, Hono]> = [
  ["/api/stripe-webhook", billingWebhook],
];
