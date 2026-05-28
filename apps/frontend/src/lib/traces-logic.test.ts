// apps/frontend/src/lib/traces-logic.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildTraceQuery, formatCents, formatMs, groupByStatus, traceStatusBadge } from './traces-logic'
import type { TraceRow } from './gateway-types'

test('buildTraceQuery drops empties and respects "all"', () => {
  assert.equal(buildTraceQuery({}), '')
  assert.equal(buildTraceQuery({ status: 'all' }), '')
  assert.equal(
    buildTraceQuery({ model: 'claude', status: 'error', from: '2026-05-01T00:00:00Z' }),
    'model=claude&status=error&from=2026-05-01T00%3A00%3A00Z',
  )
  assert.equal(buildTraceQuery({ search: 'foo bar' }), 'q=foo+bar')
})

test('formatters', () => {
  assert.equal(formatCents(null), '—')
  assert.equal(formatCents(0), '$0.0000')
  assert.equal(formatCents(123), '$1.2300')
  assert.equal(formatMs(null), '—')
  assert.equal(formatMs(500), '500ms')
  assert.equal(formatMs(2345), '2.35s')
})

test('traceStatusBadge mapping', () => {
  assert.match(traceStatusBadge('ok'), /green/)
  assert.match(traceStatusBadge('error'), /red/)
  assert.match(traceStatusBadge('blocked'), /yellow/)
  assert.match(traceStatusBadge('rate_limited'), /blue/)
})

test('groupByStatus tallies correctly', () => {
  const mk = (s: TraceRow['status']): TraceRow => ({
    id: 'x',
    ts: '',
    actor: { org_id: 'o' },
    route: '/v1/chat/completions',
    model_requested: 'm',
    model_used: 'm',
    provider: 'p',
    status: s,
    latency_ms: 0,
    ttft_ms: 0,
    tokens_in: 0,
    tokens_out: 0,
    tokens_cache_read: 0,
    tokens_cache_write: 0,
    cost_cents: 0,
    cache_hit: false,
    error: null,
  })
  const rows = [mk('ok'), mk('ok'), mk('error'), mk('blocked')]
  const grouped = groupByStatus(rows)
  assert.equal(grouped.ok, 2)
  assert.equal(grouped.error, 1)
  assert.equal(grouped.blocked, 1)
  assert.equal(grouped.rate_limited, 0)
})
