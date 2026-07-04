import type { CanonicalChatRequest, Usage } from "@vortex/shared";
import type { Capability } from "@vortex/core";

// An OpenAI Chat Completion object (canonical response shape). Loosely typed —
// we normalize every provider back into this and forward extra fields untouched.
export type OpenAIChatCompletion = {
  id: string;
  object: "chat.completion";
  created: number;
  model: string;
  choices: unknown[];
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  [k: string]: unknown;
};

export type StreamTransformResult = {
  /** OpenAI-chat-shaped SSE bytes to forward downstream. */
  stream: ReadableStream<Uint8Array>;
  /** Resolves with the final normalized usage once the stream is fully read. */
  usage: Promise<Usage>;
};

/**
 * A provider spoke. OpenAI Chat is canonical; each adapter maps
 * canonical → provider on the way out and provider → canonical on the way back.
 */
export interface ProviderAdapter {
  id: string;
  /** Which registry capability/endpoint a canonical chat request maps to. */
  chatCapability: Capability;
  /** Build the upstream request body from a canonical OpenAI-chat request. */
  toProviderBody(
    req: CanonicalChatRequest,
    model: string,
    streaming: boolean,
  ): Record<string, unknown>;
  /** Normalize a non-streaming upstream JSON response → OpenAI chat + usage. */
  fromProviderResponse(
    raw: unknown,
    model: string,
  ): { openai: OpenAIChatCompletion; usage: Usage };
  /** Transform an upstream SSE stream → OpenAI-chat SSE bytes + captured usage. */
  streamTransform(
    upstream: ReadableStream<Uint8Array>,
    model: string,
  ): StreamTransformResult;
}

let counter = 0;
export function newCompletionId(): string {
  return `chatcmpl-${Date.now().toString(36)}${(counter++).toString(36)}`;
}

/** Rough token estimate when a provider omits usage (≈ chars / 4). */
export function estTokens(chars: number): number {
  return Math.max(0, Math.ceil(chars / 4));
}
