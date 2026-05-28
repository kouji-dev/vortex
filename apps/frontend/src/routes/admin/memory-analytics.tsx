/**
 * /admin/memory-analytics — org-wide insights for the Memory module.
 *
 * Shows memory count over time, top recalled memories, recall hit-rate, and
 * extraction outcomes — sourced from `/v1/memories/analytics` (rollup
 * computed by `memory.analytics.rollup_all`).
 */
import { createFileRoute } from '@tanstack/react-router'

import { useMemoryAnalyticsQuery } from '~/hooks/useMemoriesV1Query'

export const Route = createFileRoute('/admin/memory-analytics')({
  component: MemoryAnalyticsPage,
})

function MemoryAnalyticsPage() {
  const q = useMemoryAnalyticsQuery()

  if (q.isPending) {
    return (
      <div className="panel" style={{ padding: 20, fontSize: 12, color: 'var(--ink-3)' }} data-testid="admin-memory-analytics">
        Loading analytics…
      </div>
    )
  }
  if (q.isError) {
    return (
      <div className="panel" style={{ padding: 20, fontSize: 12, color: 'var(--err)' }} data-testid="admin-memory-analytics">
        {(q.error as Error).message}
      </div>
    )
  }
  const data = q.data ?? {}
  const count = data.count_over_time ?? []
  const top = data.top_recalled ?? []
  const hit = data.recall_hit_rate ?? 0
  const out = data.extraction_outcomes

  return (
    <div data-testid="admin-memory-analytics" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="panel">
        <div className="panel-head">Memory count over time</div>
        <div style={{ padding: 12 }}>
          {count.length === 0 ? (
            <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No data yet.</p>
          ) : (
            <Sparkline points={count.map((p) => p.count)} />
          )}
          <div className="meta" style={{ marginTop: 6 }}>
            {count.length} buckets · latest {count[count.length - 1]?.count ?? 0}
          </div>
        </div>
      </div>

      <div className="gw-kpi-row" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        <Kpi label="Recall hit rate" value={`${(hit * 100).toFixed(1)}%`} sub="recalled & cited / recalled" />
        <Kpi label="Created" value={String(out?.created ?? 0)} sub="last 7d" />
        <Kpi label="Updated" value={String(out?.updated ?? 0)} sub="dedupe merge" />
        <Kpi label="Skipped (sensitive + dedup + paused)" value={String((out?.skipped_sensitive ?? 0) + (out?.skipped_dedup ?? 0) + (out?.skipped_paused ?? 0))} sub="last 7d" />
      </div>

      <div className="panel">
        <div className="panel-head">Top recalled memories</div>
        <div style={{ padding: 12 }}>
          {top.length === 0 ? (
            <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No recalls recorded yet.</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase' }}>
                  <th style={{ textAlign: 'left', padding: '4px 8px' }}>Memory</th>
                  <th style={{ textAlign: 'right', padding: '4px 8px', width: 80 }}>Uses</th>
                </tr>
              </thead>
              <tbody>
                {top.map((row) => (
                  <tr key={row.memory_id} data-testid="mem-top-row">
                    <td style={{ padding: '4px 8px', borderTop: '1px solid var(--line)' }}>{row.text}</td>
                    <td style={{ padding: '4px 8px', textAlign: 'right', borderTop: '1px solid var(--line)', fontFamily: 'var(--font-mono)' }}>{row.uses}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

function Kpi({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div
      style={{
        background: 'var(--bg)',
        border: '1px solid var(--line)',
        borderRadius: 6,
        padding: '12px 14px',
      }}
      data-testid="mem-kpi"
    >
      <div style={{ fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 600, color: 'var(--ink)', marginTop: 4 }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 2 }}>{sub}</div>
    </div>
  )
}

function Sparkline({ points }: { points: number[] }) {
  if (points.length === 0) return null
  const w = 600
  const h = 80
  const max = Math.max(...points, 1)
  const step = points.length > 1 ? w / (points.length - 1) : 0
  const d = points
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(h - (v / max) * h).toFixed(1)}`)
    .join(' ')
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: 'block' }}>
      <path d={d} fill="none" stroke="var(--accent, #5b8def)" strokeWidth={2} />
    </svg>
  )
}
