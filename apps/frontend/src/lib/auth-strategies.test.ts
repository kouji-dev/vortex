/**
 * Run: `node --test --experimental-strip-types src/lib/auth-strategies.test.ts`
 * Pure logic, no React deps, no DOM.
 */
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import type { AuthConfig } from './admin-types.ts'
import {
  DEFAULT_AUTH_CONFIG,
  hasAnyStrategy,
  showDirectoryLogin,
  showEnterpriseSso,
  showPasswordForm,
  socialButtons,
  socialLabel,
} from './auth-strategies.ts'

const FULL: AuthConfig = {
  password: true,
  social: ['google', 'github'],
  directory: true,
  enterprise: true,
}

test('defaults keep password + enterprise on, social/directory off', () => {
  assert.equal(DEFAULT_AUTH_CONFIG.password, true)
  assert.equal(DEFAULT_AUTH_CONFIG.enterprise, true)
  assert.deepEqual(DEFAULT_AUTH_CONFIG.social, [])
  assert.equal(DEFAULT_AUTH_CONFIG.directory, false)
})

test('undefined config falls back to defaults (never locks the user out)', () => {
  assert.equal(showPasswordForm(undefined), true)
  assert.equal(showEnterpriseSso(undefined), true)
  assert.equal(showDirectoryLogin(undefined), false)
  assert.deepEqual(socialButtons(undefined), [])
  assert.equal(hasAnyStrategy(undefined), true)
})

test('renders only configured social providers, in order', () => {
  const btns = socialButtons(FULL, 'http://api')
  assert.deepEqual(btns.map((b) => b.provider), ['google', 'github'])
  assert.equal(btns[0].startUrl, 'http://api/api/v1/auth/social/google/start')
  assert.equal(btns[0].label, 'Google')
})

test('password can be disabled', () => {
  const cfg: AuthConfig = { ...FULL, password: false }
  assert.equal(showPasswordForm(cfg), false)
  assert.equal(hasAnyStrategy(cfg), true)
})

test('directory + enterprise toggles respected', () => {
  assert.equal(showDirectoryLogin(FULL), true)
  const noEnt: AuthConfig = { ...FULL, enterprise: false }
  assert.equal(showEnterpriseSso(noEnt), false)
})

test('empty config (all off) reports no strategies', () => {
  const empty: AuthConfig = { password: false, social: [], directory: false, enterprise: false }
  assert.equal(hasAnyStrategy(empty), false)
})

test('socialLabel falls back to capitalized provider', () => {
  assert.equal(socialLabel('gitlab'), 'GitLab')
  assert.equal(socialLabel('custom'), 'Custom')
})
