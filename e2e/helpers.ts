import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  createHmac,
  createCipheriv,
  hkdfSync,
  randomBytes,
  randomUUID,
} from "node:crypto";
import { request, type APIRequestContext } from "@playwright/test";
import postgres from "postgres";

// ── endpoints (see playwright.config.ts webServer entries) ───────────────────
export const BASE = "http://localhost:8080"; // single-tenant / self-hosted
export const MULTI_BASE = "http://localhost:8081"; // multi-tenant / managed + Stripe
export const MOCK_PROVIDER = "http://localhost:9099";
export const ORIGIN = { origin: "http://localhost:4200" };

export const DATABASE_URL =
  process.env.DATABASE_URL ?? "postgres://vortex:vortex@localhost:5433/vortex";

// must match playwright.config.ts (multi API server env)
const STRIPE_WEBHOOK_SECRET = "whsec_e2e_test_secret";

export type Prov = {
  member: {
    membershipId: string;
    orgId: string;
    role: string;
    teamId: string;
    teamRole: string | null;
  };
  defaultKey: string;
};

/** Sign up a fresh user + provision. Works on both API instances. */
export async function signUpAndProvision(
  base: string = BASE,
): Promise<{ ctx: APIRequestContext; prov: Prov }> {
  const ctx = await request.newContext();
  const email = `e2e+${Date.now()}-${Math.floor(Math.random() * 1e6)}@acme.test`;
  await ctx.post(`${base}/api/auth/sign-up/email`, {
    headers: ORIGIN,
    data: { name: "E2E", email, password: "changeme123" },
  });
  const prov = (await (
    await ctx.post(`${base}/api/provision`, { data: {} })
  ).json()) as Prov;
  return { ctx, prov };
}

/** Owner-connection SQL tap (bypasses RLS) for seeding/asserting DB state. */
export async function withDb<T>(
  fn: (sql: postgres.Sql) => Promise<T>,
): Promise<T> {
  const sql = postgres(DATABASE_URL, { max: 1 });
  try {
    return await fn(sql);
  } finally {
    await sql.end();
  }
}

