import {
  Brain,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Globe,
  Library,
  Link as LinkIcon,
  Loader2,
  Wrench,
} from 'lucide-react'
import * as React from 'react'

import type { ThreadItem } from '~/lib/chat-types'

type SecondaryKind =
  | 'thinking'
  | 'memory_pill'
  | 'tool_call'
  | 'server_tool_use'
  | 'kb_search'
  | 'citation'

type SecondaryItem = ThreadItem & { kind: SecondaryKind }

type Props = {
  items: SecondaryItem[]
  isStreaming?: boolean
  /** Default expanded only while live; collapsed by default once done. */
  defaultOpen?: boolean
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function stepIcon(item: SecondaryItem) {
  const cls = 'size-3'
  const sw = 2
  if (item.kind === 'thinking') return <Brain className={cls} strokeWidth={sw} />
  if (item.kind === 'memory_pill') return <Brain className={cls} strokeWidth={sw} />
  if (item.kind === 'citation') return <ExternalLink className={cls} strokeWidth={sw} />
  if (item.kind === 'kb_search') return <Library className={cls} strokeWidth={sw} />
  const name = (item.data as { tool_name?: string }).tool_name
  if (name === 'web_search') return <Globe className={cls} strokeWidth={sw} />
  if (name === 'fetch_webpage') return <LinkIcon className={cls} strokeWidth={sw} />
  if (name === 'kb_search' || name === 'search_knowledge_base')
    return <Library className={cls} strokeWidth={sw} />
  return <Wrench className={cls} strokeWidth={sw} />
}

function stepTitle(item: SecondaryItem): React.ReactNode {
  switch (item.kind) {
    case 'thinking':
      return <>Reasoning</>
    case 'memory_pill': {
      const n = item.data.count
      return (
        <>
          Memory injection
          <span className="mono muted">
            · {n} {n === 1 ? 'fact' : 'facts'}
          </span>
        </>
      )
    }
    case 'tool_call': {
      const { tool_name, params } = item.data as {
        tool_name: string
        params?: Record<string, unknown>
      }
      const q = typeof params?.query === 'string' ? (params.query as string) : null
      return (
        <>
          <span className="mono">{tool_name}</span>
          {q && <span className="hits">&ldquo;{q}&rdquo;</span>}
        </>
      )
    }
    case 'server_tool_use': {
      const { tool_name, input } = item.data as {
        tool_name: string
        input?: Record<string, unknown>
      }
      const qs = Array.isArray(input?.queries) ? (input!.queries as unknown[]) : null
      const q = typeof input?.query === 'string' ? (input.query as string) : null
      const label =
        qs && qs.length > 0
          ? qs.map((s) => `"${String(s)}"`).join(', ')
          : q
            ? `"${q}"`
            : null
      return (
        <>
          <span className="mono">{tool_name}</span>
          {label && <span className="hits">{label}</span>}
        </>
      )
    }
    case 'citation': {
      const { url, title } = item.data
      const domain = domainOf(url)
      const label = title && title.trim() && title.trim() !== domain ? title.trim() : domain
      return (
        <>
          <span className="mono">{label}</span>
          {label !== domain && <span className="hits">{domain}</span>}
        </>
      )
    }
    case 'kb_search': {
      const { query, chunks } = item.data
      return (
        <>
          <span className="mono">search_knowledge_base</span>
          {query && <span className="hits">&ldquo;{query}&rdquo;</span>}
          <span className="mono muted">
            · {chunks.length} {chunks.length === 1 ? 'chunk' : 'chunks'}
          </span>
        </>
      )
    }
  }
}

function stepSub(item: SecondaryItem): React.ReactNode {
  if (item.kind === 'citation') {
    const snippet = item.data.snippet
    return snippet ? <div className="step-sub">{snippet}</div> : null
  }
  if (item.kind === 'tool_call') {
    const data = item.data as { result_snippet?: string | null; error?: string | null }
    if (data.error) return <div className="step-sub" style={{ color: 'var(--err)' }}>{data.error}</div>
    if (data.result_snippet) return <div className="step-sub">{data.result_snippet}</div>
  }
  if (item.kind === 'thinking') {
    const text = (item.data as { text: string }).text
    return text ? <div className="step-sub">{text}</div> : null
  }
  if (item.kind === 'kb_search') {
    if (item.data.error) {
      return <div className="step-sub" style={{ color: 'var(--err)' }}>{item.data.error}</div>
    }
    const chunks = item.data.chunks ?? []
    if (chunks.length === 0) {
      return <div className="step-sub">No matching chunks.</div>
    }
    return (
      <div className="step-sub flex flex-col gap-1">
        {chunks.map((c, i) => (
          <div key={c.chunk_id ?? `${c.document_id}-${i}`} className="flex flex-col gap-0.5">
            <div className="flex items-baseline gap-1.5">
              <span className="mono" style={{ color: 'var(--ink-2)' }}>
                {c.document_name}
              </span>
              {c.kb_name && (
                <span className="mono muted text-[10px]">· {c.kb_name}</span>
              )}
              <span className="mono muted text-[10px]" style={{ marginLeft: 'auto' }}>
                {c.score.toFixed(3)}
              </span>
            </div>
            {c.snippet && (
              <span className="line-clamp-2" style={{ color: 'var(--ink-3)' }}>
                {c.snippet}
              </span>
            )}
          </div>
        ))}
      </div>
    )
  }
  return null
}

function Step({ item, last }: { item: SecondaryItem; last: boolean }) {
  const running = item.status === 'streaming'
  const isMemory = item.kind === 'memory_pill'
  const kindClass = isMemory ? 'memory-step' : 'tool-step'
  const inner = (
    <>
      <div className="step-gutter">
        <div className="step-dot">
          {running ? <Loader2 className="size-2.5 animate-spin" strokeWidth={2.5} /> : stepIcon(item)}
        </div>
        {!last && <div className="step-bar" />}
      </div>
      <div className="step-content">
        <div className="step-title">
          {stepTitle(item)}
          {running && <span className="running-label">running…</span>}
          {!running && item.latency_ms != null && (
            <span className="ms mono muted">{item.latency_ms}ms</span>
          )}
        </div>
        {stepSub(item)}
      </div>
    </>
  )
  const rowCls = `think-step ${kindClass} ${last ? 'last' : ''} ${running ? 'running' : ''}`
  // Citations are linkified so the user can jump to the source from inside
  // the collapsed block without losing the surrounding context.
  if (item.kind === 'citation') {
    return (
      <a
        href={item.data.url}
        target="_blank"
        rel="noopener noreferrer"
        className={rowCls}
        style={{ textDecoration: 'none' }}
      >
        {inner}
      </a>
    )
  }
  return <div className={rowCls}>{inner}</div>
}

export function ProcessBlock({ items, isStreaming, defaultOpen }: Props) {
  const [open, setOpen] = React.useState(defaultOpen ?? Boolean(isStreaming))
  const count = items.length
  if (count === 0) return null

  const totalLatency = items.reduce((acc, it) => acc + (it.latency_ms ?? 0), 0)
  const citationsCount = items.filter((i) => i.kind === 'citation').length

  let title: React.ReactNode
  if (isStreaming) {
    title = (
      <>
        Thinking
        <span className="ellipsis">
          <span />
          <span />
          <span />
        </span>
      </>
    )
  } else if (citationsCount > 0) {
    title = (
      <>
        Researched
        <span className="mono muted">
          · {citationsCount} {citationsCount === 1 ? 'source' : 'sources'}
        </span>
      </>
    )
  } else {
    title = <>Thought</>
  }

  return (
    <div
      className={`thinking-block ${isStreaming ? 'running' : 'done'}`}
      data-testid="process-block"
    >
      <div
        className="thinking-head"
        role="button"
        tabIndex={0}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setOpen((v) => !v)
          }
        }}
      >
        {open ? (
          <ChevronDown className="size-3" strokeWidth={2} />
        ) : (
          <ChevronRight className="size-3" strokeWidth={2} />
        )}
        <Brain className="size-3.5" strokeWidth={2} />
        <span className="thinking-title">{title}</span>
        <span className="mono muted">
          · {count} {count === 1 ? 'step' : 'steps'}
        </span>
        {!isStreaming && totalLatency > 0 && (
          <span className="ms mono muted">{(totalLatency / 1000).toFixed(1)}s</span>
        )}
        {isStreaming && (
          <span className="streaming-badge" style={{ marginLeft: 'auto' }}>
            <span className="dot" />
            live
          </span>
        )}
      </div>
      {open && (
        <div className="thinking-body">
          {items.map((item, i) => (
            <Step key={item.id} item={item} last={i === items.length - 1} />
          ))}
        </div>
      )}
    </div>
  )
}
