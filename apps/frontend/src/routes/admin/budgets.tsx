import { Select } from '~/components/ui/select'
import { createFileRoute } from '@tanstack/react-router'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import {
  createBudget,
  createQuota,
  deleteBudget,
  deleteQuota,
  fetchBudgetStatus,
  fetchBudgets,
  fetchQuotas,
} from '~/lib/admin-api'
import type {
  Budget,
  BudgetCreateRequest,
  Quota,
  QuotaCreateRequest,
  ScopeKind,
} from '~/lib/admin-types'
import { formatUsd, statusToBar, validateBudgetName, validateLimitUsd } from '~/lib/budgets-format'

export const Route = createFileRoute('/admin/budgets')({
  component: BudgetsPage,
})

function BudgetsPage() {
  const qc = useQueryClient()
  const budgets = useQuery({ queryKey: ['admin', 'budgets'], queryFn: fetchBudgets })
  const quotas = useQuery({ queryKey: ['admin', 'quotas'], queryFn: fetchQuotas })

  const [creatingBudget, setCreatingBudget] = React.useState(false)
  const [creatingQuota, setCreatingQuota] = React.useState(false)

  const newBudget = useMutation({
    mutationFn: createBudget,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'budgets'] })
      setCreatingBudget(false)
    },
  })
  const rmBudget = useMutation({
    mutationFn: deleteBudget,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'budgets'] }),
  })

  const newQuota = useMutation({
    mutationFn: createQuota,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'quotas'] })
      setCreatingQuota(false)
    },
  })
  const rmQuota = useMutation({
    mutationFn: deleteQuota,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'quotas'] }),
  })

  return (
    <div className="panel" data-testid="admin-budgets">
      <div className="panel-head">
        <span>Budgets &amp; Quotas</span>
      </div>

      <div className="panel-body" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 24 }}>
        <Section
          title="Budgets"
          actionLabel="New budget"
          onAction={() => setCreatingBudget(true)}
          testId="admin-budgets-section"
        >
          {budgets.isPending && <Loading />}
          {budgets.error && <ErrorMsg msg={(budgets.error as Error).message} />}
          {budgets.data && budgets.data.length === 0 && (
            <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No budgets yet.</p>
          )}
          {budgets.data && budgets.data.length > 0 && (
            <BudgetsTable
              budgets={budgets.data}
              onDelete={(id) => {
                if (confirm('Delete this budget? Spend tracking stops.')) rmBudget.mutate(id)
              }}
            />
          )}
        </Section>

        <Section
          title="Quotas"
          actionLabel="New quota"
          onAction={() => setCreatingQuota(true)}
          testId="admin-quotas-section"
        >
          {quotas.isPending && <Loading />}
          {quotas.error && <ErrorMsg msg={(quotas.error as Error).message} />}
          {quotas.data && quotas.data.length === 0 && (
            <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No quotas yet.</p>
          )}
          {quotas.data && quotas.data.length > 0 && (
            <QuotasTable
              quotas={quotas.data}
              onDelete={(id) => {
                if (confirm('Delete this quota?')) rmQuota.mutate(id)
              }}
            />
          )}
        </Section>

        {creatingBudget && (
          <BudgetDialog
            saving={newBudget.isPending}
            error={newBudget.error?.message ?? null}
            onCancel={() => setCreatingBudget(false)}
            onSubmit={(r) => newBudget.mutate(r)}
          />
        )}

        {creatingQuota && (
          <QuotaDialog
            saving={newQuota.isPending}
            error={newQuota.error?.message ?? null}
            onCancel={() => setCreatingQuota(false)}
            onSubmit={(r) => newQuota.mutate(r)}
          />
        )}
      </div>
    </div>
  )
}

