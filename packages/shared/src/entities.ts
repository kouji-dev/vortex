import { z } from "zod";
import {
  appKindSchema,
  appPrincipalSchema,
  appRoleSchema,
  budgetEnforcementSchema,
  credHealthSchema,
  credScopeSchema,
  keyRuleTypeSchema,
  keyStatusSchema,
  memberTypeSchema,
  orgRoleSchema,
  orgStatusSchema,
  subStatusSchema,
  teamRoleSchema,
  usageStatusSchema,
} from "./enums.js";

// DTO entity schemas. Each maps 1:1 to a table in @vortex/db (packages/db/src/schema.ts).
// Money fields are integer micro-USD (bigint mode:"number" in the DB → z.number().int()).
// Timestamps cross the wire as ISO-8601 strings (JSON), not Date objects.

const isoDateTime = z.string();
const microUsd = z.number().int();
const id = z.string();

// ── routing policy (schema.ts shared types: RoutingCandidate / RoutingPolicy) ──
export const routingCandidateSchema = z.object({
  provider: z.string(),
  model: z.string(),
  credentialId: id.optional(),
});
export type RoutingCandidate = z.infer<typeof routingCandidateSchema>;

export const routingPolicySchema = z.object({
  candidates: z.array(routingCandidateSchema),
});
export type RoutingPolicy = z.infer<typeof routingPolicySchema>;

// ── organizations ──
export const organizationSchema = z.object({
  id,
  name: z.string(),
  status: orgStatusSchema,
  planId: id.nullable(),
  defaultRoutingPolicy: routingPolicySchema,
  createdAt: isoDateTime,
});
export type Organization = z.infer<typeof organizationSchema>;

// ── teams ──
export const teamSchema = z.object({
  id,
  orgId: id,
  name: z.string(),
  defaultMemberBudgetMicro: microUsd.nullable(),
  budgetEnforcement: budgetEnforcementSchema,
  createdAt: isoDateTime,
});
export type Team = z.infer<typeof teamSchema>;

// ── memberships (human or technical; belongs to exactly one team) ──
export const memberSchema = z.object({
  id,
  orgId: id,
  userId: id.nullable(), // null for technical members
  type: memberTypeSchema,
  role: orgRoleSchema.nullable(), // null for technical members
  teamId: id.nullable(),
  teamRole: teamRoleSchema.nullable(),
  budgetOverrideMicro: microUsd.nullable(),
  createdAt: isoDateTime,
});
export type Member = z.infer<typeof memberSchema>;

// ── apps ──
export const appSchema = z.object({
  id,
  orgId: id,
  name: z.string(),
  kind: appKindSchema,
  ownerMemberId: id.nullable(), // personal apps
  technicalMemberId: id.nullable(), // system/service apps' service account
  defaultRoutingPolicy: routingPolicySchema.nullable(),
  createdAt: isoDateTime,
});
export type App = z.infer<typeof appSchema>;

// ── app_access (grant a Team OR a Member) ──
export const appAccessGrantSchema = z.object({
  id,
  orgId: id,
  appId: id,
  principalType: appPrincipalSchema,
  principalId: id, // team.id or membership.id
  role: appRoleSchema,
  createdAt: isoDateTime,
});
export type AppAccessGrant = z.infer<typeof appAccessGrantSchema>;

// ── api_key_rules ──
export const apiKeyRuleSchema = z.object({
  id,
  apiKeyId: id,
  ruleType: keyRuleTypeSchema,
  ruleValue: z.unknown(), // jsonb — shape depends on ruleType
});
export type ApiKeyRule = z.infer<typeof apiKeyRuleSchema>;

// ── api_keys (keyHash never leaves the server — DTO exposes prefix only) ──
export const apiKeySchema = z.object({
  id,
  orgId: id,
  ownerMemberId: id,
  isDefault: z.boolean(),
  keyPrefix: z.string(),
  rateLimitRpm: z.number().int().nullable(),
  status: keyStatusSchema,
  expiresAt: isoDateTime.nullable(),
  createdBy: id.nullable(),
  lastUsedAt: isoDateTime.nullable(),
  createdAt: isoDateTime,
  rules: z.array(apiKeyRuleSchema),
});
export type ApiKey = z.infer<typeof apiKeySchema>;

// ── provider_credentials (encryptedKey never leaves the server) ──
export const priceOverrideSchema = z.object({
  inputPer1k: z.number().optional(),
  outputPer1k: z.number().optional(),
});
export type PriceOverride = z.infer<typeof priceOverrideSchema>;

export const providerCredentialSchema = z.object({
  id,
  orgId: id,
  scopeType: credScopeSchema,
  scopeId: id.nullable(), // app.id when scope=app
  provider: z.string(),
  label: z.string().nullable(),
  region: z.string().nullable(),
  priceOverride: priceOverrideSchema.nullable(),
  healthStatus: credHealthSchema,
  lastCheckedAt: isoDateTime.nullable(),
  rotatedAt: isoDateTime.nullable(),
  enabled: z.boolean(),
  createdAt: isoDateTime,
});
export type ProviderCredential = z.infer<typeof providerCredentialSchema>;

// ── models (global catalog) ──
export const modelSchema = z.object({
  id,
  provider: z.string(),
  modelName: z.string(),
  inputPer1kMicro: microUsd,
  outputPer1kMicro: microUsd,
  contextWindow: z.number().int().nullable(),
  effectiveAt: isoDateTime,
});
export type Model = z.infer<typeof modelSchema>;

// ── plans ──
export const planSchema = z.object({
  id,
  name: z.string(),
  limits: z.record(z.unknown()),
  stripePriceId: z.string().nullable(),
  priceMicro: microUsd.nullable(),
  createdAt: isoDateTime,
});
export type Plan = z.infer<typeof planSchema>;

// ── subscriptions ──
export const subscriptionSchema = z.object({
  id,
  orgId: id,
  stripeCustomerId: z.string().nullable(),
  stripeSubscriptionId: z.string().nullable(),
  planId: id.nullable(),
  status: subStatusSchema,
  currentPeriodEnd: isoDateTime.nullable(),
  cancelAt: isoDateTime.nullable(),
  createdAt: isoDateTime,
});
export type Subscription = z.infer<typeof subscriptionSchema>;

// ── usage_records ──
export const usageRecordSchema = z.object({
  id,
  requestId: z.string(),
  orgId: id,
  apiKeyId: id.nullable(),
  memberId: id.nullable(),
  appId: id.nullable(),
  teamId: id.nullable(),
  actingUserId: id.nullable(),
  provider: z.string(),
  model: z.string(),
  promptTokens: z.number().int(),
  completionTokens: z.number().int(),
  totalTokens: z.number().int(),
  costMicro: microUsd,
  status: usageStatusSchema,
  latencyMs: z.number().int().nullable(),
  ttfbMs: z.number().int().nullable(),
  createdAt: isoDateTime,
});
export type UsageRecord = z.infer<typeof usageRecordSchema>;

// ── budget (derived view — not a table) ──
// Effective per-member monthly ceiling = member override ?? team default.
// Composed from teams.default_member_budget_micro + memberships.budget_override_micro.
export const budgetViewSchema = z.object({
  memberId: id,
  teamId: id.nullable(),
  teamDefaultBudgetMicro: microUsd.nullable(),
  memberOverrideMicro: microUsd.nullable(),
  effectiveBudgetMicro: microUsd.nullable(),
  enforcement: budgetEnforcementSchema,
  month: z.string().optional(), // "YYYY-MM"
  spentMicro: microUsd.optional(),
});
export type BudgetView = z.infer<typeof budgetViewSchema>;
