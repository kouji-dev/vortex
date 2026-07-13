import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { resetAll } from "./reset";
import {
  BASE,
  MULTI_BASE,
  CHAT,
  MOCK_COST_MICRO,
  signUpAndProvision,
  withDb,
  pollUntil,
  sendStripeEvent,
  subscriptionEvent,
  invoiceEvent,
  creditTopupEvent,
  eventId,
  seedManagedProviderKey,
  setPlanPrices,
} from "./helpers";

// Billing-plane business scenarios. Stripe is mocked at the webhook boundary:
// the specs POST event JSON with a REAL `stripe-signature` (HMAC with the
// configured whsec) — verifyWebhook runs unmodified. Checkout/portal calls go
// to the mock Stripe server via STRIPE_API_BASE.
//
// Multi server (:8081) = managed SaaS billing; single server (:8080) = budgets/seats.

test.beforeEach(async () => {
  await resetAll();
});

async function orgStatus(orgId: string): Promise<string> {
  return withDb(async (sql) => {
    const [row] = await sql`select status from organizations where id = ${orgId}`;
    return row?.status as string;
  });
}

async function getSubscription(ctx: any) {
  const r = await ctx.get(`${MULTI_BASE}/api/billing`);
  expect(r.status()).toBe(200);
  return (await r.json()).subscription;
}

async function walletBalance(ctx: any): Promise<number> {
  const r = await ctx.get(`${MULTI_BASE}/api/billing/credits`);
  expect(r.status()).toBe(200);
  return (await r.json()).balanceMicro as number;
}

/** Provision a managed org on the multi server: keyMode managed + pool key. */
async function managedOrg(markupBps = 2500) {
  const { ctx, prov } = await signUpAndProvision(MULTI_BASE);
  expect(prov.member.role).toBe("owner");
  await seedManagedProviderKey("openai", "test-mock");
  const r = await ctx.patch(`${MULTI_BASE}/api/billing/key-mode`, {
    data: { keyMode: "managed", markupBps },
  });
  expect(r.status()).toBe(200);
  return { ctx, prov };
}

/** Credit an org's wallet through the real webhook path. */
async function topupViaWebhook(ctx: any, orgId: string, amountMicro: number) {
  const status = await sendStripeEvent(ctx, creditTopupEvent({ orgId, amountMicro }));
  expect(status).toBe(200);
}

// ── 1. subscription lifecycle ────────────────────────────────────────────────

test("subscription lifecycle: created → plan change → past_due → deleted → invoice events", async () => {
  await setPlanPrices();
  const { ctx, prov } = await signUpAndProvision(MULTI_BASE);
  const orgId = prov.member.orgId;
  const customer = `cus_e2e_${randomUUID()}`;
  const t = Math.floor(Date.now() / 1000) - 100;

  // created (active, Pro price) → org active + planId synced
  expect(
    await sendStripeEvent(
      ctx,
      subscriptionEvent({
        type: "customer.subscription.created",
        createdSec: t,
        orgId,
        customer,
        status: "active",
        priceId: "price_pro_e2e",
      }),
    ),
  ).toBe(200);
  let sub = await getSubscription(ctx);
  expect(sub.status).toBe("active");
  expect(sub.planId).toBe("plan_pro");
  expect(await orgStatus(orgId)).toBe("active");

  // updated (plan change → Enterprise price) → planId switches
  await sendStripeEvent(
    ctx,
    subscriptionEvent({
      createdSec: t + 10,
      orgId,
      customer,
      status: "active",
      priceId: "price_ent_e2e",
    }),
  );
  sub = await getSubscription(ctx);
  expect(sub.planId).toBe("plan_enterprise");

  // past_due sync → subscription past_due + org suspended
  await sendStripeEvent(
    ctx,
    subscriptionEvent({
      createdSec: t + 20,
      orgId,
      customer,
      status: "past_due",
      priceId: "price_ent_e2e",
    }),
  );
  sub = await getSubscription(ctx);
  expect(sub.status).toBe("past_due");
  expect(await orgStatus(orgId)).toBe("suspended");

  // deleted → canceled
  await sendStripeEvent(
    ctx,
    subscriptionEvent({
      type: "customer.subscription.deleted",
      createdSec: t + 30,
      orgId,
      customer,
      status: "canceled",
      priceId: "price_ent_e2e",
    }),
  );
  sub = await getSubscription(ctx);
  expect(sub.status).toBe("canceled");

  // invoice.paid (resolved by customer id) → active again
  await sendStripeEvent(ctx, invoiceEvent({ type: "invoice.paid", customer }));
  sub = await getSubscription(ctx);
  expect(sub.status).toBe("active");
  expect(await orgStatus(orgId)).toBe("active");

  // invoice.payment_failed → past_due + suspended
  await sendStripeEvent(
    ctx,
    invoiceEvent({ type: "invoice.payment_failed", customer }),
  );
  sub = await getSubscription(ctx);
  expect(sub.status).toBe("past_due");
  expect(await orgStatus(orgId)).toBe("suspended");
});

