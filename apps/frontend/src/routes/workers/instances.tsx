/**
 * Workers → Workers (instances) list.
 *
 * Lists first-class spawned workers with their lifecycle state. "Spawn worker"
 * drawer collects model + mode (interactive | autonomous) + GitLab connector
 * (+ runtime + skills) and POSTs to /v1/workers/instances.
 */
import { createFileRoute, Link } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import * as api from '~/lib/workers-api'
import { formatTs, workerStateBadgeClass } from '~/lib/workers-logic'
import type { WorkerMode, WorkerRuntime, WorkerState } from '~/lib/workers-types'

export const Route = createFileRoute('/workers/instances')({
  component: InstancesPage,
})

const STATE_OPTIONS: { value: WorkerState | ''; label: string }[] = [
  { value: '', label: 'Any' },
  { value: 'idle', label: 'Idle' },
  { value: 'provisioning', label: 'Provisioning' },
  { value: 'running', label: 'Running' },
  { value: 'error', label: 'Error' },
  { value: 'stopped', label: 'Stopped' },
]

function InstancesPage() {
  const [stateFilter, setStateFilter] = React.useState<WorkerState | ''>('')
  const [showSpawn, setShowSpawn] = React.useState(false)
  const qc = useQueryClient()

  const workersQ = useQuery({
    queryKey: ['workers', 'instances', { state: stateFilter }],
    queryFn: () => api.listWorkers({ state: stateFilter || null }),
    refetchInterval: 5000,
  })

  const stopMut = useMutation({
    mutationFn: (id: string) => api.stopWorker(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['workers', 'instances'] }),
  })

  return (
    <div data-testid="workers-instances">
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center' }}>
        <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>State</label>
        <select
          className="wk-input"
          value={stateFilter}
          onChange={(e) => setStateFilter(e.target.value as WorkerState | '')}
          data-testid="wk-instance-state-filter"
        >
          {STATE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <button
          className="btn btn-sm btn-primary"
          onClick={() => setShowSpawn(true)}
          data-testid="wk-instance-spawn-open"
          style={{ marginLeft: 'auto' }}
        >
          + Spawn worker
        </button>
      </div>

      <div className="wk-pane">
        <div className="wk-pane-head">
          <span>
            {workersQ.isPending ? 'Loading…' : `${workersQ.data?.length ?? 0} workers`}
          </span>
          <button
            className="btn btn-sm"
            onClick={() => workersQ.refetch()}
            data-testid="wk-instances-refresh"
          >
            Refresh
          </button>
        </div>
        <div style={{ overflow: 'auto' }}>
          <table className="tbl" style={{ width: '100%', fontSize: 11 }}>
            <thead>
              <tr>
                <th>Created</th>
                <th>Name</th>
                <th>Mode</th>
                <th>Model</th>
                <th>Runtime</th>
                <th>Repo</th>
                <th>State</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(workersQ.data ?? []).map((w) => (
                <tr key={w.id}>
                  <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-3)' }}>
                    {formatTs(w.created_at)}
                  </td>
                  <td>{w.name}</td>
                  <td style={{ fontSize: 10, color: 'var(--ink-3)' }}>{w.mode}</td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>{w.model}</td>
                  <td style={{ fontSize: 10 }}>{w.runtime}</td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                    {w.repo_url ?? '—'}
                  </td>
                  <td>
                    <span
                      className={workerStateBadgeClass(w.state)}
                      data-testid={`wk-instance-state-${w.id}`}
                    >
                      {w.state}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <Link
                      to="/workers/instances/$workerId"
                      params={{ workerId: w.id }}
                      className="btn btn-sm"
                      data-testid={`wk-instance-open-${w.id}`}
                    >
                      Open
                    </Link>
                    {w.state !== 'stopped' && (
                      <button
                        className="btn btn-sm btn-danger"
                        style={{ marginLeft: 4 }}
                        disabled={stopMut.isPending}
                        onClick={() => stopMut.mutate(w.id)}
                        data-testid={`wk-instance-stop-${w.id}`}
                      >
                        Stop
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {(workersQ.data ?? []).length === 0 && !workersQ.isPending && (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: 24, color: 'var(--ink-3)' }}>
                    No workers yet. Spawn one to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showSpawn && <SpawnDrawer onClose={() => setShowSpawn(false)} />}
    </div>
  )
}

const MODE_OPTIONS: { value: WorkerMode; label: string }[] = [
  { value: 'interactive', label: 'Interactive (you drive it)' },
  { value: 'autonomous', label: 'Autonomous (works on its own)' },
]

const RUNTIME_OPTIONS: { value: WorkerRuntime; label: string }[] = [
  { value: 'claude', label: 'Claude Agent SDK' },
  { value: 'codex', label: 'Codex CLI' },
]

function SpawnDrawer({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [name, setName] = React.useState('')
  const [model, setModel] = React.useState('claude-sonnet-4-6')
  const [mode, setMode] = React.useState<WorkerMode>('interactive')
  const [runtime, setRuntime] = React.useState<WorkerRuntime>('claude')
  const [gitlabProject, setGitlabProject] = React.useState('')
  const [repoUrl, setRepoUrl] = React.useState('')
  const [branch, setBranch] = React.useState('main')

  const spawn = useMutation({
    mutationFn: () =>
      api.spawnWorker({
        name,
        model,
        mode,
        runtime,
        repo_url: repoUrl || null,
        // GitLab is the v1 priority connector.
        connector: { kind: 'gitlab', project: gitlabProject, branch },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workers', 'instances'] })
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
        data-testid="wk-instance-spawn-drawer"
      >
        <h3 style={{ marginTop: 0, marginBottom: 12 }}>Spawn a worker</h3>

        <Field label="Name">
          <input
            className="wk-input"
            style={{ width: '100%' }}
            value={name}
            onChange={(e) => setName(e.target.value)}
            data-testid="wk-instance-spawn-name"
          />
        </Field>

        <Field label="Model">
          <input
            className="wk-input"
            style={{ width: '100%' }}
            value={model}
            onChange={(e) => setModel(e.target.value)}
            data-testid="wk-instance-spawn-model"
          />
        </Field>

        <Field label="Mode">
          <select
            className="wk-input"
            style={{ width: '100%' }}
            value={mode}
            onChange={(e) => setMode(e.target.value as WorkerMode)}
            data-testid="wk-instance-spawn-mode"
          >
            {MODE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Runtime">
          <select
            className="wk-input"
            style={{ width: '100%' }}
            value={runtime}
            onChange={(e) => setRuntime(e.target.value as WorkerRuntime)}
            data-testid="wk-instance-spawn-runtime"
          >
            {RUNTIME_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="GitLab project (group/repo)">
          <input
            className="wk-input"
            style={{ width: '100%' }}
            value={gitlabProject}
            onChange={(e) => setGitlabProject(e.target.value)}
            placeholder="acme/api"
            data-testid="wk-instance-spawn-gitlab"
          />
        </Field>

        <Field label="Repo URL (clone)">
          <input
            className="wk-input"
            style={{ width: '100%' }}
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="https://gitlab.com/acme/api.git"
            data-testid="wk-instance-spawn-repo-url"
          />
        </Field>

        <Field label="Branch">
          <input
            className="wk-input"
            style={{ width: '100%' }}
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
          />
        </Field>

        {spawn.error && (
          <div style={{ color: 'var(--red, #c43c3c)', fontSize: 11, marginBottom: 8 }}>
            {(spawn.error as Error).message}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
          <button className="btn btn-sm" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-sm btn-primary"
            disabled={!name || !model || spawn.isPending}
            onClick={() => spawn.mutate()}
            data-testid="wk-instance-spawn-submit"
          >
            {spawn.isPending ? 'Spawning…' : 'Spawn'}
          </button>
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <label style={{ display: 'block', fontSize: 11, color: 'var(--ink-3)', marginBottom: 4 }}>
        {label}
      </label>
      {children}
    </div>
  )
}
