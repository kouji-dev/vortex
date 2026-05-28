/**
 * Q2 — Per-KB overview (status, stats).
 *
 * Reads the analytics overview to surface query volume + cost; falls back
 * to dashes when the KB has no traffic yet.
 */
import { useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'

import { getAnalytics } from '~/lib/rag-api'
import { summariseAnalytics } from '~/lib/rag-logic'

export const Route = createFileRoute('/rag/kbs/$id/overview')({
  component: OverviewPage,
})

function OverviewPage() {
  const { id } = Route.useParams()
  const kbId = Number(id)
  const q = useQuery({
    queryKey: ['rag', 'analytics', kbId],
    queryFn: () => getAnalytics(kbId),
  })

  return (
    <div className="panel" data-testid="rag-overview">
      <div className="panel-head">
        <span>Overview — KB {id}</span>
      </div>
      <div className="panel-body" style={{ padding: 16 }}>
        {q.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
        {q.error && (
          <p style={{ fontSize: 12, color: 'var(--red, #c43c3c)' }}>{(q.error as Error).message}</p>
        )}
        {q.data && <OverviewKpis data={q.data} />}
      </div>
    </div>
  )
}

function OverviewKpis({ data }: { data: Awaited<ReturnType<typeof getAnalytics>> }) {
  const s = summariseAnalytics(data)
  return (
    <div className="rag-kpi-row" data-testid="rag-overview-kpis">
      <div className="rag-kpi">
        <div className="rag-kpi-label">Queries (30d)</div>
        <div className="rag-kpi-value">{s.totalQueries}</div>
      </div>
      <div className="rag-kpi">
        <div className="rag-kpi-label">Cost (30d)</div>
        <div className="rag-kpi-value">{s.totalCost}</div>
      </div>
      <div className="rag-kpi">
        <div className="rag-kpi-label">Citation hit-rate</div>
        <div className="rag-kpi-value">{s.hitRate}</div>
      </div>
      <div className="rag-kpi">
        <div className="rag-kpi-label">Zero-result rate</div>
        <div className="rag-kpi-value">{s.zeroRate}</div>
      </div>
    </div>
  )
}
