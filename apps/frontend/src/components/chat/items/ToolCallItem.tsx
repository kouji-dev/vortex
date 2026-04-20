import type { ThreadItem } from '~/lib/chat-types'

type Props = { item: ThreadItem & { kind: 'tool_call' | 'server_tool_use' } }

export function ToolCallItem({ item }: Props) {
  const toolName = 'tool_name' in item.data ? item.data.tool_name : ''
  const isRunning = item.status === 'streaming'
  const resultSnippet =
    item.kind === 'tool_call' && 'result_snippet' in item.data
      ? (item.data as { result_snippet?: string | null }).result_snippet
      : null
  return (
    <div className="flex items-center gap-1.5 text-xs py-0.5" data-testid="tool-call-item" data-tool-name={toolName}>
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
      {resultSnippet && (
        <span
          className="text-[10px] truncate max-w-[200px]"
          style={{ color: 'var(--ink-3)' }}
        >
          {resultSnippet}
        </span>
      )}
    </div>
  )
}
