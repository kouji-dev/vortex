/**
 * Q10 — Search providers config (deploy-vs-runtime).
 *
 * The deployment declares which web-search providers exist + their API keys
 * (YAML/env). This page is runtime-only: it shows the declared set and lets the
 * admin pick the default-for-web among the ENABLED providers. It NEVER collects
 * an API key or endpoint — those live in deployment config.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import {
  resolveSelected,
  selectableIds,
  type ProvidersConfig,
} from '~/lib/kb-provider-config'

export const Route = createFileRoute('/rag/search-providers')({
  component: SearchProvidersPage,
})

function SearchProvidersPage() {
  const qc = useQueryClient()
  const providers = useQuery({
    queryKey: ['rag', 'providers-config'],
    queryFn: async (): Promise<ProvidersConfig> => {
      const res = await fetch(
        `${getApiBase()}/api/knowledge-bases/providers-config`,
        { headers: await getAuthHeaders() },
      )
      if (!res.ok) throw new Error(await res.text())
      return (await res.json()) as ProvidersConfig
    },
    staleTime: 5 * 60_000,
  })

  const layer = providers.data?.search_providers
  const enabled = selectableIds(layer)
  const [draftDefault, setDraftDefault] = React.useState<string | null>(null)
  const currentDefault = resolveSelected(layer, layer?.default_id)
  const selectedDefault = draftDefault ?? currentDefault

  // The default-for-web is runtime state. Persist via the org search-default
  // endpoint when present; a 404 is treated as a no-op so the chosen default
  // still reflects in the UI for builds without that endpoint.
  const saveDefault = useMutation({
    mutationFn: async (providerId: string) => {
      const res = await fetch(`${getApiBase()}/api/search-providers/default`, {
        method: 'PUT',
        headers: {
          ...(await getAuthHeaders()),
          'content-type': 'application/json',
        },
        body: JSON.stringify({ provider: providerId }),
      })
      if (!res.ok && res.status !== 404) throw new Error(await res.text())
      return providerId
    },
    onSuccess: () => {
      setDraftDefault(null)
      void qc.invalidateQueries({ queryKey: ['rag', 'providers-config'] })
    },
  })

  return (
    <div className="panel" data-testid="rag-search-providers">
      <div className="panel-head">
        <span>Search providers</span>
        <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>
          {layer ? `${layer.items.length} declared` : '…'}
        </span>
      </div>
      <div className="panel-body" style={{ padding: 16, display: 'grid', gap: 12 }}>
        <p
          style={{ fontSize: 11, color: 'var(--ink-3)', margin: 0 }}
          data-testid="rag-sp-deploy-note"
        >
          Available providers and their API keys are set in deployment config.
          Enable/disable them there; choose the default below.
        </p>

        {providers.isPending && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>
        )}

        {layer && (
          <>
            <table className="rag-table" data-testid="rag-sp-table">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Status</th>
                  <th>Credential</th>
                  <th>Default</th>
                </tr>
              </thead>
              <tbody>
                {layer.items.map((p) => (
                  <tr key={p.id} data-testid={`rag-sp-row-${p.id}`}>
                    <td>{p.id}</td>
                    <td>
                      <span
                        className="pill"
                        data-testid={`rag-sp-status-${p.id}`}
                        style={{
                          fontSize: 11,
                          color: p.enabled ? 'var(--green, #2ea36b)' : 'var(--ink-3)',
                        }}
                      >
                        {p.enabled ? 'enabled' : 'disabled'}
                      </span>
                    </td>
                    <td style={{ fontSize: 11, color: 'var(--ink-3)' }}>
                      {p.id === 'internal_kbs'
                        ? 'n/a'
                        : p.has_credential
                          ? 'configured'
                          : 'missing'}
                    </td>
                    <td>
                      {selectedDefault === p.id ? (
                        <span data-testid={`rag-sp-default-${p.id}`}>★</span>
                      ) : (
                        ''
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <label style={{ fontSize: 12, display: 'grid', gap: 4, maxWidth: 320 }}>
              Default for web search
              <select
                className="rag-input"
                value={selectedDefault}
                disabled={enabled.length === 0 || saveDefault.isPending}
                data-testid="rag-sp-default-select"
                onChange={(e) => setDraftDefault(e.target.value)}
              >
                {enabled.length === 0 && <option value="">— none enabled —</option>}
                {enabled.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </label>

            <div>
              <button
                type="button"
                disabled={
                  enabled.length === 0 ||
                  saveDefault.isPending ||
                  selectedDefault === currentDefault
                }
                onClick={() => saveDefault.mutate(selectedDefault)}
                data-testid="rag-sp-save"
              >
                {saveDefault.isPending ? 'Saving…' : 'Set default'}
              </button>
              {saveDefault.isError && (
                <span style={{ fontSize: 11, color: 'var(--err)', marginLeft: 8 }}>
                  {(saveDefault.error as Error).message}
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
