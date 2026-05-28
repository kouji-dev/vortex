import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { formatCents, groupInvoicesByYear, PLAN_OPTIONS, subscriptionStatusLabel } from './billing-format.ts'
import type { Invoice, Subscription } from './admin-types.ts'

function sub(o: Partial<Subscription> = {}): Subscription {
  return {
    id: 's1',
    org_id: 'o1',
    provider: 'stripe',
    customer_id: 'cus_x',
    external_id: null,
    plan_kind: 'usage',
    plan_code: 'free',
    status: 'active',
    currency: 'USD',
    seats: 1,
    current_period_start: null,
    current_period_end: null,
    canceled_at: null,
    ...o,
  }
}

function inv(o: Partial<Invoice> = {}): Invoice {
  return {
    id: `i-${Math.random()}`,
    org_id: 'o1',
    subscription_id: null,
    external_id: null,
    amount_cents: 1000,
    currency: 'USD',
    status: 'paid',
    pdf_url: null,
    memo: null,
    issued_at: '2025-03-01T00:00:00Z',
    due_at: null,
    paid_at: null,
    ...o,
  }
}

test('PLAN_OPTIONS includes 4 builtin plans', () => {
  assert.equal(PLAN_OPTIONS.length, 4)
  assert.ok(PLAN_OPTIONS.find((p) => p.code === 'free'))
  assert.ok(PLAN_OPTIONS.find((p) => p.code === 'pro-seat'))
})

test('formatCents: usd default contains 25.00', () => {
  const s = formatCents(2500)
  assert.ok(s.includes('25.00'), `expected to contain 25.00, got ${s}`)
})

test('subscriptionStatusLabel: canceled flag wins', () => {
  assert.equal(subscriptionStatusLabel(sub({ canceled_at: '2025-01-01' })), 'canceled')
})

test('subscriptionStatusLabel: past_due → "past due"', () => {
  assert.equal(subscriptionStatusLabel(sub({ status: 'past_due' })), 'past due')
})

test('subscriptionStatusLabel: trialing passthrough', () => {
  assert.equal(subscriptionStatusLabel(sub({ status: 'trialing' })), 'trialing')
})

test('groupInvoicesByYear: groups + newest first', () => {
  const groups = groupInvoicesByYear([
    inv({ id: 'a', issued_at: '2024-06-01T00:00:00Z' }),
    inv({ id: 'b', issued_at: '2025-02-01T00:00:00Z' }),
    inv({ id: 'c', issued_at: '2025-08-01T00:00:00Z' }),
  ])
  assert.equal(groups.length, 2)
  assert.equal(groups[0].year, 2025)
  assert.equal(groups[1].year, 2024)
  assert.equal(groups[0].items[0].id, 'c') // newest in year first
})

test('groupInvoicesByYear: invoices with no dates land in year=0 bucket', () => {
  const groups = groupInvoicesByYear([inv({ issued_at: null, due_at: null })])
  assert.equal(groups[0].year, 0)
})
