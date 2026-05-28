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

export interface ApiKeySummary {
  id: string
  name: string
  prefix: string
  scopes: ApiKeyScope[]
  expires_at: string | null
  last_used_at: string | null
  created_at: string
  revoked_at: string | null
}

export interface CreateApiKeyRequest {
  name: string
  scopes: ApiKeyScope[]
  expires_at?: string | null
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
