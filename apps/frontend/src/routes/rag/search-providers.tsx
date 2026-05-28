/**
 * Q10 — Search providers config.
 *
 * Lists every external search provider the org can wire up. The backend
 * stores config encrypted; this page only collects the form values and
 * validates them client-side via `validateSearchProviderConfig`.
 */
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import { SEARCH_PROVIDER_KINDS, validateSearchProviderConfig } from '~/lib/rag-logic'

export const Route = createFileRoute('/rag/search-providers')({
  component: SearchProvidersPage,
})

function SearchProvidersPage() {
  const [kind, setKind] = React.useState<(typeof SEARCH_PROVIDER_KINDS)[number]>('tavily')
  const [apiKey, setApiKey] = React.useState('')
  const [cx, setCx] = React.useState('')

  const config: Record<string, unknown> = { api_key: apiKey, ...(kind === 'google_cse' ? { cx } : {}) }
  const err = validateSearchProviderConfig(kind, config)

  return (
    <div className="panel" data-testid="rag-search-providers">
      <div className="panel-head">
        <span>Search providers</span>
        <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>
          {SEARCH_PROVIDER_KINDS.length} kinds available
        </span>
      </div>
      <div className="panel-body" style={{ padding: 16, display: 'grid', gap: 10 }}>
        <label style={{ fontSize: 12 }}>
          Provider kind
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as typeof kind)}
            className="rag-input"
            data-testid="rag-sp-kind"
          >
            {SEARCH_PROVIDER_KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        {kind !== 'internal' && (
          <label style={{ fontSize: 12 }}>
            API key
            <input
              className="rag-input"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              data-testid="rag-sp-key"
            />
          </label>
        )}
        {kind === 'google_cse' && (
          <label style={{ fontSize: 12 }}>
            cx (custom search engine id)
            <input
              className="rag-input"
              value={cx}
              onChange={(e) => setCx(e.target.value)}
              data-testid="rag-sp-cx"
            />
          </label>
        )}
        <div data-testid="rag-sp-status" style={{ fontSize: 12 }}>
          {err ? (
            <span style={{ color: 'var(--red, #c43c3c)' }}>{err}</span>
          ) : (
            <span style={{ color: 'var(--green, #2ea36b)' }}>Config valid.</span>
          )}
        </div>
        <button type="button" disabled={!!err} data-testid="rag-sp-save">
          Save provider
        </button>
      </div>
    </div>
  )
}
