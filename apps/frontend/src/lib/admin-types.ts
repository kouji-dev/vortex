// Control Plane admin domain types.
// Source-of-truth shapes mirrored from server/api/src/ai_portal/<domain>/schemas.py.

// ---------- Members ----------
export type MemberRole = 'owner' | 'admin' | 'member' | 'viewer'

export interface OrgMember {
  user_id: string
  email: string
  name: string | null
  role: MemberRole
  joined_at: string
  last_active_at: string | null
}

export interface OrgInvitation {
  id: string
  email: string
  role: MemberRole
  invited_by: string
  expires_at: string
  created_at: string
}

export interface InviteMemberRequest {
  email: string
  role: MemberRole
}

export interface UpdateMemberRoleRequest {
  role: MemberRole
}

// ---------- SSO / IdP ----------
export type IdpKind = 'oidc' | 'saml' | 'entra' | 'okta' | 'google'

export interface IdpConnection {
  id: string
  kind: IdpKind
  name: string
  enabled: boolean
  sso_required: boolean
  domain: string | null
  config: Record<string, string>
  created_at: string
}

export interface CreateIdpConnectionRequest {
  kind: IdpKind
  name: string
  domain?: string | null
  config: Record<string, string>
  enabled?: boolean
  sso_required?: boolean
}

export interface UpdateIdpConnectionRequest {
  name?: string
  domain?: string | null
  config?: Record<string, string>
  enabled?: boolean
  sso_required?: boolean
}

// ---------- API Keys ----------
export type ApiKeyScope = string // permission key like "gateway:complete"

export interface RateLimits {
  rpm?: number | null
  tpm?: number | null
  concurrency?: number | null
}

export interface ApiKeySummary {
  id: string
  name: string
  prefix: string
  scopes: ApiKeyScope[]
  rate_limits?: RateLimits | null
  expires_at: string | null
  last_used_at: string | null
  created_at: string
  revoked_at: string | null
}

export interface CreateApiKeyRequest {
  name: string
  scopes: ApiKeyScope[]
  rate_limits?: RateLimits | null
  expires_at?: string | null
}

export interface EditApiKeyRequest {
  name?: string
  rate_limits?: RateLimits | null
}

export interface CreateApiKeyResponse {
  key: ApiKeySummary
  plaintext: string // full secret, shown ONCE on creation only
}

// ---------- Audit ----------
export interface AuditEvent {
  id: string
  org_id: string
  actor_kind: 'user' | 'api_key' | 'system'
  actor_id: string | null
  actor_email: string | null
  action: string
  resource_type: string | null
  resource_id: string | null
  payload: Record<string, unknown>
  ip: string | null
  user_agent: string | null
  ts: string
}

export interface AuditFilter {
  action?: string
  actor?: string
  resource_type?: string
  resource_id?: string
  from?: string // ISO date-time
  to?: string
  cursor?: string
  limit?: number
}

export interface AuditPage {
  items: AuditEvent[]
  next_cursor: string | null
}

// ---------- Usage ----------
export type UsageDimension = 'user' | 'team' | 'key' | 'model' | 'module'

export type UsagePeriod = 'hour' | 'day' | 'week' | 'month'

export interface UsageBucket {
  dim_value: string // user id, key prefix, model name etc
  dim_label: string // human label
  tokens_in: number
  tokens_out: number
  cost_cents: number
  count: number
}

export interface UsageTimeseriesPoint {
  ts: string // bucket start
  tokens_in: number
  tokens_out: number
  cost_cents: number
}

export interface UsageReport {
  dim: UsageDimension
  period: UsagePeriod
  from: string
  to: string
  buckets: UsageBucket[]
  timeseries: UsageTimeseriesPoint[]
  total_tokens_in: number
  total_tokens_out: number
  total_cost_cents: number
}

// ---------- Budgets / Quotas ----------
export type ScopeKind = 'org' | 'user' | 'team' | 'api_key'
export type BudgetPeriod = 'day' | 'month' | 'custom'
export type QuotaAction = 'block' | 'warn' | 'allow'

export interface Quota {
  id: number
  name: string
  scope_kind: ScopeKind
  scope_id: string | null
  unit: string
  period: BudgetPeriod
  max_qty: string // decimal serialized as string
  action_on_breach: QuotaAction
  disabled_at: string | null
}

export interface QuotaCreateRequest {
  name: string
  scope_kind: ScopeKind
  scope_id?: string | null
  unit: string
  period?: BudgetPeriod
  max_qty: string
  action_on_breach?: QuotaAction
}

export interface Budget {
  id: number
  name: string
  scope_kind: ScopeKind
  scope_id: string | null
  limit_usd: string
  period: BudgetPeriod
  period_start: string | null
  period_end: string | null
  warn_at_pcts: number[]
  hard_cutoff: boolean
  grace_extension_usd: string | null
  grace_expires_at: string | null
  webhook_on_threshold: boolean
  disabled_at: string | null
}

export interface BudgetCreateRequest {
  name: string
  scope_kind: ScopeKind
  scope_id?: string | null
  limit_usd: string
  period?: BudgetPeriod
  period_start?: string | null
  period_end?: string | null
  warn_at_pcts?: number[]
  hard_cutoff?: boolean
  webhook_on_threshold?: boolean
}

export interface BudgetStatus {
  budget_id: number
  period_start: string
  period_end: string
  spent_usd: string
  limit_usd: string
  effective_limit_usd: string
  used_pct: number
  blocked: boolean
  grace_active: boolean
}

