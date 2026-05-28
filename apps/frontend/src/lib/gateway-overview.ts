// Pure aggregation helpers for the Gateway Overview KPIs.
// Derives p50/p95, error rate, top models, requests/min from a list of
// trace summaries — so the dashboard can render even when the backend
// `/v1/gateway/overview` endpoint isn't available yet (graceful fallback).

import type { TraceRow } from './gateway-types'

export interface OverviewKpis {
  windowSeconds: number
  requests: number
  errors: number
  errorRate: number // 0..1
  requestsPerMin: number
  p50: number | null
  p95: number | null
  p99: number | null
  topModels: Array<{ model: string; count: number; cost_cents: number }>
  topProviders: Array<{ provider: string; count: number; errorRate: number }>
}

const ERROR_STATUSES = new Set(['error', 'blocked', 'rate_limited', 'budget_exhausted'])

/** Compute percentile from a pre-sorted ascending array. Returns null if empty. */
export function percentile(sortedAsc: readonly number[], p: number): number | null {
  if (sortedAsc.length === 0) return null
  if (sortedAsc.length === 1) return sortedAsc[0]
  const idx = Math.min(sortedAsc.length - 1, Math.max(0, Math.ceil(p * sortedAsc.length) - 1))
  return sortedAsc[idx]
}

/** Aggregate KPIs from a window of traces. */
export function computeOverview(traces: readonly TraceRow[], windowSeconds: number): OverviewKpis {
  let errors = 0
  const lat: number[] = []
  const byModel = new Map<string, { count: number; cost_cents: number }>()
  const byProvider = new Map<string, { count: number; errors: number }>()

  for (const t of traces) {
    if (ERROR_STATUSES.has(t.status)) errors += 1
    if (typeof t.latency_ms === 'number') lat.push(t.latency_ms)
    const model = t.model_used ?? t.model_requested ?? 'unknown'
    const m = byModel.get(model) ?? { count: 0, cost_cents: 0 }
    m.count += 1
    m.cost_cents += t.cost_cents ?? 0
    byModel.set(model, m)
    const provider = t.provider ?? 'unknown'
    const pv = byProvider.get(provider) ?? { count: 0, errors: 0 }
    pv.count += 1
    if (ERROR_STATUSES.has(t.status)) pv.errors += 1
    byProvider.set(provider, pv)
  }
  lat.sort((a, b) => a - b)

  const requests = traces.length
  const requestsPerMin = windowSeconds > 0 ? (requests / windowSeconds) * 60 : 0
  const errorRate = requests === 0 ? 0 : errors / requests

  const topModels = Array.from(byModel.entries())
    .map(([model, v]) => ({ model, count: v.count, cost_cents: v.cost_cents }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5)

  const topProviders = Array.from(byProvider.entries())
    .map(([provider, v]) => ({
      provider,
      count: v.count,
      errorRate: v.count === 0 ? 0 : v.errors / v.count,
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5)

  return {
    windowSeconds,
    requests,
    errors,
    errorRate,
    requestsPerMin,
    p50: percentile(lat, 0.5),
    p95: percentile(lat, 0.95),
    p99: percentile(lat, 0.99),
    topModels,
    topProviders,
  }
}

/** Pretty-print latency in ms with one decimal when below 1s, else seconds. */
export function formatLatency(ms: number | null): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

/** Format cents as a $ string. */
export function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

/** Format a 0..1 rate as a % string. */
export function formatPct(rate: number, digits = 1): string {
  return `${(rate * 100).toFixed(digits)}%`
}
