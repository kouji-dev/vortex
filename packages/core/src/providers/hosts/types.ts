import type { ModelFamily } from "../catalog.js";

export type Capability =
  | "chat"
  | "messages"
  | "responses"
  | "embeddings"
  | "models";

export type AuthStyle = "bearer" | "x-api-key" | "query";

/** BYOK / deployment options stored per provider credential (or from env). */
export interface ProviderOptions {
  azureResource?: string;
  azureApiVersion?: string;
  deployment?: string; // Azure deployment name (defaults to the model)
  region?: string; // Bedrock / Vertex region
  project?: string; // Vertex GCP project
  tokenType?: "oauth" | "apikey"; // Vertex auth mode
}

export interface EndpointCtx {
  token: string;
  /** Upstream model id (already region-prefixed by the caller when applicable). */
  model: string;
  capability: Capability;
  stream: boolean;
  /** Wire envelope — on multi-family hosts (bedrock/vertex) it picks the path. */
  family?: ModelFamily;
  options?: ProviderOptions | null;
  byokBaseUrl?: string | null;
}

/** Anthropic API version tokens for the managed clouds (sent in the body). */
export const BEDROCK_ANTHROPIC_VERSION = "bedrock-2023-05-31";
export const VERTEX_ANTHROPIC_VERSION = "vertex-2023-10-16";

/**
 * A PROVIDER (host) transport adapter. Owns everything about talking to one
 * host's HTTP surface: endpoint URL, auth, single-tenant env config, the
 * region-prefix on the model id, and — for multi-family hosts — the per-family
 * ("leg") body tweak + stream framing. The wire ENVELOPE (request/response
 * shape) is the family adapter's job; a provider never re-implements it.
 */
export interface ProviderAdapter {
  /** Stable provider id (matches ENABLED_PROVIDERS + DB provider column). */
  readonly id: string;
  /** Default upstream base URL (no trailing slash). */
  readonly defaultBaseUrl: string;
  /** How credentials are attached to the upstream request. */
  readonly authStyle: AuthStyle;
  /** Single-tenant API key from env (or undefined when unset). */
  envKey(): string | undefined;
  /** Single-tenant deployment options from env (azure/bedrock/vertex). */
  envOptions(): ProviderOptions | undefined;
  /**
   * Fallback model-name inference for unprefixed routing (e.g. `claude-*` →
   * anthropic). Catalog resolution is primary; this only guesses unknowns.
   */
  inferFromModel(model: string): boolean;
  /** Final upstream model id — region-prefixed when the host requires it. */
  upstreamModelId(
    model: string,
    opts: { regionPrefix?: boolean; region?: string | null },
  ): string;
  /** Host×family body tweak on top of the family envelope (anthropic_version). */
  adjustBody(
    body: Record<string, unknown>,
    family: ModelFamily,
  ): Record<string, unknown>;
  /** Re-frame the raw upstream stream into SSE the family adapter can read. */
  wrapStream(
    body: ReadableStream<Uint8Array>,
    family: ModelFamily,
  ): ReadableStream<Uint8Array>;
  /** Build the upstream `{ url, headers }`. */
  resolveEndpoint(ctx: EndpointCtx): {
    url: string;
    headers: Record<string, string>;
  };
}
