import { Brain, Check, ChevronDown, ChevronRight, Globe, Library, Link, Wrench } from 'lucide-react'
import * as React from 'react'
import { PrismLogo } from '~/components/brand'
import type { StreamThreadItem } from '~/lib/chat-types'

interface Props {
  item: StreamThreadItem
}

type Kind = StreamThreadItem['kind']

type Accent = {
  token: string
  chipStyle: React.CSSProperties
  dotColor: string
}

function getAccent(kind: Kind): Accent {
  switch (kind) {
    case 'memory':
      return {
        token: 'var(--acc-violet)',
        chipStyle: {
          color: 'var(--acc-violet)',
          background: 'color-mix(in oklch, var(--acc-violet) 8%, var(--panel))',
          borderColor: 'color-mix(in oklch, var(--acc-violet) 30%, var(--line))',
        },
        dotColor: 'var(--acc-violet)',
      }
    case 'kb_search':
      return {
        token: 'var(--acc-violet)',
        chipStyle: {
          color: 'var(--acc-violet)',
          background: 'color-mix(in oklch, var(--acc-violet) 7%, var(--panel))',
          borderColor: 'color-mix(in oklch, var(--acc-violet) 25%, var(--line))',
        },
        dotColor: 'var(--acc-violet)',
      }
    case 'web_search':
    case 'fetch_webpage':
      return {
        token: 'var(--accent)',
        chipStyle: {
          color: 'var(--ink-2)',
          background: 'var(--bg-2)',
          borderColor: 'var(--line)',
        },
        dotColor: 'var(--accent)',
      }
    default:
      return {
        token: 'var(--ink-2)',
        chipStyle: {
          color: 'var(--ink-2)',
          background: 'var(--bg-2)',
          borderColor: 'var(--line)',
        },
        dotColor: 'var(--ink-3)',
      }
  }
}

function getIcon(kind: Kind) {
  switch (kind) {
    case 'memory': return <Brain className="size-3 shrink-0" strokeWidth={2} />
    case 'web_search': return <Globe className="size-3 shrink-0" strokeWidth={2} />
    case 'fetch_webpage': return <Link className="size-3 shrink-0" strokeWidth={2} />
    case 'kb_search': return <Library className="size-3 shrink-0" strokeWidth={2} />
    default: return <Wrench className="size-3 shrink-0" strokeWidth={2} />
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
    case 'web_search': return <>Web searched <em className="not-italic opacity-70">&ldquo;{item.query}&rdquo;</em></>
    case 'fetch_webpage': return <>Fetched <em className="not-italic opacity-70">{item.url}</em></>
    case 'kb_search': return <>KB searched <em className="not-italic opacity-70">&ldquo;{item.query}&rdquo;</em></>
    case 'tool_call': return <>{item.tool}</>
  }
}

function formatProviderName(provider: string): string {
  const map: Record<string, string> = {
    TavilyProvider: 'Tavily',
    SerperProvider: 'Serper',
    ExaProvider: 'Exa',
    DuckDuckGoProvider: 'DuckDuckGo',
    FirecrawlFetchProvider: 'Firecrawl',
    Crawl4AiFetchProvider: 'Crawl4AI',
    JinaFetchProvider: 'Jina',
    RequestsFetchProvider: 'Requests',
  }
  return map[provider] ?? provider
}

function ProviderBadge({ provider }: { provider: string }) {
  return (
    <span className="cap-tag" style={{ fontSize: 10 }}>
      {formatProviderName(provider)}
    </span>
  )
}

function ParamRow({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="tool-params">
      <span className="param-k">{k}</span>
      <span className="param-v">{v}</span>
    </div>
  )
}

function ExpandedDetails({ item }: { item: StreamThreadItem }) {
  switch (item.kind) {
    case 'web_search':
      return (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            <ParamRow k="query" v={item.query} />
            {item.provider && <ProviderBadge provider={item.provider} />}
          </div>
          {item.result_snippet && (
            <>
              <div className="tool-params"><span className="param-k">results</span></div>
              <div className="text-[11px] leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--ink-2)' }}>
                {item.result_snippet}
              </div>
            </>
          )}
        </div>
      )
    case 'fetch_webpage':
      return (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            <ParamRow k="url" v={<span className="break-all">{item.url}</span>} />
            {item.provider && <ProviderBadge provider={item.provider} />}
          </div>
          {item.result_snippet && (
            <>
              <div className="tool-params"><span className="param-k">content</span></div>
              <div className="text-[11px] leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--ink-2)' }}>
                {item.result_snippet}
              </div>
            </>
          )}
        </div>
      )
    case 'kb_search':
      return (
        <div className="flex flex-col gap-2">
          <ParamRow k="query" v={item.query} />
          {item.sources && item.sources.length > 0 && (
            <div className="flex flex-col gap-0.5">
              <div className="tool-params"><span className="param-k">sources</span></div>
              {item.sources.map((s, i) => (
                <div key={i} className="text-[11px]" style={{ color: 'var(--ink-2)' }}>
                  {s.kb_name}
                  {s.chunks_used > 0 && (
                    <span className="mono ml-1" style={{ color: 'var(--ink-3)', fontSize: 10 }}>
                      · {s.chunks_used} chunks
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )
    case 'tool_call':
      return (
        <div className="flex flex-col gap-1">
          <ParamRow k="tool" v={item.tool} />
        </div>
      )
    default:
      return null
  }
}

export function ThreadItemChip({ item }: Props) {
  const [expanded, setExpanded] = React.useState(false)
  const accent = getAccent(item.kind)
  const isRunning = item.status === 'running'
  const isMemory = item.kind === 'memory'

  if (isRunning) {
    return (
      <div data-testid="thread-item-chip" data-kind={item.kind} data-status="running">
        <span className="cap-tag" style={accent.chipStyle}>
          {getIcon(item.kind)}
          <span>{getRunningLabel(item)}</span>
          <PrismLogo state="loading" size={10} />
        </span>
      </div>
    )
  }

  if (isMemory) {
    return (
      <div data-testid="thread-item-chip" data-kind="memory" data-status="done">
        <span className="cap-tag" style={accent.chipStyle}>
          {getIcon(item.kind)}
          <span>{getDoneLabel(item)}</span>
          <Check className="size-3 shrink-0" strokeWidth={2.5} style={{ color: accent.dotColor }} />
        </span>
      </div>
    )
  }

  return (
    <div data-testid="thread-item-chip" data-kind={item.kind} data-status="done">
      <button
        type="button"
        data-testid="thread-item-chip-toggle"
        onClick={() => setExpanded((e) => !e)}
        className="cap-tag cursor-pointer transition-opacity hover:opacity-90"
        style={accent.chipStyle}
      >
        {getIcon(item.kind)}
        <span>{getDoneLabel(item)}</span>
        <Check className="size-3 shrink-0" strokeWidth={2.5} style={{ color: 'var(--ok)' }} />
        {expanded
          ? <ChevronDown className="size-3" strokeWidth={2} />
          : <ChevronRight className="size-3" strokeWidth={2} />}
      </button>
      {expanded && (
        <div
          data-testid="thread-item-details"
          className="mt-1.5 rounded-[4px] px-3 py-2 max-w-md"
          style={{
            background: 'var(--bg-2)',
            border: '1px solid var(--line)',
          }}
        >
          <ExpandedDetails item={item} />
        </div>
      )}
    </div>
  )
}
