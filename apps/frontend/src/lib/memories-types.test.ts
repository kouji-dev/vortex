import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import {
  clampImportance,
  countByType,
  filterMemories,
  isShared,
  normaliseRecallWeights,
  parseRetentionDays,
  quantizeImportance,
  toggleCategory,
  validateRetentionDays,
  type MemoryV1,
} from './memories-types.ts'

function m(over: Partial<MemoryV1> = {}): MemoryV1 {
  return {
    id: '1',
    type: 'fact',
    scope_kind: 'user',
    scope_ids: ['u-1'],
    text: 'user prefers TypeScript',
    importance: 0.5,
    confidence: 0.9,
    tags: [],
    pinned: false,
    created_at: null,
    ...over,
  }
}

test('clampImportance: clamps + handles NaN', () => {
  assert.equal(clampImportance(-1), 0)
  assert.equal(clampImportance(2), 1)
  assert.equal(clampImportance(0.4), 0.4)
  assert.equal(clampImportance(Number.NaN), 0.5)
})

test('quantizeImportance: rounds to step', () => {
  assert.equal(quantizeImportance(0.43), 0.45)
  assert.equal(quantizeImportance(0.41, 0.1), 0.4)
})

test('filterMemories: type filter', () => {
  const list = [m({ id: '1', type: 'fact' }), m({ id: '2', type: 'preference' })]
  const out = filterMemories(list, { type: 'preference' })
  assert.equal(out.length, 1)
  assert.equal(out[0].id, '2')
})

test('filterMemories: scope filter', () => {
  const list = [m({ id: '1', scope_kind: 'user' }), m({ id: '2', scope_kind: 'org' })]
  assert.equal(filterMemories(list, { scope: 'org' }).length, 1)
  assert.equal(filterMemories(list, { scope: 'all' }).length, 2)
})

test('filterMemories: free-text q', () => {
  const list = [m({ text: 'likes Vim' }), m({ text: 'prefers Emacs' })]
  assert.equal(filterMemories(list, { q: 'vim' }).length, 1)
  assert.equal(filterMemories(list, { q: '   ' }).length, 2)
})

test('isShared: team/org/assistant only', () => {
  assert.equal(isShared(m({ scope_kind: 'team' })), true)
  assert.equal(isShared(m({ scope_kind: 'org' })), true)
  assert.equal(isShared(m({ scope_kind: 'assistant' })), true)
  assert.equal(isShared(m({ scope_kind: 'user' })), false)
  assert.equal(isShared(m({ scope_kind: 'conversation' })), false)
})

test('toggleCategory: add then remove', () => {
  const a = toggleCategory<string>([], 'health')
  assert.deepEqual(a, ['health'])
  const b = toggleCategory(a, 'health')
  assert.deepEqual(b, [])
})

test('normaliseRecallWeights: vector = 1 - r - i', () => {
  const w = normaliseRecallWeights({ recency_weight: 0.2, importance_weight: 0.3 })
  assert.equal(Math.round(w.vector * 100) / 100, 0.5)
  assert.equal(w.recency, 0.2)
  assert.equal(w.importance, 0.3)
})

test('normaliseRecallWeights: clamps over-1 sum', () => {
  const w = normaliseRecallWeights({ recency_weight: 0.9, importance_weight: 0.9 })
  // vector clamped to 0 (won't go negative)
  assert.equal(w.vector, 0)
})

test('validateRetentionDays: ok / blank / bad', () => {
  assert.equal(validateRetentionDays(''), null)
  assert.equal(validateRetentionDays('never'), null)
  assert.equal(validateRetentionDays('365'), null)
  assert.equal(typeof validateRetentionDays('abc'), 'string')
  assert.equal(typeof validateRetentionDays('-1'), 'string')
  assert.equal(typeof validateRetentionDays('999999'), 'string')
})

test('parseRetentionDays: blank → null; numeric floored', () => {
  assert.equal(parseRetentionDays(''), null)
  assert.equal(parseRetentionDays('never'), null)
  assert.equal(parseRetentionDays('90.7'), 90)
  assert.equal(parseRetentionDays('-3'), 0)
})

test('countByType: sums per type', () => {
  const c = countByType([
    m({ type: 'fact' }),
    m({ type: 'fact' }),
    m({ type: 'preference' }),
  ])
  assert.equal(c.fact, 2)
  assert.equal(c.preference, 1)
  assert.equal(c.episode, 0)
})
