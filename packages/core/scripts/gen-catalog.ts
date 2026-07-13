/**
 * Regenerate src/providers/models.json from models.dev.
 *
 *   pnpm --filter @vortex/core gen:catalog
 *
 * Enumerates EVERY model models.dev lists for the providers we support (no
 * hand-picked allow-list, so new/recent models appear automatically). Guards:
 *   • only providers in HOST_TO_MDEV,
 *   • only (host, family) combos our transport can actually serve,
 *   • only chat LLMs + embeddings (image/tts/audio/video/rerank skipped),
 *   • only models with an input price (unbillable ones skipped).
 * The same logical model served by several hosts is merged (Claude on anthropic/
 * bedrock/vertex → one entry, three hosts) via id normalization. Output is
 * data-only JSON that `catalog.ts` imports; no catalog values live in source.
 */
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const MODELS_JSON = resolve(__dirname, "../src/providers/models.json");
const MODELS_DEV = "https://models.dev/api.json";
// OpenRouter enriches each model with Artificial Analysis quality scores +
// Hugging Face id (matched by normalized id). Best-effort; catalog still builds
// if it's unreachable. (Note: OpenRouter's usage/trending is NOT in the public
// API — that comes from our own usage_records.)
const OPENROUTER = "https://openrouter.ai/api/v1/models";

type Family = "openai" | "anthropic" | "google";
type Modality = "text" | "multimodal" | "embedding";

// our host id → models.dev provider id (iteration order also picks the
// display-name / first-party source when a model is served by several hosts).
const HOST_TO_MDEV: Record<string, string> = {
  openai: "openai",
  anthropic: "anthropic",
  google: "google",
  azure: "azure",
  bedrock: "amazon-bedrock",
  vertex: "google-vertex",
  groq: "groq",
  mistral: "mistral",
  deepseek: "deepseek",
  xai: "xai",
  together: "togetherai",
  fireworks: "fireworks-ai",
};

// Hosts that speak the OpenAI wire envelope for every model they serve.
const OPENAI_WIRE = new Set([
  "openai",
  "groq",
  "mistral",
  "deepseek",
  "xai",
  "together",
  "fireworks",
]);

// Azure via models.dev is multi-vendor (Azure AI Foundry), but our transport is
// Azure OpenAI only — restrict to genuine OpenAI-deployment model families.
const AZURE_OPENAI = /^(gpt|chatgpt|o[1-9]|text-embedding|ada|babbage|davinci|codex|computer-use)/;

interface MdevModel {
  id?: string;
  name?: string;
  cost?: { input?: number; output?: number; cache_read?: number; cache_write?: number };
  limit?: { context?: number; output?: number };
  modalities?: { input?: string[]; output?: string[] };
  tool_call?: boolean;
  reasoning?: boolean;
  structured_output?: boolean;
  open_weights?: boolean;
  release_date?: string;
  knowledge?: string;
  last_updated?: string;
  description?: string;
}
type MdevApi = Record<string, { models: Record<string, MdevModel> }>;

const per1kMicro = (usdPerMillion?: number): number | null =>
  usdPerMillion == null ? null : Math.round(usdPerMillion * 1000);

/** Wire envelope our transport uses for (host, upstream-id), or null if unsupported. */
function familyFor(host: string, id: string): Family | null {
  if (host === "azure") return AZURE_OPENAI.test(id.toLowerCase()) ? "openai" : null;
  if (OPENAI_WIRE.has(host)) return "openai";
  if (host === "anthropic") return "anthropic";
  if (host === "google") return "google";
  // Bedrock: only Claude (Anthropic envelope) — other Bedrock models aren't wired.
  if (host === "bedrock") return /(^|\.)anthropic\.|claude/.test(id) ? "anthropic" : null;
  // Vertex: Claude (anthropic) + Gemini (google) only.
  if (host === "vertex")
    return id.includes("claude") ? "anthropic" : id.includes("gemini") ? "google" : null;
  return null;
}

/** Chat/embedding classification, or null to skip (image/tts/audio/video/…). */
function classify(m: MdevModel, host: string): Modality | null {
  const id = (m.id ?? "").toLowerCase();
  const out = m.modalities?.output ?? [];
  const inp = m.modalities?.input ?? [];
  if (/embed/.test(id)) return host === "openai" || host === "azure" ? "embedding" : null;
  if (!out.includes("text")) return null; // image / audio / video / tts generators
  if (/(whisper|tts|transcrib|moderation|rerank|guard|image)/.test(id)) return null;
  return inp.includes("image") ? "multimodal" : "text";
}

