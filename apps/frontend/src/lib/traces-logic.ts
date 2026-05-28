// apps/frontend/src/lib/traces-logic.ts
// Pure helpers for the Gateway → Traces page (J7).
import type { TraceRow, TraceStatus } from './gateway-types'

export interface TraceFilters {
  model?: string
  provider?: string
  status?: TraceStatus | 'all'
  from?: string // ISO
  to?: string // ISO
  search?: string
}

/** Build a query string from filter state — empty values are dropped. */
export function buildTraceQuery(f: TraceFilters): string {
  const p = new URLSearchParams()
  if (f.model) p.set('model', f.model)
  if (f.provider) p.set('provider', f.provider)
  if (f.status && f.status !== 'all') p.set('status', f.status)
  if (f.from) p.set('from', f.from)
  if (f.to) p.set('to', f.to)
  if (f.search) p.set('q', f.search)
  return p.toString()
}

/** Status badge class fragment. */
export function traceStatusBadge(s: TraceStatus): string {
  switch (s) {
    case 'ok':
      return 'pill pill-green'
    case 'error':
      return 'pill pill-red'
    case 'blocked':
      return 'pill pill-yellow'
    case 'rate_limited':
      return 'pill pill-blue'
    case 'budget_exhausted':
      return 'pill pill-red'
  }
}

/** Format cost cents → "$0.0123". */
export function formatCents(cents: number | null): string {
  if (cents == null) return '—'
  return '$' + (cents / 100).toFixed(4)
}

/** Format duration ms → "123ms" / "1.2s". */
export function formatMs(ms: number | null): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

/** Group rows by a key for sparkline-style summaries. */
export function groupByStatus(rows: TraceRow[]): Record<TraceStatus, number> {
  const out: Record<TraceStatus, number> = {
    ok: 0,
    error: 0,
    blocked: 0,
    rate_limited: 0,
    budget_exhausted: 0,
  }
  for (const r of rows) out[r.status]++
  return out
}
