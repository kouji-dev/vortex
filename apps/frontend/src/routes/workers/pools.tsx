/**
 * Workers → Pools (list + CRUD + template editor).
 *
 * Pools own: sandbox template, repo allow-list, budget, approval policy,
 * default model. The drawer lets admins edit the template + budget inline.
 */
import { createFileRoute, Link } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import * as api from '~/lib/workers-api'
import { formatCents } from '~/lib/workers-logic'
import type { WorkerPool } from '~/lib/workers-types'

export const Route = createFileRoute('/workers/pools')({
  component: PoolsPage,
})

const TEMPLATES = ['python', 'node', 'go', 'rust', 'polyglot'] as const
const SANDBOX_PROVIDERS = ['fake', 'docker', 'kubernetes', 'e2b', 'daytona'] as const

function PoolsPage() {
  const qc = useQueryClient()
  const poolsQ = useQuery({ queryKey: ['workers', 'pools'], queryFn: api.listPools })
  const [showCreate, setShowCreate] = React.useState(false)

  const delMut = useMutation({
    mutationFn: (id: string) => api.deletePool(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['workers', 'pools'] }),
  })

  return (
    <div data-testid="workers-pools">
      <div style={{ display: 'flex', marginBottom: 12, alignItems: 'center' }}>
        <h2 style={{ margin: 0, fontSize: 14 }}>Worker pools</h2>
        <button
          className="btn btn-sm btn-primary"
          style={{ marginLeft: 'auto' }}
          onClick={() => setShowCreate(true)}
          data-testid="wk-pool-create-open"
        >
          + New pool
        </button>
      </div>
      <div className="wk-pane">
        <div className="wk-pane-head">
          <span>{poolsQ.isPending ? 'Loading…' : `${poolsQ.data?.length ?? 0} pools`}</span>
        </div>
        <table className="tbl" style={{ width: '100%', fontSize: 11 }}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Template</th>
              <th>Sandbox</th>
              <th>Repos</th>
              <th>Default model</th>
              <th>Budget</th>
              <th>Enabled</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(poolsQ.data ?? []).map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td>{p.template}</td>
                <td>{p.sandbox_provider}</td>
                <td style={{ fontFamily: 'var(--font-mono)' }}>
                  {p.repo_allow_list.length === 0
                    ? '—'
                    : p.repo_allow_list.slice(0, 2).join(', ') +
                      (p.repo_allow_list.length > 2 ? ` +${p.repo_allow_list.length - 2}` : '')}
                </td>
                <td>{p.default_model}</td>
                <td>{formatCents(p.budget_cents_per_task)}/task</td>
                <td>{p.enabled ? 'yes' : 'no'}</td>
                <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <Link
                    to="/workers/pools/$id/template"
                    params={{ id: p.id }}
                    className="btn btn-sm"
                    style={{ marginRight: 6 }}
                    data-testid={`wk-pool-template-${p.id}`}
                  >
                    Template
                  </Link>
                  <button
                    className="btn btn-sm btn-danger"
                    onClick={() => {
                      if (confirm(`Delete pool ${p.name}?`)) delMut.mutate(p.id)
                    }}
                    data-testid={`wk-pool-delete-${p.id}`}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {(poolsQ.data ?? []).length === 0 && !poolsQ.isPending && (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', padding: 24, color: 'var(--ink-3)' }}>
                  No pools yet. Create one to start submitting tasks.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showCreate && <CreatePoolDrawer onClose={() => setShowCreate(false)} />}
    </div>
  )
}

function CreatePoolDrawer({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [name, setName] = React.useState('')
  const [template, setTemplate] = React.useState<(typeof TEMPLATES)[number]>('python')
  const [sandbox, setSandbox] = React.useState<(typeof SANDBOX_PROVIDERS)[number]>('docker')
  const [repos, setRepos] = React.useState('')
  const [budget, setBudget] = React.useState(10000)
  const [model, setModel] = React.useState('claude-sonnet-4-6')
  const [enabled, setEnabled] = React.useState(true)

  const createMut = useMutation({
    mutationFn: () =>
      api.createPool({
        name,
        template,
        sandbox_provider: sandbox,
        repo_allow_list: repos
          .split(/[\n,]/)
          .map((s) => s.trim())
          .filter(Boolean),
        budget_cents_per_task: budget,
        default_model: model,
        enabled,
        settings: {},
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workers', 'pools'] })
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
        data-testid="wk-pool-create-drawer"
      >
        <h3 style={{ marginTop: 0 }}>Create pool</h3>
        <Field label="Name">
          <input
            className="wk-input"
            style={{ width: '100%' }}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field label="Template">
          <select
            className="wk-input"
            style={{ width: '100%' }}
            value={template}
            onChange={(e) => setTemplate(e.target.value as (typeof TEMPLATES)[number])}
          >
            {TEMPLATES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Sandbox provider">
          <select
            className="wk-input"
            style={{ width: '100%' }}
            value={sandbox}
            onChange={(e) => setSandbox(e.target.value as (typeof SANDBOX_PROVIDERS)[number])}
          >
            {SANDBOX_PROVIDERS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Repos (one per line, or comma-separated)">
          <textarea
            className="wk-input"
            rows={3}
            style={{ width: '100%' }}
            value={repos}
            onChange={(e) => setRepos(e.target.value)}
            placeholder="acme/api, acme/web"
          />
        </Field>
        <Field label="Budget per task (cents)">
          <input
            type="number"
            className="wk-input"
            style={{ width: '100%' }}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
          />
        </Field>
        <Field label="Default model">
          <input
            className="wk-input"
            style={{ width: '100%' }}
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
        </Field>
        <label style={{ fontSize: 12, display: 'flex', gap: 6, alignItems: 'center', marginBottom: 12 }}>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          Enabled
        </label>
        {createMut.error && (
          <div style={{ color: 'var(--red, #c43c3c)', fontSize: 11, marginBottom: 6 }}>
            {(createMut.error as Error).message}
          </div>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className="btn btn-sm" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-sm btn-primary"
            disabled={!name || createMut.isPending}
            onClick={() => createMut.mutate()}
            data-testid="wk-pool-create-submit"
          >
            {createMut.isPending ? 'Creating…' : 'Create'}
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

export type { WorkerPool }
