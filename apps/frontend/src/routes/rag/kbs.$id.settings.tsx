/**
 * Q5 — KB settings (embedder, chunker, retrieval policy).
 *
 * Read-only first cut: the UI fetches current settings and shows them in a
 * disabled form. Editing wiring lands when the KB PATCH endpoint exposes
 * those fields (the column is already on the model).
 */
import { useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'

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
}

function SettingsPage() {
  const { id } = Route.useParams()
  const kbId = Number(id)
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
