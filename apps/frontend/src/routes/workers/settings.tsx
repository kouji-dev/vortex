/**
 * Workers → Settings.
 *
 * Tabs: Budgets · Egress · Secrets · Approval policies. The fields collect
 * the same per-pool configuration the backend stores in
 * ``worker_pools.settings_json``, ``worker_egress_rules``,
 * ``worker_secrets_grants``.
 */
import { createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import * as React from 'react'
import * as api from '~/lib/workers-api'
import { formatCents } from '~/lib/workers-logic'

export const Route = createFileRoute('/workers/settings')({
  component: SettingsPage,
})

type Tab = 'budgets' | 'egress' | 'secrets' | 'approvals'

function SettingsPage() {
  const [tab, setTab] = React.useState<Tab>('budgets')
  const poolsQ = useQuery({ queryKey: ['workers', 'pools'], queryFn: api.listPools })
  const pools = poolsQ.data ?? []

  return (
    <div data-testid="workers-settings">
      <div style={{ display: 'flex', gap: 4, marginBottom: 12 }}>
        {(['budgets', 'egress', 'secrets', 'approvals'] as Tab[]).map((t) => (
          <button
            key={t}
            className={`btn btn-sm${tab === t ? ' btn-primary' : ''}`}
            onClick={() => setTab(t)}
            data-testid={`wk-settings-tab-${t}`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'budgets' && (
        <div className="wk-pane">
          <div className="wk-pane-head">
            <span>Per-pool budgets</span>
          </div>
          <table className="tbl" style={{ width: '100%', fontSize: 11 }}>
            <thead>
              <tr>
                <th>Pool</th>
                <th>Budget per task</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {pools.map((p) => (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  <td>{formatCents(p.budget_cents_per_task)}</td>
                  <td>{p.enabled ? 'enabled' : 'disabled'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'egress' && (
        <div className="wk-pane">
          <div className="wk-pane-head">
            <span>Egress allow-list (default-deny)</span>
          </div>
          <div className="wk-pane-body">
            <p style={{ marginTop: 0, color: 'var(--ink-3)' }}>
              Common presets: <code>pypi</code>, <code>npm</code>, <code>crates</code>,{' '}
              <code>maven</code>, <code>go-modules</code>.
            </p>
            {pools.map((p) => (
              <div
                key={p.id}
                style={{ borderTop: '1px dashed var(--line)', padding: '6px 0' }}
                data-testid={`wk-egress-pool-${p.id}`}
              >
                <strong>{p.name}</strong>{' '}
                <span style={{ color: 'var(--ink-3)', fontSize: 11 }}>
                  hosts:{' '}
                  {((p.settings as { egress_allow_list?: string[] })?.egress_allow_list ?? []).join(
                    ', ',
                  ) || '(none configured)'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'secrets' && (
        <div className="wk-pane">
          <div className="wk-pane-head">
            <span>Secrets bindings (per-pool, per-repo)</span>
          </div>
          <div className="wk-pane-body">
            <p style={{ color: 'var(--ink-3)', marginTop: 0 }}>
              Secrets are injected as env vars in the sandbox and redacted from all logs.
              Manage bindings via <code>POST /v1/workers/secrets</code>.
            </p>
            {pools.map((p) => (
              <div key={p.id} style={{ borderTop: '1px dashed var(--line)', padding: '6px 0' }}>
                <strong>{p.name}</strong>{' '}
                <span style={{ color: 'var(--ink-3)', fontSize: 11 }}>
                  bound secrets:{' '}
                  {((p.settings as { secret_refs?: string[] })?.secret_refs ?? []).join(', ') ||
                    '(none)'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'approvals' && (
        <div className="wk-pane">
          <div className="wk-pane-head">
            <span>Approval policies</span>
          </div>
          <div className="wk-pane-body">
            <p style={{ marginTop: 0, color: 'var(--ink-3)' }}>
              Policy kinds: <code>always</code>, <code>never</code>,{' '}
              <code>on_cost_above</code>, <code>on_files_matching</code>,{' '}
              <code>on_first_run_for_repo</code>. M-of-N supported via{' '}
              <code>required_approvers</code>.
            </p>
            {pools.map((p) => {
              const policy = (p.settings as { approval_policy?: Record<string, unknown> })
                ?.approval_policy
              return (
                <div
                  key={p.id}
                  style={{ borderTop: '1px dashed var(--line)', padding: '6px 0' }}
                  data-testid={`wk-approvals-pool-${p.id}`}
                >
                  <strong>{p.name}</strong>{' '}
                  <span style={{ color: 'var(--ink-3)', fontSize: 11 }}>
                    {policy ? JSON.stringify(policy) : '(default — never)'}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
