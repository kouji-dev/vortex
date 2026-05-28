import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { formatUsd, statusToBar, validateBudgetName, validateLimitUsd } from './budgets-format.ts'
import type { BudgetStatus } from './admin-types.ts'

function status(over: Partial<BudgetStatus> = {}): BudgetStatus {
  return {
    budget_id: 1,
    period_start: '2025-01-01T00:00:00Z',
    period_end: '2025-02-01T00:00:00Z',
    spent_usd: '10.00',
    limit_usd: '100.00',
    effective_limit_usd: '100.00',
    used_pct: 10,
    blocked: false,
    grace_active: false,
    ...over,
  }
}

test('statusToBar: under 80% → ok zone', () => {
  const bar = statusToBar(status({ used_pct: 30 }))
  assert.equal(bar.zone, 'ok')
  assert.equal(bar.pct, 0.3)
})

test('statusToBar: between 80 and 100 → warn', () => {
  const bar = statusToBar(status({ used_pct: 85 }))
  assert.equal(bar.zone, 'warn')
})

test('statusToBar: blocked flag → block zone regardless of pct', () => {
  const bar = statusToBar(status({ used_pct: 50, blocked: true }))
  assert.equal(bar.zone, 'block')
})

test('statusToBar: >=100% → block + pct clamped to 1', () => {
  const bar = statusToBar(status({ used_pct: 150 }))
  assert.equal(bar.zone, 'block')
  assert.equal(bar.pct, 1)
})

test('statusToBar: label uses formatted usd', () => {
  const bar = statusToBar(status({ spent_usd: '12.5', effective_limit_usd: '100' }))
  assert.equal(bar.label, '$12.50 / $100.00')
})

test('formatUsd: handles string + number', () => {
  assert.equal(formatUsd('12'), '$12.00')
  assert.equal(formatUsd(0.5), '$0.50')
  assert.equal(formatUsd('not-a-number'), '$0.00')
})

test('validateLimitUsd: positive numeric string → null', () => {
  assert.equal(validateLimitUsd('10.50'), null)
})

test('validateLimitUsd: empty → error', () => {
  assert.equal(validateLimitUsd(''), 'Limit required')
})

test('validateLimitUsd: zero or negative → error', () => {
  assert.equal(validateLimitUsd('0'), 'Must be greater than 0')
  assert.equal(validateLimitUsd('-5'), 'Must be greater than 0')
})

test('validateBudgetName: empty → error; long → error; ok → null', () => {
  assert.equal(validateBudgetName(''), 'Name required')
  assert.equal(validateBudgetName('a'.repeat(129)), 'Name too long (max 128)')
  assert.equal(validateBudgetName('Sales team'), null)
})
