/**
 * Validate IdP config schema → required-field detection.
 */
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { getIdpFields, validateIdpConfig } from './idp-config.ts'

test('oidc fields include issuer + client_id', () => {
  const keys = getIdpFields('oidc').map((f) => f.key)
  assert.ok(keys.includes('issuer'))
  assert.ok(keys.includes('client_id'))
  assert.ok(keys.includes('client_secret'))
})

test('saml fields include sso_url + x509_cert', () => {
  const keys = getIdpFields('saml').map((f) => f.key)
  assert.ok(keys.includes('sso_url'))
  assert.ok(keys.includes('x509_cert'))
})

test('entra fields include tenant_id', () => {
  const keys = getIdpFields('entra').map((f) => f.key)
  assert.ok(keys.includes('tenant_id'))
})

test('validate: missing required → reported', () => {
  const missing = validateIdpConfig('oidc', {})
  assert.deepEqual(missing.sort(), ['client_id', 'client_secret', 'issuer'])
})

test('validate: all present → empty', () => {
  const missing = validateIdpConfig('oidc', {
    issuer: 'https://x',
    client_id: 'a',
    client_secret: 'b',
  })
  assert.deepEqual(missing, [])
})

test('validate: whitespace-only treated as missing', () => {
  const missing = validateIdpConfig('oidc', {
    issuer: '  ',
    client_id: 'a',
    client_secret: 'b',
  })
  assert.deepEqual(missing, ['issuer'])
})

test('validate: optional field absent → ok', () => {
  const missing = validateIdpConfig('google', {
    client_id: 'a',
    client_secret: 'b',
  })
  assert.deepEqual(missing, [])
})
