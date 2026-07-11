import { Hono } from "hono";
import { withBypass, models } from "@vortex/db";
import { listEnabledProviders } from "@vortex/core";
import {
  chatCompletionRequestSchema,
  anthropicMessagesRequestSchema,
  openAIResponsesRequestSchema,
  embeddingsRequestSchema,
  type ChatCompletionRequest,
  type CanonicalChatRequest,
} from "@vortex/shared";
import { gatewayAuth, type GatewayEnv } from "./gateway.auth.js";
import { runWithRequestCache } from "../shared/request-context.js";
import {
  handleChat,
  handleEmbeddings,
  handleNative,
  type ChatResult,
  type NativeResult,
} from "./core.js";
import type { Context } from "hono";

/** Forward provider-native request headers upstream (version/beta negotiation). */
function forwardHeaders(c: Context, names: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const n of names) {
    const v = c.req.header(n);
    if (v) out[n] = v;
  }
  return out;
}

/** Render a native-passthrough result (raw upstream shape, no transcode). */
function renderNative(c: Context, result: NativeResult): Response {
  if (result.kind === "error")
    return c.json(result.body as object, result.status as never, result.headers);
  if (result.kind === "stream")
    return new Response(result.stream, {
      headers: withHeaders(SSE_HEADERS, result.headers),
    });
  return c.json(result.json as object, 200, result.headers);
}

const SSE_HEADERS = {
  "content-type": "text/event-stream; charset=utf-8",
  "cache-control": "no-cache",
  connection: "keep-alive",
};

function withHeaders(
  base: Record<string, string>,
  extra?: Record<string, string>,
): Record<string, string> {
  return extra ? { ...base, ...extra } : base;
}

function errJson(message: string, type: string, code?: string) {
  return { error: { message, type, param: null, code: code ?? null } };
}

/** True when the thrown error is a hard-cap budget rejection. */
function isBudgetError(e: unknown): boolean {
  return (
    typeof e === "object" &&
    e !== null &&
    ((e as { name?: string }).name === "BudgetExceededError" || "scope" in e)
  );
}

function chatToCanonical(req: ChatCompletionRequest): CanonicalChatRequest {
  return {
    model: req.model,
    messages: req.messages.map((m) => ({
      role: m.role,
      content: (m.content ?? null) as CanonicalChatRequest["messages"][number]["content"],
    })),
    stream: req.stream,
    maxTokens: req.max_tokens,
    temperature: req.temperature,
    tools: req.tools,
    includeUsage: req.stream_options?.include_usage,
  };
}

export const gatewayRouter = new Hono<GatewayEnv>();

// Per-request memo scope (budget pool etc. dedup within a request).
gatewayRouter.use("*", (_c, next) => runWithRequestCache(() => next()));
gatewayRouter.use("*", gatewayAuth);

// ── POST /v1/chat/completions (canonical OpenAI Chat) ─────────
gatewayRouter.post("/chat/completions", async (c) => {
  const parsed = chatCompletionRequestSchema.safeParse(await c.req.json().catch(() => null));
  if (!parsed.success) {
    return c.json(errJson("Invalid chat request.", "invalid_request_error"), 400);
  }
  const ctx = c.get("gateway");
  const canonical = chatToCanonical(parsed.data);
  let result: ChatResult;
  try {
    result = await handleChat(ctx, canonical);
  } catch (e) {
    if (isBudgetError(e))
      return c.json(errJson("Monthly budget exceeded.", "insufficient_quota", "budget_exceeded"), 402);
    throw e;
  }
  if (result.kind === "error")
    return c.json(result.body as object, result.status as any, result.headers);
  if (result.kind === "stream")
    return new Response(result.stream, {
      headers: withHeaders(SSE_HEADERS, result.headers),
    });
  return c.json(result.openai, 200, result.headers);
});

