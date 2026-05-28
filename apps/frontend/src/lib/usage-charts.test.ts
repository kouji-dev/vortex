import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import {
  buildLinePath,
  formatCost,
  formatTokens,
  scaleBars,
  scaleTimeseries,
} from './usage-charts.ts'
import type { UsageBucket, UsageTimeseriesPoint } from './admin-types.ts'

const bucket = (label: string, cost: number): UsageBucket => ({
  dim_value: label,
  dim_label: label,
  tokens_in: 0,
  tokens_out: 0,
  cost_cents: cost,
  count: 0,
})

test('scaleBars: empty input', () => {
  assert.deepEqual(scaleBars([], (b) => b.cost_cents, 100), [])
})

test('scaleBars: largest bar fills width', () => {
  const bars = scaleBars(
    [bucket('a', 10), bucket('b', 5), bucket('c', 20)],
    (b) => b.cost_cents,
    100,
  )
  const max = bars.find((b) => b.label === 'c')!
  assert.equal(max.width, 100)
  assert.equal(max.pct, 1)
})

test('scaleBars: proportional widths', () => {
  const bars = scaleBars(
    [bucket('a', 50), bucket('b', 25)],
    (b) => b.cost_cents,
    200,
  )
  assert.equal(bars[0].width, 200)
  assert.equal(bars[1].width, 100)
})

test('scaleBars: all zeros → all zero width', () => {
  const bars = scaleBars(
    [bucket('a', 0), bucket('b', 0)],
    (b) => b.cost_cents,
    100,
  )
  assert.equal(bars[0].width, 0)
  assert.equal(bars[1].width, 0)
})

const ts = (t: string, v: number): UsageTimeseriesPoint => ({
  ts: t,
  tokens_in: v,
  tokens_out: 0,
  cost_cents: 0,
})

test('scaleTimeseries: empty', () => {
  assert.deepEqual(scaleTimeseries([], (p) => p.tokens_in, 100, 50), [])
})

test('scaleTimeseries: x spans full width', () => {
  const pts = scaleTimeseries(
    [ts('a', 0), ts('b', 1), ts('c', 2)],
    (p) => p.tokens_in,
    100,
    50,
  )
  assert.equal(pts[0].x, 0)
  assert.equal(pts[pts.length - 1].x, 100)
})

test('scaleTimeseries: y inverted (max value → y=0)', () => {
  const pts = scaleTimeseries(
    [ts('a', 0), ts('b', 10)],
    (p) => p.tokens_in,
    100,
    50,
  )
  assert.equal(pts[1].y, 0) // max value on top
  assert.equal(pts[0].y, 50) // zero at bottom
})

test('scaleTimeseries: single point centered', () => {
  const pts = scaleTimeseries([ts('a', 5)], (p) => p.tokens_in, 100, 50)
  assert.equal(pts[0].x, 50)
})

test('buildLinePath: empty', () => {
  assert.equal(buildLinePath([]), '')
})

test('buildLinePath: M then L', () => {
  const path = buildLinePath([
    { x: 0, y: 10, ts: 'a', value: 1 },
    { x: 5, y: 20, ts: 'b', value: 2 },
  ])
  assert.equal(path, 'M 0.00,10.00 L 5.00,20.00')
})

test('formatCost: thousands of dollars', () => {
  assert.equal(formatCost(50000), '$500') // 500 dollars
})

test('formatCost: small values', () => {
  assert.equal(formatCost(150), '$1.50')
  assert.equal(formatCost(5), '$0.0500')
  assert.equal(formatCost(0), '$0.000000')
})

test('formatTokens: k/M suffixes', () => {
  assert.equal(formatTokens(500), '500')
  assert.equal(formatTokens(1500), '1.5k')
  assert.equal(formatTokens(2_500_000), '2.5M')
})
