import * as React from 'react'

interface UsageInfo {
  input_tokens?: number
  output_tokens?: number
  cached_input_tokens?: number
  cost_usd?: number | string
  model?: string
}

export function MessageUsageBadge({ extra }: { extra: Record<string, unknown> | null }) {
  const usage = extra?.usage as UsageInfo | undefined
  if (!usage || (!usage.input_tokens && !usage.output_tokens)) return null

  const cost = usage.cost_usd != null ? parseFloat(String(usage.cost_usd)) : null
  const cached = usage.cached_input_tokens ?? 0
  const input = usage.input_tokens ?? 0
  const output = usage.output_tokens ?? 0

  return (
    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-gray-400 dark:text-gray-500 select-none">
      <span title="Input tokens">{input.toLocaleString()} in</span>
      <span title="Output tokens">{output.toLocaleString()} out</span>
      {cached > 0 && (
        <span title="Cached input tokens" className="text-green-500 dark:text-green-600">
          {cached.toLocaleString()} cached
        </span>
      )}
      {cost != null && cost > 0 && (
        <span title="Estimated cost">${cost.toFixed(6)}</span>
      )}
    </div>
  )
}
