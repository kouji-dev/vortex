import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { isRangeValid, normalizeAuditFilter } from './audit-filter.ts'

test('normalizeAuditFilter: empty inputs → only limit', () => {
  const f = normalizeAuditFilter({ action: '', actor: '', resourceType: '', resourceId: '', fromDate: '', toDate: '' })
  assert.deepEqual(f, { limit: 100 })
})

test('normalizeAuditFilter: trims and applies filters', () => {
  const f = normalizeAuditFilter({
    action: ' org:update ', actor: 'u1', resourceType: 'org', resourceId: '42', fromDate: '', toDate: '',
  })
  assert.equal(f.action, 'org:update')
  assert.equal(f.actor, 'u1')
  assert.equal(f.resource_type, 'org')
  assert.equal(f.resource_id, '42')
})

test('normalizeAuditFilter: date range becomes ISO start/end', () => {
  const f = normalizeAuditFilter({
    action: '', actor: '', resourceType: '', resourceId: '', fromDate: '2025-01-01', toDate: '2025-01-02',
  })
  assert.equal(f.from, '2025-01-01T00:00:00.000Z')
  assert.equal(f.to, '2025-01-02T23:59:59.999Z')
})

test('isRangeValid: both empty', () => {
  assert.equal(isRangeValid('', ''), true)
})

test('isRangeValid: same day', () => {
  assert.equal(isRangeValid('2025-01-01', '2025-01-01'), true)
})

test('isRangeValid: from before to', () => {
  assert.equal(isRangeValid('2025-01-01', '2025-01-02'), true)
})

test('isRangeValid: from after to → invalid', () => {
  assert.equal(isRangeValid('2025-01-02', '2025-01-01'), false)
})

test('isRangeValid: one side empty → valid', () => {
  assert.equal(isRangeValid('', '2025-01-01'), true)
  assert.equal(isRangeValid('2025-01-01', ''), true)
})
