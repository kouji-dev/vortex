/**
 * Run: `node --test --experimental-strip-types src/lib/admin-permissions.test.ts`
 * Pure logic, no React deps, no DOM.
 */
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { isAdminActor } from './admin-permissions.ts'

test('isAdminActor: owner allowed', () => {
  assert.equal(isAdminActor(['owner']), true)
})

test('isAdminActor: admin allowed', () => {
  assert.equal(isAdminActor(['admin']), true)
})

test('isAdminActor: member denied', () => {
  assert.equal(isAdminActor(['member']), false)
})

test('isAdminActor: viewer denied', () => {
  assert.equal(isAdminActor(['viewer']), false)
})

test('isAdminActor: empty denied', () => {
  assert.equal(isAdminActor([]), false)
})

test('isAdminActor: undefined denied', () => {
  assert.equal(isAdminActor(undefined), false)
})

test('isAdminActor: null denied', () => {
  assert.equal(isAdminActor(null), false)
})

test('isAdminActor: mixed admin allowed', () => {
  assert.equal(isAdminActor(['member', 'admin']), true)
})
