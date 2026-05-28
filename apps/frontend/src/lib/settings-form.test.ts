import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import {
  AUTH_FIELDS,
  castValue,
  diffSettings,
  GENERAL_FIELDS,
  KNOWN_MODULES,
  SETTINGS_TABS,
  validateNumberField,
} from './settings-form.ts'

test('SETTINGS_TABS: 5 tabs incl. auth + modules', () => {
  const values = SETTINGS_TABS.map((t) => t.value)
  assert.deepEqual(values, ['general', 'modules', 'notifications', 'retention', 'auth'])
})

test('KNOWN_MODULES contains gateway + rag', () => {
  assert.ok(KNOWN_MODULES.includes('gateway'))
  assert.ok(KNOWN_MODULES.includes('rag'))
})

test('AUTH_FIELDS: sso_required key present', () => {
  assert.ok(AUTH_FIELDS.find((f) => f.key === 'auth.sso_required'))
})

test('GENERAL_FIELDS: support_email is string', () => {
  const f = GENERAL_FIELDS.find((x) => x.key === 'support_email')!
  assert.equal(f.type, 'string')
})

test('diffSettings: identical → empty', () => {
  const d = diffSettings({ a: 1, b: 'x' }, { a: 1, b: 'x' })
  assert.deepEqual(d, {})
})

test('diffSettings: changed values only', () => {
  const d = diffSettings({ a: 1, b: 'x' }, { a: 2, b: 'x', c: true })
  assert.deepEqual(d, { a: 2, c: true })
})

test('diffSettings: null vs undefined considered equal', () => {
  const d = diffSettings({ a: null }, { a: null })
  assert.deepEqual(d, {})
})

test('castValue: boolean field coerces string → bool', () => {
  const f = { key: 'x', label: 'X', type: 'boolean' as const }
  assert.equal(castValue(f, true), true)
  assert.equal(castValue(f, false), false)
})

test('castValue: number field with bad input → null', () => {
  const f = { key: 'x', label: 'X', type: 'number' as const }
  assert.equal(castValue(f, 'nan'), null)
  assert.equal(castValue(f, '12'), 12)
})

test('validateNumberField: empty allowed', () => {
  assert.equal(validateNumberField(''), null)
})

test('validateNumberField: negative rejected', () => {
  assert.equal(validateNumberField('-1'), 'Must be >= 0')
})

test('validateNumberField: NaN rejected', () => {
  assert.equal(validateNumberField('abc'), 'Must be a number')
})

test('validateNumberField: positive ok', () => {
  assert.equal(validateNumberField('42'), null)
})
