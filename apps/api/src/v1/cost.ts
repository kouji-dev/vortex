import { withBypass, models } from "@vortex/db";
import { ttlMemo } from "@vortex/core";
import type { CanonicalChatRequest, Usage } from "@vortex/shared";

export type Price = {
  inputPer1kMicro: number;
  outputPer1kMicro: number;
};

type ModelRow = typeof models.$inferSelect;

/**
 * In-memory model catalog, cached 60s (the `models` table is small and changes
 * ~never). Backs both `lookupPrice` and `resolveModel` so neither hits the DB
 * on the request path. Keeps only the latest-`effectiveAt` row per model.
 */
const CATALOG_KEY = "catalog";
const catalog = ttlMemo(60_000, async (_: string) => {
  const rows = await withBypass((tx) => tx.select().from(models));
  const latest = new Map<string, ModelRow>();
  for (const r of rows) {
    const k = `${r.provider}/${r.modelName}`;
    const cur = latest.get(k);
    if (!cur || new Date(r.effectiveAt) > new Date(cur.effectiveAt)) {
      latest.set(k, r);
    }
  }
  return { rows, latest };
});

/** All catalog rows (cached). Used by resolveModel for in-memory name matching. */
export async function catalogRows(): Promise<ModelRow[]> {
  return (await catalog(CATALOG_KEY)).rows;
}

/** Drop the catalog cache after a model/pricing mutation (seed/admin). */
export function clearCatalog(): void {
  catalog.clear();
}

/** Rough token estimate from character count (≈ chars / 4). */
export function estTokensFromChars(chars: number): number {
  return Math.max(0, Math.ceil(chars / 4));
}

/** Approximate prompt-token count for a canonical request (budget pre-check). */
export function estimatePromptTokens(req: CanonicalChatRequest): number {
  let chars = 0;
  for (const m of req.messages) {
    if (typeof m.content === "string") chars += m.content.length;
    else if (m.content != null) chars += JSON.stringify(m.content).length;
  }
  return estTokensFromChars(chars);
}

/**
 * Look up the current price for a model. `override` (per-credential negotiated
 * price) wins when present. Returns null when the model is not in the catalog.
 */
export async function lookupPrice(
  provider: string,
  model: string,
  override?: { inputPer1k?: number; outputPer1k?: number } | null,
): Promise<Price | null> {
  if (override?.inputPer1k != null && override?.outputPer1k != null) {
    return {
      inputPer1kMicro: override.inputPer1k,
      outputPer1kMicro: override.outputPer1k,
    };
  }
  const row = (await catalog(CATALOG_KEY)).latest.get(`${provider}/${model}`);
  if (!row) return null;
  return {
    inputPer1kMicro: row.inputPer1kMicro,
    outputPer1kMicro: row.outputPer1kMicro,
  };
}

/** cost = prompt/1000 * in + completion/1000 * out (micro-USD, integer). */
export function costMicro(usage: Usage, price: Price | null): number {
  if (!price) return 0;
  const inCost = (usage.promptTokens / 1000) * price.inputPer1kMicro;
  const outCost = (usage.completionTokens / 1000) * price.outputPer1kMicro;
  return Math.round(inCost + outCost);
}
