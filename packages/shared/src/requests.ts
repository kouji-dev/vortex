import { z } from "zod";
import {
  appKindSchema,
  appPrincipalSchema,
  appRoleSchema,
  budgetEnforcementSchema,
  credScopeSchema,
  keyRuleTypeSchema,
  orgRoleSchema,
  teamRoleSchema,
} from "./enums.js";
import { priceOverrideSchema, routingPolicySchema } from "./entities.js";

// Create/update input DTOs. org_id / actor are always derived from the request
// context (auth), never trusted from the body — so they are omitted here.

const microUsd = z.number().int();
const id = z.string();

// ── organizations ──
export const createOrgSchema = z.object({
  name: z.string().min(1),
  planId: id.optional(),
});
export type CreateOrg = z.infer<typeof createOrgSchema>;

// ── teams ──
export const createTeamSchema = z.object({
  name: z.string().min(1),
  defaultMemberBudgetMicro: microUsd.nullish(),
  budgetEnforcement: budgetEnforcementSchema.optional(),
});
export type CreateTeam = z.infer<typeof createTeamSchema>;

// ── memberships (invite a human member) ──
export const inviteMemberSchema = z.object({
  email: z.string().email(),
  role: orgRoleSchema.optional(),
  teamId: id.optional(),
  teamRole: teamRoleSchema.optional(),
  budgetOverrideMicro: microUsd.nullish(),
});
export type InviteMember = z.infer<typeof inviteMemberSchema>;

// ── apps ──
export const createAppSchema = z.object({
  name: z.string().min(1),
  kind: appKindSchema,
  ownerMemberId: id.optional(), // personal apps
  defaultRoutingPolicy: routingPolicySchema.optional(),
});
export type CreateApp = z.infer<typeof createAppSchema>;

// ── app_access ──
export const grantAppAccessSchema = z.object({
  appId: id,
  principalType: appPrincipalSchema,
  principalId: id,
  role: appRoleSchema.optional(),
});
export type GrantAppAccess = z.infer<typeof grantAppAccessSchema>;

// ── api_keys ──
export const createApiKeyRuleSchema = z.object({
  ruleType: keyRuleTypeSchema,
  ruleValue: z.unknown(),
});
export type CreateApiKeyRule = z.infer<typeof createApiKeyRuleSchema>;

export const createApiKeySchema = z.object({
  name: z.string().min(1),
  ownerMemberId: id.optional(), // defaults to the caller's member
  rules: z.array(createApiKeyRuleSchema).optional(),
  rateLimit: z.number().int().positive().optional(),
  expiresAt: z.string().optional(), // ISO-8601
});
export type CreateApiKey = z.infer<typeof createApiKeySchema>;

// ── provider_credentials ──
export const createProviderCredentialSchema = z.object({
  provider: z.string().min(1),
  scopeType: credScopeSchema,
  scopeId: id.optional(), // app.id when scope=app
  label: z.string().optional(),
  region: z.string().optional(),
  key: z.string().min(1), // plaintext provider key — encrypted server-side, never returned
  priceOverride: priceOverrideSchema.optional(),
});
export type CreateProviderCredential = z.infer<
  typeof createProviderCredentialSchema
>;

// ── budgets (team default + per-member override) ──
export const setTeamBudgetSchema = z.object({
  teamId: id,
  defaultMemberBudgetMicro: microUsd.nullable(), // null clears the default
  budgetEnforcement: budgetEnforcementSchema.optional(),
});
export type SetTeamBudget = z.infer<typeof setTeamBudgetSchema>;

export const setMemberBudgetOverrideSchema = z.object({
  memberId: id,
  budgetOverrideMicro: microUsd.nullable(), // null clears the override
});
export type SetMemberBudgetOverride = z.infer<
  typeof setMemberBudgetOverrideSchema
>;
