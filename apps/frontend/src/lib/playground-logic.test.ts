// apps/frontend/src/lib/playground-logic.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { clampModelPicks, summarize, wordDiff } from './playground-logic'

test('wordDiff identifies adds and removes', () => {
  const d = wordDiff('the quick brown fox', 'the slow brown fox')
  // Reconstruct each side and confirm.
  const a = d.filter((t) => t.op !== 'add').map((t) => t.text).join('')
  const b = d.filter((t) => t.op !== 'remove').map((t) => t.text).join('')
  assert.equal(a, 'the quick brown fox')
  assert.equal(b, 'the slow brown fox')
  assert.ok(d.some((t) => t.op === 'remove' && t.text.includes('quick')))
  assert.ok(d.some((t) => t.op === 'add' && t.text.includes('slow')))
})

test('wordDiff identical inputs yield only "same" tokens', () => {
  const d = wordDiff('hello world', 'hello world')
  assert.ok(d.every((t) => t.op === 'same'))
})

test('wordDiff empty side', () => {
  const d = wordDiff('', 'hello')
  assert.ok(d.every((t) => t.op === 'add'))
  const d2 = wordDiff('hello', '')
  assert.ok(d2.every((t) => t.op === 'remove'))
})

test('summarize formats run result', () => {
  assert.equal(
    summarize({
      model: 'm',
      output: 'x',
      latency_ms: 1234,
      cost_cents: 5,
      tokens_in: 100,
      tokens_out: 50,
    }),
    '100/50 tok · 1234ms · $0.0500',
  )
})

test('clampModelPicks dedupes + caps at 4', () => {
  assert.deepEqual(clampModelPicks(['a', 'b', 'a', 'c', 'd', 'e']), ['a', 'b', 'c', 'd'])
  assert.deepEqual(clampModelPicks(['', 'x']), ['x'])
})
