import { test, expect, request } from "@playwright/test";
import { resetAll } from "./reset";
import { mockControl, withDb, pollUntil } from "./helpers";

const BASE = "http://localhost:8080";

// fresh single-org state (DB + Redis buckets) before each test →
// first signup provisions as owner
test.beforeEach(async () => {
  await resetAll();
  await mockControl({}); // reset mock-provider failure/stream knobs
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
  const id = keys.items[0].id;
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

// ── model resolution ──────────────────────────────────────────────────────────

test("unknown model is rejected with 400 model_not_found", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const r = await ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${prov.defaultKey}` },
    data: { model: "definitely-not-a-model-9000", messages: [{ role: "user", content: "hi" }] },
  });
  expect(r.status()).toBe(400);
  const body = await r.json();
  expect(body.error.code).toBe("model_not_found");
});

// ── upstream resilience ───────────────────────────────────────────────────────

test("a single upstream 500 is retried and the request still succeeds", async () => {
  const { ctx, prov } = await signUpAndProvision();
  await mockControl({ fail500Times: 1 });
  const r = await ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${prov.defaultKey}` },
    data: CHAT,
  });
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body.choices[0].message.content).toBeTruthy();
});

test("an upstream hang beyond the timeout surfaces as 504 upstream_timeout", async () => {
  const { ctx, prov } = await signUpAndProvision();
  // UPSTREAM_TOTAL_TIMEOUT_MS=2500 in the e2e server env; hang well past it.
  await mockControl({ hangMs: 15_000 });
  const r = await ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${prov.defaultKey}` },
    data: CHAT,
  });
  expect(r.status()).toBe(504);
  const body = await r.json();
  expect(body.error.code).toBe("upstream_timeout");
});

// ── rate limiting ─────────────────────────────────────────────────────────────

test("an RPM 429 carries x-ratelimit-limit/remaining/reset headers", async () => {
  const { ctx, prov } = await signUpAndProvision();
  let denied: import("@playwright/test").APIResponse | null = null;
  // Free plan RPM = 20 (burst) → sequential requests must hit a 429 within ~25.
  for (let i = 0; i < 30; i++) {
    const r = await ctx.post(`${BASE}/v1/chat/completions`, {
      headers: { authorization: `Bearer ${prov.defaultKey}` },
      data: CHAT,
    });
    if (r.status() === 429) {
      denied = r;
      break;
    }
    expect(r.status()).toBe(200);
  }
  expect(denied, "expected a 429 within 30 sequential requests").toBeTruthy();
  const h = denied!.headers();
  expect(Number(h["x-ratelimit-limit"])).toBe(20);
  expect(Number(h["x-ratelimit-remaining"])).toBeGreaterThanOrEqual(0);
  expect(Number(h["x-ratelimit-reset"])).toBeGreaterThan(0);
  expect(h["retry-after"]).toBeTruthy();
});

test("plan RPM is an org-wide bucket shared by every key of the org", async () => {
  const { ctx, prov } = await signUpAndProvision();

  // second key in the same org
  const minted = await ctx.post(`${BASE}/api/keys`, { data: {} });
  expect(minted.status()).toBe(201);
  const key2 = (await minted.json()).key as string;

  // exhaust the org bucket with key 1
  let exhausted = false;
  for (let i = 0; i < 30; i++) {
    const r = await ctx.post(`${BASE}/v1/chat/completions`, {
      headers: { authorization: `Bearer ${prov.defaultKey}` },
      data: CHAT,
    });
    if (r.status() === 429) {
      exhausted = true;
      break;
    }
  }
  expect(exhausted).toBeTruthy();

  // key 2 of the SAME org is throttled by the same bucket
  const r2 = await ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${key2}` },
    data: CHAT,
  });
  expect(r2.status()).toBe(429);
});

test("oversized token estimate is admitted on an idle TPM bucket (idle-bucket admission)", async () => {
  const { ctx, prov } = await signUpAndProvision();
  // Free TPM = 40_000; max_tokens 50_000 → estimate exceeds burst capacity.
  // Fresh (flushed) bucket is idle → the request must be admitted, not 429'd.
  const r = await ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${prov.defaultKey}` },
    data: { ...CHAT, max_tokens: 50_000 },
  });
  expect(r.status()).toBe(200);
});

// ── streaming: client aborts must release concurrency + meter estimated usage ─

test("aborted streams release their slots and record estimated usage", async () => {
  const { ctx, prov } = await signUpAndProvision();
  await mockControl({ streamChunks: 50, streamDelayMs: 100 });

  // abort 4 streams mid-flight (concurrency limit on the Free plan is exactly 4 —
  // a leaked slot would block the follow-up burst below)
  for (let i = 0; i < 4; i++) {
    const resp = await fetch(`${BASE}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${prov.defaultKey}`,
      },
      body: JSON.stringify({ ...CHAT, stream: true }),
    });
    expect(resp.status).toBe(200);
    const reader = resp.body!.getReader();
    await reader.read(); // first chunk arrived — stream is live
    await reader.cancel(); // …then the client walks away
  }

  // every aborted stream must have finalized a usage row with estimated tokens
  await pollUntil(
    async () => {
      const rows = await withDb(
        (sql) =>
          sql`select id from usage_records where usage_estimated = true`,
      );
      return rows.length >= 4 ? true : undefined;
    },
    { timeoutMs: 10_000, label: "estimated usage rows for aborted streams" },
  );

  // all 4 slots must be free again: a full-width parallel burst succeeds
  await mockControl({});
  const results = await Promise.all(
    Array.from({ length: 4 }, () =>
      ctx.post(`${BASE}/v1/chat/completions`, {
        headers: { authorization: `Bearer ${prov.defaultKey}` },
        data: CHAT,
      }),
    ),
  );
  for (const r of results) expect(r.status()).toBe(200);
});