// ── POST /v1/messages (Anthropic Messages — native passthrough) ──
// Claude Code speaks Anthropic Messages → forward verbatim to an Anthropic-family
// host (anthropic / bedrock / vertex). Tools, tool_use/result, images, thinking,
// and cache_control pass through intact; the response stays native Anthropic.
gatewayRouter.post("/messages", async (c) => {
  const raw = await c.req.json().catch(() => null);
  const parsed = anthropicMessagesRequestSchema.safeParse(raw);
  if (!parsed.success)
    return c.json(errJson("Invalid messages request.", "invalid_request_error"), 400);
  const body = parsed.data as Record<string, unknown>;
  const ctx = c.get("gateway");
  let result: NativeResult;
  try {
    result = await handleNative(ctx, {
      model: body.model as string,
      rawBody: body,
      stream: body.stream === true,
      inboundFamily: "anthropic",
      capability: "messages",
      promptChars: JSON.stringify(raw).length,
      maxTokens: (body.max_tokens as number) ?? 0,
      hasTools: Array.isArray(body.tools) && body.tools.length > 0,
      extraHeaders: forwardHeaders(c, ["anthropic-version", "anthropic-beta"]),
    });
  } catch (e) {
    if (isBudgetError(e))
      return c.json(errJson("Monthly budget exceeded.", "insufficient_quota", "budget_exceeded"), 402);
    throw e;
  }
  return renderNative(c, result);
});

// ── POST /v1/responses (OpenAI Responses — native passthrough) ──
// Codex speaks the Responses API → forward verbatim to an OpenAI-family host.
// Stateless: `previous_response_id`/`store` are not honoured (resend full input).
gatewayRouter.post("/responses", async (c) => {
  const raw = await c.req.json().catch(() => null);
  const parsed = openAIResponsesRequestSchema.safeParse(raw);
  if (!parsed.success)
    return c.json(errJson("Invalid responses request.", "invalid_request_error"), 400);
  const body = parsed.data as Record<string, unknown>;
  if (body.previous_response_id != null)
    return c.json(
      errJson(
        "previous_response_id is not supported (stateless gateway); resend the full input.",
        "invalid_request_error",
        "stateful_unsupported",
      ),
      400,
    );
  const ctx = c.get("gateway");
  let result: NativeResult;
  try {
    result = await handleNative(ctx, {
      model: body.model as string,
      rawBody: body,
      stream: body.stream === true,
      inboundFamily: "openai",
      capability: "responses",
      promptChars: JSON.stringify(raw).length,
      maxTokens: (body.max_output_tokens as number) ?? 0,
      hasTools: Array.isArray(body.tools) && body.tools.length > 0,
      extraHeaders: forwardHeaders(c, ["openai-beta"]),
    });
  } catch (e) {
    if (isBudgetError(e))
      return c.json(errJson("Monthly budget exceeded.", "insufficient_quota", "budget_exceeded"), 402);
    throw e;
  }
  return renderNative(c, result);
});

// ── POST /v1/embeddings ───────────────────────────────────────
gatewayRouter.post("/embeddings", async (c) => {
  const parsed = embeddingsRequestSchema.safeParse(await c.req.json().catch(() => null));
  if (!parsed.success) {
    return c.json(errJson("Invalid embeddings request.", "invalid_request_error"), 400);
  }
  const ctx = c.get("gateway");
  let result: ChatResult;
  try {
    result = await handleEmbeddings(ctx, parsed.data);
  } catch (e) {
    if (isBudgetError(e))
      return c.json(errJson("Monthly budget exceeded.", "insufficient_quota", "budget_exceeded"), 402);
    throw e;
  }
  if (result.kind === "error")
    return c.json(result.body as object, result.status as any, result.headers);
  if (result.kind === "json") return c.json(result.openai, 200, result.headers);
  return c.json(errJson("Unexpected stream for embeddings.", "api_error"), 500);
});

// ── GET /v1/models (catalog ∩ enabled providers) ──────────────
gatewayRouter.get("/models", async (c) => {
  const enabled = new Set(listEnabledProviders().map((p) => p.id));
  const rows = await withBypass((tx) => tx.select().from(models));
  const data = rows
    .filter((r) => enabled.has(r.provider))
    .map((r) => ({
      id: `${r.provider}/${r.modelName}`,
      object: "model" as const,
      created: Math.floor(new Date(r.effectiveAt).getTime() / 1000),
      owned_by: r.provider,
    }));
  return c.json({ object: "list", data });
});

export type GatewayRouter = typeof gatewayRouter;
