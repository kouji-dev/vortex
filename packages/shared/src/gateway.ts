import { z } from "zod";

// Gateway API surface schemas. Deliberately permissive (.passthrough()) — we validate
// only the fields the gateway itself reads; everything else is forwarded to the upstream
// provider untouched. OpenAI Chat is the canonical internal format (hub-and-spoke).

// ── OpenAI Chat Completions (/v1/chat/completions) — canonical inbound ──
export const chatMessageSchema = z
  .object({
    role: z.string(),
    content: z.union([z.string(), z.array(z.unknown())]).nullable().optional(),
  })
  .passthrough();
export type ChatMessage = z.infer<typeof chatMessageSchema>;

export const streamOptionsSchema = z
  .object({
    include_usage: z.boolean().optional(),
  })
  .passthrough();

export const chatCompletionRequestSchema = z
  .object({
    model: z.string(),
    messages: z.array(chatMessageSchema),
    stream: z.boolean().optional(),
    max_tokens: z.number().int().optional(),
    temperature: z.number().optional(),
    tools: z.array(z.unknown()).optional(),
    stream_options: streamOptionsSchema.optional(),
  })
  .passthrough();
export type ChatCompletionRequest = z.infer<typeof chatCompletionRequestSchema>;

// ── Anthropic Messages (/v1/messages) — inbound adapter → canonical ──
export const anthropicMessagesRequestSchema = z
  .object({
    model: z.string(),
    messages: z.array(z.unknown()),
    max_tokens: z.number().int(),
    system: z.union([z.string(), z.array(z.unknown())]).optional(),
    stream: z.boolean().optional(),
  })
  .passthrough();
export type AnthropicMessagesRequest = z.infer<
  typeof anthropicMessagesRequestSchema
>;

// ── OpenAI Responses (/v1/responses) — inbound adapter → canonical ──
export const openAIResponsesRequestSchema = z
  .object({
    model: z.string(),
    input: z.union([z.string(), z.array(z.unknown())]),
    stream: z.boolean().optional(),
  })
  .passthrough();
export type OpenAIResponsesRequest = z.infer<
  typeof openAIResponsesRequestSchema
>;

// ── Embeddings (/v1/embeddings) ──
export const embeddingsRequestSchema = z
  .object({
    model: z.string(),
    input: z.union([
      z.string(),
      z.array(z.string()),
      z.array(z.number()),
      z.array(z.array(z.number())),
    ]),
  })
  .passthrough();
export type EmbeddingsRequest = z.infer<typeof embeddingsRequestSchema>;

// ── Canonical internal chat request (what the core handler operates on) ──
// Normalized, camelCase; every inbound format transcodes into this shape.
export const canonicalChatMessageSchema = z.object({
  role: z.string(),
  content: z.union([z.string(), z.array(z.unknown())]).nullable().optional(),
});
export type CanonicalChatMessage = z.infer<typeof canonicalChatMessageSchema>;

export const canonicalChatRequestSchema = z.object({
  model: z.string(),
  messages: z.array(canonicalChatMessageSchema),
  stream: z.boolean().optional(),
  maxTokens: z.number().int().optional(),
  temperature: z.number().optional(),
  tools: z.array(z.unknown()).optional(),
  includeUsage: z.boolean().optional(),
});
export type CanonicalChatRequest = z.infer<typeof canonicalChatRequestSchema>;

// ── Usage (normalized token counts) ──
export const usageSchema = z.object({
  promptTokens: z.number().int(),
  completionTokens: z.number().int(),
  totalTokens: z.number().int(),
  /** True when counts were estimated (e.g. chars/4 fallback), not provider-reported. */
  isEstimated: z.boolean().optional(),
});
export type Usage = z.infer<typeof usageSchema>;

// ── OpenAI-shaped error envelope (all gateway errors serialize to this) ──
export const gatewayErrorSchema = z.object({
  error: z.object({
    message: z.string(),
    type: z.string(),
    param: z.string().nullable().optional(),
    code: z.string().nullable().optional(),
  }),
});
export type GatewayError = z.infer<typeof gatewayErrorSchema>;
