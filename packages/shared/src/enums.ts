import { z } from "zod";

// Enum schemas mirror the pgEnum definitions in @vortex/db (packages/db/src/schema.ts).
// Keep the value tuples identical to the DB — these are the single source of truth on the wire.

export const orgRoleSchema = z.enum(["owner", "admin", "member"]);
export type OrgRole = z.infer<typeof orgRoleSchema>;

export const teamRoleSchema = z.enum(["team_admin", "member"]);
export type TeamRole = z.infer<typeof teamRoleSchema>;

export const memberTypeSchema = z.enum(["human", "technical"]);
export type MemberType = z.infer<typeof memberTypeSchema>;

export const appKindSchema = z.enum(["system", "service", "personal"]);
export type AppKind = z.infer<typeof appKindSchema>;

export const appRoleSchema = z.enum(["app_admin", "app_member"]);
export type AppRole = z.infer<typeof appRoleSchema>;

export const appPrincipalSchema = z.enum(["team", "member"]);
export type AppPrincipal = z.infer<typeof appPrincipalSchema>;

export const keyStatusSchema = z.enum(["active", "disabled", "revoked"]);
export type KeyStatus = z.infer<typeof keyStatusSchema>;

export const credScopeSchema = z.enum(["org", "app"]);
export type CredScope = z.infer<typeof credScopeSchema>;

export const credHealthSchema = z.enum([
  "valid",
  "invalid",
  "expired",
  "rate_limited",
]);
export type CredHealth = z.infer<typeof credHealthSchema>;

export const budgetEnforcementSchema = z.enum(["hard", "soft"]);
export type BudgetEnforcement = z.infer<typeof budgetEnforcementSchema>;

export const orgStatusSchema = z.enum(["active", "suspended"]);
export type OrgStatus = z.infer<typeof orgStatusSchema>;

export const subStatusSchema = z.enum([
  "active",
  "past_due",
  "canceled",
  "trialing",
  "incomplete",
]);
export type SubStatus = z.infer<typeof subStatusSchema>;

export const keyRuleTypeSchema = z.enum([
  "allow_models",
  "deny_models",
  "allow_providers",
  "deny_providers",
  "ip_cidrs",
]);
export type KeyRuleType = z.infer<typeof keyRuleTypeSchema>;

export const usageStatusSchema = z.enum(["success", "error"]);
export type UsageStatus = z.infer<typeof usageStatusSchema>;

export const platformRoleSchema = z.enum([
  "platform_owner",
  "platform_admin",
  "support",
]);
export type PlatformRole = z.infer<typeof platformRoleSchema>;
