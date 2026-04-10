import { Brain, Check, ChevronDown, ChevronRight, Globe, Library, Link, Loader2, Wrench } from 'lucide-react'
import * as React from 'react'
import type { StreamThreadItem } from '~/lib/chat-types'

interface Props {
  item: StreamThreadItem
}

type Theme = {
  border: string
  bg: string
  text: string
  iconColor: string
  chevronColor: string
}

function getTheme(kind: StreamThreadItem['kind']): Theme {
  switch (kind) {
    case 'memory':
      return {
        border: 'border-blue-900/60 dark:border-blue-900/40',
        bg: 'bg-blue-950/40 dark:bg-blue-950/30',
        text: 'text-blue-300 dark:text-blue-300',
        iconColor: 'text-blue-400',
        chevronColor: 'text-blue-800',
      }
    case 'web_search':
    case 'fetch_webpage':
      return {
        border: 'border-neutral-700/60',
        bg: 'bg-neutral-900/50',
        text: 'text-neutral-300',
        iconColor: 'text-neutral-400',
        chevronColor: 'text-neutral-600',
      }
    case 'kb_search':
      return {
        border: 'border-purple-900/60',
        bg: 'bg-purple-950/30',
        text: 'text-purple-300',
        iconColor: 'text-purple-400',
        chevronColor: 'text-purple-800',
      }
    default:
      return {
        border: 'border-neutral-700/60',
        bg: 'bg-neutral-900/50',
        text: 'text-neutral-400',
        iconColor: 'text-neutral-500',
        chevronColor: 'text-neutral-600',
      }
  }
}

function getIcon(kind: StreamThreadItem['kind']) {
  switch (kind) {
    case 'memory': return <Brain className="size-3.5 shrink-0" strokeWidth={2} />
    case 'web_search': return <Globe className="size-3.5 shrink-0" strokeWidth={2} />
    case 'fetch_webpage': return <Link className="size-3.5 shrink-0" strokeWidth={2} />
    case 'kb_search': return <Library className="size-3.5 shrink-0" strokeWidth={2} />
    default: return <Wrench className="size-3.5 shrink-0" strokeWidth={2} />
  }
}

function getRunningLabel(item: StreamThreadItem): string {
  switch (item.kind) {
    case 'memory': return 'Loading memories\u2026'
    case 'web_search': return `Searching for \u201c${item.query}\u201d\u2026`
    case 'fetch_webpage': return `Fetching ${item.url}\u2026`
    case 'kb_search': return `Searching knowledge base for \u201c${item.query}\u201d\u2026`
    case 'tool_call': return `Running ${item.tool}\u2026`
  }
}

function getDoneLabel(item: StreamThreadItem): React.ReactNode {
  switch (item.kind) {
    case 'memory': return <>{item.count} {item.count === 1 ? 'memory' : 'memories'} loaded</>
    case 'web_search': return <>Web Searched <em className="not-italic opacity-70">&ldquo;{item.query}&rdquo;</em></>
    case 'fetch_webpage': return <>Fetched <em className="not-italic opacity-70">{item.url}</em></>
    case 'kb_search': return <>KB Searched <em className="not-italic opacity-70">&ldquo;{item.query}&rdquo;</em></>
    case 'tool_call': return <>{item.tool}</>
  }
}

