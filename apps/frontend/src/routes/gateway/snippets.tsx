// apps/frontend/src/routes/gateway/snippets.tsx
// Gateway → Snippets (J10): pick an endpoint + model + key → see code samples.
import { Select } from '~/components/ui/select'
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'
import { CodeSnippetPanel } from '~/components/gateway/CodeSnippetPanel'
import { authorizedFetch } from '~/lib/authorizedFetch'
import type { ModelInfo, SnippetEndpoint } from '~/lib/gateway-types'

export const Route = createFileRoute('/gateway/snippets')({
  component: SnippetsPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function SnippetsPage() {
  const [endpoint, setEndpoint] = React.useState<SnippetEndpoint>('openai_chat')
  const [models, setModels] = React.useState<ModelInfo[]>([])
  const [model, setModel] = React.useState('claude-sonnet-4-6')
  const [apiKey, setApiKey] = React.useState('sk-your-gateway-key')
  const baseUrl = React.useMemo(() => {
    if (typeof window !== 'undefined') return `${window.location.origin}/api`
    return API_BASE || 'https://gateway.example.com'
  }, [])

  React.useEffect(() => {
    authorizedFetch(`${API_BASE}/api/v1/models`)
      .then((r) => r.json())
      .then((d) => Array.isArray(d?.data) && setModels(d.data))
      .catch(() => null)
  }, [])

  return (
    <div className="main-inner" data-testid="gateway-snippets">
      <div className="screen-head">
        <div>
          <h1>Code snippets</h1>
          <div className="sub">Drop-in samples for every compatible endpoint</div>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-body" style={{ display: 'flex', gap: 8, flexWrap: 'wrap', padding: 12 }}>
          <label style={{ fontSize: 11, color: 'var(--ink-3)', display: 'flex', flexDirection: 'column', gap: 4 }}>
            Model
            <Select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              data-testid="snippet-model"
            size="sm"
            inline
            >
              {models.length === 0 && <option value={model}>{model}</option>}
              {models.map((m) => <option key={m.id} value={m.model_id}>{m.display_name || m.model_id}</option>)}
            </Select>
          </label>
          <label style={{ fontSize: 11, color: 'var(--ink-3)', display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 200 }}>
            API key (paste yours; not stored)
            <input
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              style={{ fontSize: 11, padding: 4, border: '1px solid var(--line)', borderRadius: 3, background: 'var(--bg)', color: 'var(--ink)', fontFamily: 'var(--font-mono)' }}
              data-testid="snippet-apikey"
            />
          </label>
        </div>
      </div>

      <CodeSnippetPanel
        endpoint={endpoint}
        baseUrl={baseUrl}
        apiKey={apiKey}
        model={model}
        onEndpointChange={setEndpoint}
      />
    </div>
  )
}
