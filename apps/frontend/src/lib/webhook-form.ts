/**
 * Pure helpers for the Webhooks page. Validation + delivery rendering.
 */
import type { WebhookDelivery } from './admin-types'

/** Validate a URL: must parse and be http/https. */
export function validateWebhookUrl(v: string): string | null {
  const t = v.trim()
  if (!t) return 'URL required'
  let url: URL
  try {
    url = new URL(t)
  } catch {
    return 'Invalid URL'
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    return 'URL must use http(s)'
  }
  return null
}

/** Validate selected event types. Must be non-empty. */
export function validateEventTypes(types: string[]): string | null {
  if (!types.length) return 'Select at least one event type'
  return null
}

export type DeliveryZone = 'success' | 'pending' | 'failed'

export function deliveryZone(d: WebhookDelivery): DeliveryZone {
  if (d.delivered_at) return 'success'
  if (d.failed_at) return 'failed'
  if (d.status === 'success') return 'success'
  if (d.status === 'failed') return 'failed'
  return 'pending'
}

export function deliveryColor(z: DeliveryZone): string {
  return z === 'success' ? 'var(--accent)' : z === 'failed' ? 'var(--red)' : 'var(--ink-3)'
}
