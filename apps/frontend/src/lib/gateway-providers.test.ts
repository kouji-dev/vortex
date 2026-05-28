import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import {
  healthBadge,
  providerLabel,
  validateCredentialLabel,
  validateCredentialSecret,
} from './gateway-providers.ts'

const NOW = new Date('2026-05-28T12:00:00Z').getTime()

test('healthBadge: never probed → unknown', () => {
  assert.equal(
    healthBadge({ healthy: false, last_health_at: null }, NOW),
    'unknown',
  )
})

test('healthBadge: probed recently + healthy → healthy', () => {
  const ts = new Date(NOW - 60_000).toISOString()
  assert.equal(healthBadge({ healthy: true, last_health_at: ts }, NOW), 'healthy')
})

test('healthBadge: probed recently + unhealthy → unhealthy', () => {
  const ts = new Date(NOW - 60_000).toISOString()
  assert.equal(healthBadge({ healthy: false, last_health_at: ts }, NOW), 'unhealthy')
})

test('healthBadge: probe older than 24h → stale', () => {
  const ts = new Date(NOW - 48 * 3600 * 1000).toISOString()
  assert.equal(healthBadge({ healthy: true, last_health_at: ts }, NOW), 'stale')
})

test('validateCredentialSecret: empty → error', () => {
  assert.equal(validateCredentialSecret(''), 'Secret required')
})

test('validateCredentialSecret: short → error', () => {
  assert.equal(validateCredentialSecret('abc'), 'Secret looks too short')
})

test('validateCredentialSecret: ok → null', () => {
  assert.equal(validateCredentialSecret('sk-abcdef1234'), null)
})

test('validateCredentialLabel: empty → null (optional)', () => {
  assert.equal(validateCredentialLabel(''), null)
})

test('validateCredentialLabel: bad chars → error', () => {
  assert.equal(
    validateCredentialLabel('my label!'),
    'Label may only use letters, digits, _ and -',
  )
})

test('validateCredentialLabel: too long → error', () => {
  assert.equal(
    validateCredentialLabel('a'.repeat(65)),
    'Label too long (max 64)',
  )
})

test('validateCredentialLabel: clean → null', () => {
  assert.equal(validateCredentialLabel('prod-1'), null)
})

test('providerLabel: known → catalog label', () => {
  assert.equal(providerLabel('openai'), 'OpenAI')
})

test('providerLabel: unknown → echo input', () => {
  assert.equal(providerLabel('custom-thing'), 'custom-thing')
})
