import { ADMIN_DATABASE_URL } from "./env.js";
import postgres from "postgres";
import { drizzle } from "drizzle-orm/postgres-js";
import { sql } from "drizzle-orm";
import { catalogSeedRows } from "@vortex/core";
import { plans, models, planEntitlements, pricingTiers } from "./schema.js";

const PLANS = [
  { id: "plan_free", name: "Free", priceMicro: 0, limits: {} },
  { id: "plan_pro", name: "Pro", priceMicro: 99_000_000, limits: {} },
  {
    id: "plan_enterprise",
    name: "Enterprise",
    priceMicro: null,
    limits: {},
  },
] as const;

// Per-plan governance + limits. null = unlimited.
const ENTITLEMENTS = [
  {
    planId: "plan_free",
    seatsPerOrg: 2,
    servicePerMember: 1,
    teamBudgetMicro: 50_000_000, // $50 hard team cap
    rpm: 20,
    tpm: 40_000,
    concurrency: 4,
    flags: { allowCustomRateLimit: false },
  },
  {
    planId: "plan_pro",
    seatsPerOrg: 10,
    servicePerMember: 3,
    teamBudgetMicro: null,
    rpm: 600,
    tpm: 2_000_000,
    concurrency: 50,
    flags: { allowCustomRateLimit: true },
  },
  {
    planId: "plan_enterprise",
    seatsPerOrg: null,
    servicePerMember: null,
    teamBudgetMicro: null,
    rpm: null,
    tpm: null,
    concurrency: null,
    flags: { allowCustomRateLimit: true },
  },
] as const;

// Graduated (volume-tiered) unit pricing — billing plane (managed) only.
// unitPriceMicro × quantity_in_tier = charge. upToQty null = final tier.
const PRICING_TIERS = [
  // Pro: $25 / seat / month
  { scopeType: "plan", scopeId: "plan_pro", meter: "seats", upToQty: null, unitPriceMicro: 25_000_000 },
  // Pro: request overage, stepping down with volume
  { scopeType: "plan", scopeId: "plan_pro", meter: "requests", upToQty: 10_000, unitPriceMicro: 0 },
  { scopeType: "plan", scopeId: "plan_pro", meter: "requests", upToQty: 100_000, unitPriceMicro: 2_000 },
  { scopeType: "plan", scopeId: "plan_pro", meter: "requests", upToQty: null, unitPriceMicro: 1_000 },
] as const;

// The full (host, model) catalog — flattened from the code source of truth in
// @vortex/core (per-host upstreamModelId, pricing, regions, supportedFeatures).
const MODELS = catalogSeedRows();

async function main() {
  const admin = postgres(ADMIN_DATABASE_URL, { max: 1 });
  const db = drizzle(admin);

  console.log("→ seeding plans…");
  await db.insert(plans).values([...PLANS]).onConflictDoNothing();

  console.log("→ seeding plan entitlements…");
  await db
    .insert(planEntitlements)
    .values(ENTITLEMENTS.map((e) => ({ ...e })))
    .onConflictDoNothing();

  console.log("→ seeding pricing tiers…");
  await db
    .insert(pricingTiers)
    .values(PRICING_TIERS.map((t) => ({ ...t })))
    .onConflictDoNothing();

  console.log(`→ seeding model catalog (${MODELS.length} host×model rows)…`);
  await db
    .insert(models)
    .values([...MODELS])
    .onConflictDoUpdate({
      target: [models.provider, models.modelName],
      set: {
        family: sql`excluded.family`,
        upstreamModelId: sql`excluded.upstream_model_id`,
        inputPer1kMicro: sql`excluded.input_per_1k_micro`,
        outputPer1kMicro: sql`excluded.output_per_1k_micro`,
        cachedInputPer1kMicro: sql`excluded.cached_input_per_1k_micro`,
        cacheWritePer1kMicro: sql`excluded.cache_write_per_1k_micro`,
        contextWindow: sql`excluded.context_window`,
        maxOutput: sql`excluded.max_output`,
        regions: sql`excluded.regions`,
        supportedFeatures: sql`excluded.supported_features`,
        modalities: sql`excluded.modalities`,
        releaseDate: sql`excluded.release_date`,
        knowledge: sql`excluded.knowledge`,
        lastUpdated: sql`excluded.last_updated`,
        openWeights: sql`excluded.open_weights`,
        description: sql`excluded.description`,
        config: sql`excluded.config`,
        customPricing: sql`excluded.custom_pricing`,
      },
    });

  await admin.end();
  console.log("✓ seed complete");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
