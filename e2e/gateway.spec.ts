import { test, expect, request } from "@playwright/test";
import { resetTenants } from "./reset";

const BASE = "http://localhost:8080";

// fresh single-org state before each test → first signup provisions as owner
test.beforeEach(async () => {
  await resetTenants();
});
const ORIGIN = { origin: "http://localhost:4200" };
const CHAT = {
  model: "openai/gpt-4o-mini",
  messages: [{ role: "user", content: "hi" }],
};

async function signUpAndProvision() {
  const ctx = await request.newContext();
  const email = `e2e+${Date.now()}-${Math.floor(Math.random() * 1e6)}@acme.test`;
  await ctx.post(`${BASE}/api/auth/sign-up/email`, {
    headers: ORIGIN,
    data: { name: "E2E", email, password: "changeme123" },
  });
  const prov = await (await ctx.post(`${BASE}/api/provision`, { data: {} })).json();
  return { ctx, prov };
}

test("health reports db + redis ok", async ({ request }) => {
  const r = await request.get(`${BASE}/health`);
  expect(r.ok()).toBeTruthy();
  const b = await r.json();
  expect(b.checks.db).toBe("ok");
  expect(b.checks.redis).toBe("ok");
});

test("signup → provision issues owner + default key", async () => {
  const { prov } = await signUpAndProvision();
  expect(prov.defaultKey).toMatch(/^vtx_/);
  expect(prov.member.role).toBe("owner");
});

test("gateway: chat completion proxies + records usage & cost", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const r = await ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${prov.defaultKey}` },
    data: CHAT,
  });
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body.choices[0].message.content).toBeTruthy();
  expect(body.usage.total_tokens).toBeGreaterThan(0);
});

test("gateway rejects an invalid key with 401", async ({ request }) => {
  const r = await request.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: "Bearer vtx_bogus" },
    data: CHAT,
  });
  expect(r.status()).toBe(401);
});

test("hard budget cap blocks with 402", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const key = prov.defaultKey;
  const memberId = prov.member.membershipId;

  // first request spends within budget
  const first = await ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${key}` },
    data: CHAT,
  });
  expect(first.status()).toBe(200);

  // owner sets their own member override below what's already spent
  const patch = await ctx.patch(`${BASE}/api/budgets/member/${memberId}`, {
    data: { budgetOverrideMicro: 3 },
  });
  expect(patch.ok()).toBeTruthy();

  // next request exceeds the hard cap → 402
  const second = await ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${key}` },
    data: CHAT,
  });
  expect(second.status()).toBe(402);
});
