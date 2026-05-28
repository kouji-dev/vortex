import { authorizedFetch } from './authorizedFetch'
import { getApiBase } from './api-base'
import type {
  ApiKeySummary,
  AuditFilter,
  AuditPage,
  Budget,
  BudgetCreateRequest,
  BudgetStatus,
  CreateApiKeyRequest,
  CreateApiKeyResponse,
  CreateIdpConnectionRequest,
  DataDeleteCreateRequest,
  DataDeleteJob,
  DataExportJob,
  IdpConnection,
  Invoice,
  InviteMemberRequest,
  ModuleFlagsMap,
  OrgInvitation,
  OrgMember,
  Quota,
  QuotaCreateRequest,
  ScimEndpoint,
  ScimEndpointCreateRequest,
  ScimEndpointCreated,
  ScimGroup,
  ScimGroupRoleMapRequest,
  SettingsKv,
  Subscription,
  SubscriptionPatchRequest,
  UpdateIdpConnectionRequest,
  UpdateMemberRoleRequest,
  UsageDimension,
  UsagePeriod,
  UsageReport,
  Webhook,
  WebhookCreateRequest,
  WebhookCreated,
  WebhookDelivery,
  WebhookEventType,
  WebhookUpdateRequest,
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

// ---------- Budgets / Quotas ----------
export async function fetchBudgets(): Promise<Budget[]> {
  return asJson(await authorizedFetch(v1('/v1/budgets')))
}

export async function createBudget(req: BudgetCreateRequest): Promise<Budget> {
  return asJson(
    await authorizedFetch(v1('/v1/budgets'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function deleteBudget(id: number): Promise<void> {
  const res = await authorizedFetch(v1(`/v1/budgets/${id}`), { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

export async function fetchBudgetStatus(id: number): Promise<BudgetStatus> {
  return asJson(await authorizedFetch(v1(`/v1/budgets/${id}/status`)))
}

export async function fetchQuotas(): Promise<Quota[]> {
  return asJson(await authorizedFetch(v1('/v1/quotas')))
}

export async function createQuota(req: QuotaCreateRequest): Promise<Quota> {
  return asJson(
    await authorizedFetch(v1('/v1/quotas'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function deleteQuota(id: number): Promise<void> {
  const res = await authorizedFetch(v1(`/v1/quotas/${id}`), { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

// ---------- Webhooks ----------
export async function fetchWebhooks(): Promise<Webhook[]> {
  return asJson(await authorizedFetch(v1('/v1/webhooks')))
}

export async function createWebhook(req: WebhookCreateRequest): Promise<WebhookCreated> {
  return asJson(
    await authorizedFetch(v1('/v1/webhooks'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function updateWebhook(id: string, req: WebhookUpdateRequest): Promise<Webhook> {
  return asJson(
    await authorizedFetch(v1(`/v1/webhooks/${id}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function deleteWebhook(id: string): Promise<void> {
  const res = await authorizedFetch(v1(`/v1/webhooks/${id}`), { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

export async function fetchWebhookDeliveries(id: string): Promise<{ items: WebhookDelivery[]; total: number }> {
  return asJson(await authorizedFetch(v1(`/v1/webhooks/${id}/deliveries`)))
}

export async function replayWebhookDelivery(
  webhookId: string,
  deliveryId: string,
): Promise<WebhookDelivery> {
  return asJson(
    await authorizedFetch(v1(`/v1/webhooks/${webhookId}/deliveries/${deliveryId}/replay`), {
      method: 'POST',
    }),
  )
}

export async function fetchWebhookEventTypes(): Promise<{ items: WebhookEventType[] }> {
  return asJson(await authorizedFetch(v1('/v1/webhook-event-types')))
}

// ---------- Billing ----------
export async function fetchSubscription(): Promise<Subscription | null> {
  const res = await authorizedFetch(v1('/v1/billing/subscription'))
  if (res.status === 404) return null
  return asJson(res)
}

export async function patchSubscription(req: SubscriptionPatchRequest): Promise<Subscription> {
  return asJson(
    await authorizedFetch(v1('/v1/billing/subscription'), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function fetchInvoices(): Promise<{ items: Invoice[] }> {
  return asJson(await authorizedFetch(v1('/v1/billing/invoices')))
}

// ---------- Settings ----------
export async function fetchSettings(): Promise<SettingsKv> {
  return asJson(await authorizedFetch(v1('/v1/settings')))
}

export async function patchSettings(settings: Record<string, unknown>): Promise<SettingsKv> {
  return asJson(
    await authorizedFetch(v1('/v1/settings'), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings }),
    }),
  )
}

export async function fetchModuleFlags(): Promise<ModuleFlagsMap> {
  return asJson(await authorizedFetch(v1('/v1/module-flags')))
}

export async function patchModuleFlags(
  modules: Record<string, { enabled?: boolean; gates?: Record<string, unknown> }>,
): Promise<ModuleFlagsMap> {
  return asJson(
    await authorizedFetch(v1('/v1/module-flags'), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ modules }),
    }),
  )
}

// ---------- SCIM ----------
export async function fetchScimEndpoints(): Promise<ScimEndpoint[]> {
  return asJson(await authorizedFetch(v1('/v1/scim/endpoints')))
}

export async function createScimEndpoint(
  req: ScimEndpointCreateRequest,
): Promise<ScimEndpointCreated> {
  return asJson(
    await authorizedFetch(v1('/v1/scim/endpoints'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function revokeScimEndpoint(id: string): Promise<void> {
  const res = await authorizedFetch(v1(`/v1/scim/endpoints/${id}`), { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

export async function upsertScimGroupRole(
  endpointId: string,
  req: ScimGroupRoleMapRequest,
): Promise<ScimGroup> {
  return asJson(
    await authorizedFetch(v1(`/v1/scim/endpoints/${endpointId}/group-roles`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

// ---------- GDPR Data ----------
export async function requestDataExport(): Promise<DataExportJob> {
  return asJson(
    await authorizedFetch(v1('/v1/data-export'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    }),
  )
}

export async function fetchDataExport(id: string): Promise<DataExportJob> {
  return asJson(await authorizedFetch(v1(`/v1/data-export/${id}`)))
}

export async function requestDataDelete(req: DataDeleteCreateRequest): Promise<DataDeleteJob> {
  return asJson(
    await authorizedFetch(v1('/v1/data-delete'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function fetchDataDelete(id: string): Promise<DataDeleteJob> {
  return asJson(await authorizedFetch(v1(`/v1/data-delete/${id}`)))
}
