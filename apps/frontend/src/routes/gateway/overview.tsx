import { createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import type * as React from 'react'
import { searchTraces } from '~/lib/gateway-api'
import {
  computeOverview,
  formatCents,
  formatLatency,
  formatPct,
} from '~/lib/gateway-overview'
import type { TraceRow } from '~/lib/gateway-types'

export const Route = createFileRoute('/gateway/overview')({
  component: OverviewPage,
})

const WINDOW_SECONDS = 3600 // 1h KPI window

function OverviewPage() {
  const since = new Date(Date.now() - WINDOW_SECONDS * 1000).toISOString()
  const traces = useQuery({
    queryKey: ['gateway', 'overview-traces', since],
    queryFn: () => searchTraces({ from: since, limit: 200 }),
  })

  return (
    <div className="panel" data-testid="gw-overview">
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>Overview · last hour</span>
        <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>derived from traces</span>
      </div>
      <div className="panel-body" style={{ padding: 16 }}>
        {traces.isPending && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>
        )}
        {traces.error && (
          <p style={{ fontSize: 12, color: 'var(--red)' }}>
            {(traces.error as Error).message}
          </p>
        )}
        {traces.data && <OverviewBody items={traces.data.items} />}
      </div>
    </div>
  )
}

function OverviewBody({ items }: { items: TraceRow[] }) {
  const k = computeOverview(items, WINDOW_SECONDS)
  return (
    <>
      <div className="gw-kpi-row" data-testid="gw-overview-kpis">
        <div className="gw-kpi">
          <div className="gw-kpi-label">Requests / min</div>
          <div className="gw-kpi-value">{k.requestsPerMin.toFixed(1)}</div>
          <div className="gw-kpi-sub">{k.requests} in last hour</div>
        </div>
        <div className="gw-kpi">
          <div className="gw-kpi-label">p95 latency</div>
          <div className="gw-kpi-value">{formatLatency(k.p95)}</div>
          <div className="gw-kpi-sub">
            p50 {formatLatency(k.p50)} · p99 {formatLatency(k.p99)}
          </div>
        </div>
        <div className="gw-kpi">
          <div className="gw-kpi-label">Error rate</div>
          <div className="gw-kpi-value" style={{ color: k.errorRate > 0.05 ? 'var(--red)' : 'var(--ink)' }}>
            {formatPct(k.errorRate)}
          </div>
          <div className="gw-kpi-sub">{k.errors} errors</div>
        </div>
        <div className="gw-kpi">
          <div className="gw-kpi-label">Top model</div>
          <div className="gw-kpi-value" style={{ fontSize: 14, marginTop: 8 }}>
            {k.topModels[0]?.model ?? '—'}
          </div>
          <div className="gw-kpi-sub">
            {k.topModels[0] ? `${k.topModels[0].count} calls · ${formatCents(k.topModels[0].cost_cents)}` : '—'}
          </div>
        </div>
      </div>

      <section style={{ marginTop: 20 }}>
        <h3 style={{ fontSize: 12, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
          Top models
        </h3>
        <div className="tbl" data-testid="gw-overview-top-models">
          <div className="audit-row" style={headerRowStyle}>
            <span>Model</span><span>Calls</span><span>Cost</span>
          </div>
          {k.topModels.length === 0 && (
            <div className="audit-row" style={dataRowStyle}>
              <span style={{ color: 'var(--ink-3)' }}>No data.</span><span /><span />
            </div>
          )}
          {k.topModels.map((m) => (
            <div key={m.model} className="audit-row" style={dataRowStyle}>
              <span style={{ color: 'var(--ink)' }}>{m.model}</span>
              <span className="meta">{m.count}</span>
              <span className="meta">{formatCents(m.cost_cents)}</span>
            </div>
          ))}
        </div>
      </section>

      <section style={{ marginTop: 20 }}>
        <h3 style={{ fontSize: 12, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
          Top providers
        </h3>
        <div className="tbl" data-testid="gw-overview-top-providers">
          <div className="audit-row" style={headerRowStyle}>
            <span>Provider</span><span>Calls</span><span>Error rate</span>
          </div>
          {k.topProviders.length === 0 && (
            <div className="audit-row" style={dataRowStyle}>
              <span style={{ color: 'var(--ink-3)' }}>No data.</span><span /><span />
            </div>
          )}
          {k.topProviders.map((p) => (
            <div key={p.provider} className="audit-row" style={dataRowStyle}>
              <span style={{ color: 'var(--ink)' }}>{p.provider}</span>
              <span className="meta">{p.count}</span>
              <span className="meta" style={{ color: p.errorRate > 0.05 ? 'var(--red)' : 'var(--ink-2)' }}>
                {formatPct(p.errorRate)}
              </span>
            </div>
          ))}
        </div>
      </section>
    </>
  )
}

const headerRowStyle: React.CSSProperties = {
  gridTemplateColumns: '1fr 100px 120px',
  background: 'var(--bg-2)',
  borderBottom: '1px solid var(--line)',
  fontWeight: 600,
  fontSize: 10,
  color: 'var(--ink-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
}
const dataRowStyle: React.CSSProperties = {
  gridTemplateColumns: '1fr 100px 120px',
}
