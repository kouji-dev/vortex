/**
 * Q12 — Quarantine: failed docs + retry.
 *
 * Shows documents with status="failed" (or quarantined) and exposes a
 * re-ingest action. The backend reingest route already exists under
 * `/api/knowledge-bases/{id}/documents/{docId}/reingest`.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import {
  parseKnowledgeBaseDocumentsListJson,
  type KnowledgeBaseDocument,
} from '~/lib/knowledge-base-types'

export const Route = createFileRoute('/rag/kbs/$id/quarantine')({
  component: QuarantinePage,
})

function QuarantinePage() {
  const { id } = Route.useParams()
  const kbId = Number(id)
  const qc = useQueryClient()
  const docsQ = useQuery({
    queryKey: ['rag', 'documents', kbId],
    queryFn: async () => {
      const res = await fetch(`${getApiBase()}/api/knowledge-bases/${kbId}/documents`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
      return parseKnowledgeBaseDocumentsListJson(await res.text())
    },
  })

  const reingest = useMutation({
    mutationFn: async (docId: number) => {
      const res = await fetch(
        `${getApiBase()}/api/knowledge-bases/${kbId}/documents/${docId}/reingest`,
        {
          method: 'POST',
          headers: await getAuthHeaders(),
        },
      )
      if (!res.ok) throw new Error(await res.text())
      return res.json()
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['rag', 'documents', kbId] }),
  })

  const docs: KnowledgeBaseDocument[] = docsQ.data ?? []
  const failed = docs.filter((d) => d.status === 'failed' || d.status === 'quarantined')

  return (
    <div className="panel" data-testid="rag-quarantine">
      <div className="panel-head">
        <span>Quarantined documents</span>
        <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{failed.length} failed</span>
      </div>
      <div className="panel-body" style={{ padding: 12 }}>
        {docsQ.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
        <table className="rag-table">
          <thead>
            <tr>
              <th>Filename</th>
              <th>Reason</th>
              <th>Last sync error</th>
              <th>Failed at</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {failed.map((d) => (
              <tr key={d.id} data-testid={`rag-quarantine-row-${d.id}`}>
                <td>{d.filename}</td>
                <td
                  style={{ fontSize: 11, color: 'var(--ink-3)' }}
                  data-testid={`rag-quarantine-reason-${d.id}`}
                >
                  {d.quarantine_reason ?? d.ingest_error ?? '—'}
                </td>
                <td
                  style={{ fontSize: 11, color: 'var(--ink-3)' }}
                  data-testid={`rag-quarantine-last-error-${d.id}`}
                >
                  {d.last_error
                    ? `${d.last_error}${d.sync_run_id ? ` (run ${d.sync_run_id.slice(0, 8)})` : ''}`
                    : '—'}
                </td>
                <td>{new Date(d.created_at).toLocaleString()}</td>
                <td>
                  <button
                    type="button"
                    disabled={reingest.isPending}
                    onClick={() => reingest.mutate(d.id)}
                    data-testid={`rag-quarantine-retry-${d.id}`}
                  >
                    Retry
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!failed.length && !docsQ.isPending && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)', textAlign: 'center', padding: 16 }}>
            No quarantined documents.
          </p>
        )}
      </div>
    </div>
  )
}
