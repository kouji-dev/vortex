// apps/frontend/src/lib/evals-logic.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  blankRecord,
  detectRegression,
  fmtPassRate,
  summarizeRun,
  validateTestSet,
} from './evals-logic'
import type { EvalRunRowResult } from './gateway-types'

test('summarizeRun computes pass-rate, p95, cost', () => {
  const rows: EvalRunRowResult[] = [
    { record_id: '1', passed: true, output: '', latency_ms: 100, cost_cents: 1 },
    { record_id: '2', passed: true, output: '', latency_ms: 200, cost_cents: 2 },
    { record_id: '3', passed: false, output: '', latency_ms: 300, cost_cents: 3 },
    { record_id: '4', passed: true, output: '', latency_ms: 400, cost_cents: 4 },
  ]
  const s = summarizeRun('claude', rows)
  assert.equal(s.passed, 3)
  assert.equal(s.failed, 1)
  assert.equal(s.pass_rate, 0.75)
  assert.equal(s.total_cost_cents, 10)
  assert.equal(s.p95_latency_ms, 400) // index = floor(4*0.95)=3 -> sorted[3]=400
})

test('summarizeRun handles empty', () => {
  const s = summarizeRun('m', [])
  assert.equal(s.pass_rate, 0)
  assert.equal(s.p95_latency_ms, 0)
})

test('detectRegression triggers at threshold', () => {
  const baseline = summarizeRun('m', [
    { record_id: '1', passed: true, output: '', latency_ms: 1, cost_cents: 0 },
    { record_id: '2', passed: true, output: '', latency_ms: 1, cost_cents: 0 },
  ])
  const current = summarizeRun('m', [
    { record_id: '1', passed: true, output: '', latency_ms: 1, cost_cents: 0 },
    { record_id: '2', passed: false, output: '', latency_ms: 1, cost_cents: 0 },
  ])
  // baseline 100%, current 50% → 50pp drop, far above 5pp default.
  assert.equal(detectRegression(baseline, current), true)
  assert.equal(detectRegression(baseline, baseline), false)
})

test('validateTestSet', () => {
  assert.equal(validateTestSet({ name: '', records: [] }), 'Name is required')
  assert.equal(validateTestSet({ name: 'X', records: [] }), 'At least one record is required')
  assert.equal(
    validateTestSet({ name: 'X', records: [blankRecord('a')] }),
    'Record 1: input is required',
  )
  assert.equal(
    validateTestSet({
      name: 'X',
      records: [{ id: 'a', input: 'hi', expected: 'hi', judge: 'exact' }],
    }),
    null,
  )
})

test('fmtPassRate', () => {
  assert.equal(fmtPassRate(0.85), '85.0%')
  assert.equal(fmtPassRate(0), '0.0%')
  assert.equal(fmtPassRate(1), '100.0%')
})
