import { Select } from '~/components/ui/select'
import { createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import {
  createModelAlias,
  createRoutingPolicy,
  deleteModelAlias,
  deleteRoutingPolicy,
  fetchModelAliases,
  fetchRoutingPolicies,
  updateRoutingPolicy,
} from '~/lib/gateway-api'
import {
  STRATEGY_OPTIONS,
  parseRules,
  reorder,
  validateAliasName,
  validatePolicyName,
  type PriorityRules,
  type StaticRules,
  type WeightedRules,
} from '~/lib/gateway-routing-logic'
import type { ModelAlias, RoutingPolicy, RoutingStrategy } from '~/lib/gateway-types'

export const Route = createFileRoute('/gateway/routing')({
  component: RoutingPage,
})

function RoutingPage() {
  const policies = useQuery({ queryKey: ['gateway', 'policies'], queryFn: fetchRoutingPolicies })
  const aliases = useQuery({ queryKey: ['gateway', 'aliases'], queryFn: fetchModelAliases })

  const [editing, setEditing] = React.useState<RoutingPolicy | 'new' | null>(null)
  const [addingAlias, setAddingAlias] = React.useState(false)

  return (
    <div data-testid="gw-routing" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="panel">
        <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>Routing policies</span>
          <button
            className="btn btn-primary"
            onClick={() => setEditing('new')}
            data-testid="gw-routing-new-policy"
          >
            New policy
          </button>
        </div>
        <div className="panel-body" style={{ padding: 16 }}>
          {policies.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
          {policies.error && (
            <p style={{ fontSize: 12, color: 'var(--red)' }}>{(policies.error as Error).message}</p>
          )}
          {policies.data && (
            <PoliciesTable
              policies={policies.data}
              onEdit={(p) => setEditing(p)}
            />
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>Model aliases</span>
          <button
            className="btn btn-primary"
            onClick={() => setAddingAlias(true)}
            data-testid="gw-routing-new-alias"
          >
            New alias
          </button>
        </div>
        <div className="panel-body" style={{ padding: 16 }}>
          {aliases.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
          {aliases.error && (
            <p style={{ fontSize: 12, color: 'var(--red)' }}>{(aliases.error as Error).message}</p>
          )}
          {aliases.data && policies.data && (
            <AliasesTable aliases={aliases.data} policies={policies.data} />
          )}
        </div>
      </div>

      {editing !== null && (
        <PolicyEditorDialog
          initial={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
      {addingAlias && policies.data && (
        <AliasDialog policies={policies.data} onClose={() => setAddingAlias(false)} />
      )}
    </div>
  )
}

function PoliciesTable({
  policies,
  onEdit,
}: {
  policies: RoutingPolicy[]
  onEdit: (p: RoutingPolicy) => void
}) {
  const qc = useQueryClient()
  const delMut = useMutation({
    mutationFn: deleteRoutingPolicy,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gateway', 'policies'] }),
  })

  if (policies.length === 0) {
    return <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No policies yet.</p>
  }
  return (
    <div className="tbl" data-testid="gw-routing-policies-table">
      <div className="audit-row" style={pHeader}><span>Name</span><span>Strategy</span><span /></div>
      {policies.map((p) => (
        <div key={p.id} className="audit-row" style={pData}>
          <span style={{ color: 'var(--ink)' }}>{p.name}</span>
          <span className="meta">{p.strategy}</span>
          <span style={{ display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
            <button className="btn btn-sm" onClick={() => onEdit(p)}>Edit</button>
            <button
              className="btn btn-sm"
              style={{ color: 'var(--red)' }}
              onClick={() => {
                if (confirm(`Delete policy "${p.name}"? Aliases pointing to it will break.`)) {
                  delMut.mutate(p.id)
                }
              }}
            >
              Delete
            </button>
          </span>
        </div>
      ))}
    </div>
  )
}

function AliasesTable({
  aliases,
  policies,
}: {
  aliases: ModelAlias[]
  policies: RoutingPolicy[]
}) {
  const qc = useQueryClient()
  const delMut = useMutation({
    mutationFn: deleteModelAlias,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gateway', 'aliases'] }),
  })
  const policyName = (id: string) => policies.find((p) => p.id === id)?.name ?? '—'

  if (aliases.length === 0) {
    return <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No aliases yet.</p>
  }
  return (
    <div className="tbl" data-testid="gw-routing-aliases-table">
      <div className="audit-row" style={pHeader}><span>Alias</span><span>Policy</span><span /></div>
      {aliases.map((a) => (
        <div key={a.id} className="audit-row" style={pData}>
          <span style={{ color: 'var(--ink)', fontFamily: 'var(--font-mono)' }}>{a.alias}</span>
          <span className="meta">{policyName(a.routing_policy_id)}</span>
          <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              className="btn btn-sm"
              style={{ color: 'var(--red)' }}
              onClick={() => {
                if (confirm(`Delete alias "${a.alias}"?`)) delMut.mutate(a.id)
              }}
            >
              Delete
            </button>
          </span>
        </div>
      ))}
    </div>
  )
}

function PolicyEditorDialog({
  initial,
  onClose,
}: {
  initial: RoutingPolicy | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const isEdit = !!initial
  const [name, setName] = React.useState(initial?.name ?? '')
  const [strategy, setStrategy] = React.useState<RoutingStrategy>(initial?.strategy ?? 'priority')
  const [rules, setRules] = React.useState<unknown>(initial?.rules_json ?? defaultRulesFor(initial?.strategy ?? 'priority'))
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    // Reset rules to a sane default when strategy changes
    setRules(defaultRulesFor(strategy))
  }, [strategy])

  const createMut = useMutation({
    mutationFn: createRoutingPolicy,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['gateway', 'policies'] })
      onClose()
    },
  })
  const updMut = useMutation({
    mutationFn: ({ id, req }: { id: string; req: Parameters<typeof updateRoutingPolicy>[1] }) =>
      updateRoutingPolicy(id, req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['gateway', 'policies'] })
      onClose()
    },
  })

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const nameErr = validatePolicyName(name)
    if (nameErr) {
      setError(nameErr)
      return
    }
    setError(null)
    const body = { name: name.trim(), strategy, rules_json: rules }
    if (isEdit && initial) {
      updMut.mutate({ id: initial.id, req: body })
    } else {
      createMut.mutate(body)
    }
  }

  return (
    <Modal title={isEdit ? 'Edit policy' : 'New routing policy'} onClose={onClose} testId="gw-routing-policy-dialog">
      <form onSubmit={submit}>
        <label style={fieldRow}>
          Name
          <input
            className="gw-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="cheapest-coder"
            data-testid="gw-routing-policy-name"
            disabled={isEdit}
          />
        </label>
        <label style={fieldRow}>
          Strategy
          <Select
            className="gw-input"
            value={strategy}
            onChange={(e) => setStrategy(e.target.value as RoutingStrategy)}
            data-testid="gw-routing-policy-strategy"
          size="sm"
          inline
          >
            {STRATEGY_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </Select>
          <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>
            {STRATEGY_OPTIONS.find((s) => s.value === strategy)?.blurb}
          </span>
        </label>

        <RulesEditor strategy={strategy} value={rules} onChange={setRules} />

        {(error || createMut.error || updMut.error) && (
          <p style={{ fontSize: 11, color: 'var(--red)', marginBottom: 8 }}>
            {error ?? (createMut.error as Error)?.message ?? (updMut.error as Error)?.message}
          </p>
        )}
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="submit" className="btn btn-primary" disabled={createMut.isPending || updMut.isPending}>
            {createMut.isPending || updMut.isPending ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="btn btn-sm" onClick={onClose}>Cancel</button>
        </div>
      </form>
    </Modal>
  )
}

function RulesEditor({
  strategy,
  value,
  onChange,
}: {
  strategy: RoutingStrategy
  value: unknown
  onChange: (v: unknown) => void
}) {
  const parsed = parseRules({ strategy, rules_json: value as object })

  if (parsed.kind === 'static') {
    return (
      <label style={fieldRow}>
        Target model (provider:model_id)
        <input
          className="gw-input"
          value={parsed.rules.target}
          onChange={(e) => onChange({ target: e.target.value } satisfies StaticRules)}
          placeholder="anthropic:claude-sonnet-4-6"
          data-testid="gw-routing-rules-target"
        />
      </label>
    )
  }
  if (parsed.kind === 'priority') {
    return (
      <PriorityEditor
        rules={parsed.rules}
        onChange={(r) => onChange(r)}
      />
    )
  }
  if (parsed.kind === 'weighted') {
    return (
      <WeightedEditor
        rules={parsed.rules}
        onChange={(r) => onChange(r)}
      />
    )
  }
  // raw fallback — textarea JSON
  return (
    <label style={fieldRow}>
      Rules JSON
      <textarea
        className="gw-input"
        rows={6}
        value={JSON.stringify(parsed.rules, null, 2)}
        onChange={(e) => {
          try {
            onChange(JSON.parse(e.target.value))
          } catch {
            // ignore until parseable
          }
        }}
        style={{ fontFamily: 'var(--font-mono)' }}
        data-testid="gw-routing-rules-raw"
      />
    </label>
  )
}

function PriorityEditor({
  rules,
  onChange,
}: {
  rules: PriorityRules
  onChange: (r: PriorityRules) => void
}) {
  const [draft, setDraft] = React.useState('')
  function add() {
    if (!draft.trim()) return
    onChange({ candidates: [...rules.candidates, draft.trim()] })
    setDraft('')
  }
  function move(from: number, to: number) {
    onChange({ candidates: reorder(rules.candidates, from, to) })
  }
  function remove(idx: number) {
    onChange({ candidates: rules.candidates.filter((_, i) => i !== idx) })
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 11, color: 'var(--ink-3)', marginBottom: 6 }}>
        Candidates (priority — top first, drag to reorder)
      </div>
      <div data-testid="gw-routing-priority-list">
        {rules.candidates.map((c, i) => (
          <div
            key={`${c}-${i}`}
            draggable
            onDragStart={(e) => e.dataTransfer.setData('text/plain', String(i))}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              const from = Number(e.dataTransfer.getData('text/plain'))
              if (!Number.isNaN(from)) move(from, i)
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '4px 8px',
              border: '1px solid var(--line)',
              borderRadius: 4,
              marginBottom: 4,
              background: 'var(--bg-2)',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              cursor: 'grab',
            }}
          >
            <span style={{ color: 'var(--ink-3)', minWidth: 18 }}>{i + 1}</span>
            <span style={{ flex: 1 }}>{c}</span>
            <button type="button" className="btn btn-xs" onClick={() => move(i, Math.max(0, i - 1))}>↑</button>
            <button type="button" className="btn btn-xs" onClick={() => move(i, Math.min(rules.candidates.length - 1, i + 1))}>↓</button>
            <button type="button" className="btn btn-xs" style={{ color: 'var(--red)' }} onClick={() => remove(i)}>✕</button>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
        <input
          className="gw-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="provider:model_id"
          style={{ flex: 1 }}
          data-testid="gw-routing-priority-add-input"
        />
        <button type="button" className="btn btn-sm" onClick={add} data-testid="gw-routing-priority-add">Add</button>
      </div>
    </div>
  )
}

function WeightedEditor({
  rules,
  onChange,
}: {
  rules: WeightedRules
  onChange: (r: WeightedRules) => void
}) {
  const [draftTarget, setDraftTarget] = React.useState('')
  const [draftWeight, setDraftWeight] = React.useState('1')
  function add() {
    const w = Number(draftWeight)
    if (!draftTarget.trim() || Number.isNaN(w)) return
    onChange({ candidates: [...rules.candidates, { target: draftTarget.trim(), weight: w }] })
    setDraftTarget('')
    setDraftWeight('1')
  }
  function remove(idx: number) {
    onChange({ candidates: rules.candidates.filter((_, i) => i !== idx) })
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 11, color: 'var(--ink-3)', marginBottom: 6 }}>
        Weighted candidates
      </div>
      {rules.candidates.map((c, i) => (
        <div
          key={`${c.target}-${i}`}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '4px 8px',
            border: '1px solid var(--line)',
            borderRadius: 4,
            marginBottom: 4,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
          }}
        >
          <span style={{ flex: 1 }}>{c.target}</span>
          <span className="meta">weight {c.weight}</span>
          <button type="button" className="btn btn-xs" style={{ color: 'var(--red)' }} onClick={() => remove(i)}>✕</button>
        </div>
      ))}
      <div style={{ display: 'flex', gap: 6 }}>
        <input
          className="gw-input"
          value={draftTarget}
          onChange={(e) => setDraftTarget(e.target.value)}
          placeholder="provider:model_id"
          style={{ flex: 1 }}
        />
        <input
          className="gw-input"
          type="number"
          min={1}
          value={draftWeight}
          onChange={(e) => setDraftWeight(e.target.value)}
          style={{ width: 80 }}
        />
        <button type="button" className="btn btn-sm" onClick={add}>Add</button>
      </div>
    </div>
  )
}