// ── 2. idempotency / ordering ────────────────────────────────────────────────

test("webhook idempotency: same event id twice applies once; stale events are ignored", async () => {
  await setPlanPrices();
  const { ctx, prov } = await signUpAndProvision(MULTI_BASE);
  const orgId = prov.member.orgId;
  const customer = `cus_e2e_${randomUUID()}`;
  const t = Math.floor(Date.now() / 1000) - 100;
  const dupId = eventId("evt_dup");

  expect(
    await sendStripeEvent(
      ctx,
      subscriptionEvent({
        id: dupId,
        createdSec: t,
        orgId,
        customer,
        status: "active",
        priceId: "price_pro_e2e",
      }),
    ),
  ).toBe(200);

  // replay: SAME id but different (canceled) content → must be a no-op
  expect(
    await sendStripeEvent(
      ctx,
      subscriptionEvent({
        id: dupId,
        createdSec: t,
        orgId,
        customer,
        status: "canceled",
        priceId: "price_pro_e2e",
      }),
    ),
  ).toBe(200);
  let sub = await getSubscription(ctx);
  expect(sub.status).toBe("active");

  // stale event (created BEFORE lastEventAt) → ignored
  await sendStripeEvent(
    ctx,
    subscriptionEvent({
      createdSec: t - 50,
      orgId,
      customer,
      status: "canceled",
      priceId: "price_pro_e2e",
    }),
  );
  sub = await getSubscription(ctx);
  expect(sub.status).toBe("active");
});

// ── 3. credit top-up ─────────────────────────────────────────────────────────

test("credit topup: checkout URL, webhook credits wallet exactly once", async () => {
  const { ctx, prov } = await signUpAndProvision(MULTI_BASE);
  const orgId = prov.member.orgId;

  // managed org + Stripe enabled → topup returns a Checkout URL (mock Stripe)
  const r = await ctx.post(`${MULTI_BASE}/api/billing/credits/topup`, {
    data: { amountMicro: 5_000_000 },
  });
  expect(r.status()).toBe(200);
  const { url } = await r.json();
  expect(url).toContain("checkout.stripe.mock");

  // checkout.session.completed (kind=credit_topup) → wallet credited
  const evt = creditTopupEvent({ orgId, amountMicro: 5_000_000 });
  expect(await sendStripeEvent(ctx, evt)).toBe(200);
  expect(await walletBalance(ctx)).toBe(5_000_000);

  // replay of the SAME event → no double credit
  expect(await sendStripeEvent(ctx, evt)).toBe(200);
  expect(await walletBalance(ctx)).toBe(5_000_000);
});

// ── 4. managed deduction ─────────────────────────────────────────────────────

test("managed chat debits wallet with markup and writes a ledger row tied to the request", async () => {
  const { ctx, prov } = await managedOrg(2500); // 25% markup
  const orgId = prov.member.orgId;
  await topupViaWebhook(ctx, orgId, 5_000_000);

  const r = await ctx.post(`${MULTI_BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${prov.defaultKey}` },
    data: CHAT,
  });
  expect(r.status()).toBe(200);

  const charge = Math.round(MOCK_COST_MICRO * 1.25); // 6 × 1.25 → 8
  expect(await walletBalance(ctx)).toBe(5_000_000 - charge);

  const rows = await withDb(
    (sql) =>
      sql`select delta_micro, request_id from credit_ledger
          where org_id = ${orgId} and reason = 'spend'`,
  );
  expect(rows.length).toBe(1);
  expect(Number(rows[0]!.delta_micro)).toBe(-charge);
  expect(rows[0]!.request_id).toBeTruthy();

  const usage = await withDb(
    (sql) =>
      sql`select request_id, cost_micro from usage_records where org_id = ${orgId}`,
  );
  expect(usage.length).toBe(1);
  expect(usage[0]!.request_id).toBe(rows[0]!.request_id);
  expect(Number(usage[0]!.cost_micro)).toBe(MOCK_COST_MICRO);
});

test("managed org with empty wallet gets 402 credits_exhausted", async () => {
  const { ctx, prov } = await managedOrg(0);
  const r = await ctx.post(`${MULTI_BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${prov.defaultKey}` },
    data: { ...CHAT, max_tokens: 1000 },
  });
  expect(r.status()).toBe(402);
  const body = await r.json();
  expect(body.error.code).toBe("credits_exhausted");
});

