import {
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  Globe,
  Library,
  Loader2,
  Table2,
  Wrench,
} from 'lucide-react'
import { StreamItem, ThinkingChildItem, ThinkingItem } from '~/lib/chat-types'

interface Props {
  items: StreamItem[]
  expanded: boolean
  onToggle: () => void
}

function getToolIcon(tool: string, isMemory: boolean) {
  if (isMemory) return <Brain className="size-3.5 shrink-0" strokeWidth={2} />
  switch (tool) {
    case 'web_search':
      return <Globe className="size-3.5 shrink-0" strokeWidth={2} />
    case 'search_knowledge_base':
      return <Library className="size-3.5 shrink-0" strokeWidth={2} />
    case 'query_structured_data':
      return <Table2 className="size-3.5 shrink-0" strokeWidth={2} />
    default:
      return <Wrench className="size-3.5 shrink-0" strokeWidth={2} />
  }
}

function getToolLabel(tool: string, isMemory: boolean): string {
  if (isMemory) return 'Memory'
  switch (tool) {
    case 'web_search':
      return 'Web Search'
    case 'search_knowledge_base':
      return 'Knowledge Base'
    case 'query_structured_data':
      return 'Data Analysis'
    default:
      return tool
  }
}

function getToolParam(child: ThinkingChildItem): string {
  if (child.kind === 'memory') {
    return child.count === 1 ? '1 memory loaded' : `${child.count} memories loaded`
  }
  return child.params.query ?? child.params.question ?? Object.values(child.params)[0] ?? ''
}

function ToolCard({ child }: { child: ThinkingChildItem }) {
  const isMemory = child.kind === 'memory'
  const tool = isMemory ? 'memory' : child.tool
  const isRunning = child.status === 'running'
  const icon = getToolIcon(tool, isMemory)
  const label = getToolLabel(tool, isMemory)
  const param = getToolParam(child)

  const cardClass = isRunning
    ? 'bg-blue-500/5 dark:bg-blue-500/[0.07] border border-blue-500/20'
    : 'bg-neutral-100/50 dark:bg-white/[0.03] border border-neutral-200/50 dark:border-white/[0.06]'

  const iconColor = isRunning
    ? 'text-blue-500 dark:text-blue-400'
    : 'text-neutral-400 dark:text-neutral-500'

  return (
    <div
      data-testid="chat-tool-card"
      className={`flex items-center gap-2 rounded-lg px-2.5 py-2 ${cardClass}`}
    >
      <span className={iconColor}>{icon}</span>
      <span
        data-testid="chat-tool-card-name"
        className="text-[11px] font-medium text-neutral-700 dark:text-neutral-300"
      >
        {label}
      </span>
      {param && (
        <span className="text-[11px] text-neutral-400 dark:text-neutral-500 truncate flex-1">
          {param}
        </span>
      )}
      <span
        data-testid="chat-tool-card-status"
        className={`flex items-center gap-1 shrink-0 text-[11px] ${
          isRunning ? 'text-blue-500 dark:text-blue-400' : 'text-green-500'
        }`}
      >
        {isRunning ? (
          <Loader2 className="size-3 animate-spin" strokeWidth={2} />
        ) : (
          <Check className="size-3" strokeWidth={2.5} />
        )}
        {isRunning ? 'running' : 'done'}
      </span>
    </div>
  )
}

export function StreamingThinkingBlock({ items, expanded, onToggle }: Props) {
  const thinking = items.find((i): i is ThinkingItem => i.kind === 'thinking')
  if (!thinking) return null

  const children = thinking.children

  if (thinking.status === 'running') {
    return (
      <div
        data-testid="chat-thinking-block"
        className="border border-neutral-200/60 dark:border-neutral-700/50 rounded-xl overflow-hidden mb-2"
      >
        <div className="flex items-center gap-1.5 px-3 py-2 text-[11px] font-medium text-neutral-500 dark:text-neutral-400">
          <span className="size-1.5 rounded-full bg-blue-500 dark:bg-blue-400 animate-pulse" />
          <span className="flex-1">Thinking…</span>
          <button
            onClick={onToggle}
            className="text-neutral-400 dark:text-neutral-500"
            aria-label={expanded ? 'Collapse thinking' : 'Expand thinking'}
          >
            {expanded ? (
              <ChevronDown className="size-3" strokeWidth={2} />
            ) : (
              <ChevronRight className="size-3" strokeWidth={2} />
            )}
          </button>
        </div>
        {expanded && children.length > 0 && (
          <div className="px-3 pb-3 flex flex-col gap-1.5">
            {children.map((child, i) => (
              <ToolCard key={i} child={child} />
            ))}
          </div>
        )}
      </div>
    )
  }

  // done state
  return (
    <div data-testid="chat-thinking-block">
      <button
        data-testid="chat-thinking-pill"
        onClick={onToggle}
        className="mb-2 inline-flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400 rounded-full border border-neutral-200 dark:border-neutral-700/60 px-2.5 py-1 cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-800/50 transition-colors"
      >
        {expanded ? (
          <ChevronDown className="size-3 text-neutral-400 dark:text-neutral-500" strokeWidth={2} />
        ) : (
          <ChevronRight className="size-3 text-neutral-400 dark:text-neutral-500" strokeWidth={2} />
        )}
        Thinking
      </button>
      {expanded && children.length > 0 && (
        <div className="border-l border-neutral-200/60 dark:border-neutral-700/50 ml-1.5 pl-3 flex flex-col gap-1.5 mt-1.5">
          {children.map((child, i) => (
            <ToolCard key={i} child={child} />
          ))}
        </div>
      )}
    </div>
  )
}