function AliasDialog({
  policies,
  onClose,
}: {
  policies: RoutingPolicy[]
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [alias, setAlias] = React.useState('')
  const [policyId, setPolicyId] = React.useState(policies[0]?.id ?? '')
  const [error, setError] = React.useState<string | null>(null)
  const mut = useMutation({
    mutationFn: createModelAlias,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['gateway', 'aliases'] })
      onClose()
    },
  })
  function submit(e: React.FormEvent) {
    e.preventDefault()
    const err = validateAliasName(alias)
    if (err) {
      setError(err)
      return
    }
    if (!policyId) {
      setError('Pick a policy')
      return
    }
    setError(null)
    mut.mutate({ alias: alias.trim(), routing_policy_id: policyId })
  }
  return (
    <Modal title="New model alias" onClose={onClose} testId="gw-routing-alias-dialog">
      <form onSubmit={submit}>
        <label style={fieldRow}>
          Alias
          <input
            className="gw-input"
            value={alias}
            onChange={(e) => setAlias(e.target.value)}
            placeholder="smart"
            data-testid="gw-routing-alias-name"
          />
        </label>
        <label style={fieldRow}>
          Policy
          <Select
            className="gw-input"
            value={policyId}
            onChange={(e) => setPolicyId(e.target.value)}
            data-testid="gw-routing-alias-policy"
          size="sm"
          inline
          >
            {policies.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </Select>
        </label>
        {(error || mut.error) && (
          <p style={{ fontSize: 11, color: 'var(--red)', marginBottom: 8 }}>
            {error ?? (mut.error as Error)?.message}
          </p>
        )}
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="submit" className="btn btn-primary" disabled={mut.isPending}>
            {mut.isPending ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="btn btn-sm" onClick={onClose}>Cancel</button>
        </div>
      </form>
    </Modal>
  )
}

function defaultRulesFor(s: RoutingStrategy): unknown {
  switch (s) {
    case 'static': return { target: '' }
    case 'priority': return { candidates: [] }
    case 'weighted': return { candidates: [] }
    case 'cost_optimized': return { capabilities: [] }
    case 'latency_optimized': return { capabilities: [] }
    case 'capability_match': return { capabilities: [] }
    case 'custom_rules': return { rules: [] }
  }
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
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 8,
          padding: 20, width: '90%', maxWidth: 560, maxHeight: '85vh', overflowY: 'auto',
        }}
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

const pHeader: React.CSSProperties = {
  gridTemplateColumns: '1fr 160px 200px',
  background: 'var(--bg-2)',
  borderBottom: '1px solid var(--line)',
  fontWeight: 600,
  fontSize: 10,
  color: 'var(--ink-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
}
const pData: React.CSSProperties = { gridTemplateColumns: '1fr 160px 200px' }
const fieldRow: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
  fontSize: 11,
  marginBottom: 12,
}
