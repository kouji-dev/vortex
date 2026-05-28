import { authorizedFetch } from './authorizedFetch'
import { getApiBase } from './api-base'
import type {
  ApiKeySummary,
  AuditFilter,
  AuditPage,
  CreateApiKeyRequest,
  CreateApiKeyResponse,
  CreateIdpConnectionRequest,
  IdpConnection,
  InviteMemberRequest,
  OrgInvitation,
  OrgMember,
  UpdateIdpConnectionRequest,
  UpdateMemberRoleRequest,
  UsageDimension,
  UsagePeriod,
  UsageReport,
} from './admin-types'

function v1(path: string): string {
  return `${getApiBase()}/api${path}`
}

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: string | undefined
    try {
      const body = (await res.clone().json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // swallow
    }
    throw new Error(detail ? `HTTP ${res.status}: ${detail}` : `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

// ---------- Members ----------
export async function fetchMembers(): Promise<OrgMember[]> {
  return asJson(await authorizedFetch(v1('/v1/members')))
}

export async function inviteMember(req: InviteMemberRequest): Promise<OrgInvitation> {
  return asJson(
    await authorizedFetch(v1('/v1/members/invitations'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function fetchInvitations(): Promise<OrgInvitation[]> {
  return asJson(await authorizedFetch(v1('/v1/members/invitations')))
}

export async function updateMemberRole(
  userId: string,
  req: UpdateMemberRoleRequest,
): Promise<OrgMember> {
  return asJson(
    await authorizedFetch(v1(`/v1/members/${userId}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function removeMember(userId: string): Promise<void> {
  const res = await authorizedFetch(v1(`/v1/members/${userId}`), { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

export async function revokeInvitation(id: string): Promise<void> {
  const res = await authorizedFetch(v1(`/v1/members/invitations/${id}`), { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

// ---------- SSO ----------
export async function fetchIdpConnections(): Promise<IdpConnection[]> {
  return asJson(await authorizedFetch(v1('/v1/idp-connections')))
}

export async function createIdpConnection(
  req: CreateIdpConnectionRequest,
): Promise<IdpConnection> {
  return asJson(
    await authorizedFetch(v1('/v1/idp-connections'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function updateIdpConnection(
  id: string,
  req: UpdateIdpConnectionRequest,
): Promise<IdpConnection> {
  return asJson(
    await authorizedFetch(v1(`/v1/idp-connections/${id}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function deleteIdpConnection(id: string): Promise<void> {
  const res = await authorizedFetch(v1(`/v1/idp-connections/${id}`), { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

// ---------- API Keys ----------
export async function fetchApiKeys(): Promise<ApiKeySummary[]> {
  return asJson(await authorizedFetch(v1('/v1/api-keys')))
}

export async function createApiKey(req: CreateApiKeyRequest): Promise<CreateApiKeyResponse> {
  return asJson(
    await authorizedFetch(v1('/v1/api-keys'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function revokeApiKey(id: string): Promise<void> {
  const res = await authorizedFetch(v1(`/v1/api-keys/${id}`), { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

// ---------- Audit ----------
export function buildAuditQuery(filter: AuditFilter): string {
  const p = new URLSearchParams()
  if (filter.action) p.set('action', filter.action)
  if (filter.actor) p.set('actor', filter.actor)
  if (filter.resource_type) p.set('resource_type', filter.resource_type)
  if (filter.resource_id) p.set('resource_id', filter.resource_id)
  if (filter.from) p.set('from', filter.from)
  if (filter.to) p.set('to', filter.to)
  if (filter.cursor) p.set('cursor', filter.cursor)
  if (filter.limit != null) p.set('limit', String(filter.limit))
  return p.toString()
}

export async function fetchAuditEvents(filter: AuditFilter): Promise<AuditPage> {
  const q = buildAuditQuery(filter)
  return asJson(await authorizedFetch(v1(`/v1/audit-events${q ? `?${q}` : ''}`)))
}

export function auditExportUrl(filter: AuditFilter): string {
  const q = buildAuditQuery({ ...filter, limit: undefined, cursor: undefined })
  return v1(`/v1/audit-events:export?fmt=csv${q ? `&${q}` : ''}`)
}

// ---------- Usage ----------
export async function fetchUsage(
  dim: UsageDimension,
  period: UsagePeriod,
  from?: string,
  to?: string,
): Promise<UsageReport> {
  const p = new URLSearchParams({ dim, period })
  if (from) p.set('from', from)
  if (to) p.set('to', to)
  return asJson(await authorizedFetch(v1(`/v1/usage?${p}`)))
}
