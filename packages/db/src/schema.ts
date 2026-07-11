import { randomUUID } from "node:crypto";
import {
  pgTable,
  pgEnum,
  text,
  boolean,
  timestamp,
  jsonb,
  bigint,
  integer,
  uniqueIndex,
  index,
} from "drizzle-orm/pg-core";

// ── id helper ────────────────────────────────────────────────
const id = () =>
  text("id")
    .primaryKey()
    .$defaultFn(() => randomUUID());
const money = (name: string) => bigint(name, { mode: "number" }); // micro-USD
const createdAt = () =>
  timestamp("created_at", { withTimezone: true }).defaultNow().notNull();

// ── enums ────────────────────────────────────────────────────
export const orgStatus = pgEnum("org_status", ["active", "suspended"]);
export const platformRole = pgEnum("platform_role", [
  "platform_owner",
  "platform_admin",
  "support",
]);
export const subStatus = pgEnum("sub_status", [
  "active",
  "past_due",
  "canceled",
  "trialing",
  "incomplete",
]);
export const budgetEnforcement = pgEnum("budget_enforcement", ["hard", "soft"]);
export const appKind = pgEnum("app_kind", ["system", "service", "personal"]);
export const memberType = pgEnum("member_type", ["human", "technical"]);
export const orgRole = pgEnum("org_role", ["owner", "admin", "member"]);
export const teamRole = pgEnum("team_role", ["team_admin", "member"]);
export const appPrincipal = pgEnum("app_principal", ["team", "member"]);
export const appRole = pgEnum("app_role", ["app_admin", "app_member"]);
export const keyStatus = pgEnum("key_status", ["active", "disabled", "revoked"]);
export const credScope = pgEnum("cred_scope", ["org", "app"]);
export const credHealth = pgEnum("cred_health", [
  "valid",
  "invalid",
  "expired",
  "rate_limited",
]);
export const keyRuleType = pgEnum("key_rule_type", [
  "allow_models",
  "deny_models",
  "allow_providers",
  "deny_providers",
  "ip_cidrs",
]);
export const usageStatus = pgEnum("usage_status", ["success", "error"]);
// wire envelope a model speaks — decides which adapter transcodes it. Distinct
// from the `host` (provider column), which decides endpoint/auth/model-id.
export const modelFamily = pgEnum("model_family", [
  "openai",
  "anthropic",
  "google",
]);
export const keyMode = pgEnum("key_mode", ["byok", "managed", "hybrid"]);
export const meterType = pgEnum("meter_type", [
  "requests",
  "input_tokens",
  "output_tokens",
  "cost_micro",
  "seats",
  "service_accounts",
]);
export const pricingScope = pgEnum("pricing_scope", ["plan", "contract"]);
export const contractStatus = pgEnum("contract_status", [
  "draft",
  "active",
  "expired",
  "canceled",
]);

