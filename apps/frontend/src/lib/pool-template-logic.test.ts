/**
 * Run: `node --test --experimental-strip-types src/lib/pool-template-logic.test.ts`
 * Pure logic, no React deps, no DOM.
 */
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import {
  formatSettings,
  isDirty,
  validateSettingsJson,
} from './pool-template-logic.ts'

test('validateSettingsJson: empty input is an empty object', () => {
  const r = validateSettingsJson('')
  assert.equal(r.ok, true)
  if (r.ok) assert.deepEqual(r.value, {})
})

test('validateSettingsJson: whitespace-only input is empty object', () => {
  const r = validateSettingsJson('   \n  ')
  assert.equal(r.ok, true)
})

test('validateSettingsJson: rejects array', () => {
  const r = validateSettingsJson('[1, 2]')
  assert.equal(r.ok, false)
  if (!r.ok) assert.match(r.error, /must be a JSON object/)
})

test('validateSettingsJson: rejects scalar', () => {
  const r = validateSettingsJson('42')
  assert.equal(r.ok, false)
})

test('validateSettingsJson: rejects null', () => {
  const r = validateSettingsJson('null')
  assert.equal(r.ok, false)
})

test('validateSettingsJson: parses object', () => {
  const r = validateSettingsJson('{"agent_loop": "react", "timeout": 600}')
  assert.equal(r.ok, true)
  if (r.ok) {
    assert.equal(r.value.agent_loop, 'react')
    assert.equal(r.value.timeout, 600)
  }
})

test('validateSettingsJson: surfaces parser error', () => {
  const r = validateSettingsJson('{not json}')
  assert.equal(r.ok, false)
})

test('formatSettings: stable sorted keys', () => {
  const out = formatSettings({ b: 2, a: 1, c: { z: 9, y: 8 } })
  assert.equal(
    out,
    '{\n  "a": 1,\n  "b": 2,\n  "c": {\n    "y": 8,\n    "z": 9\n  }\n}',
  )
})

test('formatSettings: null/undefined => empty object', () => {
  assert.equal(formatSettings(null), '{}')
  assert.equal(formatSettings(undefined), '{}')
})

test('isDirty: same content different key order = clean', () => {
  const server = { a: 1, b: 2 }
  assert.equal(isDirty('{"b": 2, "a": 1}', server), false)
})

test('isDirty: same content different whitespace = clean', () => {
  const server = { a: 1 }
  assert.equal(isDirty('{ "a":  1   }', server), false)
})

test('isDirty: changed value = dirty', () => {
  assert.equal(isDirty('{"a": 2}', { a: 1 }), true)
})

test('isDirty: added key = dirty', () => {
  assert.equal(isDirty('{"a": 1, "b": 2}', { a: 1 }), true)
})

test('isDirty: invalid JSON = dirty (so save stays disabled)', () => {
  assert.equal(isDirty('{not json}', { a: 1 }), true)
})

test('isDirty: empty input vs empty server = clean', () => {
  assert.equal(isDirty('', {}), false)
  assert.equal(isDirty('', null), false)
})

test('isDirty: nested arrays compared positionally', () => {
  assert.equal(
    isDirty('{"repos": ["a","b"]}', { repos: ['a', 'b'] }),
    false,
  )
  assert.equal(
    isDirty('{"repos": ["b","a"]}', { repos: ['a', 'b'] }),
    true,
  )
})
