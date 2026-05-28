/**
 * React Query hooks bound to the v1 memories surface
 * (`server/api/src/ai_portal/memory/v1_router.py`).
 *
 * Distinct from the older `useMemoriesQuery` (single-row legacy profile at
 * `/api/users/me/memories`). Both will co-exist until the legacy UI is
 * migrated.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import type {
  ExtractionPolicy,
  MemoryAnalytics,
  MemoryPoliciesPayload,
  MemoryProvenance,
  MemoryType,
  MemoryV1,
  RecallPolicy,
  RecalledMemory,
  ScopeKind,
} from '~/lib/memories-types'

// ── helpers ──────────────────────────────────────────────────────────

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}${body ? `: ${body}` : ''}`)
  }
  // 204
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const v1QK = {
  list: (filters: { type?: MemoryType; scope?: ScopeKind; q?: string }) =>
    ['memories-v1', 'list', filters] as const,
  policies: () => ['memories-v1', 'policies'] as const,
  analytics: () => ['memories-v1', 'analytics'] as const,
  uses: (id: string) => ['memories-v1', 'uses', id] as const,
}

// ── list ──────────────────────────────────────────────────────────────

export interface ListMemoriesFilters {
  type?: MemoryType
  scope?: ScopeKind
  q?: string
  limit?: number
}

export function useMemoriesV1Query(filters: ListMemoriesFilters = {}) {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: v1QK.list(filters),
    queryFn: async (): Promise<MemoryV1[]> => {
      const qs = new URLSearchParams()
      if (filters.type) qs.set('type', filters.type)
      if (filters.scope) qs.set('scope', filters.scope)
      if (filters.q) qs.set('q', filters.q)
      if (filters.limit) qs.set('limit', String(filters.limit))
      const res = await fetch(`${apiBase}/v1/memories?${qs.toString()}`, {
        headers: await getAuthHeaders(),
      })
      return jsonOrThrow<MemoryV1[]>(res)
    },
  })
}

// ── create (manual) ───────────────────────────────────────────────────

export interface CreateMemoryV1Body {
  type: MemoryType
  text: string
  scope_kind?: ScopeKind
  scope_ids?: string[]
  importance?: number
  confidence?: number
  tags?: string[]
  pinned?: boolean
}

export function useCreateMemoryV1() {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: CreateMemoryV1Body) => {
      const res = await fetch(`${apiBase}/v1/memories`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(await getAuthHeaders()) },
        body: JSON.stringify(body),
      })
      return jsonOrThrow<{ id: string; text: string; type: MemoryType }>(res)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['memories-v1'] })
    },
  })
}

// ── patch ─────────────────────────────────────────────────────────────

export interface PatchMemoryBody {
  text?: string
  importance?: number
  pinned?: boolean
  tags?: string[]
  confidence?: number
}

export function usePatchMemoryV1() {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: PatchMemoryBody }) => {
      const res = await fetch(`${apiBase}/v1/memories/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...(await getAuthHeaders()) },
        body: JSON.stringify(body),
      })
      return jsonOrThrow<{ id: string; text: string; importance: number; pinned: boolean }>(res)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['memories-v1'] })
    },
  })
}

// ── delete ────────────────────────────────────────────────────────────

export function useDeleteMemoryV1() {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await fetch(`${apiBase}/v1/memories/${id}`, {
        method: 'DELETE',
        headers: await getAuthHeaders(),
      })
      return jsonOrThrow<void>(res)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['memories-v1'] })
    },
  })
}

// ── bulk delete ──────────────────────────────────────────────────────

export interface BulkDeleteFilter {
  ids?: string[]
  type?: MemoryType
  scope_kind?: ScopeKind
  time_from?: string
  time_to?: string
}

export function useBulkDeleteMemoriesV1() {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (filter: BulkDeleteFilter) => {
      const res = await fetch(`${apiBase}/v1/memories/bulk-delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(await getAuthHeaders()) },
        body: JSON.stringify(filter),
      })
      return jsonOrThrow<{ deleted: number }>(res)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['memories-v1'] })
    },
  })
}

// ── provenance (uses) ────────────────────────────────────────────────

export function useMemoryUsesQuery(id: string | null) {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: v1QK.uses(id ?? ''),
    enabled: !!id,
    queryFn: async (): Promise<MemoryProvenance> => {
      const res = await fetch(`${apiBase}/v1/memories/${id}/uses`, {
        headers: await getAuthHeaders(),
      })
      return jsonOrThrow<MemoryProvenance>(res)
    },
  })
}

// ── recall (debug) ───────────────────────────────────────────────────

export interface RecallRequestBody {
  query: string
  top_k?: number
  recency_weight?: number
  importance_weight?: number
  assistant_id?: string | null
  conversation_id?: string | null
}

export function useRecallMemories() {
  const apiBase = getApiBase()
  return useMutation({
    mutationFn: async (body: RecallRequestBody) => {
      const res = await fetch(`${apiBase}/v1/memories/recall`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(await getAuthHeaders()) },
        body: JSON.stringify(body),
      })
      return jsonOrThrow<RecalledMemory[]>(res)
    },
  })
}

// ── policies ─────────────────────────────────────────────────────────

export function useMemoryPoliciesQuery() {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: v1QK.policies(),
    queryFn: async (): Promise<MemoryPoliciesPayload> => {
      const res = await fetch(`${apiBase}/v1/memories/policies`, {
        headers: await getAuthHeaders(),
      })
      return jsonOrThrow<MemoryPoliciesPayload>(res)
    },
  })
}

export function useSaveExtractionPolicy() {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (p: ExtractionPolicy) => {
      const res = await fetch(`${apiBase}/v1/memories/policies/extraction`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(await getAuthHeaders()) },
        body: JSON.stringify(p),
      })
      return jsonOrThrow<{ ok: boolean }>(res)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: v1QK.policies() })
    },
  })
}

export function useSaveRecallPolicy() {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (p: RecallPolicy) => {
      const res = await fetch(`${apiBase}/v1/memories/policies/recall`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(await getAuthHeaders()) },
        body: JSON.stringify(p),
      })
      return jsonOrThrow<{ ok: boolean }>(res)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: v1QK.policies() })
    },
  })
}

// ── pause / resume ───────────────────────────────────────────────────

export interface PauseBody {
  scope_kind?: ScopeKind | null
  scope_id?: string | null
}

export function usePauseMemoriesV1() {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: PauseBody) => {
      const res = await fetch(`${apiBase}/v1/memories/pause`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(await getAuthHeaders()) },
        body: JSON.stringify(body),
      })
      return jsonOrThrow<{ id: string; paused_at: string | null }>(res)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['memories-v1'] })
    },
  })
}

export function useResumeMemoriesV1() {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: PauseBody) => {
      const res = await fetch(`${apiBase}/v1/memories/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(await getAuthHeaders()) },
        body: JSON.stringify(body),
      })
      return jsonOrThrow<{ cleared: number }>(res)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['memories-v1'] })
    },
  })
}

// ── export ───────────────────────────────────────────────────────────

export function useExportMemoriesV1() {
  const apiBase = getApiBase()
  return useMutation({
    mutationFn: async (): Promise<Record<string, unknown>> => {
      const res = await fetch(`${apiBase}/v1/memories/export`, {
        headers: await getAuthHeaders(),
      })
      return jsonOrThrow(res)
    },
  })
}

// ── analytics ────────────────────────────────────────────────────────

export function useMemoryAnalyticsQuery() {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: v1QK.analytics(),
    queryFn: async (): Promise<MemoryAnalytics> => {
      const res = await fetch(`${apiBase}/v1/memories/analytics`, {
        headers: await getAuthHeaders(),
      })
      return jsonOrThrow<MemoryAnalytics>(res)
    },
  })
}