/** Poll `fn` until it returns non-undefined truthy-check result or times out. */
export async function pollUntil<T>(
  fn: () => Promise<T | undefined>,
  opts: { timeoutMs?: number; intervalMs?: number; label?: string } = {},
): Promise<T> {
  const timeoutMs = opts.timeoutMs ?? 15_000;
  const intervalMs = opts.intervalMs ?? 400;
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const v = await fn();
    if (v !== undefined) return v;
    if (Date.now() > deadline)
      throw new Error(`pollUntil timed out: ${opts.label ?? "condition"}`);
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

// ── Stripe webhook signing (real signature verification, mocked event) ───────

/** Stripe-Signature header for a payload: t=<ts>,v1=<hmac-sha256>. */
export function stripeSignature(payload: string): string {
  const t = Math.floor(Date.now() / 1000);
  const v1 = createHmac("sha256", STRIPE_WEBHOOK_SECRET)
    .update(`${t}.${payload}`)
    .digest("hex");
  return `t=${t},v1=${v1}`;
}

/** POST a (signed) Stripe event to the multi server's webhook endpoint. */
export async function sendStripeEvent(
  ctx: APIRequestContext,
  event: Record<string, unknown>,
): Promise<number> {
  const payload = JSON.stringify(event);
  const r = await ctx.post(`${MULTI_BASE}/api/stripe-webhook`, {
    headers: {
      "content-type": "application/json",
      "stripe-signature": stripeSignature(payload),
    },
    data: payload,
  });
  return r.status();
}

let evtSeq = 0;
export function eventId(prefix = "evt_e2e"): string {
  return `${prefix}_${Date.now()}_${++evtSeq}_${Math.floor(Math.random() * 1e6)}`;
}

export function subscriptionEvent(a: {
  id?: string;
  type?: string; // customer.subscription.created|updated|deleted
  createdSec: number;
  orgId?: string;
  customer: string;
  subId?: string;
  status: string;
  priceId?: string;
}): Record<string, unknown> {
  return {
    id: a.id ?? eventId(),
    object: "event",
    type: a.type ?? "customer.subscription.updated",
    created: a.createdSec,
    data: {
      object: {
        id: a.subId ?? "sub_e2e_1",
        object: "subscription",
        status: a.status,
        customer: a.customer,
        metadata: a.orgId ? { orgId: a.orgId } : {},
        items: {
          data: [
            {
              ...(a.priceId ? { price: { id: a.priceId } } : {}),
              current_period_end: a.createdSec + 30 * 24 * 3600,
            },
          ],
        },
      },
    },
  };
}

export function invoiceEvent(a: {
  type: "invoice.paid" | "invoice.payment_failed";
  customer: string;
  id?: string;
}): Record<string, unknown> {
  return {
    id: a.id ?? eventId(),
    object: "event",
    type: a.type,
    created: Math.floor(Date.now() / 1000),
    data: { object: { object: "invoice", customer: a.customer } },
  };
}

export function creditTopupEvent(a: {
  orgId: string;
  amountMicro: number;
  id?: string;
  sessionId?: string;
}): Record<string, unknown> {
  return {
    id: a.id ?? eventId(),
    object: "event",
    type: "checkout.session.completed",
    created: Math.floor(Date.now() / 1000),
    data: {
      object: {
        id: a.sessionId ?? `cs_e2e_${randomUUID()}`,
        object: "checkout.session",
        mode: "payment",
        customer: "cus_e2e_topup",
        metadata: {
          orgId: a.orgId,
          kind: "credit_topup",
          amountMicro: String(a.amountMicro),
        },
      },
    },
  };
}

// ── platform-scope encryption (matches packages/core secretbox v1) ───────────

function encryptionKeyFromEnvFile(): Buffer {
  const envText = readFileSync(resolve(process.cwd(), ".env"), "utf8");
  const m = envText.match(/^ENCRYPTION_KEY=(.+)$/m);
  if (!m) throw new Error("ENCRYPTION_KEY not found in .env");
  const raw = m[1]!.trim();
  const b64 = Buffer.from(raw, "base64");
  return b64.length > 0 ? b64 : Buffer.from(raw, "utf8");
}

/** Encrypt a managed-pool provider key exactly like encryptForOrg(PLATFORM_SCOPE, …). */
export function encryptPlatformSecret(plaintext: string): string {
  const ikm = encryptionKeyFromEnvFile();
  const key = Buffer.from(
    hkdfSync(
      "sha256",
      ikm,
      Buffer.from("__platform__", "utf8"),
      Buffer.from("vortex:provider-credentials:v1", "utf8"),
      32,
    ),
  );
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const ct = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([Buffer.from([0x01]), iv, tag, ct]).toString("base64");
}

/** Seed a platform-owned managed provider key (decryptable by the API). */
export async function seedManagedProviderKey(
  provider = "openai",
  token = "test-mock",
): Promise<void> {
  const encrypted = encryptPlatformSecret(token);
  await withDb(async (sql) => {
    await sql`insert into managed_provider_keys (id, provider, encrypted_key, enabled)
              values (${randomUUID()}, ${provider}, ${encrypted}, true)`;
  });
}

/** Give the seeded plans Stripe price ids so webhook price→plan sync resolves. */
export async function setPlanPrices(): Promise<void> {
  await withDb(async (sql) => {
    await sql`update plans set stripe_price_id = 'price_pro_e2e' where id = 'plan_pro'`;
    await sql`update plans set stripe_price_id = 'price_ent_e2e' where id = 'plan_enterprise'`;
  });
}

/** Configure the mock provider's failure/stream behavior. */
export async function mockControl(
  opts: Record<string, number>,
): Promise<void> {
  const ctx = await request.newContext();
  await ctx.post(`${MOCK_PROVIDER}/__control`, { data: opts });
  await ctx.dispose();
}

export const CHAT = {
  model: "openai/gpt-4o-mini",
  messages: [{ role: "user", content: "hi" }],
};

// Mock provider always returns usage {12, 7} → gpt-4o-mini cost:
//   12/1000×150 + 7/1000×600 = 1.8 + 4.2 = 6 micro-USD per request.
export const MOCK_COST_MICRO = 6;
