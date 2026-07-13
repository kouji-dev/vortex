import type { ModelFamily } from "../catalog.js";
import type { FamilyAdapter } from "./types.js";
import { openaiAdapter } from "./openai.js";
import { anthropicAdapter } from "./anthropic.js";
import { googleAdapter } from "./google.js";

// The wire ENVELOPE is chosen by the model's family, NOT the host. So Claude on
// Bedrock/Vertex uses the Anthropic adapter, Gemini on Vertex uses Google, and
// every OpenAI-compatible host (openai/azure/groq/…) uses OpenAI.
const BY_FAMILY: Record<ModelFamily, FamilyAdapter> = {
  openai: openaiAdapter,
  anthropic: anthropicAdapter,
  google: googleAdapter,
};

/** Wire-envelope adapter for a model family (defaults to OpenAI passthrough). */
export function getAdapter(family: ModelFamily | undefined): FamilyAdapter {
  return (family && BY_FAMILY[family]) ?? openaiAdapter;
}

export type { FamilyAdapter } from "./types.js";
export type { OpenAIChatCompletion } from "./types.js";
