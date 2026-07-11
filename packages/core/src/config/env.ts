import { config } from "dotenv";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { z } from "zod";

// load the single repo-root .env regardless of cwd
// this file lives at packages/core/src/config/env.ts → root is four levels up
const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../../../..");
config({ path: resolve(root, ".env") });

export const ROOT = root;

const csv = z
  .string()
  .transform((s) =>
    s
      .split(",")
      .map((v) => v.trim())
      .filter((v) => v.length > 0),
  );

const envSchema = z.object({
  // Deployment
  NODE_ENV: z
    .enum(["development", "test", "production"])
    .default("development"),
  TENANCY_MODE: z.enum(["single", "multi"]).default("single"),
  // managed = Vortex-hosted SaaS (billing plane ON). self_hosted = billing OFF,
  // only metering + budgeting + rate limiting run.
  DEPLOYMENT_MODE: z.enum(["managed", "self_hosted"]).default("self_hosted"),
  // On a Redis error the rate limiter allows the request (availability) vs denies.
  RATE_LIMIT_FAIL_OPEN: z
    .enum(["true", "false"])
    .default("true")
    .transform((v) => v === "true"),
  API_PORT: z.coerce.number().int().positive().default(8080),
  WEB_ORIGIN: z.string().url(),
  PLATFORM_ORIGIN: z.string().url(),
  // Marketing landing origin — allowed CORS origin for the public catalog.
  LANDING_ORIGIN: z.string().url().default("http://localhost:4400"),

  // Database
  DATABASE_URL: z.string().min(1),
  APP_DATABASE_URL: z.string().min(1),

  // Redis
  REDIS_URL: z.string().min(1),

  // Auth (better-auth)
  BETTER_AUTH_SECRET: z.string().min(1),
  BETTER_AUTH_URL: z.string().url(),

  // Platform-admin bootstrap (SaaS/multi). The create-admin API needs an
  // existing admin, so the first one is seeded from config: when both are set,
  // this account is created (if missing) + promoted to platform_admin on boot.
  PLATFORM_ADMIN_EMAIL: z.string().email().optional(),
  PLATFORM_ADMIN_PASSWORD: z.string().min(8).optional(),

  // Social auth (OAuth) — optional; enabled per provider when both id + secret set
  GITHUB_CLIENT_ID: z.string().optional(),
  GITHUB_CLIENT_SECRET: z.string().optional(),
  GOOGLE_CLIENT_ID: z.string().optional(),
  GOOGLE_CLIENT_SECRET: z.string().optional(),

  // Encryption — per-org key derivation root
  ENCRYPTION_KEY: z.string().min(1),

  // API-key hashing pepper — HMAC secret for virtual-key hashes. Must be stable
  // across all API replicas; rotating it invalidates every issued key.
  API_KEY_PEPPER: z.string().min(1),

  // Providers — env activates + overrides the code catalog
  ENABLED_PROVIDERS: csv.default(""),
  OPENAI_API_KEY: z.string().optional(),
  OPENAI_BASE_URL: z.string().url().optional().or(z.literal("")),
  ANTHROPIC_API_KEY: z.string().optional(),
  ANTHROPIC_BASE_URL: z.string().url().optional().or(z.literal("")),
  GOOGLE_API_KEY: z.string().optional(),
  GOOGLE_BASE_URL: z.string().url().optional().or(z.literal("")),
  // Azure OpenAI (deployment-specific)
  AZURE_OPENAI_RESOURCE: z.string().optional(),
  AZURE_OPENAI_API_VERSION: z.string().optional(),
  AZURE_OPENAI_API_KEY: z.string().optional(),
  // AWS Bedrock (bearer API key — no SigV4)
  AWS_BEDROCK_REGION: z.string().optional(),
  AWS_BEDROCK_BASE_URL: z.string().url().optional().or(z.literal("")),
  AWS_BEDROCK_API_KEY: z.string().optional(),
  // Google Vertex
  GOOGLE_VERTEX_PROJECT: z.string().optional(),
  GOOGLE_VERTEX_REGION: z.string().optional(),
  GOOGLE_VERTEX_API_KEY: z.string().optional(),
  // OpenAI-compatible inference providers (bearer key; base URL overridable)
  GROQ_API_KEY: z.string().optional(),
  GROQ_BASE_URL: z.string().url().optional().or(z.literal("")),
  MISTRAL_API_KEY: z.string().optional(),
  MISTRAL_BASE_URL: z.string().url().optional().or(z.literal("")),
  DEEPSEEK_API_KEY: z.string().optional(),
  DEEPSEEK_BASE_URL: z.string().url().optional().or(z.literal("")),
  XAI_API_KEY: z.string().optional(),
  XAI_BASE_URL: z.string().url().optional().or(z.literal("")),
  TOGETHER_API_KEY: z.string().optional(),
  TOGETHER_BASE_URL: z.string().url().optional().or(z.literal("")),
  FIREWORKS_API_KEY: z.string().optional(),
  FIREWORKS_BASE_URL: z.string().url().optional().or(z.literal("")),

  // Stripe (SaaS / multi mode only)
  STRIPE_SECRET_KEY: z.string().optional(),
  STRIPE_WEBHOOK_SECRET: z.string().optional(),
  STRIPE_PORTAL_RETURN_URL: z.string().url().optional().or(z.literal("")),
});

// On Render, default the public origins + auth URL to the service URL when unset.
const externalUrl = process.env.RENDER_EXTERNAL_URL;
if (externalUrl) {
  process.env.WEB_ORIGIN ||= externalUrl;
  process.env.PLATFORM_ORIGIN ||= externalUrl;
  process.env.LANDING_ORIGIN ||= externalUrl;
  process.env.BETTER_AUTH_URL ||= externalUrl;
}

const parsed = envSchema.safeParse(process.env);

if (!parsed.success) {
  const issues = parsed.error.issues
    .map((i) => `  - ${i.path.join(".") || "(root)"}: ${i.message}`)
    .join("\n");
  throw new Error(`Invalid environment configuration:\n${issues}`);
}

export const env = parsed.data;
export type Env = typeof env;
