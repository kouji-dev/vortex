import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { ALL_SCOPES, labelForScope, validateScopes } from './api-key-scopes.ts'

test('all scopes are unique', () => {
  const dedup = new Set(ALL_SCOPES)
  assert.equal(dedup.size, ALL_SCOPES.length)
})

test('all scopes follow module:action shape', () => {
  for (const s of ALL_SCOPES) assert.match(s, /^[a-z]+:[a-z:]+$/)
})

test('labelForScope: known scope', () => {
  assert.equal(labelForScope('gateway:complete'), 'Call LLMs')
})

test('labelForScope: unknown returns key', () => {
  assert.equal(labelForScope('xxx:yyy'), 'xxx:yyy')
})

test('validateScopes: empty rejected', () => {
  assert.equal(validateScopes([]), 'Select at least one scope')
})

test('validateScopes: known scopes pass', () => {
  assert.equal(validateScopes(['gateway:complete', 'kb:read']), null)
})

test('validateScopes: unknown scope rejected', () => {
  const err = validateScopes(['gateway:complete', 'bogus:thing'])
  assert.ok(err && err.includes('bogus:thing'))
})
