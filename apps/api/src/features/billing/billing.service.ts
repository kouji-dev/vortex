import type Stripe from "stripe";
import { eq, sql } from "drizzle-orm";
import {
  withBypass,
  organizations,
  plans,
  subscriptions,
  stripeEvents,
  type Tx,
} from "@vortex/db";
import { env } from "@vortex/core";
import { topupCreditTx } from "./credits.service.js";

// Pin the API version the installed stripe package's types are built against —
// an account-default drift would silently change webhook/object shapes.
const STRIPE_API_VERSION: Stripe.LatestApiVersion = "2025-02-24.acacia";

let _stripe: Stripe | null = null;

export function stripeEnabled(): boolean {
  return env.TENANCY_MODE === "multi" && !!env.STRIPE_SECRET_KEY;
}

export async function getStripe(): Promise<Stripe> {
  if (!env.STRIPE_SECRET_KEY) throw new Error("stripe_not_configured");
  if (!_stripe) {
    const { default: StripeCtor } = await import("stripe");
    // Test/dev seam: STRIPE_API_BASE points the SDK at a mock Stripe server.
    let hostOverride: Partial<Stripe.StripeConfig> = {};
    if (env.STRIPE_API_BASE) {
      const u = new URL(env.STRIPE_API_BASE);
      hostOverride = {
        host: u.hostname,
        port: u.port ? Number(u.port) : undefined,
        protocol: u.protocol.replace(":", "") as "http" | "https",
      };
    }
    _stripe = new StripeCtor(env.STRIPE_SECRET_KEY, {
      apiVersion: STRIPE_API_VERSION,
      ...hostOverride,
    });
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
  // Race-safe upsert on the org unique index: if a concurrent request already
  // stored a customer id, keep it (coalesce) and return the stored winner.
  const [row] = await tx
    .insert(subscriptions)
    .values({ orgId, stripeCustomerId: customer.id, status: "incomplete" })
    .onConflictDoUpdate({
      target: subscriptions.orgId,
      set: {
        stripeCustomerId: sql`coalesce(${subscriptions.stripeCustomerId}, excluded.stripe_customer_id)`,
      },
    })
    .returning({ stripeCustomerId: subscriptions.stripeCustomerId });
  return row?.stripeCustomerId ?? customer.id;
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

/**
 * Create a payment-mode Checkout session that purchases managed credits.
 * The webhook (checkout.session.completed, kind=credit_topup) credits the
 * wallet — no direct grant here. Returns the session URL.
 */
export async function createCreditCheckout(
  orgId: string,
  amountMicro: number,
): Promise<string> {
  const amountCents = Math.round(amountMicro / 10_000); // micro-USD → cents
  if (amountCents < 50) throw new Error("amount_below_stripe_minimum");
  return withBypass(async (tx) => {
    const customer = await ensureCustomer(tx, orgId);
    const session = await (await getStripe()).checkout.sessions.create({
      mode: "payment",
      customer,
      line_items: [
        {
          quantity: 1,
          price_data: {
            currency: "usd",
            unit_amount: amountCents,
            product_data: { name: "Vortex managed credits" },
          },
        },
      ],
      metadata: { orgId, kind: "credit_topup", amountMicro: String(amountMicro) },
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

/** Verify a webhook payload's signature → the Stripe event. */
export async function verifyWebhook(
  payload: string,
  signature: string,
): Promise<Stripe.Event> {
  const secret = env.STRIPE_WEBHOOK_SECRET;
  if (!secret) throw new Error("webhook_secret_missing");
  return (await getStripe()).webhooks.constructEvent(payload, signature, secret);
}

/**
 * Apply a verified Stripe event exactly once. The FIRST statement of the tx
 * inserts the event id with ON CONFLICT DO NOTHING — no row back means this
 * event was already processed (Stripe redelivery / DLQ retry) → no-op.
 */
export async function processStripeEvent(event: Stripe.Event): Promise<void> {
  await withBypass(async (tx) => {
    const claimed = await tx
      .insert(stripeEvents)
      .values({
        id: event.id,
        type: event.type,
        created: new Date(event.created * 1000),
        processedAt: new Date(),
      })
      .onConflictDoNothing()
      .returning({ id: stripeEvents.id });
    if (claimed.length === 0) return; // replay — already applied
    await applyStripeEvent(tx, event);
  });
}

/** Verify + apply a Stripe webhook (compat wrapper). */
export async function handleWebhook(
  payload: string,
  signature: string,
): Promise<void> {
  const event = await verifyWebhook(payload, signature);
  await processStripeEvent(event);
}

async function applyStripeEvent(tx: Tx, event: Stripe.Event): Promise<void> {
  if (event.type.startsWith("customer.subscription.")) {
    await applySubscriptionEvent(tx, event);
    return;
  }
  switch (event.type) {
    case "checkout.session.completed":
      await applyCheckoutCompleted(tx, event.data.object as Stripe.Checkout.Session);
      return;
    case "invoice.paid":
      await applyInvoiceStatus(tx, event.data.object as Stripe.Invoice, "active");
      return;
    case "invoice.payment_failed":
      await applyInvoiceStatus(tx, event.data.object as Stripe.Invoice, "past_due");
      return;
    default:
      return; // unhandled event type — dedupe row still recorded
  }
}

/** current_period_end moved onto subscription items in newer API versions. */
function periodEnd(s: Stripe.Subscription): Date | null {
  const item = s.items?.data?.[0] as
    | { current_period_end?: number }
    | undefined;
  const ts =
    item?.current_period_end ??
    (s as unknown as { current_period_end?: number }).current_period_end;
  return ts ? new Date(ts * 1000) : null;
}

async function applySubscriptionEvent(
  tx: Tx,
  event: Stripe.Event,
): Promise<void> {
  const s = event.data.object as Stripe.Subscription;
  const orgId = (s.metadata?.orgId as string) ?? undefined;
  const customerId = typeof s.customer === "string" ? s.customer : s.customer.id;
  const org = orgId ?? (await orgByCustomer(tx, customerId));
  if (!org) return;

  const eventAt = new Date(event.created * 1000);
  const [existing] = await tx
    .select()
    .from(subscriptions)
    .where(eq(subscriptions.orgId, org))
    .limit(1);
  // out-of-order delivery: never let a stale event overwrite fresher state
  if (existing?.lastEventAt && eventAt < existing.lastEventAt) return;

  // sync planId from the subscription's price
  const priceId = s.items?.data?.[0]?.price?.id;
  let planId: string | undefined;
  if (priceId) {
    const [plan] = await tx
      .select()
      .from(plans)
      .where(eq(plans.stripePriceId, priceId))
      .limit(1);
    planId = plan?.id;
  }

  const status = mapStatus(s.status);
  const currentPeriodEnd = periodEnd(s);
  await tx
    .insert(subscriptions)
    .values({
      orgId: org,
      stripeCustomerId: customerId,
      stripeSubscriptionId: s.id,
      status,
      planId: planId ?? null,
      currentPeriodEnd,
      lastEventAt: eventAt,
    })
    .onConflictDoUpdate({
      target: subscriptions.orgId,
      set: {
        stripeCustomerId: customerId,
        stripeSubscriptionId: s.id,
        status,
        ...(planId && { planId }),
        currentPeriodEnd,
        lastEventAt: eventAt,
      },
    });
  await tx
    .update(organizations)
    .set({ status: SUSPENDED.has(s.status) ? "suspended" : "active" })
    .where(eq(organizations.id, org));
}

/** Payment-mode checkout for credits → credit the wallet in the SAME tx. */
async function applyCheckoutCompleted(
  tx: Tx,
  session: Stripe.Checkout.Session,
): Promise<void> {
  if (session.mode !== "payment") return;
  if (session.metadata?.kind !== "credit_topup") return;
  const orgId = session.metadata?.orgId;
  const amountMicro = Number(session.metadata?.amountMicro);
  if (!orgId || !Number.isFinite(amountMicro) || amountMicro <= 0) return;
  await topupCreditTx(tx, orgId, Math.round(amountMicro));
}

async function applyInvoiceStatus(
  tx: Tx,
  invoice: Stripe.Invoice,
  status: "active" | "past_due",
): Promise<void> {
  const customerId =
    typeof invoice.customer === "string" ? invoice.customer : invoice.customer?.id;
  if (!customerId) return;
  const org = await orgByCustomer(tx, customerId);
  if (!org) return;
  await tx
    .update(subscriptions)
    .set({ status })
    .where(eq(subscriptions.orgId, org));
  await tx
    .update(organizations)
    .set({ status: status === "active" ? "active" : "suspended" })
    .where(eq(organizations.id, org));
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
