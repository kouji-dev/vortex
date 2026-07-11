import { test, expect, request } from "@playwright/test";
import { resetTenants } from "./reset";

// Phase 0 — faithful model×host forwarding. Drives the SAME logical model to
// different hosts and asserts the gateway picks the right wire envelope + upstream
// model id (region-prefixed for Bedrock) for each. All hosts point at one mock.
const BASE = process.env.E2E_BASE ?? "http://localhost:8080";
const MOCK = process.env.E2E_MOCK ?? "http://localhost:9099";
const ORIGIN = { origin: "http://localhost:4200" };

test.beforeEach(async () => {
  await resetTenants();
});

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

async function chat(ctx: any, key: string, model: string) {
  const r = await ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${key}` },
    data: { model, messages: [{ role: "user", content: "hi" }] },
  });
  return r;
}

async function lastUpstream() {
  return (await (await request.newContext()).get(`${MOCK}/__last`)).json();
}

test("openai host → OpenAI envelope, verbatim model id", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const r = await chat(ctx, prov.defaultKey, "openai/gpt-4o-mini");
  expect(r.status()).toBe(200);
  const last = await lastUpstream();
  expect(last.envelope).toBe("openai");
  expect(last.model).toBe("gpt-4o-mini");
});

test("anthropic host → Anthropic Messages envelope + date-stamped id", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const r = await chat(ctx, prov.defaultKey, "anthropic/claude-opus-4-5");
  expect(r.status()).toBe(200);
  const last = await lastUpstream();
  expect(last.envelope).toBe("anthropic");
  // logical → host-specific upstream id (models.dev alias for Anthropic-direct)
  expect(last.model).toBe("claude-opus-4-5");
  // Messages envelope carries `system`/`messages`, not OpenAI `messages` only
  expect(last.body.max_tokens).toBeGreaterThan(0);
});

test("bedrock host → Anthropic envelope, region-prefixed id, model in URL", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const r = await chat(ctx, prov.defaultKey, "bedrock/claude-opus-4-5");
  expect(r.status()).toBe(200);
  const last = await lastUpstream();
  expect(last.envelope).toBe("anthropic-bedrock");
  // us-east-1 → `us.` inference-profile prefix on the Bedrock model id
  expect(last.model).toBe("us.anthropic.claude-opus-4-5-20251101-v1:0");
  // Bedrock takes the model in the URL; body carries anthropic_version, no `model`
  expect(last.body.anthropic_version).toBe("bedrock-2023-05-31");
  expect(last.body.model).toBeUndefined();
});

test("same logical model, two hosts → two different upstream ids", async () => {
  const { ctx, prov } = await signUpAndProvision();
  await chat(ctx, prov.defaultKey, "anthropic/claude-opus-4-5");
  const a = await lastUpstream();
  await chat(ctx, prov.defaultKey, "bedrock/claude-opus-4-5");
  const b = await lastUpstream();
  expect(a.model).not.toBe(b.model);
  expect(a.envelope).toBe("anthropic");
  expect(b.envelope).toBe("anthropic-bedrock");
});
