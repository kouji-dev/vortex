import { ADMIN_DATABASE_URL } from "./env.js";
import postgres from "postgres";
import { drizzle } from "drizzle-orm/postgres-js";
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

// micro-USD per 1k tokens (1 USD = 1_000_000 micro)
const MODELS = [
  { provider: "openai", modelName: "gpt-4o", inputPer1kMicro: 2500, outputPer1kMicro: 10000, contextWindow: 128000 },
  { provider: "openai", modelName: "gpt-4o-mini", inputPer1kMicro: 150, outputPer1kMicro: 600, contextWindow: 128000 },
  { provider: "anthropic", modelName: "claude-sonnet-4-5", inputPer1kMicro: 3000, outputPer1kMicro: 15000, contextWindow: 200000 },
  { provider: "anthropic", modelName: "claude-haiku-4-5", inputPer1kMicro: 800, outputPer1kMicro: 4000, contextWindow: 200000 },
  { provider: "google", modelName: "gemini-2.5-pro", inputPer1kMicro: 1250, outputPer1kMicro: 10000, contextWindow: 1000000 },
] as const;

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

  console.log("→ seeding model catalog…");
  await db.insert(models).values([...MODELS]).onConflictDoNothing();

  await admin.end();
  console.log("✓ seed complete");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