test("concurrent burst on a near-zero wallet never drives the balance negative", async () => {
  const { ctx, prov } = await managedOrg(2500);
  const orgId = prov.member.orgId;
  await topupViaWebhook(ctx, orgId, 20); // 20 micro-USD ≈ 2–3 requests worth

  const results = await Promise.all(
    Array.from({ length: 10 }, () =>
      ctx.post(`${MULTI_BASE}/v1/chat/completions`, {
        headers: { authorization: `Bearer ${prov.defaultKey}` },
        data: { ...CHAT, max_tokens: 10 },
      }),
    ),
  );
  const codes = results.map((r) => r.status());
  expect(codes.every((c) => c === 200 || c === 402 || c === 429)).toBeTruthy();
  expect(codes.some((c) => c === 402)).toBeTruthy();

  const balance = await walletBalance(ctx);
  expect(balance).toBeGreaterThanOrEqual(0);
  const served = codes.filter((c) => c === 200).length;
  const charge = Math.round(MOCK_COST_MICRO * 1.25);
  expect(balance).toBe(20 - served * charge);
});

// ── 5. budgets (single-tenant server) ────────────────────────────────────────

test("member budget override hard-caps that member while a teammate keeps working", async () => {
  const owner = await signUpAndProvision(BASE);
  const member = await signUpAndProvision(BASE);
  expect(member.prov.member.role).toBe("member");

  // hard member cap of 3 micro (one mock request costs 6)
  const patch = await owner.ctx.patch(
    `${BASE}/api/budgets/member/${member.prov.member.membershipId}`,
    { data: { budgetOverrideMicro: 3 } },
  );
  expect(patch.status()).toBe(200);

  // member's first request lands (estimate 0 against an empty pool)…
  const first = await member.ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${member.prov.defaultKey}` },
    data: CHAT,
  });
  expect(first.status()).toBe(200);

  // …but its 6-micro spend now exceeds the 3-micro cap → 402 (member scope)
  const second = await member.ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${member.prov.defaultKey}` },
    data: CHAT,
  });
  expect(second.status()).toBe(402);
  const body = await second.json();
  expect(body.error.code).toBe("budget_exceeded");
  expect(body.error.scope).toBe("member");

  // teammate (owner) is unaffected
  const teammate = await owner.ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${owner.prov.defaultKey}` },
    data: CHAT,
  });
  expect(teammate.status()).toBe(200);
});

test("hard team pool under concurrent burst: total spend never exceeds the cap", async () => {
  const { ctx, prov } = await signUpAndProvision(BASE);
  const teamId = prov.member.teamId;
  const CAP = 20; // micro-USD; each request holds/settles 6

  const patch = await ctx.patch(`${BASE}/api/budgets/team/${teamId}`, {
    data: { budgetMicro: CAP },
  });
  expect(patch.status()).toBe(200);

  const results = await Promise.all(
    Array.from({ length: 10 }, () =>
      ctx.post(`${BASE}/v1/chat/completions`, {
        headers: { authorization: `Bearer ${prov.defaultKey}` },
        data: { ...CHAT, max_tokens: 10 }, // estimate = 6 micro → cap admits ≤ 3
      }),
    ),
  );
  const codes = results.map((r) => r.status());
  expect(codes.some((c) => c === 200)).toBeTruthy();
  expect(codes.some((c) => c === 402)).toBeTruthy();
  expect(codes.every((c) => c === 200 || c === 402 || c === 429)).toBeTruthy();

  const budgets = await (await ctx.get(`${BASE}/api/budgets`)).json();
  const team = budgets.teams.find((t: any) => t.id === teamId);
  expect(team.spentMicro).toBeLessThanOrEqual(CAP);
  const served = codes.filter((c) => c === 200).length;
  expect(team.spentMicro).toBe(served * MOCK_COST_MICRO);
});

test("soft team enforcement: over-budget requests are tracked but served (200)", async () => {
  const { ctx, prov } = await signUpAndProvision(BASE);
  const teamId = prov.member.teamId;

  const patch = await ctx.patch(`${BASE}/api/budgets/team/${teamId}`, {
    data: { budgetMicro: 1, enforcement: "soft" },
  });
  expect(patch.status()).toBe(200);

  // way over the 1-micro pool, but soft → still served
  const r = await ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${prov.defaultKey}` },
    data: { ...CHAT, max_tokens: 100 },
  });
  expect(r.status()).toBe(200);
});

// ── 6. BYOK vs managed ───────────────────────────────────────────────────────