function Section({
  title,
  actionLabel,
  onAction,
  children,
  testId,
}: {
  title: string
  actionLabel: string
  onAction: () => void
  children: React.ReactNode
  testId: string
}) {
  return (
    <section data-testid={testId}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <h3 style={{ fontSize: 12, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {title}
        </h3>
        <button className="btn btn-sm btn-primary" onClick={onAction} data-testid={`${testId}-new`}>
          {actionLabel}
        </button>
      </div>
      {children}
    </section>
  )
}

function Loading() {
  return <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>
}
function ErrorMsg({ msg }: { msg: string }) {
  return <p style={{ fontSize: 12, color: 'var(--red)' }}>{msg}</p>
}

function BudgetsTable({ budgets, onDelete }: { budgets: Budget[]; onDelete: (id: number) => void }) {
  // Fan out a status query per row. Stable order; statuses keyed by id.
  const statuses = useQueries({
    queries: budgets.map((b) => ({
      queryKey: ['admin', 'budget', 'status', b.id],
      queryFn: () => fetchBudgetStatus(b.id),
    })),
  })

  return (
    <div className="tbl" data-testid="admin-budgets-table">
      <div
        className="audit-row"
        style={{
          gridTemplateColumns: '1fr 110px 110px 1.5fr 100px',
          background: 'var(--bg-2)',
          borderBottom: '1px solid var(--line)',
          fontWeight: 600,
          fontSize: 10,
          color: 'var(--ink-3)',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        <span>Name</span>
        <span>Scope</span>
        <span>Period</span>
        <span>Spend</span>
        <span />
      </div>
      {budgets.map((b, i) => {
        const s = statuses[i]
        return (
          <div
            key={b.id}
            className="audit-row"
            style={{ gridTemplateColumns: '1fr 110px 110px 1.5fr 100px' }}
            data-testid={`admin-budgets-row-${b.id}`}
          >
            <span style={{ color: 'var(--ink)' }}>{b.name}</span>
            <span className="meta">{b.scope_kind}{b.scope_id ? `:${b.scope_id.slice(0, 8)}` : ''}</span>
            <span className="meta">{b.period}</span>
            <span>{s.data ? <Bar status={s.data} /> : <span className="meta">{formatUsd(b.limit_usd)}</span>}</span>
            <button
              className="btn btn-sm"
              style={{ color: 'var(--red)' }}
              onClick={() => onDelete(b.id)}
            >
              Delete
            </button>
          </div>
        )
      })}
    </div>
  )
}

function Bar({ status }: { status: import('~/lib/admin-types').BudgetStatus }) {
  const bar = statusToBar(status)
  const color =
    bar.zone === 'block' ? 'var(--red)' : bar.zone === 'warn' ? '#f59e0b' : 'var(--accent)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div
        style={{
          flex: 1,
          height: 6,
          background: 'var(--bg-2)',
          borderRadius: 3,
          overflow: 'hidden',
        }}
      >
        <div style={{ width: `${bar.pct * 100}%`, height: '100%', background: color }} />
      </div>
      <span className="meta" style={{ minWidth: 130, fontSize: 11, textAlign: 'right' }}>{bar.label}</span>
    </div>
  )
}

function QuotasTable({ quotas, onDelete }: { quotas: Quota[]; onDelete: (id: number) => void }) {
  return (
    <div className="tbl" data-testid="admin-quotas-table">
      <div
        className="audit-row"
        style={{
          gridTemplateColumns: '1fr 110px 110px 100px 100px 100px 100px',
          background: 'var(--bg-2)',
          borderBottom: '1px solid var(--line)',
          fontWeight: 600,
          fontSize: 10,
          color: 'var(--ink-3)',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        <span>Name</span>
        <span>Scope</span>
        <span>Unit</span>
        <span>Period</span>
        <span>Max</span>
        <span>On breach</span>
        <span />
      </div>
      {quotas.map((q) => (
        <div
          key={q.id}
          className="audit-row"
          style={{ gridTemplateColumns: '1fr 110px 110px 100px 100px 100px 100px' }}
          data-testid={`admin-quotas-row-${q.id}`}
        >
          <span style={{ color: 'var(--ink)' }}>{q.name}</span>
          <span className="meta">{q.scope_kind}{q.scope_id ? `:${q.scope_id.slice(0, 8)}` : ''}</span>
          <span className="meta">{q.unit}</span>
          <span className="meta">{q.period}</span>
          <span className="meta">{q.max_qty}</span>
          <span className="meta">{q.action_on_breach}</span>
          <button
            className="btn btn-sm"
            style={{ color: 'var(--red)' }}
            onClick={() => onDelete(q.id)}
          >
            Delete
          </button>
        </div>
      ))}
    </div>
  )
}

const SCOPES: ScopeKind[] = ['org', 'user', 'team', 'api_key']

function BudgetDialog({
  saving,
  error,
  onSubmit,
  onCancel,
}: {
  saving: boolean
  error: string | null
  onSubmit: (req: BudgetCreateRequest) => void
  onCancel: () => void
}) {
  const [name, setName] = React.useState('')
  const [scopeKind, setScopeKind] = React.useState<ScopeKind>('org')
  const [scopeId, setScopeId] = React.useState('')
  const [limit, setLimit] = React.useState('')
  const [period, setPeriod] = React.useState<'day' | 'month' | 'custom'>('month')
  const [hardCutoff, setHardCutoff] = React.useState(true)
  const [localError, setLocalError] = React.useState<string | null>(null)

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const nameErr = validateBudgetName(name)
    const limitErr = validateLimitUsd(limit)
    if (nameErr || limitErr) {
      setLocalError(nameErr || limitErr)
      return
    }
    setLocalError(null)
    onSubmit({
      name: name.trim(),
      scope_kind: scopeKind,
      scope_id: scopeKind === 'org' ? null : scopeId.trim() || null,
      limit_usd: limit.trim(),
      period,
      hard_cutoff: hardCutoff,
    })
  }

  return (
    <Modal title="New budget" onClose={onCancel} testId="admin-budgets-create-dialog">
      <form onSubmit={submit}>
        <Field label="Name">
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Q1 marketing"
            style={inputStyle}
          />
        </Field>
        <Field label="Scope">
          <Select value={scopeKind} onChange={(e) => setScopeKind(e.target.value as ScopeKind)} size="sm" inline>
            {SCOPES.map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
        </Field>
        {scopeKind !== 'org' && (
          <Field label="Scope id">
            <input value={scopeId} onChange={(e) => setScopeId(e.target.value)} placeholder="uuid / id" style={inputStyle} />
          </Field>
        )}
        <Field label="Limit USD">
          <input value={limit} onChange={(e) => setLimit(e.target.value)} placeholder="100.00" style={inputStyle} />
        </Field>
        <Field label="Period">
          <Select value={period} onChange={(e) => setPeriod(e.target.value as 'day' | 'month' | 'custom')} size="sm" inline>
            <option value="day">Day</option>
            <option value="month">Month</option>
            <option value="custom">Custom</option>
          </Select>
        </Field>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12, margin: '8px 0' }}>
          <input
            type="checkbox"
            checked={hardCutoff}
            onChange={(e) => setHardCutoff(e.target.checked)}
          />
          Hard cutoff on breach
        </label>
        {(error || localError) && <p style={{ fontSize: 11, color: 'var(--red)', marginBottom: 8 }}>{error || localError}</p>}
        <DialogActions saving={saving} onCancel={onCancel} />
      </form>
    </Modal>
  )
}

function QuotaDialog({
  saving,
  error,
  onSubmit,
  onCancel,
}: {
  saving: boolean
  error: string | null
  onSubmit: (req: QuotaCreateRequest) => void
  onCancel: () => void
}) {
  const [name, setName] = React.useState('')
  const [scopeKind, setScopeKind] = React.useState<ScopeKind>('org')
  const [scopeId, setScopeId] = React.useState('')
  const [unit, setUnit] = React.useState('tokens_in')
  const [maxQty, setMaxQty] = React.useState('')
  const [period, setPeriod] = React.useState<'day' | 'month' | 'custom'>('month')
  const [action, setAction] = React.useState<'block' | 'warn' | 'allow'>('block')
  const [localError, setLocalError] = React.useState<string | null>(null)

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) {
      setLocalError('Name required')
      return
    }
    if (!maxQty.trim() || !Number.isFinite(Number(maxQty))) {
      setLocalError('Max quantity must be a number')
      return
    }
    setLocalError(null)
    onSubmit({
      name: name.trim(),
      scope_kind: scopeKind,
      scope_id: scopeKind === 'org' ? null : scopeId.trim() || null,
      unit,
      period,
      max_qty: maxQty.trim(),
      action_on_breach: action,
    })
  }

  return (
    <Modal title="New quota" onClose={onCancel} testId="admin-quotas-create-dialog">
      <form onSubmit={submit}>
        <Field label="Name"><input required value={name} onChange={(e) => setName(e.target.value)} style={inputStyle} /></Field>
        <Field label="Scope">
          <Select value={scopeKind} onChange={(e) => setScopeKind(e.target.value as ScopeKind)} size="sm" inline>
            {SCOPES.map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
        </Field>
        {scopeKind !== 'org' && (
          <Field label="Scope id"><input value={scopeId} onChange={(e) => setScopeId(e.target.value)} style={inputStyle} /></Field>
        )}
        <Field label="Unit">
          <Select value={unit} onChange={(e) => setUnit(e.target.value)} size="sm" inline>
            <option value="tokens_in">tokens_in</option>
            <option value="tokens_out">tokens_out</option>
            <option value="embeddings">embeddings</option>
            <option value="documents_ingested">documents_ingested</option>
            <option value="queries">queries</option>
            <option value="worker_minutes">worker_minutes</option>
            <option value="storage_gb">storage_gb</option>
          </Select>
        </Field>
        <Field label="Max"><input value={maxQty} onChange={(e) => setMaxQty(e.target.value)} placeholder="1000000" style={inputStyle} /></Field>
        <Field label="Period">
          <Select value={period} onChange={(e) => setPeriod(e.target.value as 'day' | 'month' | 'custom')} size="sm" inline>
            <option value="day">Day</option>
            <option value="month">Month</option>
            <option value="custom">Custom</option>
          </Select>
        </Field>
        <Field label="On breach">
          <Select value={action} onChange={(e) => setAction(e.target.value as 'block' | 'warn' | 'allow')} size="sm" inline>
            <option value="block">block</option>
            <option value="warn">warn</option>
            <option value="allow">allow</option>
          </Select>
        </Field>
        {(error || localError) && <p style={{ fontSize: 11, color: 'var(--red)', marginBottom: 8 }}>{error || localError}</p>}
        <DialogActions saving={saving} onCancel={onCancel} />
      </form>
    </Modal>
  )
}

const inputStyle: React.CSSProperties = {
  borderRadius: 4,
  border: '1px solid var(--line)',
  background: 'var(--bg)',
  color: 'var(--ink)',
  padding: '4px 8px',
  fontSize: 12,
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, marginBottom: 10 }}>
      {label}
      {children}
    </label>
  )
}

function DialogActions({ saving, onCancel }: { saving: boolean; onCancel: () => void }) {
  return (
    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
      <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
      <button type="button" className="btn btn-sm" onClick={onCancel}>Cancel</button>
    </div>
  )
}

function Modal({
  title,
  children,
  onClose,
  testId,
}: {
  title: string
  children: React.ReactNode
  onClose: () => void
  testId?: string
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      data-testid={testId}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 8, padding: 20, width: '90%', maxWidth: 560, maxHeight: '85vh', overflowY: 'auto' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600 }}>{title}</h3>
          <button type="button" onClick={onClose} className="btn btn-sm" aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}
