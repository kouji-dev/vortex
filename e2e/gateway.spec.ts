import { test, expect, request } from "@playwright/test";
import { resetTenants } from "./reset";

const BASE = process.env.E2E_BASE ?? "http://localhost:8080";

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

test("gateway routes an OpenAI-compatible provider prefix (groq/*)", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const r = await ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${prov.defaultKey}` },
    data: { model: "groq/llama-3.3-70b-versatile", messages: [{ role: "user", content: "hi" }] },
  });
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body.choices[0].message.content).toBeTruthy();
});

test("gateway rejects an invalid key with 401", async ({ request }) => {
  const r = await request.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: "Bearer vtx_bogus" },
    data: CHAT,
  });
  expect(r.status()).toBe(401);
});

test("hard TEAM budget cap blocks with 402", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const key = prov.defaultKey;
  const teamId = prov.member.teamId;

  // first request spends within budget
  const first = await ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${key}` },
    data: CHAT,
  });
  expect(first.status()).toBe(200);

  // owner sets the TEAM pool cap below what's already spent
  const patch = await ctx.patch(`${BASE}/api/budgets/team/${teamId}`, {
    data: { budgetMicro: 3 },
  });
  expect(patch.ok()).toBeTruthy();

  // next request exceeds the hard team cap → 402
  const second = await ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${key}` },
    data: CHAT,
  });
  expect(second.status()).toBe(402);
});

test("rate-limit headers are present on a proxied request", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const r = await ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${prov.defaultKey}` },
    data: CHAT,
  });
  expect(r.status()).toBe(200);
  const h = r.headers();
  // Free plan RPM ceiling = 20 (see db seed).
  expect(h["ratelimit-limit"]).toBe("20");
  expect(Number(h["ratelimit-remaining"])).toBeGreaterThanOrEqual(0);
});

test("concurrency cap returns 429 under parallel load", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const key = prov.defaultKey;
  // Free concurrency = 4; fire 12 in parallel → some rejected with 429.
  const results = await Promise.all(
    Array.from({ length: 12 }, () =>
      ctx.post(`${BASE}/v1/chat/completions`, {
        headers: { authorization: `Bearer ${key}` },
        data: CHAT,
      }),
    ),
  );
  const codes = results.map((r) => r.status());
  expect(codes.some((c) => c === 429)).toBeTruthy();
  expect(codes.some((c) => c === 200)).toBeTruthy();
});

test("Free plan cannot set a custom per-key rate limit (403)", async () => {
  const { ctx } = await signUpAndProvision();
  const keys = await (await ctx.get(`${BASE}/api/keys`)).json();
  const id = keys[0].id;
  const r = await ctx.patch(`${BASE}/api/keys/${id}`, {
    data: { rateLimitRpm: 5 },
  });
  expect(r.status()).toBe(403);
});

test("seat cap: Free org blocks the 3rd human member (403)", async () => {
  // seat 1 (owner) + seat 2 (member) provision OK; seat 3 → 403.
  const statuses: number[] = [];
  for (let i = 0; i < 3; i++) {
    const ctx = await request.newContext();
    const email = `e2e+seat${Date.now()}-${i}-${Math.floor(Math.random() * 1e6)}@acme.test`;
    await ctx.post(`${BASE}/api/auth/sign-up/email`, {
      headers: ORIGIN,
      data: { name: "Seat", email, password: "changeme123" },
    });
    const prov = await ctx.post(`${BASE}/api/provision`, { data: {} });
    statuses.push(prov.status());
  }
  expect(statuses[0]).toBe(200);
  expect(statuses[1]).toBe(200);
  expect(statuses[2]).toBe(403);
});
