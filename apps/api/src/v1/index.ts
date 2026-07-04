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
import { handleChat, handleEmbeddings, type ChatResult } from "./core.js";
import {
  messagesToCanonical,
  canonicalToMessagesResponse,
  canonicalStreamToMessages,
} from "./format/messages.js";
import {
  responsesToCanonical,
  canonicalToResponses,
  canonicalStreamToResponses,
} from "./format/responses.js";

const SSE_HEADERS = {
  "content-type": "text/event-stream; charset=utf-8",
  "cache-control": "no-cache",
  connection: "keep-alive",
};

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
  if (result.kind === "error") return c.json(result.body as object, result.status as any);
  if (result.kind === "stream")
    return new Response(result.stream, { headers: SSE_HEADERS });
  return c.json(result.openai);
});

// ── POST /v1/messages (Anthropic Messages → canonical) ────────
gatewayRouter.post("/messages", async (c) => {
  const parsed = anthropicMessagesRequestSchema.safeParse(await c.req.json().catch(() => null));
  if (!parsed.success) {
    return c.json(errJson("Invalid messages request.", "invalid_request_error"), 400);
  }
  const ctx = c.get("gateway");
  const canonical = messagesToCanonical(parsed.data);
  let result: ChatResult;
  try {
    result = await handleChat(ctx, canonical);
  } catch (e) {
    if (isBudgetError(e))
      return c.json(errJson("Monthly budget exceeded.", "insufficient_quota", "budget_exceeded"), 402);
    throw e;
  }
  if (result.kind === "error") return c.json(result.body as object, result.status as any);
  if (result.kind === "stream")
    return new Response(canonicalStreamToMessages(result.stream, result.model), {
      headers: SSE_HEADERS,
    });
  return c.json(canonicalToMessagesResponse(result.openai));
});

// ── POST /v1/responses (OpenAI Responses → canonical) ─────────
gatewayRouter.post("/responses", async (c) => {
  const parsed = openAIResponsesRequestSchema.safeParse(await c.req.json().catch(() => null));
  if (!parsed.success) {
    return c.json(errJson("Invalid responses request.", "invalid_request_error"), 400);
  }
  const ctx = c.get("gateway");
  const canonical = responsesToCanonical(parsed.data);
  let result: ChatResult;
  try {
    result = await handleChat(ctx, canonical);
  } catch (e) {
    if (isBudgetError(e))
      return c.json(errJson("Monthly budget exceeded.", "insufficient_quota", "budget_exceeded"), 402);
    throw e;
  }
  if (result.kind === "error") return c.json(result.body as object, result.status as any);
  if (result.kind === "stream")
    return new Response(canonicalStreamToResponses(result.stream, result.model), {
      headers: SSE_HEADERS,
    });
  return c.json(canonicalToResponses(result.openai));
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
  if (result.kind === "error") return c.json(result.body as object, result.status as any);
  if (result.kind === "json") return c.json(result.openai);
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
