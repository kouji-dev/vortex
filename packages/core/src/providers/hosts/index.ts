import { env } from "../../config/env.js";
import type { EndpointCtx, ProviderAdapter } from "./types.js";
import {
  openaiProvider,
  groqProvider,
  mistralProvider,
  deepseekProvider,
  xaiProvider,
  togetherProvider,
  fireworksProvider,
} from "./openai.js";
import { anthropicProvider } from "./anthropic.js";
import { googleProvider } from "./google.js";
import { azureProvider } from "./azure.js";
import { bedrockProvider } from "./bedrock.js";
import { vertexProvider } from "./vertex.js";

const REGISTRY: Record<string, ProviderAdapter> = {
  openai: openaiProvider,
  anthropic: anthropicProvider,
  google: googleProvider,
  azure: azureProvider,
  bedrock: bedrockProvider,
  vertex: vertexProvider,
  groq: groqProvider,
  mistral: mistralProvider,
  deepseek: deepseekProvider,
  xai: xaiProvider,
  together: togetherProvider,
  fireworks: fireworksProvider,
};

/** Look up a provider (host) adapter by id, or `undefined` if unknown. */
export function getProviderAdapter(id: string): ProviderAdapter | undefined {
  return REGISTRY[id];
}

/** @deprecated alias of {@link getProviderAdapter}. */
export const getProvider = getProviderAdapter;

/**
 * Providers available for this deployment = code catalog ∩ ENABLED_PROVIDERS.
 * An empty ENABLED_PROVIDERS means "all providers in the code catalog".
 */
export function listEnabledProviders(): ProviderAdapter[] {
  const enabled = env.ENABLED_PROVIDERS;
  if (enabled.length === 0) return Object.values(REGISTRY);
  return enabled
    .map((id) => REGISTRY[id])
    .filter((p): p is ProviderAdapter => p !== undefined);
}

/**
 * First provider whose model-name inference matches (fallback routing for an
 * unprefixed unknown model). Catalog resolution is primary; this only guesses.
 */
export function inferProviderId(model: string): string | null {
  for (const p of Object.values(REGISTRY)) {
    if (p.inferFromModel(model)) return p.id;
  }
  return null;
}

/** @deprecated free-function shim; prefer `getProviderAdapter(id).resolveEndpoint(ctx)`. */
export function resolveEndpoint(
  providerId: string,
  ctx: EndpointCtx,
): { url: string; headers: Record<string, string> } {
  const p = getProviderAdapter(providerId);
  if (!p) throw new Error(`unknown provider '${providerId}'`);
  return p.resolveEndpoint(ctx);
}

export * from "./types.js";

/** @deprecated retained for back-compat; renamed to {@link ProviderAdapter}. */
export type { ProviderAdapter as ProviderDef } from "./types.js";
