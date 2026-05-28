// apps/frontend/src/routes/gateway/guardrails.tsx
// Gateway → Guardrails (J6): policy bundle editor + live test pane.
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'
import { authorizedFetch } from '~/lib/authorizedFetch'
import {
  addStep,
  decisionBadge,
  removeStep,
  reorderStep,
  resolveFinalDecision,
} from '~/lib/guardrails-logic'
import type {
  GuardrailAction,
  GuardrailBundle,
  GuardrailKind,
  GuardrailPolicy,
  GuardrailStep,
  GuardrailTestResult,
} from '~/lib/gateway-types'

export const Route = createFileRoute('/gateway/guardrails')({
  component: GuardrailsPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

const KINDS: GuardrailKind[] = [
  'regex',
  'presidio',
  'openai_moderation',
  'llamaguard',
  'prompt_injection_classifier',
  'secret_scanner',
  'topic_filter',
  'schema_validator',
  'custom_classifier',
]
const ACTIONS: GuardrailAction[] = ['allow', 'flag', 'redact', 'block']

const EMPTY: GuardrailBundle = { input: [], output: [] }

function GuardrailsPage() {
  const [policies, setPolicies] = React.useState<GuardrailPolicy[]>([])
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [draft, setDraft] = React.useState<GuardrailBundle>(EMPTY)
  const [name, setName] = React.useState('')

  React.useEffect(() => {
    authorizedFetch(`${API_BASE}/api/v1/gateway/guardrail-policies`)
      .then((r) => r.json())
      .then((d) => Array.isArray(d) && setPolicies(d))
      .catch(() => null)
  }, [])

  React.useEffect(() => {
    const p = policies.find((x) => x.id === selectedId)
    if (p) {
      setDraft(p.bundle)
      setName(p.name)
    }
  }, [selectedId, policies])

  async function save() {
    const body = JSON.stringify({ name, bundle: draft })
    const url = selectedId
      ? `${API_BASE}/api/v1/gateway/guardrail-policies/${selectedId}`
      : `${API_BASE}/api/v1/gateway/guardrail-policies`
    const res = await authorizedFetch(url, {
      method: selectedId ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    })
    if (res.ok) {
      const saved: GuardrailPolicy = await res.json()
      setPolicies((prev) => {
        const i = prev.findIndex((p) => p.id === saved.id)
        if (i === -1) return [...prev, saved]
        const next = prev.slice()
        next[i] = saved
        return next
      })
      setSelectedId(saved.id)
    }
  }

  return (
    <div className="main-inner" data-testid="gateway-guardrails">
      <div className="screen-head">
        <div>
          <h1>Guardrails</h1>
          <div className="sub">Policy bundles · pre/post checks · live test</div>
        </div>
      </div>

      <div className="gov-grid" style={{ gridTemplateColumns: '240px 1fr 1fr', gap: 16 }}>
        <PolicyList
          policies={policies}
          selectedId={selectedId}
          onSelect={(id) => setSelectedId(id)}
          onNew={() => {
            setSelectedId(null)
            setDraft(EMPTY)
            setName('')
          }}
        />
        <BundleEditor
          name={name}
          onName={setName}
          bundle={draft}
          onChange={setDraft}
          onSave={save}
        />
        <TestPane bundle={draft} />
      </div>
    </div>
  )
}

function PolicyList({
  policies,
  selectedId,
  onSelect,
  onNew,
}: {
  policies: GuardrailPolicy[]
  selectedId: string | null
  onSelect: (id: string) => void
  onNew: () => void
}) {
  return (
    <div className="panel">
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>Policies</span>
        <button className="btn btn-sm" onClick={onNew} data-testid="new-policy">
          + New
        </button>
      </div>
      <div className="panel-body" style={{ padding: 0 }}>
        {policies.map((p) => (
          <button
            key={p.id}
            onClick={() => onSelect(p.id)}
            className={`conv-row${p.id === selectedId ? ' active' : ''}`}
            style={{ width: '100%', textAlign: 'left', padding: '8px 12px' }}
          >
            <div className="title" style={{ fontSize: 12 }}>{p.name}</div>
            <div className="meta" style={{ fontSize: 10 }}>
              {p.bundle.input.length} pre · {p.bundle.output.length} post
            </div>
          </button>
        ))}
        {policies.length === 0 && (
          <p style={{ padding: 12, fontSize: 11, color: 'var(--ink-3)' }}>No policies yet.</p>
        )}
      </div>
    </div>
  )
}

function BundleEditor({
  name,
  onName,
  bundle,
  onChange,
  onSave,
}: {
  name: string
  onName: (s: string) => void
  bundle: GuardrailBundle
  onChange: (b: GuardrailBundle) => void
  onSave: () => void
}) {
  return (
    <div className="panel">
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>Bundle</span>
        <button className="btn btn-primary btn-sm" onClick={onSave} data-testid="save-policy">
          Save
        </button>
      </div>
      <div className="panel-body" style={{ padding: 12 }}>
        <input
          value={name}
          onChange={(e) => onName(e.target.value)}
          placeholder="Policy name"
          style={{ width: '100%', marginBottom: 12, fontSize: 12, padding: 6, border: '1px solid var(--line)', borderRadius: 4, background: 'var(--bg)', color: 'var(--ink)' }}
          data-testid="policy-name"
        />

        <PhaseEditor
          label="Pre-call (input)"
          phase="input"
          steps={bundle.input}
          onAdd={(s) => onChange(addStep(bundle, 'input', s))}
          onRemove={(i) => onChange(removeStep(bundle, 'input', i))}
          onReorder={(f, t) => onChange(reorderStep(bundle, 'input', f, t))}
        />

        <PhaseEditor
          label="Post-call (output)"
          phase="output"
          steps={bundle.output}
          onAdd={(s) => onChange(addStep(bundle, 'output', s))}
          onRemove={(i) => onChange(removeStep(bundle, 'output', i))}
          onReorder={(f, t) => onChange(reorderStep(bundle, 'output', f, t))}
        />
      </div>
    </div>
  )
}

function PhaseEditor({
  label,
  phase,
  steps,
  onAdd,
  onRemove,
  onReorder,
}: {
  label: string
  phase: 'input' | 'output'
  steps: GuardrailStep[]
  onAdd: (s: GuardrailStep) => void
  onRemove: (i: number) => void
  onReorder: (from: number, to: number) => void
}) {
  const [kind, setKind] = React.useState<GuardrailKind>('regex')
  const [action, setAction] = React.useState<GuardrailAction>('block')

  return (
    <section style={{ marginBottom: 16 }} data-testid={`phase-${phase}`}>
      <div className="panel-head" style={{ fontSize: 11 }}>{label}</div>
      <div style={{ display: 'flex', gap: 6, padding: '8px 0' }}>
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as GuardrailKind)}
          style={{ flex: 1, fontSize: 11, padding: 4, border: '1px solid var(--line)', borderRadius: 3, background: 'var(--bg)', color: 'var(--ink)' }}
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>{k}</option>
          ))}
        </select>
        <select
          value={action}
          onChange={(e) => setAction(e.target.value as GuardrailAction)}
          style={{ fontSize: 11, padding: 4, border: '1px solid var(--line)', borderRadius: 3, background: 'var(--bg)', color: 'var(--ink)' }}
        >
          {ACTIONS.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <button
          className="btn btn-sm"
          onClick={() => onAdd({ kind, config: {}, on_match: action })}
        >
          Add
        </button>
      </div>
      <ol style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {steps.map((s, i) => (
          <li
            key={i}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px', borderTop: '1px solid var(--line)' }}
          >
            <span style={{ fontSize: 11, color: 'var(--ink-3)', width: 18 }}>{i + 1}</span>
            <span style={{ flex: 1, fontSize: 11, fontFamily: 'var(--font-mono)' }}>{s.kind}</span>
            <span className={decisionBadge(s.on_match)} style={{ fontSize: 10 }}>{s.on_match}</span>
            <button
              className="btn btn-sm"
              onClick={() => onReorder(i, i - 1)}
              disabled={i === 0}
              aria-label="Move up"
            >↑</button>
            <button
              className="btn btn-sm"
              onClick={() => onReorder(i, i + 1)}
              disabled={i === steps.length - 1}
              aria-label="Move down"
            >↓</button>
            <button className="btn btn-sm" style={{ color: 'var(--red)' }} onClick={() => onRemove(i)}>
              ×
            </button>
          </li>
        ))}
      </ol>
    </section>
  )
}

