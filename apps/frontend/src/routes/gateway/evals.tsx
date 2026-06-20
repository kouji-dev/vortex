// apps/frontend/src/routes/gateway/evals.tsx
// Gateway → Evals (J9): test-set CRUD + run launcher + results table.
import { Select } from '~/components/ui/select'
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'
import { authorizedFetch } from '~/lib/authorizedFetch'
import { blankRecord, fmtPassRate, validateTestSet } from '~/lib/evals-logic'
import type { EvalRecord, EvalRun, EvalTestSet, ModelInfo } from '~/lib/gateway-types'

export const Route = createFileRoute('/gateway/evals')({
  component: EvalsPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function EvalsPage() {
  const [sets, setSets] = React.useState<EvalTestSet[]>([])
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [draft, setDraft] = React.useState<EvalTestSet | null>(null)
  const [models, setModels] = React.useState<ModelInfo[]>([])
  const [runs, setRuns] = React.useState<EvalRun[]>([])
  const [picked, setPicked] = React.useState<string[]>([])
  const [running, setRunning] = React.useState(false)
  const [err, setErr] = React.useState<string | null>(null)

  React.useEffect(() => {
    authorizedFetch(`${API_BASE}/api/v1/gateway/evals`)
      .then((r) => r.json())
      .then((d) => Array.isArray(d) && setSets(d))
      .catch(() => null)
    authorizedFetch(`${API_BASE}/api/v1/models`)
      .then((r) => r.json())
      .then((d) => Array.isArray(d?.data) && setModels(d.data))
      .catch(() => null)
  }, [])

  React.useEffect(() => {
    const s = sets.find((x) => x.id === selectedId)
    setDraft(s ?? null)
    setRuns([])
    if (selectedId) {
      authorizedFetch(`${API_BASE}/api/v1/gateway/evals/${selectedId}/runs`)
        .then((r) => r.json())
        .then((d) => Array.isArray(d) && setRuns(d))
        .catch(() => null)
    }
  }, [selectedId, sets])

  function newSet() {
    setSelectedId(null)
    setDraft({ id: '', name: '', records: [blankRecord(`rec-${Date.now()}`)] })
    setRuns([])
  }

  async function save() {
    if (!draft) return
    const err = validateTestSet(draft)
    if (err) {
      setErr(err)
      return
    }
    setErr(null)
    const body = JSON.stringify({ name: draft.name, records: draft.records })
    const url = selectedId
      ? `${API_BASE}/api/v1/gateway/evals/${selectedId}`
      : `${API_BASE}/api/v1/gateway/evals`
    const res = await authorizedFetch(url, {
      method: selectedId ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    })
    if (res.ok) {
      const saved: EvalTestSet = await res.json()
      setSets((prev) => {
        const i = prev.findIndex((x) => x.id === saved.id)
        if (i === -1) return [...prev, saved]
        const next = prev.slice()
        next[i] = saved
        return next
      })
      setSelectedId(saved.id)
    }
  }

  async function launchRun() {
    if (!selectedId || picked.length === 0) return
    setRunning(true)
    try {
      const res = await authorizedFetch(`${API_BASE}/api/v1/gateway/evals/${selectedId}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_models: picked }),
      })
      const data = await res.json()
      if (Array.isArray(data?.runs)) setRuns((prev) => [...data.runs, ...prev])
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="main-inner" data-testid="gateway-evals">
      <div className="screen-head">
        <div>
          <h1>Evals</h1>
          <div className="sub">Test sets · model runs · regression tracking</div>
        </div>
      </div>

      <div className="gov-grid" style={{ gridTemplateColumns: '240px 1fr', gap: 16 }}>
        <div className="panel">
          <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Test sets</span>
            <button className="btn btn-sm" onClick={newSet} data-testid="new-eval">+ New</button>
          </div>
          <div className="panel-body" style={{ padding: 0 }}>
            {sets.map((s) => (
              <button
                key={s.id}
                onClick={() => setSelectedId(s.id)}
                className={`conv-row${s.id === selectedId ? ' active' : ''}`}
                style={{ width: '100%', textAlign: 'left', padding: '8px 12px' }}
              >
                <div className="title" style={{ fontSize: 12 }}>{s.name}</div>
                <div className="meta" style={{ fontSize: 10 }}>{s.records.length} records</div>
              </button>
            ))}
          </div>
        </div>

        {draft ? (
          <div>
            <TestSetEditor
              draft={draft}
              onChange={setDraft}
              onSave={save}
              err={err}
            />
            {selectedId && (
              <RunLauncher
                models={models}
                picked={picked}
                onPick={setPicked}
                running={running}
                onLaunch={launchRun}
              />
            )}
            {runs.length > 0 && <ResultsTable runs={runs} />}
          </div>
        ) : (
          <div className="panel" style={{ padding: 32, textAlign: 'center', color: 'var(--ink-3)' }}>
            Select a test set or create a new one.
          </div>
        )}
      </div>
    </div>
  )
}

function TestSetEditor({
  draft,
  onChange,
  onSave,
  err,
}: {
  draft: EvalTestSet
  onChange: (s: EvalTestSet) => void
  onSave: () => void
  err: string | null
}) {
  function updateRecord(i: number, patch: Partial<EvalRecord>) {
    const records = draft.records.map((r, idx) => (idx === i ? { ...r, ...patch } : r))
    onChange({ ...draft, records })
  }
  function addRecord() {
    onChange({
      ...draft,
      records: [...draft.records, blankRecord(`rec-${Date.now()}-${draft.records.length}`)],
    })
  }
  function removeRecord(i: number) {
    onChange({ ...draft, records: draft.records.filter((_, idx) => idx !== i) })
  }

  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <input
          value={draft.name}
          onChange={(e) => onChange({ ...draft, name: e.target.value })}
          placeholder="Test set name"
          style={{ fontSize: 12, padding: 4, border: '1px solid var(--line)', borderRadius: 3, background: 'var(--bg)', color: 'var(--ink)' }}
          data-testid="eval-name"
        />
        <button className="btn btn-primary btn-sm" onClick={onSave} data-testid="save-eval">Save</button>
      </div>
      <div className="panel-body" style={{ padding: 12 }}>
        {err && <p style={{ fontSize: 11, color: 'var(--red)', marginBottom: 8 }}>{err}</p>}
        {draft.records.map((r, i) => (
          <div key={r.id} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 100px 40px', gap: 6, padding: 4, borderTop: '1px solid var(--line)' }}>
            <input
              placeholder="Input"
              value={r.input}
              onChange={(e) => updateRecord(i, { input: e.target.value })}
              style={{ fontSize: 11, padding: 4, border: '1px solid var(--line)', borderRadius: 3, background: 'var(--bg)', color: 'var(--ink)' }}
            />
            <input
              placeholder="Expected"
              value={r.expected}
              onChange={(e) => updateRecord(i, { expected: e.target.value })}
              style={{ fontSize: 11, padding: 4, border: '1px solid var(--line)', borderRadius: 3, background: 'var(--bg)', color: 'var(--ink)' }}
            />
            <Select
              value={r.judge}
              onChange={(e) => updateRecord(i, { judge: e.target.value as EvalRecord['judge'] })}
            size="sm"
            inline
            >
              <option value="exact">exact</option>
              <option value="regex">regex</option>
              <option value="llm">llm</option>
              <option value="custom">custom</option>
            </Select>
            <button className="btn btn-sm" style={{ color: 'var(--red)' }} onClick={() => removeRecord(i)}>×</button>
          </div>
        ))}
        <button className="btn btn-sm" onClick={addRecord} style={{ marginTop: 8 }}>+ Record</button>
      </div>
    </div>
  )
}

function RunLauncher({
  models,
  picked,
  onPick,
  running,
  onLaunch,
}: {
  models: ModelInfo[]
  picked: string[]
  onPick: (p: string[]) => void
  running: boolean
  onLaunch: () => void
}) {
  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>Run on models</span>
        <button className="btn btn-primary btn-sm" disabled={running || picked.length === 0} onClick={onLaunch} data-testid="launch-run">
          {running ? 'Running…' : 'Launch'}
        </button>
      </div>
      <div className="panel-body" style={{ padding: 12, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {models.map((m) => {
          const active = picked.includes(m.model_id)
          return (
            <button
              key={m.id}
              onClick={() =>
                onPick(active ? picked.filter((x) => x !== m.model_id) : [...picked, m.model_id])
              }
              className={`pill ${active ? 'pill-blue' : ''}`}
              style={{ cursor: 'pointer', fontSize: 11 }}
            >
              {m.display_name || m.model_id}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function ResultsTable({ runs }: { runs: EvalRun[] }) {
  return (
    <div className="panel">
      <div className="panel-head">Recent runs</div>
      <table className="tbl" style={{ width: '100%', fontSize: 11 }}>
        <thead>
          <tr>
            <th>When</th>
            <th>Model</th>
            <th style={{ textAlign: 'right' }}>Pass rate</th>
            <th style={{ textAlign: 'right' }}>Passed</th>
            <th style={{ textAlign: 'right' }}>Failed</th>
            <th style={{ textAlign: 'right' }}>P95</th>
            <th style={{ textAlign: 'right' }}>Cost</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} data-testid={`run-${r.id}`}>
              <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-3)' }}>{new Date(r.ran_at).toLocaleString()}</td>
              <td>{r.target_model}</td>
              <td style={{ textAlign: 'right', fontWeight: 600 }}>{fmtPassRate(r.summary.pass_rate)}</td>
              <td style={{ textAlign: 'right', color: 'var(--green)' }}>{r.summary.passed}</td>
              <td style={{ textAlign: 'right', color: 'var(--red)' }}>{r.summary.failed}</td>
              <td style={{ textAlign: 'right' }}>{r.summary.p95_latency_ms}ms</td>
              <td style={{ textAlign: 'right' }}>${(r.summary.total_cost_cents / 100).toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
