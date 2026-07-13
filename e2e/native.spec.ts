import { test, expect, request } from "@playwright/test";
import { resetTenants } from "./reset";

// Phase 1 — native passthrough. Claude Code (/v1/messages) and Codex (/v1/responses)
// speak their own formats; the gateway forwards them verbatim to the matching
// family host. Asserts tools / tool_use / tool_result / system survive in BOTH
// directions (no canonical flattening), and cross-format is rejected.
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

async function lastUpstream() {
  return (await (await request.newContext()).get(`${MOCK}/__last`)).json();
}

test("Claude Code /v1/messages: tools + tool_use/result + system survive both ways", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const r = await ctx.post(`${BASE}/v1/messages`, {
    headers: { authorization: `Bearer ${prov.defaultKey}`, "anthropic-version": "2023-06-01" },
    data: {
      model: "anthropic/claude-opus-4-5",
      max_tokens: 100,
      system: [{ type: "text", text: "You are helpful." }],
      tools: [
        { name: "get_weather", description: "Get weather", input_schema: { type: "object", properties: {} } },
      ],
      messages: [
        { role: "user", content: [{ type: "text", text: "weather?" }] },
        { role: "assistant", content: [{ type: "tool_use", id: "tu1", name: "get_weather", input: {} }] },
        { role: "user", content: [{ type: "tool_result", tool_use_id: "tu1", content: "sunny" }] },
      ],
    },
  });
  expect(r.status()).toBe(200);

  // Outbound fidelity: response carries a native Anthropic tool_use block.
  const body = await r.json();
  expect(body.type).toBe("message");
  const toolUse = body.content.find((b: any) => b.type === "tool_use");
  expect(toolUse?.name).toBe("get_weather");
  expect(body.stop_reason).toBe("tool_use");

  // Inbound fidelity: the upstream received tools + system + the tool_use/result
  // blocks intact (NOT flattened to text).
  const last = await lastUpstream();
  expect(last.envelope).toBe("anthropic");
  expect(last.body.tools).toHaveLength(1);
  expect(last.body.system).toBeTruthy();
  expect(last.body.messages[1].content[0].type).toBe("tool_use");
  expect(last.body.messages[2].content[0].type).toBe("tool_result");
  // model rewritten to the host-specific upstream id (Anthropic-direct alias)
  expect(last.body.model).toBe("claude-opus-4-5");
});

test("Codex /v1/responses: tools + function_call survive; usage recorded", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const r = await ctx.post(`${BASE}/v1/responses`, {
    headers: { authorization: `Bearer ${prov.defaultKey}` },
    data: {
      model: "openai/gpt-4o-mini",
      input: [{ role: "user", content: "list files" }],
      tools: [{ type: "function", name: "apply_patch", parameters: { type: "object" } }],
      max_output_tokens: 100,
    },
  });
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body.object).toBe("response");
  const fc = body.output.find((o: any) => o.type === "function_call");
  expect(fc?.name).toBe("apply_patch");

  const last = await lastUpstream();
  expect(last.envelope).toBe("responses");
  expect(last.body.tools).toHaveLength(1);
  expect(last.body.model).toBe("gpt-4o-mini");
});

test("Codex is stateless: previous_response_id is rejected (400)", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const r = await ctx.post(`${BASE}/v1/responses`, {
    headers: { authorization: `Bearer ${prov.defaultKey}` },
    data: { model: "openai/gpt-4o-mini", input: "hi", previous_response_id: "resp_prev" },
  });
  expect(r.status()).toBe(400);
  expect((await r.json()).error.code).toBe("stateful_unsupported");
});

test("cross-format is rejected: /v1/messages to a GPT model → 400", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const r = await ctx.post(`${BASE}/v1/messages`, {
    headers: { authorization: `Bearer ${prov.defaultKey}` },
    data: {
      model: "openai/gpt-4o-mini",
      max_tokens: 50,
      messages: [{ role: "user", content: "hi" }],
    },
  });
  expect(r.status()).toBe(400);
  expect((await r.json()).error.code).toBe("cross_format_unsupported");
});
