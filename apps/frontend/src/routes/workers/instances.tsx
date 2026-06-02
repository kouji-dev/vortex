/**
 * Workers → Workers (instances) list.
 *
 * Lists first-class spawned workers with their lifecycle state. "Spawn worker"
 * drawer collects model + mode (interactive | autonomous) + GitLab connector
 * (+ runtime + skills) and POSTs to /v1/workers/instances.
 */
import { Select } from '~/components/ui/select'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import * as api from '~/lib/workers-api'
import { formatTs, workerStateBadgeClass } from '~/lib/workers-logic'
import type { WorkerMode, WorkerState } from '~/lib/workers-types'
import { useWorkerModelsQuery } from '~/hooks/useWorkerModelsQuery'
import { inferRuntime } from '~/lib/worker-runtime'
import { useGitIntegrationsQuery } from '~/hooks/useGitIntegrationsQuery'

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
        <Select
          className="wk-input"
          value={stateFilter}
          onChange={(e) => setStateFilter(e.target.value as WorkerState | '')}
          data-testid="wk-instance-state-filter"
        size="sm"
        inline
        >
          {STATE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
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

const EFFORT_OPTIONS = ['low', 'medium', 'high', 'max'] as const

function SpawnDrawer({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [name, setName] = React.useState('')
  const [mode, setMode] = React.useState<WorkerMode>('interactive')

  const workerModels = useWorkerModelsQuery()
  const [model, setModel] = React.useState('') // api_model_id
  const [effort, setEffort] = React.useState('medium')

  // Default to the first worker model once loaded.
  React.useEffect(() => {
    if (!model && workerModels.data && workerModels.data.length > 0) {
      setModel(workerModels.data[0].api_model_id)
      setEffort(workerModels.data[0].effort || 'medium')
    }
  }, [workerModels.data, model])

  const runtime = inferRuntime(model) ?? 'claude'

  // Repo picker state
  const gitIntegrations = useGitIntegrationsQuery()
  const enabledRepos = React.useMemo(
    () =>
      (gitIntegrations.data ?? []).flatMap((i) =>
        i.repos.filter((r) => r.enabled).map((r) => ({ ...r, integrationId: i.id })),
      ),
    [gitIntegrations.data],
  )
  const [repoFullName, setRepoFullName] = React.useState('')
  React.useEffect(() => {
    if (!repoFullName && enabledRepos.length > 0) setRepoFullName(enabledRepos[0].full_name)
  }, [enabledRepos, repoFullName])
  const selectedRepo = enabledRepos.find((r) => r.full_name === repoFullName)

  const spawn = useMutation({
    mutationFn: () =>
      api.spawnWorker({
        name,
        model,
        effort,
        mode,
        runtime,
        repo_url: selectedRepo ? `https://github.com/${selectedRepo.full_name}.git` : null,
        connector: selectedRepo
          ? { kind: 'github', project: selectedRepo.full_name, branch: selectedRepo.default_branch }
          : undefined,
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
          <Select
            style={{ width: '100%' }}
            value={model}
            onChange={(e) => setModel(e.target.value)}
            data-testid="wk-instance-spawn-model"
            size="sm"
          >
            {(workerModels.data ?? []).map((m) => (
              <option key={m.id} value={m.api_model_id}>
                {m.display_name}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Effort">
          <Select
            style={{ width: '100%' }}
            value={effort}
            onChange={(e) => setEffort(e.target.value)}
            data-testid="wk-instance-spawn-effort"
            size="sm"
          >
            {EFFORT_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>
                {opt[0].toUpperCase() + opt.slice(1)}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Mode">
          <Select
            className="wk-input"
            style={{ width: '100%' }}
            value={mode}
            onChange={(e) => setMode(e.target.value as WorkerMode)}
            data-testid="wk-instance-spawn-mode"
          size="sm"
          inline
          >
            {MODE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Repository">
          {enabledRepos.length > 0 ? (
            <Select
              style={{ width: '100%' }}
              value={repoFullName}
              onChange={(e) => setRepoFullName(e.target.value)}
              data-testid="wk-instance-spawn-repo"
              size="sm"
            >
              {enabledRepos.map((r) => (
                <option key={r.id} value={r.full_name}>
                  {r.full_name}
                </option>
              ))}
            </Select>
          ) : (
            <div
              data-testid="wk-instance-spawn-no-repo"
              style={{
                border: '1px solid var(--line)',
                padding: 10,
                borderRadius: 6,
                fontSize: 12,
                color: 'var(--ink-3)',
              }}
            >
              No Git provider connected.{' '}
              <Link to="/workers/integrations" data-testid="wk-instance-spawn-connect-link">
                Connect in Settings →
              </Link>
            </div>
          )}
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
            disabled={!name || !model || spawn.isPending || enabledRepos.length === 0}
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
