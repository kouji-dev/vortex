import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { computeOverview, percentile, formatLatency, formatPct } from './gateway-overview.ts'
import type { TraceRow } from './gateway-types.ts'

function row(over: Partial<TraceRow> = {}): TraceRow {
  return {
    id: 'r' + Math.random(),
    ts: '2026-01-01T00:00:00Z',
    actor: { org_id: 'o' },
    route: '/v1/chat/completions',
    model_requested: 'claude-sonnet-4-6',
    model_used: 'claude-sonnet-4-6',
    provider: 'anthropic',
    status: 'ok',
    latency_ms: 100,
    ttft_ms: 30,
    tokens_in: 10,
    tokens_out: 20,
    tokens_cache_read: 0,
    tokens_cache_write: 0,
    cost_cents: 5,
    cache_hit: false,
    error: null,
    ...over,
  }
}

test('percentile: empty array → null', () => {
  assert.equal(percentile([], 0.5), null)
})

test('percentile: single value → that value', () => {
  assert.equal(percentile([42], 0.95), 42)
})

test('percentile: p95 of 1..100 → 95', () => {
  const arr: number[] = []
  for (let i = 1; i <= 100; i++) arr.push(i)
  assert.equal(percentile(arr, 0.95), 95)
})

test('computeOverview: counts, error rate, requests/min', () => {
  const traces: TraceRow[] = [
    row({ latency_ms: 50, status: 'ok' }),
    row({ latency_ms: 200, status: 'ok', provider: 'openai', model_used: 'gpt-4o' }),
    row({ latency_ms: 80, status: 'error' }),
    row({ latency_ms: 60, status: 'rate_limited' }),
  ]
  const k = computeOverview(traces, 60) // 1-minute window
  assert.equal(k.requests, 4)
  assert.equal(k.errors, 2)
  assert.equal(k.errorRate, 0.5)
  assert.equal(k.requestsPerMin, 4)
  // sorted latencies = [50, 60, 80, 200]; p50 idx = ceil(.5*4)-1 = 1 → 60
  assert.equal(k.p50, 60)
  assert.equal(k.p95, 200)
})

test('computeOverview: top models sorted by count', () => {
  const traces: TraceRow[] = [
    row({ model_used: 'a' }),
    row({ model_used: 'a' }),
    row({ model_used: 'a' }),
    row({ model_used: 'b' }),
    row({ model_used: 'b' }),
    row({ model_used: 'c' }),
  ]
  const k = computeOverview(traces, 60)
  assert.equal(k.topModels[0].model, 'a')
  assert.equal(k.topModels[0].count, 3)
  assert.equal(k.topModels[1].model, 'b')
  assert.equal(k.topModels[2].model, 'c')
})

test('computeOverview: provider error rate per provider', () => {
  const traces: TraceRow[] = [
    row({ provider: 'p1', status: 'ok' }),
    row({ provider: 'p1', status: 'error' }),
    row({ provider: 'p2', status: 'ok' }),
    row({ provider: 'p2', status: 'ok' }),
  ]
  const k = computeOverview(traces, 60)
  const p1 = k.topProviders.find((p) => p.provider === 'p1')!
  const p2 = k.topProviders.find((p) => p.provider === 'p2')!
  assert.equal(p1.errorRate, 0.5)
  assert.equal(p2.errorRate, 0)
})

test('formatLatency: ms vs seconds', () => {
  assert.equal(formatLatency(null), '—')
  assert.equal(formatLatency(123), '123 ms')
  assert.equal(formatLatency(2500), '2.50 s')
})

test('formatPct: rate to percent', () => {
  assert.equal(formatPct(0.5), '50.0%')
  assert.equal(formatPct(0.123, 2), '12.30%')
})