test("BYOK request records usage but never touches the wallet; managed debits incl. markup", async () => {
  // BYOK org: real org credential (encrypted at rest), keyMode stays byok
  const byok = await signUpAndProvision(MULTI_BASE);
  const cred = await byok.ctx.post(`${MULTI_BASE}/api/providers`, {
    data: { provider: "openai", scopeType: "org", apiKey: "test-mock" },
  });
  expect(cred.status()).toBe(201);

  const r1 = await byok.ctx.post(`${MULTI_BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${byok.prov.defaultKey}` },
    data: CHAT,
  });
  expect(r1.status()).toBe(200);

  expect(await walletBalance(byok.ctx)).toBe(0); // no wallet, no debit
  const byokLedger = await withDb(
    (sql) => sql`select * from credit_ledger where org_id = ${byok.prov.member.orgId}`,
  );
  expect(byokLedger.length).toBe(0);
  const byokUsage = await withDb(
    (sql) => sql`select * from usage_records where org_id = ${byok.prov.member.orgId}`,
  );
  expect(byokUsage.length).toBe(1);

  // Managed org: same request debits cost × (1 + markup)
  const managed = await managedOrg(2500);
  await topupViaWebhook(managed.ctx, managed.prov.member.orgId, 1_000_000);
  const r2 = await managed.ctx.post(`${MULTI_BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${managed.prov.defaultKey}` },
    data: CHAT,
  });
  expect(r2.status()).toBe(200);
  const charge = Math.round(MOCK_COST_MICRO * 1.25);
  expect(await walletBalance(managed.ctx)).toBe(1_000_000 - charge);
});

// ── 7. billing DLQ ───────────────────────────────────────────────────────────

test("DLQ: failed credit_spend is replayed by the sweeper, exactly once", async () => {
  test.setTimeout(90_000);
  const { ctx, prov } = await managedOrg(0);
  const orgId = prov.member.orgId;
  await topupViaWebhook(ctx, orgId, 1000);

  const requestId = `dlq-e2e-${randomUUID()}`;
  const payload = JSON.stringify({ orgId, costMicro: 100, markupBps: 0, requestId });
  const insertDlqRow = () =>
    withDb(
      (sql) =>
        sql`insert into failed_billing_events (id, kind, payload, error, retry_count, next_retry_at)
            values (${randomUUID()}, 'credit_spend', ${payload}::jsonb, 'e2e seeded', 0, now())`,
    );

  await insertDlqRow();
  // sweeper (DLQ_SWEEP_MS=1500) replays → wallet debited, row deleted
  await pollUntil(
    async () => {
      const rows = await withDb(
        (sql) => sql`select id from failed_billing_events`,
      );
      return rows.length === 0 ? true : undefined;
    },
    { timeoutMs: 20_000, label: "DLQ row consumed" },
  );
  expect(await walletBalance(ctx)).toBe(900);
  const ledger = await withDb(
    (sql) =>
      sql`select * from credit_ledger where request_id = ${requestId}`,
  );
  expect(ledger.length).toBe(1);

  // replay the same payload again → idempotent no-op (ledger unique request_id)
  await insertDlqRow();
  await pollUntil(
    async () => {
      const rows = await withDb(
        (sql) => sql`select id from failed_billing_events`,
      );
      return rows.length === 0 ? true : undefined;
    },
    { timeoutMs: 20_000, label: "DLQ replay consumed" },
  );
  expect(await walletBalance(ctx)).toBe(900);
  const ledgerAfter = await withDb(
    (sql) =>
      sql`select * from credit_ledger where request_id = ${requestId}`,
  );
  expect(ledgerAfter.length).toBe(1);
});

// ── 8. seats / provisioning races (single-tenant server) ────────────────────

test("concurrent /provision for the same user creates exactly one membership and one owner", async () => {
  const { request } = await import("@playwright/test");
  const ctx = await request.newContext();
  const email = `e2e+race${Date.now()}-${Math.floor(Math.random() * 1e6)}@acme.test`;
  await ctx.post(`${BASE}/api/auth/sign-up/email`, {
    headers: { origin: "http://localhost:4200" },
    data: { name: "Race", email, password: "changeme123" },
  });

  const results = await Promise.all(
    Array.from({ length: 5 }, () => ctx.post(`${BASE}/api/provision`, { data: {} })),
  );
  for (const r of results) expect(r.status()).toBe(200);

  const memberships = await withDb(
    (sql) =>
      sql`select m.id from memberships m join users u on u.id = m.user_id
          where u.email = ${email}`,
  );
  expect(memberships.length).toBe(1);

  const owners = await withDb(
    (sql) => sql`select id from memberships where role = 'owner'`,
  );
  expect(owners.length).toBe(1);
});
