// apps/frontend/src/components/gateway/CodeSnippetPanel.tsx
// J10 — reusable per-endpoint snippet panel (cURL / Python / TS / Claude-Code).
import * as React from 'react'
import { renderSnippets, type Snippet } from '~/lib/code-snippets'
import type { SnippetContext, SnippetEndpoint } from '~/lib/gateway-types'

export interface CodeSnippetPanelProps {
  endpoint: SnippetEndpoint
  baseUrl: string
  apiKey: string
  model: string
  /** Show endpoint picker (default: single fixed endpoint). */
  endpointOptions?: { value: SnippetEndpoint; label: string }[]
  onEndpointChange?: (e: SnippetEndpoint) => void
}

const DEFAULT_OPTIONS: { value: SnippetEndpoint; label: string }[] = [
  { value: 'openai_chat', label: 'OpenAI Chat' },
  { value: 'openai_embeddings', label: 'OpenAI Embeddings' },
  { value: 'anthropic_messages', label: 'Anthropic Messages' },
  { value: 'bedrock_converse', label: 'Bedrock Converse' },
  { value: 'rerank', label: 'Rerank' },
  { value: 'moderations', label: 'Moderations' },
]

export function CodeSnippetPanel(props: CodeSnippetPanelProps) {
  const ctx: SnippetContext = {
    endpoint: props.endpoint,
    baseUrl: props.baseUrl,
    apiKey: props.apiKey,
    model: props.model,
  }
  const snippets = React.useMemo(() => renderSnippets(ctx), [ctx.endpoint, ctx.baseUrl, ctx.apiKey, ctx.model])
  const [active, setActive] = React.useState<Snippet>(snippets[0])
  React.useEffect(() => {
    setActive(snippets[0])
  }, [snippets])

  async function copy() {
    try {
      await navigator.clipboard.writeText(active.body)
    } catch {
      /* ignore */
    }
  }

  const options = props.endpointOptions ?? DEFAULT_OPTIONS

  return (
    <div className="panel" data-testid="code-snippet-panel">
      <div className="panel-head" style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'space-between' }}>
        <span>Code snippet</span>
        {props.onEndpointChange && (
          <select
            value={props.endpoint}
            onChange={(e) => props.onEndpointChange?.(e.target.value as SnippetEndpoint)}
            style={{ fontSize: 11, padding: 4, border: '1px solid var(--line)', borderRadius: 3, background: 'var(--bg)', color: 'var(--ink)' }}
            data-testid="endpoint-picker"
          >
            {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        )}
      </div>
      <div style={{ display: 'flex', gap: 4, padding: '6px 10px', borderBottom: '1px solid var(--line)' }}>
        {snippets.map((s) => (
          <button
            key={s.lang}
            onClick={() => setActive(s)}
            className={`btn btn-sm${active.lang === s.lang ? ' active' : ''}`}
            data-testid={`tab-${s.lang}`}
          >
            {s.label}
          </button>
        ))}
        <button className="btn btn-sm" style={{ marginLeft: 'auto' }} onClick={copy} data-testid="copy-snippet">
          Copy
        </button>
      </div>
      <pre
        style={{
          margin: 0,
          padding: 12,
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
          background: 'var(--bg-2)',
          color: 'var(--ink)',
          overflow: 'auto',
          maxHeight: 360,
        }}
      >
        {active.body}
      </pre>
    </div>
  )
}
