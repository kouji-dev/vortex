import { Brain, ChevronDown, ChevronRight, Globe, Library, Link, Loader2, Wrench } from 'lucide-react'
import * as React from 'react'

import type { StreamThreadItem } from '~/lib/chat-types'

type Props = {
  items: StreamThreadItem[]
  /** Live streaming state — colors header with accent, shows live dots. */
  running?: boolean
  /** Default collapsed when finished; default expanded while running. */
  defaultOpen?: boolean
}

function stepIcon(kind: StreamThreadItem['kind']) {
  const cls = 'size-3'
  const sw = 2
  switch (kind) {
    case 'memory': return <Brain className={cls} strokeWidth={sw} />
    case 'web_search': return <Globe className={cls} strokeWidth={sw} />
    case 'fetch_webpage': return <Link className={cls} strokeWidth={sw} />
    case 'kb_search': return <Library className={cls} strokeWidth={sw} />
    default: return <Wrench className={cls} strokeWidth={sw} />
  }
}

function stepTitle(item: StreamThreadItem): React.ReactNode {
  switch (item.kind) {
    case 'memory':
      return (
        <>
          Memory injection
          <span className="mono muted">· {item.count} {item.count === 1 ? 'fact' : 'facts'}</span>
        </>
      )
    case 'web_search':
      return (
        <>
          <span className="mono">web_search</span>
          <span className="hits">&ldquo;{item.query}&rdquo;</span>
        </>
      )
    case 'fetch_webpage':
      return (
        <>
          <span className="mono">fetch_webpage</span>
          <span className="hits">{item.url}</span>
        </>
      )
    case 'kb_search':
      return (
        <>
          <span className="mono">kb_search</span>
          <span className="hits">&ldquo;{item.query}&rdquo;</span>
        </>
      )
    case 'tool_call':
      return <span className="mono">{item.tool}</span>
  }
}

function stepParams(item: StreamThreadItem): React.ReactNode {
  switch (item.kind) {
    case 'memory':
      return null
    case 'web_search':
      return item.provider ? (
        <div className="tool-params">
          <span className="param"><span className="param-k">provider</span>=<span className="param-v">&quot;{item.provider}&quot;</span></span>
        </div>
      ) : null
    case 'fetch_webpage':
      return item.provider ? (
        <div className="tool-params">
          <span className="param"><span className="param-k">provider</span>=<span className="param-v">&quot;{item.provider}&quot;</span></span>
        </div>
      ) : null
    case 'kb_search':
      return item.sources && item.sources.length > 0 ? (
        <div className="tool-params">
          {item.sources.map((s, i) => (
            <span key={i} className="param">
              <span className="param-k">kb</span>=<span className="param-v">&quot;{s.kb_name}&quot;</span>
              {s.chunks_used > 0 && <span className="param-k"> ({s.chunks_used} chunks)</span>}
            </span>
          ))}
        </div>
      ) : null
    case 'tool_call':
      if (!item.params) return null
      return (
        <div className="tool-params">
          {Object.entries(item.params).map(([k, v]) => (
            <span key={k} className="param">
              <span className="param-k">{k}</span>=<span className="param-v">&quot;{v}&quot;</span>
            </span>
          ))}
        </div>
      )
  }
}

function stepSub(item: StreamThreadItem): React.ReactNode {
  if (item.kind === 'web_search' && item.result_snippet) return <div className="step-sub">{item.result_snippet}</div>
  if (item.kind === 'fetch_webpage' && item.result_snippet) return <div className="step-sub">{item.result_snippet}</div>
  return null
}

function ThinkStep({ item, last }: { item: StreamThreadItem; last: boolean }) {
  const running = item.status === 'running'
  const kindClass = item.kind === 'memory' ? 'memory-step' : 'tool-step'
  return (
    <div className={`think-step ${kindClass} ${last ? 'last' : ''} ${running ? 'running' : ''}`}>
      <div className="step-gutter">
        <div className="step-dot">
          {running ? <Loader2 className="size-2.5 animate-spin" strokeWidth={2.5} /> : stepIcon(item.kind)}
        </div>
        {!last && <div className="step-bar" />}
      </div>
      <div className="step-content">
        <div className="step-title">
          {stepTitle(item)}
          {running && <span className="running-label">running…</span>}
        </div>
        {stepParams(item)}
        {stepSub(item)}
      </div>
    </div>
  )
}

export function ThinkingBlock({ items, running, defaultOpen }: Props) {
  const [open, setOpen] = React.useState(defaultOpen ?? Boolean(running))
  const count = items.length
  if (count === 0) return null

  return (
    <div className={`thinking-block ${running ? 'running' : 'done'}`} data-testid="thinking-block">
      <div
        className="thinking-head"
        onClick={() => setOpen((v) => !v)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setOpen((v) => !v)
          }
        }}
      >
        {open
          ? <ChevronDown className="size-3" strokeWidth={2} />
          : <ChevronRight className="size-3" strokeWidth={2} />}
        <Brain className="size-3.5" strokeWidth={2} />
        <span className="thinking-title">
          {running ? (
            <>Thinking<span className="ellipsis"><span/><span/><span/></span></>
          ) : (
            <>Thought ({count} step{count !== 1 ? 's' : ''})</>
          )}
        </span>
        <span className="mono muted">· {count} step{count !== 1 ? 's' : ''}</span>
        {running && (
          <span className="streaming-badge" style={{ marginLeft: 'auto' }}>
            <span className="dot" />live
          </span>
        )}
      </div>
      {open && (
        <div className="thinking-body">
          {items.map((item, i) => (
            <ThinkStep key={item.uid ?? i} item={item} last={i === items.length - 1} />
          ))}
        </div>
      )}
    </div>
  )
}