// ── auth (better-auth compatible) ────────────────────────────
export const users = pgTable("users", {
  id: id(),
  name: text("name"),
  email: text("email").notNull().unique(),
  emailVerified: boolean("email_verified").default(false).notNull(),
  image: text("image"),
  ssoSubject: text("sso_subject"),
  createdAt: createdAt(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export const sessions = pgTable("sessions", {
  id: id(),
  userId: text("user_id")
    .notNull()
    .references(() => users.id, { onDelete: "cascade" }),
  token: text("token").notNull().unique(),
  expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
  ipAddress: text("ip_address"),
  userAgent: text("user_agent"),
  createdAt: createdAt(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export const accounts = pgTable("accounts", {
  id: id(),
  userId: text("user_id")
    .notNull()
    .references(() => users.id, { onDelete: "cascade" }),
  accountId: text("account_id").notNull(),
  providerId: text("provider_id").notNull(),
  accessToken: text("access_token"),
  refreshToken: text("refresh_token"),
  idToken: text("id_token"),
  accessTokenExpiresAt: timestamp("access_token_expires_at", {
    withTimezone: true,
  }),
  refreshTokenExpiresAt: timestamp("refresh_token_expires_at", {
    withTimezone: true,
  }),
  scope: text("scope"),
  password: text("password"),
  createdAt: createdAt(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export const verifications = pgTable("verifications", {
  id: id(),
  identifier: text("identifier").notNull(),
  value: text("value").notNull(),
  expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
  createdAt: createdAt(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});

// ── platform (SaaS super-admin, above orgs) ──────────────────
export const plans = pgTable("plans", {
  id: id(),
  name: text("name").notNull(),
  limits: jsonb("limits").$type<Record<string, unknown>>().default({}).notNull(),
  stripePriceId: text("stripe_price_id"),
  priceMicro: money("price_micro"),
  createdAt: createdAt(),
});

export const platformAdmins = pgTable("platform_admins", {
  id: id(),
  userId: text("user_id")
    .notNull()
    .references(() => users.id, { onDelete: "cascade" }),
  role: platformRole("role").notNull().default("platform_admin"),
  createdAt: createdAt(),
});

export const platformAuditLogs = pgTable("platform_audit_logs", {
  id: id(),
  platformAdminId: text("platform_admin_id").references(() => platformAdmins.id),
  action: text("action").notNull(),
  targetOrg: text("target_org"),
  metadata: jsonb("metadata").$type<Record<string, unknown>>().default({}),
  prevHash: text("prev_hash"),
  entryHash: text("entry_hash").notNull(),
  createdAt: createdAt(),
});

// ── tenant: organization = the company ───────────────────────
export const organizations = pgTable("organizations", {
  id: id(),
  name: text("name").notNull(),
  status: orgStatus("status").notNull().default("active"),
  planId: text("plan_id").references(() => plans.id),
  // BYOK (org keys) | managed (Vortex pool + credits + markup) | hybrid (both)
  keyMode: keyMode("key_mode").notNull().default("byok"),
  markupBps: integer("markup_bps").notNull().default(0), // managed-key spend markup
  defaultRoutingPolicy: jsonb("default_routing_policy")
    .$type<RoutingPolicy>()
    .default({ candidates: [] })
    .notNull(),
  createdAt: createdAt(),
});

export const subscriptions = pgTable("subscriptions", {
  id: id(),
  orgId: text("org_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  stripeCustomerId: text("stripe_customer_id"),
  stripeSubscriptionId: text("stripe_subscription_id"),
  planId: text("plan_id").references(() => plans.id),
  status: subStatus("status").notNull().default("incomplete"),
  currentPeriodEnd: timestamp("current_period_end", { withTimezone: true }),
  cancelAt: timestamp("cancel_at", { withTimezone: true }),
  createdAt: createdAt(),
});

export const teams = pgTable("teams", {
  id: id(),
  orgId: text("org_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  name: text("name").notNull(),
  defaultMemberBudgetMicro: money("default_member_budget_micro"),
  budgetMicro: money("budget_micro"), // team pool cap (aggregate spend/month)
  budgetEnforcement: budgetEnforcement("budget_enforcement")
    .notNull()
    .default("hard"),
  createdAt: createdAt(),
});

// members belong to exactly one org; human or technical (per-app service account)
export const memberships = pgTable(
  "memberships",
  {
    id: id(),
    orgId: text("org_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    userId: text("user_id").references(() => users.id, { onDelete: "cascade" }), // null for technical
    type: memberType("type").notNull().default("human"),
    role: orgRole("role"), // null for technical
    teamId: text("team_id").references(() => teams.id, { onDelete: "set null" }),
    teamRole: teamRole("team_role"),
    budgetOverrideMicro: money("budget_override_micro"),
    createdAt: createdAt(),
  },
  (t) => [
    uniqueIndex("memberships_org_user_uq")
      .on(t.orgId, t.userId)
      .where(sqlNotNull(t.userId)),
    index("memberships_org_idx").on(t.orgId),
  ],
);

export const apps = pgTable("apps", {
  id: id(),
  orgId: text("org_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  name: text("name").notNull(),
  kind: appKind("kind").notNull().default("service"),
  ownerMemberId: text("owner_member_id").references(() => memberships.id, {
    onDelete: "set null",
  }), // personal apps
  technicalMemberId: text("technical_member_id").references(
    () => memberships.id,
    { onDelete: "set null" },
  ), // system/service apps
  defaultRoutingPolicy: jsonb("default_routing_policy").$type<RoutingPolicy>(),
  createdAt: createdAt(),
});

export const appAccess = pgTable(
  "app_access",
  {
    id: id(),
    orgId: text("org_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    appId: text("app_id")
      .notNull()
      .references(() => apps.id, { onDelete: "cascade" }),
    principalType: appPrincipal("principal_type").notNull(),
    principalId: text("principal_id").notNull(), // team.id or membership.id
    role: appRole("role").notNull().default("app_member"),
    createdAt: createdAt(),
  },
  (t) => [
    uniqueIndex("app_access_uq").on(t.appId, t.principalType, t.principalId),
  ],
);

export const apiKeys = pgTable(
  "api_keys",
  {
    id: id(),
    orgId: text("org_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    ownerMemberId: text("owner_member_id")
      .notNull()
      .references(() => memberships.id, { onDelete: "cascade" }),
    isDefault: boolean("is_default").notNull().default(false),
    keyHash: text("key_hash").notNull().unique(),
    keyPrefix: text("key_prefix").notNull(),
    rateLimitRpm: integer("rate_limit_rpm"),
    status: keyStatus("status").notNull().default("active"),
    expiresAt: timestamp("expires_at", { withTimezone: true }),
    createdBy: text("created_by").references(() => users.id),
    lastUsedAt: timestamp("last_used_at", { withTimezone: true }),
    createdAt: createdAt(),
  },
  (t) => [index("api_keys_org_idx").on(t.orgId)],
);

export const apiKeyRules = pgTable("api_key_rules", {
  id: id(),
  apiKeyId: text("api_key_id")
    .notNull()
    .references(() => apiKeys.id, { onDelete: "cascade" }),
  ruleType: keyRuleType("rule_type").notNull(),
  ruleValue: jsonb("rule_value").$type<unknown>().notNull(),
});

export const providerCredentials = pgTable("provider_credentials", {
  id: id(),
  orgId: text("org_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  scopeType: credScope("scope_type").notNull().default("org"),
  scopeId: text("scope_id"), // app.id when scope=app
  provider: text("provider").notNull(),
  label: text("label"),
  region: text("region"),
  // deployment-specific BYOK options (azure resource/deployment/api-version,
  // vertex project/region, bedrock region, token type, …)
  options: jsonb("options").$type<Record<string, unknown>>(),
  encryptedKey: text("encrypted_key").notNull(),
  priceOverride: jsonb("price_override").$type<{
    inputPer1k?: number;
    outputPer1k?: number;
  }>(),
  healthStatus: credHealth("health_status").notNull().default("valid"),
  lastCheckedAt: timestamp("last_checked_at", { withTimezone: true }),
  rotatedAt: timestamp("rotated_at", { withTimezone: true }),
  enabled: boolean("enabled").notNull().default(true),
  createdAt: createdAt(),
});

// global model catalog (pricing + context); tenants inherit, narrowed by env/org
export const models = pgTable(
  "models",
  {
    id: id(),
    // host = where the model is served (openai, anthropic, azure, bedrock,
    // vertex, groq…). The wire envelope is `family`; one logical model can have
    // several rows (Opus on anthropic/bedrock/vertex), each a distinct host.
    provider: text("provider").notNull(),
    family: modelFamily("family").notNull().default("openai"),
    modelName: text("model_name").notNull(),
    // Provider-specific upstream id used on the wire (Bedrock `anthropic.…-v1:0`,
    // Azure deployment, Vertex publisher model). Defaults to modelName when equal.
    upstreamModelId: text("upstream_model_id"),
    inputPer1kMicro: money("input_per_1k_micro").notNull(),
    outputPer1kMicro: money("output_per_1k_micro").notNull(),
    // Prompt-caching prices (Anthropic/OpenAI), per 1k micro-USD. Null when the
    // host×model has no cache tier.
    cachedInputPer1kMicro: money("cached_input_per_1k_micro"),
    cacheWritePer1kMicro: money("cache_write_per_1k_micro"),
    contextWindow: integer("context_window"),
    maxOutput: integer("max_output"),
    // Hosts that region-scope the id (Bedrock global/us/eu → `us.`… prefix).
    regions: jsonb("regions").$type<string[]>(),
    // Capabilities THIS host×model accepts — validated & rejected when unsupported.
    supportedFeatures: jsonb("supported_features").$type<{
      tools?: boolean;
      vision?: boolean;
      reasoning?: boolean;
      caching?: boolean;
      webSearch?: boolean;
      streaming?: boolean;
      jsonSchema?: boolean;
    }>(),
    // Input/output modalities (text/image/pdf/audio…) for the console model card.
    modalities: jsonb("modalities").$type<{ input: string[]; output: string[] }>(),
    // Display metadata (from models.dev): release/knowledge/updated dates, etc.
    releaseDate: text("release_date"),
    knowledge: text("knowledge"),
    lastUpdated: text("last_updated"),
    openWeights: boolean("open_weights"),
    description: text("description"),
    // Host routing knobs (e.g. region→model-id prefix rule, publisher).
    config: jsonb("config").$type<Record<string, unknown>>(),
    // Pricing beyond per-token (per-second, tiered, image/audio).
    customPricing: jsonb("custom_pricing").$type<Record<string, unknown>>(),
    effectiveAt: timestamp("effective_at", { withTimezone: true })
      .defaultNow()
      .notNull(),
  },
  // One row per (host, logical model). Unique so re-seeds upsert cleanly.
  (t) => [uniqueIndex("models_provider_name_idx").on(t.provider, t.modelName)],
);

export const usageRecords = pgTable(
  "usage_records",
  {
    id: id(),
    requestId: text("request_id").notNull().unique(),
    orgId: text("org_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    apiKeyId: text("api_key_id").references(() => apiKeys.id, {
      onDelete: "set null",
    }),
    memberId: text("member_id").references(() => memberships.id, {
      onDelete: "set null",
    }),
    appId: text("app_id").references(() => apps.id, { onDelete: "set null" }),
    teamId: text("team_id").references(() => teams.id, { onDelete: "set null" }),
    actingUserId: text("acting_user_id"),
    provider: text("provider").notNull(),
    model: text("model").notNull(),
    promptTokens: integer("prompt_tokens").default(0).notNull(),
    completionTokens: integer("completion_tokens").default(0).notNull(),
    totalTokens: integer("total_tokens").default(0).notNull(),
    costMicro: money("cost_micro").default(0).notNull(),
    status: usageStatus("status").notNull().default("success"),
    latencyMs: integer("latency_ms"),
    ttfbMs: integer("ttfb_ms"),
    createdAt: createdAt(),
  },
  (t) => [
    index("usage_org_created_idx").on(t.orgId, t.createdAt),
    index("usage_member_idx").on(t.memberId),
    index("usage_app_idx").on(t.appId),
  ],
);

export const auditLogs = pgTable("audit_logs", {
  id: id(),
  orgId: text("org_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  actor: text("actor"),
  action: text("action").notNull(),
  target: text("target"),
  metadata: jsonb("metadata").$type<Record<string, unknown>>().default({}),
  prevHash: text("prev_hash"),
  entryHash: text("entry_hash").notNull(),
  createdAt: createdAt(),
});

// ── entitlements / pricing / metering / credits ──────────────
// Per-plan governance + limits. Drives budget, seat caps, and rate limits in
// BOTH deployments. Null column = unlimited.
export const planEntitlements = pgTable("plan_entitlements", {
  id: id(),
  planId: text("plan_id")
    .notNull()
    .unique()
    .references(() => plans.id, { onDelete: "cascade" }),
  seatsPerOrg: integer("seats_per_org"),
  servicePerMember: integer("service_per_member"),
  teamBudgetMicro: money("team_budget_micro"),
  rpm: integer("rpm"),
  tpm: integer("tpm"),
  concurrency: integer("concurrency"),
  flags: jsonb("flags").$type<Record<string, unknown>>().default({}).notNull(),
  createdAt: createdAt(),
});

// Graduated (volume-tiered) unit pricing per meter. Consumed only by the
// billing plane (managed). `upToQty` null = final unbounded tier.
export const pricingTiers = pgTable(
  "pricing_tiers",
  {
    id: id(),
    scopeType: pricingScope("scope_type").notNull(), // plan | contract
    scopeId: text("scope_id").notNull(),
    meter: meterType("meter").notNull(),
    upToQty: bigint("up_to_qty", { mode: "number" }),
    unitPriceMicro: money("unit_price_micro").notNull(),
    createdAt: createdAt(),
  },
  (t) => [index("pricing_tiers_scope_idx").on(t.scopeType, t.scopeId, t.meter)],
);

// Per-org enterprise contract overrides (committed base, seat commit, term).
export const contracts = pgTable("contracts", {
  id: id(),
  orgId: text("org_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  baseMicro: money("base_micro"),
  seatCommit: integer("seat_commit"),
  status: contractStatus("status").notNull().default("active"),
  termStart: timestamp("term_start", { withTimezone: true }),
  termEnd: timestamp("term_end", { withTimezone: true }),
  createdAt: createdAt(),
});

// Monthly meter rollups (org × period × meter). Price-tracking source of truth.
export const usageRollups = pgTable(
  "usage_rollups",
  {
    id: id(),
    orgId: text("org_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    period: text("period").notNull(), // YYYY-MM
    meter: meterType("meter").notNull(),
    value: money("value").notNull().default(0),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .defaultNow()
      .notNull(),
    createdAt: createdAt(),
  },
  (t) => [uniqueIndex("usage_rollups_uq").on(t.orgId, t.period, t.meter)],
);

// Managed-mode credit balance + ledger (top-ups + spend deductions).
export const creditWallets = pgTable("credit_wallets", {
  id: id(),
  orgId: text("org_id")
    .notNull()
    .unique()
    .references(() => organizations.id, { onDelete: "cascade" }),
  balanceMicro: money("balance_micro").notNull().default(0),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
  createdAt: createdAt(),
});

export const creditLedger = pgTable(
  "credit_ledger",
  {
    id: id(),
    orgId: text("org_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    deltaMicro: money("delta_micro").notNull(), // +topup / -spend
    reason: text("reason").notNull(), // topup | spend | adjustment
    requestId: text("request_id"), // links a spend to its usage record
    createdAt: createdAt(),
  },
  (t) => [index("credit_ledger_org_idx").on(t.orgId, t.createdAt)],
);

// Platform-owned managed provider pool (NOT tenant-scoped; managed mode only).
export const managedProviderKeys = pgTable("managed_provider_keys", {
  id: id(),
  provider: text("provider").notNull(),
  label: text("label"),
  region: text("region"),
  options: jsonb("options").$type<Record<string, unknown>>(),
  encryptedKey: text("encrypted_key").notNull(),
  priceOverride: jsonb("price_override").$type<{
    inputPer1k?: number;
    outputPer1k?: number;
  }>(),
  healthStatus: credHealth("health_status").notNull().default("valid"),
  enabled: boolean("enabled").notNull().default(true),
  createdAt: createdAt(),
});

// ── shared types ─────────────────────────────────────────────
export type RoutingCandidate = {
  provider: string;
  model: string;
  credentialId?: string;
};
export type RoutingPolicy = { candidates: RoutingCandidate[] };

// tiny local helper to avoid importing drizzle sql in the id index
import { sql, type SQL } from "drizzle-orm";
import type { AnyPgColumn } from "drizzle-orm/pg-core";
function sqlNotNull(col: AnyPgColumn): SQL {
  return sql`${col} is not null`;
}
