// apps/frontend/src/lib/memories-types.ts
//
// Shared types + pure-logic helpers for the v1 Memories surface.
// Mirrors `server/api/src/ai_portal/memory/*` shapes. IDs and timestamps are
// kept loose (string) so the lib stays decoupled from any one runtime model.

export type ScopeKind = 'user' | 'conversation' | 'assistant' | 'team' | 'org'

export type MemoryType =
  | 'fact'
  | 'preference'
  | 'entity'
  | 'relation'
  | 'episode'
  | 'procedure'

export type ConflictStrategy = 'newer_wins' | 'keep_both' | 'prompt_user'

export interface MemoryV1 {
  id: string
  type: MemoryType
  scope_kind: ScopeKind
  scope_ids: string[]
  text: string
  importance: number
  confidence: number
  tags: string[]
  pinned: boolean
  created_at: string | null
}

export interface MemoryUse {
  response_message_id: string
  score: number
  ts: string | null
}

export interface MemoryProvenance {
  uses: MemoryUse[]
  source: {
    conversation_id: string | null
    turn_ids: string[]
    extractor_model: string | null
  }
}

export interface RecalledMemory {
  memory_id: string
  text: string
  score: number
  explain: Record<string, unknown>
}

export interface ExtractionTriggers {
  per_turn?: boolean
  on_close?: boolean
  scheduled?: boolean
  explicit_only?: boolean
}

export interface ExtractionPolicy {
  scope_kind: ScopeKind
  triggers: ExtractionTriggers
  sensitive_block: string[]
  model_allow: string[]
  conflict_strategy: ConflictStrategy
  retention_days: Record<string, number>
}

export interface RecallPolicy {
  scope_kind: ScopeKind
  top_k: number
  recency_weight: number
  importance_weight: number
  filters: Record<string, unknown>
}

export interface MemoryPoliciesPayload {
  extraction: ExtractionPolicy[]
  recall: RecallPolicy[]
}

export interface MemoryAnalytics {
  count_over_time?: Array<{ ts: string; count: number }>
  top_recalled?: Array<{ memory_id: string; text: string; uses: number }>
  recall_hit_rate?: number
  extraction_outcomes?: {
    created: number
    updated: number
    skipped_sensitive: number
    skipped_dedup: number
    skipped_paused: number
  }
}

// ── Pure helpers ──────────────────────────────────────────────────────

export const MEMORY_TYPES: MemoryType[] = [
  'fact',
  'preference',
  'entity',
  'relation',
  'episode',
  'procedure',
]

export const SCOPE_KINDS: ScopeKind[] = [
  'user',
  'conversation',
  'assistant',
  'team',
  'org',
]

export const SHARED_SCOPES: ScopeKind[] = ['team', 'org', 'assistant']

export const SENSITIVE_CATEGORIES = [
  'health',
  'racial_or_ethnic',
  'political',
  'religious',
  'trade_union',
  'genetic',
  'biometric',
  'sex_life',
  'sexual_orientation',
  'financial',
] as const

export type SensitiveCategory = (typeof SENSITIVE_CATEGORIES)[number]

/** Default TTL (days) per memory type; ∞ = null. Mirrors backend `decay.py`. */
export const DEFAULT_RETENTION_DAYS: Record<MemoryType, number | null> = {
  fact: 365,
  preference: null,
  entity: null,
  relation: 180,
  episode: 90,
  procedure: 180,
}

/** Clamp importance into [0,1] with a sensible default. */
export function clampImportance(v: number): number {
  if (Number.isNaN(v)) return 0.5
  if (v < 0) return 0
  if (v > 1) return 1
  return v
}

/** Round importance to step matching the slider granularity. */
export function quantizeImportance(v: number, step = 0.05): number {
  const c = clampImportance(v)
  return Math.round(c / step) * step
}

/** Filter by type + scope + free-text. Pure. */
export function filterMemories(
  memories: readonly MemoryV1[],
  opts: { type?: MemoryType | 'all'; scope?: ScopeKind | 'all'; q?: string },
): MemoryV1[] {
  const q = (opts.q ?? '').trim().toLowerCase()
  return memories.filter((m) => {
    if (opts.type && opts.type !== 'all' && m.type !== opts.type) return false
    if (opts.scope && opts.scope !== 'all' && m.scope_kind !== opts.scope) return false
    if (q && !m.text.toLowerCase().includes(q)) return false
    return true
  })
}

/** "Shared" = team/org/assistant scope. */
export function isShared(m: MemoryV1): boolean {
  return SHARED_SCOPES.includes(m.scope_kind)
}

/** Toggle a category value in/out of an exclusion list. Pure. */
export function toggleCategory<T extends string>(
  list: readonly T[],
  cat: T,
): T[] {
  return list.includes(cat) ? list.filter((c) => c !== cat) : [...list, cat]
}

/** Map raw RecallPolicy weights into a normalised ratio { vector, recency, importance }. */
export function normaliseRecallWeights(p: Pick<RecallPolicy, 'recency_weight' | 'importance_weight'>): {
  vector: number
  recency: number
  importance: number
} {
  const r = Math.max(0, Math.min(1, p.recency_weight))
  const i = Math.max(0, Math.min(1, p.importance_weight))
  const v = Math.max(0, 1 - r - i)
  return { vector: v, recency: r, importance: i }
}

/** Validate a retention number; returns string error or null. Pure. */
export function validateRetentionDays(raw: string): string | null {
  const t = raw.trim()
  if (t === '' || t === '∞' || t.toLowerCase() === 'never') return null
  const n = Number(t)
  if (!Number.isFinite(n)) return 'Must be a number or empty for never'
  if (n < 0) return 'Must be ≥ 0'
  if (n > 36500) return 'Too large (max 100y)'
  return null
}

/** Parse retention number from raw input. `null` = never. */
export function parseRetentionDays(raw: string): number | null {
  const t = raw.trim()
  if (!t || t === '∞' || t.toLowerCase() === 'never') return null
  const n = Number(t)
  if (!Number.isFinite(n)) return null
  return Math.max(0, Math.floor(n))
}

/** Bucket memories by type for a quick "count" summary. Pure. */
export function countByType(memories: readonly MemoryV1[]): Record<MemoryType, number> {
  const out = {
    fact: 0,
    preference: 0,
    entity: 0,
    relation: 0,
    episode: 0,
    procedure: 0,
  } satisfies Record<MemoryType, number>
  for (const m of memories) out[m.type]++
  return out
}
