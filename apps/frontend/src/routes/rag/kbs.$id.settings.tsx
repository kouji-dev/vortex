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

function SettingsPage() {
  const { id } = Route.useParams()
  const kbId = Number(id)
  const qc = useQueryClient()
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
      <div className="panel-head">
        <span>Settings</span>
      </div>
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
