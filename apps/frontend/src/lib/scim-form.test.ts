import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import {
  SCIM_PRESETS,
  SCIM_ROLE_OPTIONS,
  scimBaseUrl,
  validateEndpointName,
  validateGroupDisplayName,
} from './scim-form.ts'

test('SCIM_PRESETS: contains generic, okta, entra', () => {
  const keys = SCIM_PRESETS.map((p) => p.value)
  assert.deepEqual(keys, ['generic', 'okta', 'entra'])
})

test('SCIM_ROLE_OPTIONS: 5 stable roles', () => {
  assert.deepEqual([...SCIM_ROLE_OPTIONS], ['owner', 'admin', 'member', 'viewer', 'service'])
})

test('validateEndpointName: empty → error', () => {
  assert.equal(validateEndpointName(''), 'Name required')
})

test('validateEndpointName: long → error', () => {
  assert.equal(validateEndpointName('x'.repeat(129)), 'Name too long (max 128)')
})

test('validateEndpointName: ok → null', () => {
  assert.equal(validateEndpointName('Production'), null)
})

test('validateGroupDisplayName: empty → error', () => {
  assert.equal(validateGroupDisplayName('   '), 'Display name required')
})

test('validateGroupDisplayName: 255+ → error', () => {
  assert.equal(validateGroupDisplayName('a'.repeat(256)), 'Display name too long (max 255)')
})

test('scimBaseUrl: trims trailing slash + appends /scim/v2', () => {
  assert.equal(scimBaseUrl('https://api.example.com/', 'abc'), 'https://api.example.com/scim/v2')
  assert.equal(scimBaseUrl('https://api.example.com', 'abc'), 'https://api.example.com/scim/v2')
})
