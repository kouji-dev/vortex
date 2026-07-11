// Code-level catalog: the full set of (host, model) rows Vortex knows, plus
// host display metadata. This is the factual source of truth — seeded into the
// `models` table (env then org narrow which are actually offered).
//
// KEY IDEA (2-axis): a logical model (e.g. "claude-opus-4-5") is served by
// several HOSTS (anthropic / aws-bedrock / vertex), each with its own
// `upstreamModelId`, regions, and supported features. The wire envelope is the
// model's FAMILY (openai | anthropic | google) — the host only decides the
// endpoint/auth/model-id/stream framing. One host credential serves every family.

import modelsJson from "./models.json" with { type: "json" };

export type ModelFamily = "openai" | "anthropic" | "google";

export interface SupportedFeatures {
  tools?: boolean;
  vision?: boolean;
  reasoning?: boolean;
  caching?: boolean;
  webSearch?: boolean;
  /** Server-Sent-Events streaming (the gateway streams every chat family). */
  streaming?: boolean;
  /** Structured / JSON-schema constrained output (models.dev `structured_output`). */
  jsonSchema?: boolean;
}

/** Input/output modality lists (e.g. input: text/image/pdf, output: text). */
export interface Modalities {
  input: string[];
  output: string[];
}

/** One model as served by one host. */
export interface HostModel {
  /** Host id — matches the `provider` column + provider_credentials.provider. */
  host: string;
  /** Wire envelope this host serves the model in. */
  family: ModelFamily;
  /** Provider-specific upstream id (Bedrock arn-ish, Azure deployment, Vertex publisher model). */
  upstreamModelId: string;
  inputPer1kMicro: number;
  outputPer1kMicro: number;
  /** Cached-input read price (prompt caching), per 1k micro-USD. */
  cachedInputPer1kMicro?: number;
  /** Cache-write price, per 1k micro-USD. */
  cacheWritePer1kMicro?: number;
  contextWindow?: number;
  maxOutput?: number;
  /** Hosts that region-scope the id (Bedrock global/us/eu → `us.` prefix). */
  regions?: string[];
  supportedFeatures?: SupportedFeatures;
  /** Input/output modalities (text/image/pdf/audio…). */
  modalities?: Modalities;
  /** Model release date (YYYY-MM-DD). */
  releaseDate?: string;
  /** Training-knowledge cutoff (YYYY-MM). */
  knowledge?: string;
  /** models.dev last-updated date (YYYY-MM-DD). */
  lastUpdated?: string;
  /** Open-weights model. */
  openWeights?: boolean;
  /** Short human description. */
  description?: string;
  /** Host routing knobs (e.g. `{ regionPrefix: true }` for Bedrock). */
  config?: Record<string, unknown>;
  /** Pricing beyond per-token (per-second, tiered, image/audio). */
  customPricing?: Record<string, unknown>;
}

/** A logical model + everywhere it is hosted. */
export interface CatalogModel {
  /** Logical id clients send (unprefixed). */
  id: string;
  displayName: string;
  modality: "text" | "multimodal" | "embedding";
  hosts: HostModel[];
  // ── enrichment matched from OpenRouter (model-level; optional) ──
  /** Artificial Analysis intelligence index (0–100), via OpenRouter benchmarks. */
  intelligenceIndex?: number;
  /** Artificial Analysis coding index. */
  codingIndex?: number;
  /** Artificial Analysis agentic index. */
  agenticIndex?: number;
  /** Hugging Face repo id when the model is open-weights (OpenRouter). */
  huggingFaceId?: string;
}

/** Host (provider) display + branding metadata for the console + landing page. */
export interface HostMeta {
  id: string;
  name: string;
  /** Default family for this host's OpenAI-compatible models (drives inference). */
  defaultFamily: ModelFamily;
  brandColor: string;
}

export const HOSTS: HostMeta[] = [
  { id: "openai", name: "OpenAI", defaultFamily: "openai", brandColor: "#10a37f" },
  { id: "anthropic", name: "Anthropic", defaultFamily: "anthropic", brandColor: "#cc785c" },
  { id: "google", name: "Google AI Studio", defaultFamily: "google", brandColor: "#4285f4" },
  { id: "azure", name: "Azure OpenAI", defaultFamily: "openai", brandColor: "#0078d4" },
  { id: "bedrock", name: "AWS Bedrock", defaultFamily: "anthropic", brandColor: "#ff9900" },
  { id: "vertex", name: "Google Vertex AI", defaultFamily: "google", brandColor: "#34a853" },
  { id: "groq", name: "Groq", defaultFamily: "openai", brandColor: "#f55036" },
  { id: "mistral", name: "Mistral AI", defaultFamily: "openai", brandColor: "#ff7000" },
  { id: "deepseek", name: "DeepSeek", defaultFamily: "openai", brandColor: "#ff6b00" },
  { id: "xai", name: "xAI", defaultFamily: "openai", brandColor: "#000000" },
  { id: "together", name: "Together AI", defaultFamily: "openai", brandColor: "#ff6b35" },
  { id: "fireworks", name: "Fireworks AI", defaultFamily: "openai", brandColor: "#6366f1" },
];

const HOST_META = new Map(HOSTS.map((h) => [h.id, h]));
export function hostMeta(id: string): HostMeta | undefined {
  return HOST_META.get(id);
}

// Catalog DATA lives in ./models.json, generated from models.dev by
// `pnpm --filter @vortex/core gen:catalog` (scripts/gen-catalog.ts). No catalog
// values live in this file — edit the generator + JSON, never inline them here.
export const CATALOG: CatalogModel[] = modelsJson as unknown as CatalogModel[];

/** Flatten the catalog to one seed row per (host, model). */
export interface CatalogSeedRow {
  provider: string; // host
  family: ModelFamily;
  modelName: string; // logical id
  upstreamModelId: string;
  inputPer1kMicro: number;
  outputPer1kMicro: number;
  cachedInputPer1kMicro: number | null;
  cacheWritePer1kMicro: number | null;
  contextWindow: number | null;
  maxOutput: number | null;
  regions: string[] | null;
  supportedFeatures: SupportedFeatures | null;
  modalities: Modalities | null;
  releaseDate: string | null;
  knowledge: string | null;
  lastUpdated: string | null;
  openWeights: boolean | null;
  description: string | null;
  config: Record<string, unknown> | null;
  customPricing: Record<string, unknown> | null;
}

export function catalogSeedRows(): CatalogSeedRow[] {
  const rows: CatalogSeedRow[] = [];
  for (const m of CATALOG) {
    for (const h of m.hosts) {
      rows.push({
        provider: h.host,
        family: h.family,
        modelName: m.id,
        upstreamModelId: h.upstreamModelId,
        inputPer1kMicro: h.inputPer1kMicro,
        outputPer1kMicro: h.outputPer1kMicro,
        cachedInputPer1kMicro: h.cachedInputPer1kMicro ?? null,
        cacheWritePer1kMicro: h.cacheWritePer1kMicro ?? null,
        contextWindow: h.contextWindow ?? null,
        maxOutput: h.maxOutput ?? null,
        regions: h.regions ?? null,
        supportedFeatures: h.supportedFeatures ?? null,
        modalities: h.modalities ?? null,
        releaseDate: h.releaseDate ?? null,
        knowledge: h.knowledge ?? null,
        lastUpdated: h.lastUpdated ?? null,
        openWeights: h.openWeights ?? null,
        description: h.description ?? null,
        config: h.config ?? null,
        customPricing: h.customPricing ?? null,
      });
    }
  }
  return rows;
}