/** Normalize a provider-specific id to a cross-provider logical id (for merging). */
function canonicalId(host: string, id: string): string {
  let s = id.toLowerCase();
  if (host === "bedrock") {
    s = s.replace(/^(global|us|eu|apac|jp|au|ca|sa|me|af)\./, "");
    s = s.replace(
      /^(anthropic|meta|amazon|mistral|cohere|ai21|deepseek|openai|stability|writer|qwen|luma|twelvelabs|nova)\./,
      "",
    );
    s = s.replace(/[-:]v\d+(:\d+)?$/, ""); // -v1:0
  }
  if (host === "vertex") s = s.replace(/@[a-z0-9._-]+$/, ""); // @20251101, @default…
  s = s.replace(/^[^/]*\//, ""); // vendor path prefix: meta-llama/… → …
  s = s.replace(/-\d{8}$/, ""); // trailing date stamp
  return s;
}

function features(m: MdevModel, chat: boolean): Record<string, boolean> {
  const f: Record<string, boolean> = {};
  if (m.tool_call) f.tools = true;
  if (m.modalities?.input?.includes("image")) f.vision = true;
  if (m.reasoning) f.reasoning = true;
  if (m.cost?.cache_read != null) f.caching = true;
  if (chat) f.streaming = true; // gateway streams every chat family
  if (m.structured_output) f.jsonSchema = true;
  return f;
}

function hostConfig(host: string, family: Family): Record<string, unknown> | undefined {
  if (host === "bedrock" && family === "anthropic") return { regionPrefix: true };
  if (host === "vertex")
    return { publisher: family === "anthropic" ? "anthropic" : "google" };
  if (host === "azure") return { deploymentIsModel: true };
  return undefined;
}

interface Row {
  host: string;
  family: Family;
  upstreamModelId: string;
  canonical: string;
  displayName: string;
  modality: Modality;
  m: MdevModel;
  regions?: string[];
}

function buildHostRow(r: Row): Record<string, unknown> {
  const m = r.m;
  const chat = r.modality !== "embedding";
  const row: Record<string, unknown> = {
    host: r.host,
    family: r.family,
    upstreamModelId: r.upstreamModelId,
    inputPer1kMicro: per1kMicro(m.cost?.input) ?? 0,
    outputPer1kMicro: per1kMicro(m.cost?.output) ?? 0,
  };
  const cacheRead = per1kMicro(m.cost?.cache_read);
  const cacheWrite = per1kMicro(m.cost?.cache_write);
  if (cacheRead != null) row.cachedInputPer1kMicro = cacheRead;
  if (cacheWrite != null) row.cacheWritePer1kMicro = cacheWrite;
  if (m.limit?.context != null) row.contextWindow = m.limit.context;
  if (m.limit?.output != null) row.maxOutput = m.limit.output;
  if (r.regions?.length) row.regions = r.regions.sort();
  const feat = features(m, chat);
  if (Object.keys(feat).length) row.supportedFeatures = feat;
  if (m.modalities)
    row.modalities = { input: m.modalities.input ?? [], output: m.modalities.output ?? [] };
  if (m.release_date) row.releaseDate = m.release_date;
  if (m.knowledge) row.knowledge = m.knowledge;
  if (m.last_updated) row.lastUpdated = m.last_updated;
  if (m.open_weights != null) row.openWeights = m.open_weights;
  if (m.description) row.description = m.description;
  const cfg = hostConfig(r.host, r.family);
  if (cfg) row.config = cfg;
  return row;
}

/** Prefer the alias (id === canonical) over dated ids; else the most recent. */
function preferRow(a: Row, b: Row): Row {
  const aliasA = a.upstreamModelId.toLowerCase().replace(/^[^/]*\//, "") === a.canonical;
  const aliasB = b.upstreamModelId.toLowerCase().replace(/^[^/]*\//, "") === b.canonical;
  if (aliasA !== aliasB) return aliasA ? a : b;
  const da = a.m.release_date ?? a.m.last_updated ?? "";
  const db = b.m.release_date ?? b.m.last_updated ?? "";
  return da >= db ? a : b;
}

interface Stats {
  scanned: number;
  unsupportedFamily: number;
  nonChat: number;
  noPrice: number;
  missingProviders: string[];
}

function collectRows(api: MdevApi, stats: Stats): Row[] {
  // one row per (host, canonical): the best variant wins.
  const best = new Map<string, Row>();
  const consider = (host: string, upstreamId: string, m: MdevModel, regions?: string[]) => {
    stats.scanned++;
    const family = familyFor(host, upstreamId);
    if (!family) return void stats.unsupportedFamily++;
    const modality = classify(m, host);
    if (!modality) return void stats.nonChat++;
    if (per1kMicro(m.cost?.input) == null) return void stats.noPrice++;
    const canonical = canonicalId(host, upstreamId);
    if (!canonical) return;
    const row: Row = {
      host,
      family,
      upstreamModelId: upstreamId,
      canonical,
      displayName: m.name ?? canonical,
      modality,
      m,
      regions,
    };
    const key = `${host}::${canonical}`;
    const cur = best.get(key);
    best.set(key, cur ? preferRow(cur, row) : row);
  };

  for (const [host, mdevId] of Object.entries(HOST_TO_MDEV)) {
    const prov = api[mdevId];
    if (!prov) {
      stats.missingProviders.push(host);
      continue;
    }
    if (host === "bedrock") {
      // collapse region-scoped inference profiles (global./us./…) onto the base id.
      const groups = new Map<string, { regions: Set<string>; m: MdevModel }>();
      for (const [key, m] of Object.entries(prov.models)) {
        const rm = key.match(/^(global|us|eu|apac|jp|au|ca|sa|me|af)\.(.+)$/);
        const base = rm ? rm[2] : key;
        const g = groups.get(base) ?? { regions: new Set<string>(), m };
        if (rm) g.regions.add(rm[1]);
        groups.set(base, g);
      }
      for (const [base, g] of groups) consider("bedrock", base, g.m, [...g.regions]);
    } else {
      for (const [key, m] of Object.entries(prov.models)) consider(host, key, m);
    }
  }
  return [...best.values()];
}

// ── OpenRouter enrichment (quality scores + HF id) ──────────
interface OrModel {
  id: string;
  hugging_face_id?: string | null;
  benchmarks?: {
    artificial_analysis?: {
      intelligence_index?: number;
      coding_index?: number;
      agentic_index?: number;
    };
  };
}
interface OrEnrich {
  intelligenceIndex?: number;
  codingIndex?: number;
  agenticIndex?: number;
  huggingFaceId?: string;
}

/** Normalize an id for cross-source matching: drop vendor prefix + `:variant`, dots→dashes. */
function normId(id: string): string {
  return id.split("/").pop()!.split(":")[0].toLowerCase().replace(/\./g, "-");
}

async function fetchOpenRouter(): Promise<Map<string, OrEnrich>> {
  const map = new Map<string, OrEnrich>();
  try {
    const res = await fetch(OPENROUTER);
    if (!res.ok) return map;
    const data = ((await res.json()) as { data?: OrModel[] }).data ?? [];
    for (const m of data) {
      const key = normId(m.id);
      const aa = m.benchmarks?.artificial_analysis;
      const cur = map.get(key) ?? {};
      if (aa?.intelligence_index != null) cur.intelligenceIndex = aa.intelligence_index;
      if (aa?.coding_index != null) cur.codingIndex = aa.coding_index;
      if (aa?.agentic_index != null) cur.agenticIndex = aa.agentic_index;
      if (m.hugging_face_id) cur.huggingFaceId = m.hugging_face_id;
      map.set(key, cur);
    }
  } catch {
    /* enrichment is best-effort */
  }
  return map;
}

async function main() {
  const [api, orMap] = await Promise.all([
    fetch(MODELS_DEV).then((r) => r.json()) as Promise<MdevApi>,
    fetchOpenRouter(),
  ]);
  const stats: Stats = {
    scanned: 0,
    unsupportedFamily: 0,
    nonChat: 0,
    noPrice: 0,
    missingProviders: [],
  };
  const rows = collectRows(api, stats);

  // group (host rows) into logical models by canonical id.
  const byId = new Map<string, Record<string, unknown>>();
  for (const r of rows) {
    let cm = byId.get(r.canonical);
    if (!cm) {
      cm = { id: r.canonical, displayName: r.displayName, modality: r.modality, hosts: [] };
      byId.set(r.canonical, cm);
    }
    if (r.modality === "multimodal" && cm.modality === "text") cm.modality = "multimodal";
    (cm.hosts as unknown[]).push(buildHostRow(r));
  }

  // Enrich each model with OpenRouter quality scores + HF id (matched by id).
  let enriched = 0;
  for (const cm of byId.values()) {
    const e = orMap.get(normId(cm.id as string));
    if (!e) continue;
    if (e.intelligenceIndex != null) cm.intelligenceIndex = e.intelligenceIndex;
    if (e.codingIndex != null) cm.codingIndex = e.codingIndex;
    if (e.agenticIndex != null) cm.agenticIndex = e.agenticIndex;
    if (e.huggingFaceId) cm.huggingFaceId = e.huggingFaceId;
    if (e.intelligenceIndex != null || e.huggingFaceId) enriched++;
  }

  // Newest models first: sort by release date desc (undated sink to the bottom,
  // tie-break by id for stability).
  const releasedAt = (m: Record<string, unknown>): string => {
    let latest = "";
    for (const h of m.hosts as Array<{ releaseDate?: string }>)
      if (h.releaseDate && h.releaseDate > latest) latest = h.releaseDate;
    return latest;
  };
  const catalog = [...byId.values()].sort((a, b) => {
    const ra = releasedAt(a);
    const rb = releasedAt(b);
    if (ra !== rb) return ra && rb ? rb.localeCompare(ra) : ra ? -1 : 1;
    return (a.id as string).localeCompare(b.id as string);
  });
  writeFileSync(MODELS_JSON, JSON.stringify(catalog, null, 2) + "\n");

  const hostRows = catalog.reduce((n, m) => n + (m.hosts as unknown[]).length, 0);
  console.log(`✓ wrote models.json — ${catalog.length} models / ${hostRows} host rows`);
  console.log(`  enriched ${enriched}/${catalog.length} from OpenRouter (${orMap.size} OR models matched by id)`);
  console.log(
    `  scanned ${stats.scanned}; skipped: ${stats.unsupportedFamily} unsupported-family, ` +
      `${stats.nonChat} non-chat, ${stats.noPrice} no-price`,
  );
  if (stats.missingProviders.length)
    console.log(`  ⚠ providers absent on models.dev: ${stats.missingProviders.join(", ")}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
