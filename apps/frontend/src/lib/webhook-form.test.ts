import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { deliveryColor, deliveryZone, validateEventTypes, validateWebhookUrl } from './webhook-form.ts'
import type { WebhookDelivery } from './admin-types.ts'

function delivery(o: Partial<WebhookDelivery> = {}): WebhookDelivery {
  return {
    id: 'd1',
    webhook_id: 'w1',
    event_id: 'e1',
    event_type: 'budget.exceeded',
    status: 'pending',
    attempts: 0,
    last_response_status: null,
    last_response_body: null,
    last_error: null,
    next_attempt_at: null,
    delivered_at: null,
    failed_at: null,
    created_at: '2025-01-01T00:00:00Z',
    ...o,
  }
}

test('validateWebhookUrl: empty → error', () => {
  assert.equal(validateWebhookUrl(''), 'URL required')
})

test('validateWebhookUrl: malformed → error', () => {
  assert.equal(validateWebhookUrl('not a url'), 'Invalid URL')
})

test('validateWebhookUrl: ftp scheme → rejected', () => {
  assert.equal(validateWebhookUrl('ftp://example.com'), 'URL must use http(s)')
})

test('validateWebhookUrl: https → null', () => {
  assert.equal(validateWebhookUrl('https://hooks.example.com/x'), null)
})

test('validateEventTypes: empty → error', () => {
  assert.equal(validateEventTypes([]), 'Select at least one event type')
})

test('validateEventTypes: at least one → null', () => {
  assert.equal(validateEventTypes(['budget.exceeded']), null)
})

test('deliveryZone: delivered_at → success', () => {
  assert.equal(deliveryZone(delivery({ delivered_at: '2025-01-01T00:00:00Z' })), 'success')
})

test('deliveryZone: failed_at → failed', () => {
  assert.equal(deliveryZone(delivery({ failed_at: '2025-01-01T00:00:00Z' })), 'failed')
})

test('deliveryZone: no terminal → pending', () => {
  assert.equal(deliveryZone(delivery()), 'pending')
})

test('deliveryZone: status=success → success even without delivered_at', () => {
  assert.equal(deliveryZone(delivery({ status: 'success' })), 'success')
})

test('deliveryColor: mapping is stable', () => {
  assert.equal(deliveryColor('success'), 'var(--accent)')
  assert.equal(deliveryColor('failed'), 'var(--red)')
  assert.equal(deliveryColor('pending'), 'var(--ink-3)')
})
