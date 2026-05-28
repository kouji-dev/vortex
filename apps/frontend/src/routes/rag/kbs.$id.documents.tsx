/**
 * Q3 — Documents table with filter + status badges.
 *
 * Re-uses the existing knowledge-bases documents endpoint; this page is the
 * /rag/ flavour with status colour-coding and a status filter.
 */
import { useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import {
  parseKnowledgeBaseDocumentsListJson,
  type KnowledgeBaseDocument,
} from '~/lib/knowledge-base-types'

export const Route = createFileRoute('/rag/kbs/$id/documents')({
  component: DocumentsPage,
})

function DocumentsPage() {
  const { id } = Route.useParams()
  const kbId = Number(id)
  const [status, setStatus] = React.useState<'all' | 'ready' | 'pending' | 'failed'>('all')

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

  const docs: KnowledgeBaseDocument[] = docsQ.data ?? []
  const filtered = status === 'all' ? docs : docs.filter((d) => d.status === status)

  return (
    <div className="panel" data-testid="rag-documents">
      <div
        className="panel-head"
        style={{ display: 'flex', justifyContent: 'space-between' }}
      >
        <span>Documents</span>
        <select
          className="rag-input"
          style={{ width: 'auto' }}
          value={status}
          onChange={(e) => setStatus(e.target.value as typeof status)}
          data-testid="rag-docs-filter"
        >
          <option value="all">all</option>
          <option value="ready">ready</option>
          <option value="pending">pending</option>
          <option value="failed">failed</option>
        </select>
      </div>
      <div className="panel-body" style={{ padding: 12 }}>
        {docsQ.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
        <table className="rag-table">
          <thead>
            <tr>
              <th>Filename</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((d) => (
              <tr key={d.id} data-testid={`rag-docs-row-${d.id}`}>
                <td>{d.filename}</td>
                <td>
                  <span className={`rag-badge ${badgeKind(d.status)}`}>{d.status}</span>
                </td>
                <td>{new Date(d.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!filtered.length && !docsQ.isPending && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)', textAlign: 'center', padding: 16 }}>
            No documents.
          </p>
        )}
      </div>
    </div>
  )
}

function badgeKind(status: string): 'ok' | 'bad' | 'warn' {
  if (status === 'ready' || status === 'indexed') return 'ok'
  if (status === 'failed' || status === 'quarantined') return 'bad'
  return 'warn'
}
