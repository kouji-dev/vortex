/**
 * Q5 — KB settings (embedder, chunker, retrieval policy, tags).
 *
 * Settings fields stay read-only until the KB PATCH endpoint exposes them;
 * tags are persisted via the existing PATCH route (`PUT /api/knowledge-bases/{id}`)
 * where the column already lives on the model.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import { formatTags, parseTagsInput } from '~/lib/kb-tags'

export const Route = createFileRoute('/rag/kbs/$id/settings')({
  component: SettingsPage,
})

type KbSettingsShape = {
  id: number
  name: string
  embedder_id?: string | null
  vector_backend?: string | null
  chunker_id?: string | null
  default_retrieval_policy_id?: string | null
  language?: string | null
  tags?: string[] | null
}

type Tab = 'settings' | 'api-keys'

function SettingsPage() {
  const { id } = Route.useParams()
  const kbId = Number(id)
  const qc = useQueryClient()
  const [tab, setTab] = React.useState<Tab>('settings')
  const q = useQuery({
    queryKey: ['rag', 'kb-settings', kbId],
    queryFn: async (): Promise<KbSettingsShape> => {
      const res = await fetch(`${getApiBase()}/api/knowledge-bases/${kbId}`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
      return (await res.json()) as KbSettingsShape
    },
  })

  const [tagsDraft, setTagsDraft] = React.useState<string | null>(null)
  const liveTags = tagsDraft ?? formatTags(q.data?.tags ?? [])
  const dirty = tagsDraft !== null && tagsDraft !== formatTags(q.data?.tags ?? [])

  const saveTags = useMutation({
    mutationFn: async (next: string[]) => {
      const res = await fetch(`${getApiBase()}/api/knowledge-bases/${kbId}`, {
        method: 'PATCH',
        headers: {
          ...(await getAuthHeaders()),
          'content-type': 'application/json',
        },
        body: JSON.stringify({ tags: next }),
      })
      if (!res.ok) throw new Error(await res.text())
      return (await res.json()) as KbSettingsShape
    },
    onSuccess: () => {
      setTagsDraft(null)
      void qc.invalidateQueries({ queryKey: ['rag', 'kb-settings', kbId] })
    },
  })

  function handleSaveTags() {
    saveTags.mutate(parseTagsInput(liveTags))
  }

  return (
    <div className="panel" data-testid="rag-settings">
      <div className="panel-head" style={{ display: 'flex', gap: 12 }}>
        <button
          type="button"
          onClick={() => setTab('settings')}
          data-testid="rag-settings-tab-settings"
          data-active={tab === 'settings' ? 'true' : 'false'}
          style={{
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            fontWeight: tab === 'settings' ? 600 : 400,
            color: tab === 'settings' ? 'var(--ink)' : 'var(--ink-3)',
          }}
        >
          Settings
        </button>
        <button
          type="button"
          onClick={() => setTab('api-keys')}
          data-testid="rag-settings-tab-api-keys"
          data-active={tab === 'api-keys' ? 'true' : 'false'}
          style={{
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            fontWeight: tab === 'api-keys' ? 600 : 400,
            color: tab === 'api-keys' ? 'var(--ink)' : 'var(--ink-3)',
          }}
        >
          API Keys
        </button>
      </div>
      {tab === 'api-keys' ? (
        <ApiKeysPanel kbId={kbId} />
      ) : (
      <div className="panel-body" style={{ padding: 16, display: 'grid', gap: 10, maxWidth: 480 }}>
        {q.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
        {q.data && (
          <>
            <Field label="Embedder" value={q.data.embedder_id ?? 'voyage-3'} testId="rag-settings-embedder" />
            <Field
              label="Vector backend"
              value={q.data.vector_backend ?? 'pgvector'}
              testId="rag-settings-backend"
            />
            <Field label="Chunker" value={q.data.chunker_id ?? 'fixed_token'} testId="rag-settings-chunker" />
            <Field
              label="Retrieval policy"
              value={q.data.default_retrieval_policy_id ?? '— org default —'}
              testId="rag-settings-policy"
            />
            <Field label="Language" value={q.data.language ?? 'auto'} testId="rag-settings-language" />
            <label style={{ fontSize: 12, display: 'grid', gap: 4 }}>
              Tags (comma-separated)
              <input
                className="rag-input"
                value={liveTags}
                placeholder="legal, public, q1-2026"
                onChange={(e) => setTagsDraft(e.target.value)}
                data-testid="rag-settings-tags"
              />
            </label>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {parseTagsInput(liveTags).map((t) => (
                <span
                  key={t}
                  className="pill"
                  data-testid={`rag-settings-tag-chip-${t}`}
                  style={{ fontSize: 11 }}
                >
                  {t}
                </span>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                disabled={!dirty || saveTags.isPending}
                onClick={handleSaveTags}
                data-testid="rag-settings-tags-save"
              >
                {saveTags.isPending ? 'Saving…' : 'Save tags'}
              </button>
              {dirty && (
                <button
                  type="button"
                  disabled={saveTags.isPending}
                  onClick={() => setTagsDraft(null)}
                  data-testid="rag-settings-tags-cancel"
                >
                  Cancel
                </button>
              )}
              {saveTags.isError && (
                <span style={{ fontSize: 11, color: 'var(--err)' }}>
                  {(saveTags.error as Error).message}
                </span>
              )}
            </div>
          </>
        )}
      </div>
      )}
    </div>
  )
}

function Field({ label, value, testId }: { label: string; value: string; testId: string }) {
  return (
    <label style={{ fontSize: 12, display: 'grid', gap: 4 }}>
      {label}
      <input className="rag-input" value={value} disabled data-testid={testId} />
    </label>
  )
}

// ── API Keys tab ─────────────────────────────────────────────────────────────

type ScopedKey = {
  id: string
  name: string
  prefix: string
  scopes: string[]
  created_at: string
  last_used_at: string | null
  revoked_at: string | null
}

type ScopedKeyCreated = ScopedKey & { plaintext: string }

function ApiKeysPanel({ kbId }: { kbId: number }) {
  const qc = useQueryClient()
  const apiBase = getApiBase()
  const listKey = ['rag', 'kb-scoped-keys', kbId] as const

  const q = useQuery({
    queryKey: listKey,
    queryFn: async (): Promise<ScopedKey[]> => {
      const res = await fetch(`${apiBase}/api/knowledge-bases/${kbId}/api-keys`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json()
    },
  })

  const [draftName, setDraftName] = React.useState('')
  const [secret, setSecret] = React.useState<ScopedKeyCreated | null>(null)

  const mint = useMutation({
    mutationFn: async (name: string): Promise<ScopedKeyCreated> => {
      const res = await fetch(`${apiBase}/api/knowledge-bases/${kbId}/api-keys`, {
        method: 'POST',
        headers: {
          ...(await getAuthHeaders()),
          'content-type': 'application/json',
        },
        body: JSON.stringify({ name }),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json()
    },
    onSuccess: (created) => {
      setSecret(created)
      setDraftName('')
      void qc.invalidateQueries({ queryKey: listKey })
    },
  })

  const revoke = useMutation({
    mutationFn: async (keyId: string) => {
      const res = await fetch(
        `${apiBase}/api/knowledge-bases/${kbId}/api-keys/${keyId}`,
        { method: 'DELETE', headers: await getAuthHeaders() },
      )
      if (!res.ok && res.status !== 204) throw new Error(await res.text())
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: listKey }),
  })

  return (
    <div className="panel-body" data-testid="rag-settings-api-keys" style={{ padding: 16, display: 'grid', gap: 12 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', maxWidth: 480 }}>
        <label style={{ fontSize: 12, display: 'grid', gap: 4, flex: 1 }}>
          New key name
          <input
            className="rag-input"
            value={draftName}
            placeholder="readonly-bot"
            onChange={(e) => setDraftName(e.target.value)}
            data-testid="rag-scoped-key-name"
          />
        </label>
        <button
          type="button"
          disabled={mint.isPending}
          onClick={() => mint.mutate(draftName.trim() || `kb-${kbId}`)}
          data-testid="rag-scoped-key-mint"
        >
          {mint.isPending ? 'Minting…' : 'Mint key'}
        </button>
      </div>
      {mint.isError && (
        <p style={{ color: 'var(--err)', fontSize: 11 }}>{(mint.error as Error).message}</p>
      )}
      {secret && (
        <div
          data-testid="rag-scoped-key-secret"
          style={{
            background: 'var(--bg-2, #fff8e7)',
            border: '1px solid var(--warn, #d4a017)',
            padding: 10,
            borderRadius: 6,
            fontSize: 12,
          }}
        >
          <p style={{ fontWeight: 600, marginBottom: 4 }}>
            Copy this secret now — it will not be shown again.
          </p>
          <code style={{ display: 'block', wordBreak: 'break-all', padding: 4, background: 'var(--bg)' }}>
            {secret.plaintext}
          </code>
          <button
            type="button"
            onClick={() => setSecret(null)}
            data-testid="rag-scoped-key-secret-dismiss"
            style={{ marginTop: 6 }}
          >
            Dismiss
          </button>
        </div>
      )}

      {q.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
      <table className="rag-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Prefix</th>
            <th>Scopes</th>
            <th>Created</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(q.data ?? []).map((k) => (
            <tr key={k.id} data-testid={`rag-scoped-key-row-${k.id}`}>
              <td>{k.name}</td>
              <td><code style={{ fontSize: 11 }}>{k.prefix}…</code></td>
              <td style={{ fontSize: 11, color: 'var(--ink-3)' }}>{k.scopes.join(', ')}</td>
              <td style={{ fontSize: 11 }}>{new Date(k.created_at).toLocaleDateString()}</td>
              <td>
                <button
                  type="button"
                  onClick={() => revoke.mutate(k.id)}
                  disabled={revoke.isPending}
                  data-testid={`rag-scoped-key-revoke-${k.id}`}
                >
                  Revoke
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {q.data && q.data.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--ink-3)', textAlign: 'center', padding: 16 }}>
          No keys minted.
        </p>
      )}
    </div>
  )
}
