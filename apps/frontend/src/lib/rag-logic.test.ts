import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import {
  CONNECTOR_PRESETS,
  compareRuns,
  computeFeedbackRatio,
  filterPresets,
  formatCents,
  formatDelta,
  formatLatencyMs,
  formatPct,
  parseJudgeSpec,
  presetsByCategory,
  sortQueriesByCount,
  summariseAnalytics,
  summariseRun,
  validateEvalName,
  validateEvalRecord,
  validateSearchProviderConfig,
} from './rag-logic.ts'
import type { AnalyticsOverview, EvalRunOut } from './rag-types.ts'

// ── formatting ─────────────────────────────────────────────────────────

test('formatPct: standard', () => {
  assert.equal(formatPct(0.42), '42.0%')
})

test('formatPct: non-finite', () => {
  assert.equal(formatPct(Number.NaN), '—')
})

test('formatCents: small cents stays in ¢', () => {
  assert.equal(formatCents(42.5), '42.50¢')
})

test('formatCents: dollars over 100 cents', () => {
  assert.equal(formatCents(250), '$2.50')
})

test('formatLatencyMs: small ms', () => {
  assert.equal(formatLatencyMs(123), '123 ms')
})

test('formatLatencyMs: seconds', () => {
  assert.equal(formatLatencyMs(2500), '2.50 s')
})

test('formatDelta: positive', () => {
  assert.equal(formatDelta(0.05), '+5.0%')
})

test('formatDelta: zero', () => {
  assert.equal(formatDelta(0), '0%')
})

// ── eval validators ────────────────────────────────────────────────────

test('validateEvalName: empty', () => {
  assert.equal(validateEvalName('   '), 'Name required')
})

test('validateEvalName: too long', () => {
  assert.equal(validateEvalName('x'.repeat(256)), 'Name too long (max 255)')
})

test('validateEvalName: ok', () => {
  assert.equal(validateEvalName('my eval'), null)
})

test('validateEvalRecord: missing query', () => {
  const e = validateEvalRecord({
    id: 'r1',
    query: ' ',
    expected_doc_ids: [],
    judges: ['recall@5'],
  })
  assert.equal(e, 'Query required')
})

test('validateEvalRecord: missing id', () => {
  const e = validateEvalRecord({
    id: '',
    query: 'x',
    expected_doc_ids: [],
    judges: ['recall@5'],
  })
  assert.equal(e, 'Record id required')
})

test('validateEvalRecord: no judges', () => {
  const e = validateEvalRecord({
    id: 'r1',
    query: 'x',
    expected_doc_ids: [],
    judges: [],
  })
  assert.equal(e, 'At least one judge required')
})

test('validateEvalRecord: ok', () => {
  const e = validateEvalRecord({
    id: 'r1',
    query: 'x',
    expected_doc_ids: ['d1'],
    judges: ['recall@5'],
  })
  assert.equal(e, null)
})

// ── parseJudgeSpec ─────────────────────────────────────────────────────

test('parseJudgeSpec: with k', () => {
  assert.deepEqual(parseJudgeSpec('recall@5'), { name: 'recall', k: 5 })
})

test('parseJudgeSpec: without k', () => {
  assert.deepEqual(parseJudgeSpec('mrr'), { name: 'mrr', k: null })
})

// ── summariseRun ───────────────────────────────────────────────────────

function makeRun(passRate: number, delta: number, metrics: Record<string, number>): EvalRunOut {
  return {
    id: 'r1',
    eval_id: 'e1',
    snapshot_id: null,
    summary: {
      pass_rate: passRate,
      mean_metrics: metrics,
      n: 5,
      regression: delta < -0.05,
      regression_delta: delta,
    },
    results: [],
    regression: delta < -0.05,
    ran_at: '2026-01-01T00:00:00Z',
  }
}

test('summariseRun: regression down', () => {
  const s = summariseRun(makeRun(0.5, -0.2, { 'recall@5': 0.5 }))
  assert.equal(s.regression, 'down')
  assert.equal(s.delta, '-20.0%')
  assert.equal(s.passRate, '50.0%')
  assert.equal(s.primaryMetric, 'recall@5')
})

test('summariseRun: improvement up', () => {
  const s = summariseRun(makeRun(0.8, 0.1, { 'recall@5': 0.8 }))
  assert.equal(s.regression, 'up')
})

