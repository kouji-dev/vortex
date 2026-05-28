/**
 * Workers → Tasks (active + history list).
 *
 * Lists tasks with filters (status / pool) and a submit-task drawer that
 * POSTs to /v1/workers/tasks.
 */
import { createFileRoute, Link } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import * as api from '~/lib/workers-api'
import { formatTs, statusBadgeClass, tasksStats } from '~/lib/workers-logic'
import type { TaskStatus, WorkerPool, WorkerTask } from '~/lib/workers-types'

export const Route = createFileRoute('/workers/tasks')({
  component: TasksPage,
})

const STATUS_OPTIONS: { value: TaskStatus | ''; label: string }[] = [
  { value: '', label: 'Any' },
  { value: 'queued', label: 'Queued' },
  { value: 'planning', label: 'Planning' },
  { value: 'executing', label: 'Executing' },
  { value: 'awaiting_plan_approval', label: 'Awaiting plan' },
  { value: 'awaiting_pr_approval', label: 'Awaiting PR' },
  { value: 'paused', label: 'Paused' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
  { value: 'cancelled', label: 'Cancelled' },
]

function TasksPage() {
  const [statusFilter, setStatusFilter] = React.useState<TaskStatus | ''>('')
  const [poolFilter, setPoolFilter] = React.useState<string>('')
  const [showSubmit, setShowSubmit] = React.useState(false)

  const tasksQ = useQuery({
    queryKey: ['workers', 'tasks', { status: statusFilter, pool: poolFilter }],
    queryFn: () =>
      api.listTasks({
        status: statusFilter || null,
        pool_id: poolFilter || null,
      }),
    refetchInterval: 5000,
  })

  const poolsQ = useQuery({
    queryKey: ['workers', 'pools'],
    queryFn: api.listPools,
  })

  const stats = React.useMemo(
    () => tasksStats(tasksQ.data ?? []),
    [tasksQ.data],
  )

  return (
    <div data-testid="workers-tasks">
      <StatsCards stats={stats} />

      <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center' }}>
        <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>Status</label>
        <select
          className="wk-input"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as TaskStatus | '')}
          data-testid="wk-task-status-filter"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>Pool</label>
        <select
          className="wk-input"
          value={poolFilter}
          onChange={(e) => setPoolFilter(e.target.value)}
          data-testid="wk-task-pool-filter"
        >
          <option value="">Any</option>
          {(poolsQ.data ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button
          className="btn btn-sm"
          onClick={() => setShowSubmit(true)}
          data-testid="wk-task-submit-open"
          style={{ marginLeft: 'auto' }}
        >
          + Submit task
        </button>
      </div>

      <div className="wk-pane">
        <div className="wk-pane-head">
          <span>{tasksQ.isPending ? 'Loading…' : `${tasksQ.data?.length ?? 0} tasks`}</span>
          <button
            className="btn btn-sm"
            onClick={() => tasksQ.refetch()}
            data-testid="wk-tasks-refresh"
          >
            Refresh
          </button>
        </div>
        <div style={{ overflow: 'auto' }}>
          <table className="tbl" style={{ width: '100%', fontSize: 11 }}>
            <thead>
              <tr>
                <th>Created</th>
                <th>Title</th>
                <th>Repo</th>
                <th>Trigger</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(tasksQ.data ?? []).map((t) => (
                <tr key={t.id}>
                  <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-3)' }}>
                    {formatTs(t.created_at)}
                  </td>
                  <td>{t.title}</td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{t.repo ?? '—'}</td>
                  <td style={{ fontSize: 10, color: 'var(--ink-3)' }}>{t.trigger_source}</td>
                  <td>
                    <span className={statusBadgeClass(t.status)} data-testid={`wk-task-status-${t.id}`}>
                      {t.status}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <Link
                      to="/workers/tasks/$taskId"
                      params={{ taskId: t.id }}
                      className="btn btn-sm"
                      data-testid={`wk-task-open-${t.id}`}
                    >
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
              {(tasksQ.data ?? []).length === 0 && !tasksQ.isPending && (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: 24, color: 'var(--ink-3)' }}>
                    No tasks yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showSubmit && (
        <SubmitDrawer
          pools={poolsQ.data ?? []}
          onClose={() => setShowSubmit(false)}
        />
      )}
    </div>
  )
}

function StatsCards({
  stats,
}: {
  stats: ReturnType<typeof tasksStats>
}) {
  return (
    <div className="wk-cards">
      <div className="wk-card">
        <div className="wk-card-label">Active</div>
        <div className="wk-card-value">{stats.active}</div>
      </div>
      <div className="wk-card">
        <div className="wk-card-label">Completed</div>
        <div className="wk-card-value">{stats.completed}</div>
      </div>
      <div className="wk-card">
        <div className="wk-card-label">Failed</div>
        <div className="wk-card-value">{stats.failed}</div>
      </div>
      <div className="wk-card">
        <div className="wk-card-label">Success rate</div>
        <div className="wk-card-value">{Math.round(stats.successRate * 100)}%</div>
      </div>
    </div>
  )
}

function SubmitDrawer({
  pools,
  onClose,
}: {
  pools: WorkerPool[]
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [title, setTitle] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [repo, setRepo] = React.useState('')
  const [baseBranch, setBaseBranch] = React.useState('main')
  const [poolId, setPoolId] = React.useState<string>(pools[0]?.id ?? '')

  const submit = useMutation({
    mutationFn: () =>
      api.submitTask({
        title,
        description,
        repo,
        base_branch: baseBranch,
        pool_id: poolId || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workers', 'tasks'] })
      onClose()
    },
  })

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        className="panel"
        style={{ width: 480, padding: 20 }}
        onClick={(e) => e.stopPropagation()}
        data-testid="wk-task-submit-drawer"
      >
        <h3 style={{ marginTop: 0, marginBottom: 12 }}>Submit a worker task</h3>
        <label style={{ display: 'block', fontSize: 11, color: 'var(--ink-3)', marginBottom: 4 }}>
          Title
        </label>
        <input
          className="wk-input"
          style={{ width: '100%', marginBottom: 10 }}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          data-testid="wk-task-submit-title"
        />
        <label style={{ display: 'block', fontSize: 11, color: 'var(--ink-3)', marginBottom: 4 }}>
          Repo (owner/name)
        </label>
        <input
          className="wk-input"
          style={{ width: '100%', marginBottom: 10 }}
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          placeholder="acme/api"
          data-testid="wk-task-submit-repo"
        />
        <label style={{ display: 'block', fontSize: 11, color: 'var(--ink-3)', marginBottom: 4 }}>
          Base branch
        </label>
        <input
          className="wk-input"
          style={{ width: '100%', marginBottom: 10 }}
          value={baseBranch}
          onChange={(e) => setBaseBranch(e.target.value)}
        />
        <label style={{ display: 'block', fontSize: 11, color: 'var(--ink-3)', marginBottom: 4 }}>
          Pool
        </label>
        <select
          className="wk-input"
          style={{ width: '100%', marginBottom: 10 }}
          value={poolId}
          onChange={(e) => setPoolId(e.target.value)}
        >
          <option value="">(auto-pick)</option>
          {pools.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <label style={{ display: 'block', fontSize: 11, color: 'var(--ink-3)', marginBottom: 4 }}>
          Description
        </label>
        <textarea
          className="wk-input"
          rows={5}
          style={{ width: '100%', marginBottom: 12, resize: 'vertical' }}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        {submit.error && (
          <div style={{ color: 'var(--red, #c43c3c)', fontSize: 11, marginBottom: 8 }}>
            {(submit.error as Error).message}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button className="btn btn-sm" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-sm btn-primary"
            disabled={!title || !repo || submit.isPending}
            onClick={() => submit.mutate()}
            data-testid="wk-task-submit-submit"
          >
            {submit.isPending ? 'Submitting…' : 'Submit'}
          </button>
        </div>
      </div>
    </div>
  )
}

export type { WorkerTask }
