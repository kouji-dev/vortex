/**
 * Pure formatting helpers for the Budgets page. No React; node:test friendly.
 */
import type { BudgetStatus } from './admin-types'

export interface BudgetBar {
  pct: number // 0..1, clamped
  /** color hint: "ok" | "warn" | "block" */
  zone: 'ok' | 'warn' | 'block'
  label: string
}

/**
 * Map a status into a normalized progress bar. Warn at >=80%, block when
 * `blocked` is true or used_pct >= 100.
 */
export function statusToBar(s: BudgetStatus): BudgetBar {
  const raw = Number.isFinite(s.used_pct) ? s.used_pct : 0
  const pct = Math.max(0, Math.min(1, raw / 100))
  const blocked = s.blocked || raw >= 100
  const zone: BudgetBar['zone'] = blocked ? 'block' : raw >= 80 ? 'warn' : 'ok'
  const label = `${formatUsd(s.spent_usd)} / ${formatUsd(s.effective_limit_usd)}`
  return { pct, zone, label }
}

/** Format a decimal-string USD value as "$1,234.56". */
export function formatUsd(s: string | number): string {
  const n = typeof s === 'string' ? Number(s) : s
  if (!Number.isFinite(n)) return '$0.00'
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/** Validate a user-typed limit_usd value. Returns error string or null. */
export function validateLimitUsd(v: string): string | null {
  const trimmed = v.trim()
  if (!trimmed) return 'Limit required'
  const n = Number(trimmed)
  if (!Number.isFinite(n)) return 'Must be a number'
  if (n <= 0) return 'Must be greater than 0'
  return null
}

/** Validate a name (1..128 chars). */
export function validateBudgetName(v: string): string | null {
  const t = v.trim()
  if (t.length < 1) return 'Name required'
  if (t.length > 128) return 'Name too long (max 128)'
  return null
}
