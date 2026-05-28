/**
 * Workers → Analytics. Success rate, cost, mean wall-clock, per-template + per-repo
 * breakdowns. Computes purely client-side from the recent task list.
 */
import { createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import * as React from 'react'
import * as api from '~/lib/workers-api'
import { tasksStats, formatCents } from '~/lib/workers-logic'
import type { WorkerTask } from '~/lib/workers-types'

export const Route = createFileRoute('/workers/analytics')({
  component: AnalyticsPage,
})

function AnalyticsPage() {
  const tasksQ = useQuery({
    queryKey: ['workers', 'tasks', { limit: 500 }],
    queryFn: () => api.listTasks({ limit: 500 }),
    refetchInterval: 15000,
  })
  const tasks = tasksQ.data ?? []
  const stats = React.useMemo(() => tasksStats(tasks), [tasks])
  const byRepo = React.useMemo(() => groupBy(tasks, (t) => t.repo ?? '(none)'), [tasks])
  const byTrigger = React.useMemo(() => groupBy(tasks, (t) => t.trigger_source), [tasks])
  const meanWallMs = React.useMemo(() => meanWallClock(tasks), [tasks])

  return (
    <div data-testid="workers-analytics">
      <div className="wk-cards">
        <div className="wk-card">
          <div className="wk-card-label">Total tasks</div>
          <div className="wk-card-value">{stats.total}</div>
        </div>
        <div className="wk-card">
          <div className="wk-card-label">Success rate</div>
          <div className="wk-card-value">{Math.round(stats.successRate * 100)}%</div>
        </div>
        <div className="wk-card">
          <div className="wk-card-label">Active</div>
          <div className="wk-card-value">{stats.active}</div>
        </div>
        <div className="wk-card">
          <div className="wk-card-label">Mean wall-clock</div>
          <div className="wk-card-value">{formatDuration(meanWallMs)}</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <BreakdownPane title="By repo" rows={byRepo} />
        <BreakdownPane title="By trigger" rows={byTrigger} />
      </div>

      <div className="wk-pane" style={{ marginTop: 12 }}>
        <div className="wk-pane-head">
          <span>Recent runs (last {tasks.length})</span>
        </div>
        <table className="tbl" style={{ width: '100%', fontSize: 11 }}>
          <thead>
            <tr>
              <th>Repo</th>
              <th>Status</th>
              <th>Created</th>
              <th>Completed</th>
            </tr>
          </thead>
          <tbody>
            {tasks.slice(0, 20).map((t) => (
              <tr key={t.id}>
                <td style={{ fontFamily: 'var(--font-mono)' }}>{t.repo ?? '—'}</td>
                <td>{t.status}</td>
                <td>{t.created_at.slice(0, 19).replace('T', ' ')}</td>
                <td>{t.completed_at ? t.completed_at.slice(0, 19).replace('T', ' ') : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function BreakdownPane({
  title,
  rows,
}: {
  title: string
  rows: { key: string; total: number; completed: number; failed: number }[]
}) {
  return (
    <div className="wk-pane">
      <div className="wk-pane-head">
        <span>{title}</span>
      </div>
      <table className="tbl" style={{ width: '100%', fontSize: 11 }}>
        <thead>
          <tr>
            <th>Key</th>
            <th style={{ textAlign: 'right' }}>Total</th>
            <th style={{ textAlign: 'right' }}>Completed</th>
            <th style={{ textAlign: 'right' }}>Failed</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td>{r.key}</td>
              <td style={{ textAlign: 'right' }}>{r.total}</td>
              <td style={{ textAlign: 'right' }}>{r.completed}</td>
              <td style={{ textAlign: 'right' }}>{r.failed}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={4} style={{ textAlign: 'center', padding: 16, color: 'var(--ink-3)' }}>
                no data
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function groupBy(tasks: WorkerTask[], key: (t: WorkerTask) => string) {
  const map = new Map<string, { total: number; completed: number; failed: number }>()
  for (const t of tasks) {
    const k = key(t)
    const row = map.get(k) ?? { total: 0, completed: 0, failed: 0 }
    row.total++
    if (t.status === 'completed') row.completed++
    if (t.status === 'failed') row.failed++
    map.set(k, row)
  }
  return [...map.entries()]
    .map(([k, v]) => ({ key: k, ...v }))
    .sort((a, b) => b.total - a.total)
}

function meanWallClock(tasks: WorkerTask[]): number {
  const durations = tasks
    .filter((t) => t.completed_at)
    .map((t) => new Date(t.completed_at as string).getTime() - new Date(t.created_at).getTime())
    .filter((d) => Number.isFinite(d) && d > 0)
  if (durations.length === 0) return 0
  return durations.reduce((a, b) => a + b, 0) / durations.length
}

function formatDuration(ms: number): string {
  if (!ms) return '—'
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const rs = s % 60
  if (m < 60) return `${m}m ${rs}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

// stub re-export so the formatCents import isn't unused if cost data lands later
void formatCents