// ---------- Webhooks ----------
export interface Webhook {
  id: string
  org_id: string
  url: string
  event_types: string[]
  enabled: boolean
  description: string | null
  created_at: string
  disabled_at: string | null
}

export interface WebhookCreated extends Webhook {
  secret: string // shown once on creation
}

export interface WebhookCreateRequest {
  url: string
  event_types: string[]
  description?: string | null
}

export interface WebhookUpdateRequest {
  url?: string
  event_types?: string[]
  description?: string | null
  enabled?: boolean
}

export interface WebhookDelivery {
  id: string
  webhook_id: string
  event_id: string
  event_type: string
  status: string // 'pending' | 'success' | 'failed'
  attempts: number
  last_response_status: number | null
  last_response_body: string | null
  last_error: string | null
  next_attempt_at: string | null
  delivered_at: string | null
  failed_at: string | null
  created_at: string
}

export interface WebhookEventType {
  key: string
  description: string
  module: string
}

// ---------- Billing ----------
export interface Subscription {
  id: string
  org_id: string
  provider: string
  customer_id: string
  external_id: string | null
  plan_kind: string
  plan_code: string
  status: string
  currency: string
  seats: number
  current_period_start: string | null
  current_period_end: string | null
  canceled_at: string | null
}

export interface SubscriptionPatchRequest {
  plan_code?: string | null
  seats?: number | null
  cancel?: boolean
}

export interface Invoice {
  id: string
  org_id: string
  subscription_id: string | null
  external_id: string | null
  amount_cents: number
  currency: string
  status: string
  pdf_url: string | null
  memo: string | null
  issued_at: string | null
  due_at: string | null
  paid_at: string | null
}

// ---------- Settings ----------
export interface SettingsKv {
  settings: Record<string, unknown>
}

export interface ModuleFlag {
  enabled: boolean
  gates: Record<string, unknown>
}

export interface ModuleFlagsMap {
  modules: Record<string, ModuleFlag>
}

// ---------- SCIM ----------
export type ScimPreset = 'generic' | 'okta' | 'entra'

export interface ScimEndpoint {
  id: string
  org_id: string
  name: string
  preset: ScimPreset
  enabled: boolean
  last_sync_at: string | null
  created_at: string
  revoked_at: string | null
}

export interface ScimEndpointCreated extends ScimEndpoint {
  token: string // shown once
}

export interface ScimEndpointCreateRequest {
  name: string
  preset?: ScimPreset
}

export interface ScimGroupRoleMapRequest {
  display_name: string
  role_name: MemberRole | 'service'
}

export interface ScimGroup {
  id: string
  display_name: string
  external_id: string | null
  role_name: string | null
}

// ---------- GDPR Data lifecycle ----------
export type DataJobStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface DataExportJob {
  id: string
  org_id: string
  requested_by: number | null
  status: DataJobStatus | string
  result_url: string | null
  requested_at: string
  completed_at: string | null
}

export interface DataDeleteJob {
  id: string
  org_id: string
  scope_json: Record<string, unknown>
  status: DataJobStatus | string
  requested_at: string
  completed_at: string | null
}

export interface DataDeleteCreateRequest {
  scope: Record<string, unknown>
}

// ---------- Teams ----------
export interface Team {
  id: string
  org_id: string
  slug: string
  name: string
  description: string | null
  created_at: string
  archived_at: string | null
  member_count: number
}

export interface CreateTeamRequest {
  slug: string
  name: string
  description?: string | null
}

export interface PatchTeamRequest {
  slug?: string
  name?: string
  description?: string | null
  archived?: boolean
}

export interface TeamMember {
  id: number
  team_id: string
  user_id: number
  email: string | null
  name: string | null
  role: string | null
  created_at: string
}

export interface AddTeamMemberRequest {
  user_id: number
  role?: string | null
}

export interface TeamKeyCount {
  team_id: string
  member_count: number
  key_count: number
}

export interface TeamUsage {
  team_id: string
  member_count: number
  input_tokens: number
  output_tokens: number
  cached_input_tokens: number
  cost_usd: number
  message_count: number
}

// ---------- Directory / LDAP ----------
export type LdapKind = 'ldap' | 'active_directory'
export type LdapTlsMode = 'none' | 'starttls' | 'ldaps'

export interface LdapConnection {
  id: string
  org_id: string | null
  name: string
  kind: LdapKind
  host: string
  port: number
  bind_dn: string
  base_dn: string
  user_filter: string
  group_filter: string | null
  tls_mode: LdapTlsMode
  attr_map: Record<string, string> | null
  group_role_map: Record<string, string> | null
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface CreateLdapConnectionRequest {
  name: string
  kind?: LdapKind
  host: string
  port?: number | null
  bind_dn: string
  bind_secret: string
  base_dn: string
  user_filter?: string | null
  group_filter?: string | null
  tls_mode?: LdapTlsMode
  attr_map?: Record<string, string> | null
  group_role_map?: Record<string, string> | null
  enabled?: boolean
}

export interface UpdateLdapConnectionRequest {
  name?: string
  host?: string
  port?: number | null
  bind_dn?: string
  bind_secret?: string
  base_dn?: string
  user_filter?: string | null
  group_filter?: string | null
  tls_mode?: LdapTlsMode
  attr_map?: Record<string, string> | null
  group_role_map?: Record<string, string> | null
  enabled?: boolean
}

export interface LdapTestResult {
  ok: boolean
  message: string | null
}

// ---------- Auth config (public bootstrap) ----------
export interface AuthConfig {
  password: boolean
  social: string[]
  directory: boolean
  enterprise: boolean
}
