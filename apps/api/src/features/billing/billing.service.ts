import type Stripe from "stripe";
import { eq } from "drizzle-orm";
import {
  withBypass,
  organizations,
  plans,
  subscriptions,
  type Tx,
} from "@vortex/db";
import { env } from "@vortex/core";

let _stripe: Stripe | null = null;

export function stripeEnabled(): boolean {
  return env.TENANCY_MODE === "multi" && !!env.STRIPE_SECRET_KEY;
}

export async function getStripe(): Promise<Stripe> {
  if (!env.STRIPE_SECRET_KEY) throw new Error("stripe_not_configured");
  if (!_stripe) {
    const { default: StripeCtor } = await import("stripe");
    _stripe = new StripeCtor(env.STRIPE_SECRET_KEY);
  }
  return _stripe;
}

/** Ensure a Stripe customer exists for an org; returns customer id. */
async function ensureCustomer(tx: Tx, orgId: string): Promise<string> {
  const [sub] = await tx
    .select()
    .from(subscriptions)
    .where(eq(subscriptions.orgId, orgId))
    .limit(1);
  if (sub?.stripeCustomerId) return sub.stripeCustomerId;

  const [org] = await tx
    .select()
    .from(organizations)
    .where(eq(organizations.id, orgId))
    .limit(1);
  const customer = await (await getStripe()).customers.create({
    name: org?.name,
    metadata: { orgId },
  });
  if (sub) {
    await tx
      .update(subscriptions)
      .set({ stripeCustomerId: customer.id })
      .where(eq(subscriptions.id, sub.id));
  } else {
    await tx
      .insert(subscriptions)
      .values({ orgId, stripeCustomerId: customer.id, status: "incomplete" });
  }
  return customer.id;
}

/** Create a Checkout session to subscribe an org to a plan. Returns the URL. */
export async function createCheckout(
  orgId: string,
  planId: string,
): Promise<string> {
  return withBypass(async (tx) => {
    const [plan] = await tx.select().from(plans).where(eq(plans.id, planId)).limit(1);
    if (!plan?.stripePriceId) throw new Error("plan_has_no_price");
    const customer = await ensureCustomer(tx, orgId);
    const session = await (await getStripe()).checkout.sessions.create({
      mode: "subscription",
      customer,
      line_items: [{ price: plan.stripePriceId, quantity: 1 }],
      metadata: { orgId, planId },
      success_url: env.STRIPE_PORTAL_RETURN_URL ?? env.WEB_ORIGIN,
      cancel_url: env.STRIPE_PORTAL_RETURN_URL ?? env.WEB_ORIGIN,
    });
    return session.url ?? "";
  });
}

/** Create a Stripe Customer Portal session (manage payment / invoices / plan). */
export async function createPortal(orgId: string): Promise<string> {
  return withBypass(async (tx) => {
    const customer = await ensureCustomer(tx, orgId);
    const portal = await (await getStripe()).billingPortal.sessions.create({
      customer,
      return_url: env.STRIPE_PORTAL_RETURN_URL ?? env.WEB_ORIGIN,
    });
    return portal.url;
  });
}

const SUSPENDED = new Set(["past_due", "unpaid", "canceled", "incomplete_expired"]);

/** Verify + apply a Stripe webhook: sync subscription status → org lifecycle. */
export async function handleWebhook(
  payload: string,
  signature: string,
): Promise<void> {
  const secret = env.STRIPE_WEBHOOK_SECRET;
  if (!secret) throw new Error("webhook_secret_missing");
  const event = (await getStripe()).webhooks.constructEvent(payload, signature, secret);

  if (event.type.startsWith("customer.subscription.")) {
    const s = event.data.object as Stripe.Subscription;
    const orgId = (s.metadata?.orgId as string) ?? undefined;
    const customerId =
      typeof s.customer === "string" ? s.customer : s.customer.id;
    await withBypass(async (tx) => {
      const org = orgId ?? (await orgByCustomer(tx, customerId));
      if (!org) return;
      const status = mapStatus(s.status);
      await tx
        .insert(subscriptions)
        .values({
          orgId: org,
          stripeCustomerId: customerId,
          stripeSubscriptionId: s.id,
          status,
          currentPeriodEnd: s.current_period_end
            ? new Date(s.current_period_end * 1000)
            : null,
        })
        .onConflictDoUpdate({
          target: subscriptions.orgId,
          set: { stripeSubscriptionId: s.id, status },
        });
      await tx
        .update(organizations)
        .set({ status: SUSPENDED.has(s.status) ? "suspended" : "active" })
        .where(eq(organizations.id, org));
    });
  }
}

async function orgByCustomer(
  tx: Tx,
  customerId: string,
): Promise<string | undefined> {
  const [sub] = await tx
    .select()
    .from(subscriptions)
    .where(eq(subscriptions.stripeCustomerId, customerId))
    .limit(1);
  return sub?.orgId;
}

function mapStatus(
  s: Stripe.Subscription.Status,
): "active" | "past_due" | "canceled" | "trialing" | "incomplete" {
  switch (s) {
    case "active":
      return "active";
    case "trialing":
      return "trialing";
    case "past_due":
      return "past_due";
    case "canceled":
    case "unpaid":
    case "incomplete_expired":
      return "canceled";
    default:
      return "incomplete";
  }
}
