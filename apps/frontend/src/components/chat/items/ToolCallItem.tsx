import type { ThreadItem } from '~/lib/chat-types'

type Props = { item: ThreadItem & { kind: 'tool_call' | 'server_tool_use' } }

function _serverToolDetail(data: { input?: Record<string, unknown> }): string | null {
  const input = data.input || {}
  // Prefer multiple queries when the provider exposes them; fall back to single.
  const queries = input.queries
  if (Array.isArray(queries) && queries.length > 0) {
    return queries.map((q) => `"${String(q)}"`).join(', ')
  }
  const q = input.query
  if (typeof q === 'string' && q) return `"${q}"`
  return null
}

function _toolCallDetail(data: {
  params?: Record<string, unknown>
  result_snippet?: string | null
  error?: string | null
}): string | null {
  if (data.error) return `error: ${data.error}`
  if (data.result_snippet) return data.result_snippet
  const q = data.params?.query
  if (typeof q === 'string' && q) return `"${q}"`
  return null
}

export function ToolCallItem({ item }: Props) {
  const toolName = 'tool_name' in item.data ? item.data.tool_name : ''
  const isRunning = item.status === 'streaming'
  const detail =
    item.kind === 'server_tool_use'
      ? _serverToolDetail(item.data as { input?: Record<string, unknown> })
      : _toolCallDetail(
          item.data as {
            params?: Record<string, unknown>
            result_snippet?: string | null
            error?: string | null
          },
        )
  return (
    <div
      className="flex items-center gap-1.5 text-xs py-0.5"
      data-testid="tool-call-item"
      data-tool-name={toolName}
      data-kind={item.kind}
    >
      <span
        className="size-1.5 rounded-full"
        style={{ background: isRunning ? 'var(--brand)' : 'var(--ink-3)' }}
      />
      <span className="mono text-[11px]" style={{ color: 'var(--ink-2)' }}>
        {toolName}
      </span>
      {isRunning && (
        <span className="text-[10px]" style={{ color: 'var(--ink-3)' }}>
          running…
        </span>
      )}
      {detail && (
        <span
          className="text-[10px] truncate max-w-[320px]"
          style={{ color: 'var(--ink-3)' }}
        >
          {detail}
        </span>
      )}
    </div>
  )
}