function TestPane({ bundle }: { bundle: GuardrailBundle }) {
  const [prompt, setPrompt] = React.useState('')
  const [result, setResult] = React.useState<GuardrailTestResult | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [err, setErr] = React.useState<string | null>(null)

  async function run() {
    setLoading(true)
    setErr(null)
    setResult(null)
    try {
      const res = await authorizedFetch(`${API_BASE}/api/v1/gateway/guardrail-policies/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bundle, prompt }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = (await res.json()) as GuardrailTestResult
      // Defensive: derive final if backend omitted it.
      if (!data.final_decision) {
        data.final_decision = resolveFinalDecision(data.verdicts ?? [])
      }
      setResult(data)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="panel">
      <div className="panel-head">Live test</div>
      <div className="panel-body" style={{ padding: 12 }}>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Paste a prompt to test against this bundle…"
          rows={6}
          style={{ width: '100%', fontSize: 12, fontFamily: 'var(--font-mono)', padding: 8, border: '1px solid var(--line)', borderRadius: 4, background: 'var(--bg)', color: 'var(--ink)' }}
          data-testid="test-prompt"
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
          <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>
            {loading ? 'Running…' : `Steps: ${bundle.input.length + bundle.output.length}`}
          </span>
          <button className="btn btn-primary btn-sm" onClick={run} disabled={loading || !prompt}>
            Test
          </button>
        </div>
        {err && <p style={{ marginTop: 8, fontSize: 11, color: 'var(--red)' }}>{err}</p>}
        {result && (
          <div style={{ marginTop: 12 }} data-testid="test-result">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>Final:</span>
              <span className={decisionBadge(result.final_decision)}>{result.final_decision}</span>
            </div>
            {result.verdicts.map((v, i) => (
              <div key={i} style={{ padding: 6, borderTop: '1px solid var(--line)', fontSize: 11 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{v.guardrail}</span>
                  <span className={decisionBadge(v.decision)}>{v.decision}</span>
                </div>
                {v.reason && <div style={{ color: 'var(--ink-3)' }}>{v.reason}</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
