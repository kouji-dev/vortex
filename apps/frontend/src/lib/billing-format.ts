/**
 * Pure formatting helpers for the Billing page.
 */
import type { Invoice, Subscription } from './admin-types'

export interface PlanOption {
  code: string
  label: string
  kind: 'usage' | 'seat' | 'hybrid'
  blurb: string
}

/** Static catalog mirroring server-side _BUILTIN_PLANS. Keep in sync. */
export const PLAN_OPTIONS: PlanOption[] = [
  { code: 'free', label: 'Free', kind: 'usage', blurb: 'Pay-as-you-go, no seats' },
  { code: 'pro-seat', label: 'Pro Seat', kind: 'seat', blurb: '$20/seat/month' },
  { code: 'team-hybrid', label: 'Team Hybrid', kind: 'hybrid', blurb: '$15/seat + usage' },
  { code: 'enterprise-usage', label: 'Enterprise Usage', kind: 'usage', blurb: 'Custom usage pricing' },
]

/** Format integer cents as currency string. */
export function formatCents(cents: number, currency = 'USD'): string {
  const dollars = cents / 100
  return dollars.toLocaleString(undefined, { style: 'currency', currency, currencyDisplay: 'symbol' })
}

/**
 * Human label for a subscription status. Maps stripe-ish strings to short
 * labels used in the UI badge.
 */
export function subscriptionStatusLabel(s: Subscription): string {
  if (s.canceled_at) return 'canceled'
  switch (s.status) {
    case 'active':
    case 'trialing':
      return s.status
    case 'past_due':
      return 'past due'
    case 'unpaid':
      return 'unpaid'
    case 'incomplete':
    case 'incomplete_expired':
      return 'incomplete'
    default:
      return s.status
  }
}

/** Group invoices by year, newest first. */
export function groupInvoicesByYear(invoices: Invoice[]): { year: number; items: Invoice[] }[] {
  const map = new Map<number, Invoice[]>()
  for (const inv of invoices) {
    const ts = inv.issued_at ?? inv.due_at
    const year = ts ? new Date(ts).getUTCFullYear() : 0
    const bucket = map.get(year) ?? []
    bucket.push(inv)
    map.set(year, bucket)
  }
  const out = Array.from(map.entries())
    .map(([year, items]) => ({ year, items }))
    .sort((a, b) => b.year - a.year)
  for (const g of out) {
    g.items.sort((a, b) => {
      const at = new Date(a.issued_at ?? a.due_at ?? 0).getTime()
      const bt = new Date(b.issued_at ?? b.due_at ?? 0).getTime()
      return bt - at
    })
  }
  return out
}
