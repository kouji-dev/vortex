/**
 * Q8 — Analytics: top queries, zero-result (gap report), citation hit-rate.
 */
import { useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'

import { getAnalytics } from '~/lib/rag-api'
import { sortQueriesByCount, summariseAnalytics } from '~/lib/rag-logic'

export const Route = createFileRoute('/rag/kbs/$id/analytics')({
  component: AnalyticsPage,
})

function AnalyticsPage() {
  const { id } = Route.useParams()
  const kbId = Number(id)
  const q = useQuery({
    queryKey: ['rag', 'analytics-detail', kbId],
    queryFn: () => getAnalytics(kbId),
  })

  return (
    <div data-testid="rag-analytics">
      {q.isPending && (
        <p style={{ fontSize: 12, color: 'var(--ink-3)', padding: 16 }}>Loading…</p>
      )}
      {q.error && (
        <p style={{ fontSize: 12, color: 'var(--red, #c43c3c)', padding: 16 }}>
          {(q.error as Error).message}
        </p>
      )}
      {q.data && (
        <>
          <SummaryRow data={q.data} />
          <div className="panel" style={{ marginTop: 12 }}>
            <div className="panel-head">
              <span>Top queries</span>
            </div>
            <div className="panel-body" style={{ padding: 12 }}>
              <table className="rag-table">
                <thead>
                  <tr>
                    <th>Query</th>
                    <th>Count</th>
                    <th>Avg hits</th>
                    <th>Avg latency</th>
                  </tr>
                </thead>
                <tbody>
                  {sortQueriesByCount(q.data.top_queries).map((s) => (
                    <tr key={s.query} data-testid={`rag-an-top-${encodeURIComponent(s.query)}`}>
                      <td>{s.query}</td>
                      <td>{s.count}</td>
                      <td>{s.avg_hits.toFixed(1)}</td>
                      <td>{Math.round(s.avg_latency_ms)} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel" style={{ marginTop: 12 }}>
            <div className="panel-head">
              <span>Zero-result queries (gap report)</span>
            </div>
            <div className="panel-body" style={{ padding: 12 }}>
              <table className="rag-table">
                <thead>
                  <tr>
                    <th>Query</th>
                    <th>Count</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.zero_result_queries.map((s) => (
                    <tr key={s.query} data-testid={`rag-an-zero-${encodeURIComponent(s.query)}`}>
                      <td>{s.query}</td>
                      <td>{s.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!q.data.zero_result_queries.length && (
                <p style={{ fontSize: 12, color: 'var(--ink-3)', textAlign: 'center' }}>
                  No zero-result queries — every search returned at least one chunk.
                </p>
              )}
            </div>
          </div>

          <div className="panel" style={{ marginTop: 12 }}>
            <div className="panel-head">
              <span>Citation hit-rate by document</span>
            </div>
            <div className="panel-body" style={{ padding: 12 }}>
              <table className="rag-table">
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Citations</th>
                    <th>Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.citation_hit_rate.map((c) => (
                    <tr key={c.document_id} data-testid={`rag-an-cite-${c.document_id}`}>
                      <td>{c.document_id}</td>
                      <td>{c.citations}</td>
                      <td>{(c.rate * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function SummaryRow({ data }: { data: Awaited<ReturnType<typeof getAnalytics>> }) {
  const s = summariseAnalytics(data)
  return (
    <div className="rag-kpi-row">
      <div className="rag-kpi">
        <div className="rag-kpi-label">Queries</div>
        <div className="rag-kpi-value">{s.totalQueries}</div>
      </div>
      <div className="rag-kpi">
        <div className="rag-kpi-label">Cost</div>
        <div className="rag-kpi-value">{s.totalCost}</div>
      </div>
      <div className="rag-kpi">
        <div className="rag-kpi-label">Thumbs up</div>
        <div className="rag-kpi-value">{s.thumbsUp}</div>
      </div>
      <div className="rag-kpi">
        <div className="rag-kpi-label">Zero-result rate</div>
        <div className="rag-kpi-value">{s.zeroRate}</div>
      </div>
    </div>
  )
}
