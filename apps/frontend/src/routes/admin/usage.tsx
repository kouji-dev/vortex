import { createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import * as React from 'react'
import { fetchUsage } from '~/lib/admin-api'
import type {
  UsageBucket,
  UsageDimension,
  UsagePeriod,
  UsageTimeseriesPoint,
} from '~/lib/admin-types'
import {
  buildLinePath,
  formatCost,
  formatTokens,
  scaleBars,
  scaleTimeseries,
} from '~/lib/usage-charts'

export const Route = createFileRoute('/admin/usage')({
  component: UsagePage,
})

const DIMS: { value: UsageDimension; label: string }[] = [
  { value: 'user', label: 'By user' },
  { value: 'team', label: 'By team' },
  { value: 'key', label: 'By API key' },
  { value: 'model', label: 'By model' },
  { value: 'module', label: 'By module' },
]

const PERIODS: { value: UsagePeriod; label: string }[] = [
  { value: 'hour', label: 'Hour' },
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
]

function UsagePage() {
  const [dim, setDim] = React.useState<UsageDimension>('user')
  const [period, setPeriod] = React.useState<UsagePeriod>('day')

  const report = useQuery({
    queryKey: ['admin', 'usage', dim, period],
    queryFn: () => fetchUsage(dim, period),
  })

  return (
    <div className="panel" data-testid="admin-usage">
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Usage</span>
        <div style={{ display: 'flex', gap: 8 }}>
          <select
            value={dim}
            onChange={(e) => setDim(e.target.value as UsageDimension)}
            data-testid="admin-usage-dim"
            style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
          >
            {DIMS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
          </select>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value as UsagePeriod)}
            data-testid="admin-usage-period"
            style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
          >
            {PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </div>
      </div>

      <div className="panel-body" style={{ padding: 16 }}>
        {report.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
        {report.error && <p style={{ fontSize: 12, color: 'var(--red)' }}>{(report.error as Error).message}</p>}

        {report.data && (
          <>
            <div className="kpi-row" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
              <div className="kpi">
                <div className="kpi-label">Total cost</div>
                <div className="kpi-value">{formatCost(report.data.total_cost_cents)}</div>
              </div>
              <div className="kpi">
                <div className="kpi-label">Tokens in</div>
                <div className="kpi-value">{formatTokens(report.data.total_tokens_in)}</div>
              </div>
              <div className="kpi">
                <div className="kpi-label">Tokens out</div>
                <div className="kpi-value">{formatTokens(report.data.total_tokens_out)}</div>
              </div>
            </div>

            <section style={{ marginTop: 20 }}>
              <h3 style={{ fontSize: 12, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
                Cost over time
              </h3>
              <CostLineChart points={report.data.timeseries} />
            </section>

            <section style={{ marginTop: 20 }}>
              <h3 style={{ fontSize: 12, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
                Top {DIMS.find((d) => d.value === dim)?.label.toLowerCase()}
              </h3>
              <BucketBarChart buckets={report.data.buckets} />
            </section>
          </>
        )}
      </div>
    </div>
  )
}

const CHART_WIDTH = 640
const CHART_HEIGHT = 140
const BAR_LABEL_WIDTH = 200
const BAR_MAX_WIDTH = 340

function CostLineChart({ points }: { points: UsageTimeseriesPoint[] }) {
  const scaled = scaleTimeseries(points, (p) => p.cost_cents, CHART_WIDTH, CHART_HEIGHT)
  const path = buildLinePath(scaled)

  if (scaled.length === 0) {
    return <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No data for this period.</p>
  }

  // build area path: line + closure
  const area = `${path} L ${CHART_WIDTH},${CHART_HEIGHT} L 0,${CHART_HEIGHT} Z`

  return (
    <svg
      width={CHART_WIDTH}
      height={CHART_HEIGHT + 20}
      viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT + 20}`}
      style={{ width: '100%', height: 'auto', maxWidth: CHART_WIDTH }}
      data-testid="admin-usage-timeseries"
    >
      <path d={area} fill="var(--accent)" opacity={0.15} />
      <path d={path} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
      {scaled.map((p) => (
        <circle key={p.ts} cx={p.x} cy={p.y} r={2} fill="var(--accent)">
          <title>{`${new Date(p.ts).toLocaleString()} — ${formatCost(p.value)}`}</title>
        </circle>
      ))}
    </svg>
  )
}

function BucketBarChart({ buckets }: { buckets: UsageBucket[] }) {
  const bars = scaleBars(buckets, (b) => b.cost_cents, BAR_MAX_WIDTH)

  if (bars.length === 0) {
    return <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No data.</p>
  }

  return (
    <div data-testid="admin-usage-bars" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {bars.map((bar, i) => {
        const b = buckets[i]
        return (
          <div
            key={bar.label + i}
            style={{
              display: 'grid',
              gridTemplateColumns: `${BAR_LABEL_WIDTH}px 1fr 80px 80px`,
              alignItems: 'center',
              gap: 8,
              fontSize: 12,
            }}
          >
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--ink-2)' }}>
              {bar.label}
            </span>
            <div style={{ height: 16, background: 'var(--bg-2)', borderRadius: 3, overflow: 'hidden', position: 'relative' }}>
              <div
                style={{
                  width: `${bar.pct * 100}%`,
                  height: '100%',
                  background: 'var(--accent)',
                  opacity: 0.6,
                }}
              />
            </div>
            <span className="meta" style={{ textAlign: 'right' }}>{formatTokens(b.tokens_in + b.tokens_out)}</span>
            <span className="meta" style={{ textAlign: 'right', color: 'var(--ink)' }}>{formatCost(bar.value)}</span>
          </div>
        )
      })}
    </div>
  )
}
