import type { ProviderAdapter } from "./types.js";
import { openaiAdapter } from "./openai.js";
import { anthropicAdapter } from "./anthropic.js";
import { googleAdapter } from "./google.js";

const ADAPTERS: Record<string, ProviderAdapter> = {
  openai: openaiAdapter,
  anthropic: anthropicAdapter,
  google: googleAdapter,
  // deployment-specific providers reuse the matching wire format:
  azure: openaiAdapter, // Azure OpenAI = OpenAI Chat format
  bedrock: openaiAdapter, // Bedrock OpenAI-compat mantle
  vertex: googleAdapter, // Vertex Gemini = generateContent format
};

/** Adapter for a provider id, defaulting to OpenAI passthrough for unknowns. */
export function getAdapter(providerId: string): ProviderAdapter {
  return ADAPTERS[providerId] ?? openaiAdapter;
}

export type { ProviderAdapter } from "./types.js";
export type { OpenAIChatCompletion } from "./types.js";
