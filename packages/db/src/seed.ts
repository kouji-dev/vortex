import { ADMIN_DATABASE_URL } from "./env.js";
import postgres from "postgres";
import { drizzle } from "drizzle-orm/postgres-js";
import { plans, models } from "./schema.js";

const PLANS = [
  { id: "plan_free", name: "Free", priceMicro: 0, limits: { maxMembers: 5 } },
  { id: "plan_pro", name: "Pro", priceMicro: 99_000_000, limits: { maxMembers: 50 } },
  {
    id: "plan_enterprise",
    name: "Enterprise",
    priceMicro: null,
    limits: { maxMembers: null },
  },
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

  console.log("→ seeding model catalog…");
  await db.insert(models).values([...MODELS]).onConflictDoNothing();

  await admin.end();
  console.log("✓ seed complete");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
