import type { CanonicalChatRequest, Usage } from "@vortex/shared";
import type { Capability } from "../hosts/types.js";
import { iterSSELines, sseData } from "../sse.js";

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
 * A wire-envelope adapter, keyed by model FAMILY (openai | anthropic | google).
 * OpenAI Chat is canonical; each adapter maps canonical → family on the way out
 * and family → canonical on the way back. It also owns family-specific usage
 * extraction (native passthrough meters without transcoding).
 */
export interface FamilyAdapter {
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
  /**
   * Usage from a non-streamed native/raw upstream response (no transcode).
   * `capability` disambiguates the OpenAI family (chat vs responses shapes).
   */
  parseUsage(raw: unknown, capability: Capability): Usage;
  /** Read-only usage sniff over a native SSE stream (per family/capability). */
  sniffStreamUsage(
    stream: ReadableStream<Uint8Array>,
    capability: Capability,
  ): Promise<Usage>;
}

/**
 * Shared read-only SSE usage-sniff loop for native passthrough. `visit` updates
 * the running counts per parsed chunk; family adapters supply the per-shape rule.
 */
export async function sniffSSE(
  stream: ReadableStream<Uint8Array>,
  visit: (chunk: any, acc: { prompt: number; completion: number }) => void,
): Promise<Usage> {
  const acc = { prompt: 0, completion: 0 };
  try {
    for await (const line of iterSSELines(stream)) {
      const data = sseData(line);
      if (!data) continue;
      let j: any;
      try {
        j = JSON.parse(data);
      } catch {
        continue;
      }
      visit(j, acc);
    }
  } catch {
    /* best-effort metering */
  }
  return {
    promptTokens: acc.prompt,
    completionTokens: acc.completion,
    totalTokens: acc.prompt + acc.completion,
  };
}

let counter = 0;
export function newCompletionId(): string {
  return `chatcmpl-${Date.now().toString(36)}${(counter++).toString(36)}`;
}

/** Rough token estimate when a provider omits usage (≈ chars / 4). */
export function estTokens(chars: number): number {
  return Math.max(0, Math.ceil(chars / 4));
}
