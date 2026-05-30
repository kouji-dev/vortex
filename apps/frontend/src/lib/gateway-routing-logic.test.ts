import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import {
  parseRules,
  reorder,
  validateAliasName,
  validatePolicyName,
} from './gateway-routing-logic.ts'

test('reorder: move first to last', () => {
  const out = reorder(['a', 'b', 'c'], 0, 2)
  assert.deepEqual(out, ['b', 'c', 'a'])
})

test('reorder: move middle up', () => {
  const out = reorder(['a', 'b', 'c'], 1, 0)
  assert.deepEqual(out, ['b', 'a', 'c'])
})

test('reorder: same index → copy of input', () => {
  const out = reorder(['a', 'b'], 1, 1)
  assert.deepEqual(out, ['a', 'b'])
})

test('reorder: out-of-bounds → safe copy', () => {
  assert.deepEqual(reorder(['a', 'b'], -1, 0), ['a', 'b'])
  assert.deepEqual(reorder(['a', 'b'], 0, 99), ['a', 'b'])
})

test('validatePolicyName: empty', () => {
  assert.equal(validatePolicyName('   '), 'Name required')
})

test('validatePolicyName: too long', () => {
  assert.equal(validatePolicyName('a'.repeat(129)), 'Name too long (max 128)')
})

test('validatePolicyName: bad chars', () => {
  assert.equal(
    validatePolicyName('bad name'),
    'Name may only use letters, digits, _ and -',
  )
})

test('validatePolicyName: ok', () => {
  assert.equal(validatePolicyName('cheapest-coder'), null)
})

test('validateAliasName: ok / bad / empty', () => {
  assert.equal(validateAliasName('smart'), null)
  assert.equal(validateAliasName(''), 'Alias required')
  assert.equal(validateAliasName('with space'), 'Alias may only use letters, digits, _ and -')
})

test('parseRules: static', () => {
  const r = parseRules({ strategy: 'static', rules_json: { target: 'anthropic:claude' } })
  assert.equal(r.kind, 'static')
  assert.equal(r.kind === 'static' && r.rules.target, 'anthropic:claude')
})

test('parseRules: priority drops non-strings', () => {
  const r = parseRules({
    strategy: 'priority',
    rules_json: { candidates: ['a', 1, null, 'b'] },
  })
  assert.equal(r.kind, 'priority')
  assert.deepEqual(r.kind === 'priority' && r.rules.candidates, ['a', 'b'])
})

test('parseRules: weighted defaults', () => {
  const r = parseRules({
    strategy: 'weighted',
    rules_json: { candidates: [{ target: 'a' }, { target: 'b', weight: 3 }, { weight: 99 }] },
  })
  assert.equal(r.kind, 'weighted')
  if (r.kind === 'weighted') {
    assert.equal(r.rules.candidates.length, 2)
    assert.equal(r.rules.candidates[0].weight, 1) // default
    assert.equal(r.rules.candidates[1].weight, 3)
  }
})

test('parseRules: unknown strategy → raw', () => {
  const r = parseRules({ strategy: 'custom_rules', rules_json: { foo: 'bar' } })
  assert.equal(r.kind, 'raw')
})

test('parseRules: missing rules_json → safe defaults', () => {
  const r = parseRules({ strategy: 'priority', rules_json: null as unknown as object })
  assert.equal(r.kind, 'priority')
  if (r.kind === 'priority') assert.deepEqual(r.rules.candidates, [])
})