function ExpandedDetails({ item }: { item: StreamThreadItem }) {
  switch (item.kind) {
    case 'web_search':
      return (
        <div className="flex flex-col gap-2 text-[11px]">
          <div>
            <div className="text-neutral-600 dark:text-neutral-500 font-semibold uppercase tracking-wide text-[10px] mb-0.5">Query</div>
            <div className="text-neutral-300">{item.query}</div>
          </div>
          {item.result_snippet && (
            <div>
              <div className="text-neutral-600 dark:text-neutral-500 font-semibold uppercase tracking-wide text-[10px] mb-0.5">Results</div>
              <div className="text-neutral-400 whitespace-pre-wrap leading-relaxed">{item.result_snippet}</div>
            </div>
          )}
        </div>
      )
    case 'fetch_webpage':
      return (
        <div className="flex flex-col gap-2 text-[11px]">
          <div>
            <div className="text-neutral-600 dark:text-neutral-500 font-semibold uppercase tracking-wide text-[10px] mb-0.5">URL</div>
            <div className="text-neutral-300 break-all">{item.url}</div>
          </div>
          {item.result_snippet && (
            <div>
              <div className="text-neutral-600 dark:text-neutral-500 font-semibold uppercase tracking-wide text-[10px] mb-0.5">Content</div>
              <div className="text-neutral-400 whitespace-pre-wrap leading-relaxed">{item.result_snippet}</div>
            </div>
          )}
        </div>
      )
    case 'kb_search':
      return (
        <div className="flex flex-col gap-2 text-[11px]">
          <div>
            <div className="text-purple-700 dark:text-purple-600 font-semibold uppercase tracking-wide text-[10px] mb-0.5">Query</div>
            <div className="text-purple-300">{item.query}</div>
          </div>
          {item.sources && item.sources.length > 0 && (
            <div>
              <div className="text-purple-700 dark:text-purple-600 font-semibold uppercase tracking-wide text-[10px] mb-0.5">Sources</div>
              <div className="flex flex-col gap-0.5">
                {item.sources.map((s, i) => (
                  <div key={i} className="text-purple-300">
                    {s.kb_name}
                    {s.chunks_used > 0 && (
                      <span className="text-purple-600 ml-1">&middot; {s.chunks_used} chunks</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )
    case 'tool_call':
      return (
        <div className="flex flex-col gap-1 text-[11px]">
          <div className="text-neutral-600 font-semibold uppercase tracking-wide text-[10px]">Tool</div>
          <div className="text-neutral-300">{item.tool}</div>
        </div>
      )
    default:
      return null
  }
}

export function ThreadItemChip({ item }: Props) {
  const [expanded, setExpanded] = React.useState(false)
  const theme = getTheme(item.kind)
  const isRunning = item.status === 'running'
  const isMemory = item.kind === 'memory'
  const canExpand = !isMemory && !isRunning

  const chipClass = `inline-flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-[12px] ${theme.border} ${theme.bg} ${theme.text}`

  if (isRunning) {
    return (
      <div data-testid="thread-item-chip" data-kind={item.kind} data-status="running">
        <div className={chipClass}>
          <span className={theme.iconColor}>{getIcon(item.kind)}</span>
          <span>{getRunningLabel(item)}</span>
          <Loader2 className="size-3 animate-spin shrink-0 text-current opacity-60" strokeWidth={2} />
        </div>
      </div>
    )
  }

  if (isMemory) {
    return (
      <div data-testid="thread-item-chip" data-kind="memory" data-status="done">
        <div className={chipClass}>
          <span className={theme.iconColor}>{getIcon(item.kind)}</span>
          <span>{getDoneLabel(item)}</span>
          <Check className="size-3 shrink-0 text-blue-500" strokeWidth={2.5} />
        </div>
      </div>
    )
  }

  // Expandable done chip (web_search, kb_search, tool_call)
  return (
    <div data-testid="thread-item-chip" data-kind={item.kind} data-status="done">
      <button
        data-testid="thread-item-chip-toggle"
        onClick={() => setExpanded(e => !e)}
        className={`${chipClass} cursor-pointer hover:opacity-90 transition-opacity`}
      >
        <span className={theme.iconColor}>{getIcon(item.kind)}</span>
        <span>{getDoneLabel(item)}</span>
        <Check className="size-3 shrink-0 text-green-500" strokeWidth={2.5} />
        <span className={theme.chevronColor}>
          {expanded
            ? <ChevronDown className="size-3" strokeWidth={2} />
            : <ChevronRight className="size-3" strokeWidth={2} />}
        </span>
      </button>
      {expanded && (
        <div
          data-testid="thread-item-details"
          className={`mt-1.5 px-3 py-2 rounded-lg border ${theme.border} ${theme.bg} max-w-sm`}
        >
          <ExpandedDetails item={item} />
        </div>
      )}
    </div>
  )
}
