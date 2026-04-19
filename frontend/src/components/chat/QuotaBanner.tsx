import * as React from 'react'
import { authorizedFetch } from '~/lib/authorizedFetch'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

interface MyUsage {
  period: string
  cost_usd: string
  input_tokens: number
  output_tokens: number
  quotas: Array<{
    period: string
    max_cost_usd: number | null
    max_output_tokens: number | null
    action_on_breach: string
    cost_used: number
    tokens_used: number
  }>
}

export function QuotaBanner() {
  const [usage, setUsage] = React.useState<MyUsage | null>(null)
  const [dismissed, setDismissed] = React.useState(false)

  React.useEffect(() => {
    authorizedFetch(`${API_BASE}/api/admin/usage/my`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setUsage(d))
      .catch(() => null)
  }, [])

  if (dismissed || !usage) return null

  const warnings: string[] = []
  for (const q of usage.quotas ?? []) {
    if (q.max_cost_usd != null) {
      const pct = q.cost_used / q.max_cost_usd
      if (pct >= 0.8) {
        warnings.push(
          `${Math.round(pct * 100)}% of $${q.max_cost_usd.toFixed(2)} ${q.period} budget used`,
        )
      }
    }
    if (q.max_output_tokens != null) {
      const pct = q.tokens_used / q.max_output_tokens
      if (pct >= 0.8) {
        warnings.push(
          `${Math.round(pct * 100)}% of ${q.max_output_tokens.toLocaleString()} ${q.period} token quota used`,
        )
      }
    }
  }

  if (warnings.length === 0) return null

  return (
    <div className="mx-4 mb-2 flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm dark:border-amber-700 dark:bg-amber-950/40">
      <div className="flex items-center gap-2">
        <span className="text-amber-600 dark:text-amber-400">⚠</span>
        <span className="text-amber-700 dark:text-amber-300">{warnings.join(' · ')}</span>
      </div>
      <button
        onClick={() => setDismissed(true)}
        className="text-amber-400 hover:text-amber-600 dark:text-amber-500 dark:hover:text-amber-300"
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  )
}
