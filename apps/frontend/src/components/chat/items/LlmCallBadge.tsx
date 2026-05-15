import type { ThreadItem } from '~/lib/chat-types'

type Props = {
  item: ThreadItem & { kind: 'llm_call' }
  /** Optional prefix (e.g. "iter 1") rendered when a turn has multiple LLM calls. */
  iterationLabel?: string | null
}

export function LlmCallBadge({ item, iterationLabel }: Props) {
  const { input_tokens, output_tokens, cached_input_tokens } = item.data
  const cost = item.cost_usd != null ? parseFloat(item.cost_usd) : null

  if (!input_tokens && !output_tokens) return null

  return (
    <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-gray-400 dark:text-gray-500 select-none">
      {iterationLabel && (
        <span className="mono" style={{ color: 'var(--ink-3)' }}>{iterationLabel}</span>
      )}
      <span title="Input tokens">{(input_tokens ?? 0).toLocaleString()} in</span>
      <span title="Output tokens">{(output_tokens ?? 0).toLocaleString()} out</span>
      {(cached_input_tokens ?? 0) > 0 && (
        <span title="Cached input tokens" className="text-green-500 dark:text-green-600">
          {cached_input_tokens!.toLocaleString()} cached
        </span>
      )}
      {cost != null && cost > 0 && (
        <span title="Estimated cost">
          ${cost.toFixed(6)}
          {item.cost_estimated ? '*' : ''}
        </span>
      )}
    </div>
  )
}
