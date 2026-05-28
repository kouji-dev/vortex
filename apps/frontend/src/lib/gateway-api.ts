// Gateway HTTP client — mirrors server/api/src/ai_portal/gateway/* routers.
// Keep this file thin; pure formatting/aggregation helpers live alongside
// each page (gateway-overview.ts etc.) and are unit-tested with node:test.

import { authorizedFetch } from './authorizedFetch'
import { getApiBase } from './api-base'
import type {
  ModelAlias,
  ModelInfo,
  ProviderCredential,
  ProviderKind,
  RateLimitDimension,
  RateLimitRule,
  RoutingPolicy,
  RoutingStrategy,
  TraceRow,
} from './gateway-types'

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

async function asOk(res: Response): Promise<void> {
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

// ---------- Providers / credentials ----------
export async function fetchProviderCredentials(): Promise<ProviderCredential[]> {
  const data = await asJson<{ items: ProviderCredential[] } | ProviderCredential[]>(
    await authorizedFetch(v1('/v1/gateway/providers/credentials')),
  )
  return Array.isArray(data) ? data : data.items
}

export async function createProviderCredential(req: {
  provider: ProviderKind | string
  label?: string
  secret: string
}): Promise<ProviderCredential> {
  return asJson(
    await authorizedFetch(v1('/v1/gateway/providers/credentials'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function deleteProviderCredential(id: string): Promise<void> {
  await asOk(
    await authorizedFetch(v1(`/v1/gateway/providers/credentials/${id}`), {
      method: 'DELETE',
    }),
  )
}

export async function probeProviderHealth(id: string): Promise<ProviderCredential> {
  return asJson(
    await authorizedFetch(v1(`/v1/gateway/providers/credentials/${id}/health`), {
      method: 'POST',
    }),
  )
}

// ---------- Models catalog ----------
export async function fetchGatewayModels(): Promise<ModelInfo[]> {
  const data = await asJson<{ items: ModelInfo[] } | ModelInfo[]>(
    await authorizedFetch(v1('/v1/gateway/models')),
  )
  return Array.isArray(data) ? data : data.items
}

// ---------- Routing policies / aliases ----------
export async function fetchRoutingPolicies(): Promise<RoutingPolicy[]> {
  const data = await asJson<{ items: RoutingPolicy[] } | RoutingPolicy[]>(
    await authorizedFetch(v1('/v1/gateway/routing-policies')),
  )
  return Array.isArray(data) ? data : data.items
}

export async function createRoutingPolicy(req: {
  name: string
  strategy: RoutingStrategy
  rules_json: unknown
}): Promise<RoutingPolicy> {
  return asJson(
    await authorizedFetch(v1('/v1/gateway/routing-policies'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function updateRoutingPolicy(
  id: string,
  req: { name?: string; strategy?: RoutingStrategy; rules_json?: unknown },
): Promise<RoutingPolicy> {
  return asJson(
    await authorizedFetch(v1(`/v1/gateway/routing-policies/${id}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function deleteRoutingPolicy(id: string): Promise<void> {
  await asOk(
    await authorizedFetch(v1(`/v1/gateway/routing-policies/${id}`), { method: 'DELETE' }),
  )
}

export async function fetchModelAliases(): Promise<ModelAlias[]> {
  const data = await asJson<{ items: ModelAlias[] } | ModelAlias[]>(
    await authorizedFetch(v1('/v1/gateway/model-aliases')),
  )
  return Array.isArray(data) ? data : data.items
}

export async function createModelAlias(req: {
  alias: string
  routing_policy_id: string
}): Promise<ModelAlias> {
  return asJson(
    await authorizedFetch(v1('/v1/gateway/model-aliases'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function deleteModelAlias(id: string): Promise<void> {
  await asOk(
    await authorizedFetch(v1(`/v1/gateway/model-aliases/${id}`), { method: 'DELETE' }),
  )
}

// ---------- Rate limit rules ----------
export async function fetchRateLimitRules(): Promise<RateLimitRule[]> {
  const data = await asJson<{ items: RateLimitRule[] } | RateLimitRule[]>(
    await authorizedFetch(v1('/v1/gateway/rate-limits')),
  )
  return Array.isArray(data) ? data : data.items
}

export async function createRateLimitRule(req: {
  scope_json: Record<string, unknown>
  dimension: RateLimitDimension
  period: string
  limit: number
  burst?: number | null
}): Promise<RateLimitRule> {
  return asJson(
    await authorizedFetch(v1('/v1/gateway/rate-limits'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

export async function deleteRateLimitRule(id: string): Promise<void> {
  await asOk(
    await authorizedFetch(v1(`/v1/gateway/rate-limits/${id}`), { method: 'DELETE' }),
  )
}

// ---------- Traces (used by Overview to derive KPIs) ----------
export interface TraceSearchParams {
  from?: string
  to?: string
  model?: string
  status?: string
  provider?: string
  limit?: number
  cursor?: string
}

export interface TraceSearchPage {
  items: TraceRow[]
  next_cursor: string | null
}

export async function searchTraces(p: TraceSearchParams = {}): Promise<TraceSearchPage> {
  const q = new URLSearchParams()
  if (p.from) q.set('from', p.from)
  if (p.to) q.set('to', p.to)
  if (p.model) q.set('model', p.model)
  if (p.status) q.set('status', p.status)
  if (p.provider) q.set('provider', p.provider)
  if (p.limit != null) q.set('limit', String(p.limit))
  if (p.cursor) q.set('cursor', p.cursor)
  const qs = q.toString()
  return asJson(
    await authorizedFetch(v1(`/v1/gateway/traces${qs ? `?${qs}` : ''}`)),
  )
}