test('summariseRun: flat', () => {
  const s = summariseRun(makeRun(0.7, 0.001, { 'recall@5': 0.7 }))
  assert.equal(s.regression, 'flat')
})

// ── compareRuns ────────────────────────────────────────────────────────

test('compareRuns: returns sorted deltas per metric', () => {
  const newer = makeRun(0.7, 0.1, { 'recall@5': 0.8, mrr: 0.4 })
  const older = makeRun(0.6, 0, { 'recall@5': 0.6, mrr: 0.5 })
  const cmp = compareRuns(newer, older)
  assert.equal(cmp.length, 2)
  assert.equal(cmp[0].metric, 'mrr')
  assert.equal(Math.round(cmp[0].delta * 100) / 100, -0.1)
  assert.equal(cmp[1].metric, 'recall@5')
  assert.equal(Math.round(cmp[1].delta * 100) / 100, 0.2)
})

// ── sortQueriesByCount ─────────────────────────────────────────────────

test('sortQueriesByCount: by count desc, then alpha', () => {
  const out = sortQueriesByCount([
    { query: 'beta', count: 2, avg_hits: 0, avg_latency_ms: 0 },
    { query: 'alpha', count: 5, avg_hits: 0, avg_latency_ms: 0 },
    { query: 'zeta', count: 2, avg_hits: 0, avg_latency_ms: 0 },
  ])
  assert.equal(out[0].query, 'alpha')
  assert.equal(out[1].query, 'beta')
  assert.equal(out[2].query, 'zeta')
})

// ── computeFeedbackRatio ───────────────────────────────────────────────

test('computeFeedbackRatio: standard', () => {
  assert.equal(computeFeedbackRatio(3, 1), 0.75)
})

test('computeFeedbackRatio: zero', () => {
  assert.equal(computeFeedbackRatio(0, 0), 0)
})

// ── summariseAnalytics ─────────────────────────────────────────────────

test('summariseAnalytics: aggregates', () => {
  const o: AnalyticsOverview = {
    top_queries: [],
    zero_result_queries: [{ query: 'x', count: 3, avg_hits: 0, avg_latency_ms: 0 }],
    citation_hit_rate: [{ document_id: 'd1', citations: 4, queries: 10, rate: 0.4 }],
    feedback: { up: 3, down: 1, ratio: 0.75 },
    cost: { granularity: 'day', points: [], total_cents: 100 },
    total_queries: 10,
    total_cost_cents: 100,
  }
  const s = summariseAnalytics(o)
  assert.equal(s.totalQueries, 10)
  assert.equal(s.totalCost, '$1.00')
  assert.equal(s.zeroRate, '30.0%')
  assert.equal(s.hitRate, '40.0%')
  assert.equal(s.thumbsUp, '75.0%')
})

// ── connector presets ──────────────────────────────────────────────────

test('CONNECTOR_PRESETS: at least 14 entries (project minimum)', () => {
  assert.ok(CONNECTOR_PRESETS.length >= 14, `got ${CONNECTOR_PRESETS.length}`)
})

test('filterPresets: empty query → all', () => {
  assert.equal(filterPresets('').length, CONNECTOR_PRESETS.length)
})

test('filterPresets: matches label/kind/blurb', () => {
  const out = filterPresets('slack')
  assert.ok(out.some((p) => p.kind === 'slack'))
})

test('presetsByCategory: groups & sorts', () => {
  const g = presetsByCategory()
  assert.ok(g.storage.length >= 3)
  // sorted alphabetically by label
  const labels = g.storage.map((p) => p.label)
  const sorted = [...labels].sort()
  assert.deepEqual(labels, sorted)
})

// ── search provider validators ─────────────────────────────────────────

test('validateSearchProviderConfig: tavily needs api_key', () => {
  assert.equal(validateSearchProviderConfig('tavily', {}), 'api_key required')
})

test('validateSearchProviderConfig: google_cse needs cx', () => {
  assert.equal(
    validateSearchProviderConfig('google_cse', { api_key: 'k' }),
    'cx (custom-search engine id) required',
  )
})

test('validateSearchProviderConfig: internal ok', () => {
  assert.equal(validateSearchProviderConfig('internal', {}), null)
})

test('validateSearchProviderConfig: ok with key', () => {
  assert.equal(validateSearchProviderConfig('tavily', { api_key: 'k' }), null)
})
