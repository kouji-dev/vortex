import { and, eq, desc } from "drizzle-orm";
import { withBypass, models } from "@vortex/db";
import type { CanonicalChatRequest, Usage } from "@vortex/shared";

export type Price = {
  inputPer1kMicro: number;
  outputPer1kMicro: number;
};

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
  const row = await withBypass(async (tx) => {
    const [r] = await tx
      .select()
      .from(models)
      .where(and(eq(models.provider, provider), eq(models.modelName, model)))
      .orderBy(desc(models.effectiveAt))
      .limit(1);
    return r;
  });
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
