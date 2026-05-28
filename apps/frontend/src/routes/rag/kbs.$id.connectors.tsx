/**
 * Q4 — Connectors configure + schedule + run history.
 */
import { useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import {
  parseConnectorSyncJobsListJson,
  parseKnowledgeBaseConnectorsListJson,
  type ConnectorSyncJob,
  type KnowledgeBaseConnector,
} from '~/lib/knowledge-base-types'

export const Route = createFileRoute('/rag/kbs/$id/connectors')({
  component: ConnectorsPage,
})

function ConnectorsPage() {
  const { id } = Route.useParams()
  const kbId = Number(id)

  const connectorsQ = useQuery({
    queryKey: ['rag', 'connectors', kbId],
    queryFn: async () => {
      const res = await fetch(`${getApiBase()}/api/knowledge-bases/${kbId}/connectors`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
      return parseKnowledgeBaseConnectorsListJson(await res.text())
    },
  })
  const jobsQ = useQuery({
    queryKey: ['rag', 'connector-jobs', kbId],
    queryFn: async () => {
      const res = await fetch(`${getApiBase()}/api/knowledge-bases/${kbId}/connector-jobs`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) return [] as ConnectorSyncJob[]
      return parseConnectorSyncJobsListJson(await res.text())
    },
  })

  const connectors: KnowledgeBaseConnector[] = connectorsQ.data ?? []
  const jobs: ConnectorSyncJob[] = jobsQ.data ?? []

  return (
    <div data-testid="rag-connectors">
      <div className="panel" style={{ marginBottom: 12 }}>
        <div className="panel-head">
          <span>Connectors</span>
          <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{connectors.length} total</span>
        </div>
        <div className="panel-body" style={{ padding: 12 }}>
          <table className="rag-table">
            <thead>
              <tr>
                <th>Label</th>
                <th>Kind</th>
                <th>Enabled</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {connectors.map((c) => (
                <tr key={c.id} data-testid={`rag-connector-row-${c.id}`}>
                  <td>{c.label || '—'}</td>
                  <td>{c.kind}</td>
                  <td>
                    <span className={`rag-badge ${c.enabled ? 'ok' : 'bad'}`}>
                      {c.enabled ? 'on' : 'off'}
                    </span>
                  </td>
                  <td>{new Date(c.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!connectors.length && (
            <p style={{ fontSize: 12, color: 'var(--ink-3)', textAlign: 'center', padding: 12 }}>
              No connectors configured.
            </p>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <span>Run history</span>
        </div>
        <div className="panel-body" style={{ padding: 12 }}>
          <table className="rag-table">
            <thead>
              <tr>
                <th>Connector</th>
                <th>Job type</th>
                <th>Status</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} data-testid={`rag-connector-job-row-${j.id}`}>
                  <td>{j.connector_id}</td>
                  <td>{j.job_type}</td>
                  <td>
                    <span className={`rag-badge ${jobBadge(j.status)}`}>{j.status}</span>
                  </td>
                  <td>{j.started_at ? new Date(j.started_at).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!jobs.length && (
            <p style={{ fontSize: 12, color: 'var(--ink-3)', textAlign: 'center', padding: 12 }}>
              No sync runs yet.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

function jobBadge(status: string): 'ok' | 'bad' | 'warn' {
  if (status === 'completed' || status === 'success') return 'ok'
  if (status === 'failed') return 'bad'
  return 'warn'
}
