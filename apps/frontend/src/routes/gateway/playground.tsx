// apps/frontend/src/routes/gateway/playground.tsx
// Gateway → Playground (J8): prompt editor + model picker + diff compare 2-4.
// Monaco is not in deps — use a plain textarea editor (lazy-load slot reserved).
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'
import { authorizedFetch } from '~/lib/authorizedFetch'
import { clampModelPicks, summarize, wordDiff } from '~/lib/playground-logic'
import type { ModelInfo, PlaygroundRunResult } from '~/lib/gateway-types'

export const Route = createFileRoute('/gateway/playground')({
  component: PlaygroundPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

// Monaco-ready slot — kept as a plain textarea today; swap to lazy-import
// `@monaco-editor/react` when added to deps. Keeping it sync avoids a Suspense
// boundary while preserving the upgrade path.
function PromptEditor({
  value,
  onChange,
}: {
  value: string
  onChange: (s: string) => void
}) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      rows={12}
      style={{
        width: '100%',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        padding: 10,
        border: '1px solid var(--line)',
        borderRadius: 4,
        background: 'var(--bg)',
        color: 'var(--ink)',
        resize: 'vertical',
      }}
      data-testid="prompt-editor"
    />
  )
}

function PlaygroundPage() {
  const [prompt, setPrompt] = React.useState('')
  const [system, setSystem] = React.useState('')
  const [temperature, setTemperature] = React.useState(0.7)
  const [models, setModels] = React.useState<ModelInfo[]>([])
  const [picked, setPicked] = React.useState<string[]>([])
  const [results, setResults] = React.useState<PlaygroundRunResult[]>([])
  const [running, setRunning] = React.useState(false)
  const [showDiff, setShowDiff] = React.useState(false)

  React.useEffect(() => {
    authorizedFetch(`${API_BASE}/api/v1/models`)
      .then((r) => r.json())
      .then((d) => Array.isArray(d?.data) && setModels(d.data))
      .catch(() => null)
  }, [])

  function togglePick(modelId: string) {
    setPicked((prev) =>
      prev.includes(modelId)
        ? prev.filter((m) => m !== modelId)
        : clampModelPicks([...prev, modelId]),
    )
  }

  async function run() {
    if (picked.length === 0 || !prompt) return
    setRunning(true)
    setResults([])
    try {
      const res = await authorizedFetch(`${API_BASE}/api/v1/gateway/playground/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, system, temperature, models: picked }),
      })
      const data = await res.json()
      if (Array.isArray(data?.results)) setResults(data.results)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="main-inner" data-testid="gateway-playground">
      <div className="screen-head">
        <div>
          <h1>Playground</h1>
          <div className="sub">Prompt · model picker · side-by-side diff</div>
        </div>
      </div>

      <div className="gov-grid" style={{ gridTemplateColumns: '1fr 320px', gap: 16 }}>
        <div className="panel">
          <div className="panel-head">Prompt</div>
          <div className="panel-body" style={{ padding: 12 }}>
            <label style={{ fontSize: 10, color: 'var(--ink-3)' }}>System</label>
            <textarea
              value={system}
              onChange={(e) => setSystem(e.target.value)}
              rows={2}
              style={{ width: '100%', fontSize: 11, fontFamily: 'var(--font-mono)', padding: 6, marginBottom: 10, border: '1px solid var(--line)', borderRadius: 3, background: 'var(--bg)', color: 'var(--ink)' }}
              data-testid="system-input"
            />
            <label style={{ fontSize: 10, color: 'var(--ink-3)' }}>User prompt</label>
            <PromptEditor value={prompt} onChange={setPrompt} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10 }}>
              <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>
                Temperature
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  value={temperature}
                  onChange={(e) => setTemperature(parseFloat(e.target.value) || 0)}
                  style={{ marginLeft: 6, width: 60, fontSize: 11, padding: 3, border: '1px solid var(--line)', borderRadius: 3, background: 'var(--bg)', color: 'var(--ink)' }}
                />
              </label>
              <button
                className="btn btn-primary"
                onClick={run}
                disabled={running || picked.length === 0 || !prompt}
                data-testid="run-button"
              >
                {running ? 'Running…' : `Run on ${picked.length || 0}`}
              </button>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Models ({picked.length}/4)</span>
            <label style={{ fontSize: 10, color: 'var(--ink-3)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <input type="checkbox" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} />
              diff
            </label>
          </div>
          <div className="panel-body" style={{ padding: 8, maxHeight: 400, overflow: 'auto' }}>
            {models.map((m) => (
              <label
                key={m.id}
                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: 4, fontSize: 11, cursor: 'pointer' }}
              >
                <input
                  type="checkbox"
                  checked={picked.includes(m.model_id)}
                  onChange={() => togglePick(m.model_id)}
                  disabled={!picked.includes(m.model_id) && picked.length >= 4}
                  data-testid={`pick-${m.model_id}`}
                />
                <span style={{ fontFamily: 'var(--font-mono)' }}>{m.display_name || m.model_id}</span>
                <span style={{ marginLeft: 'auto', color: 'var(--ink-3)' }}>{m.provider}</span>
              </label>
            ))}
            {models.length === 0 && <p style={{ fontSize: 11, color: 'var(--ink-3)', padding: 8 }}>No models.</p>}
          </div>
        </div>
      </div>

      {results.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="panel-head">Results</div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: `repeat(${Math.min(results.length, 2)}, 1fr)`,
              gap: 12,
            }}
          >
            {results.map((r, i) => (
              <ResultCard key={r.model + i} r={r} compareTo={showDiff && i > 0 ? results[0].output : null} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ResultCard({ r, compareTo }: { r: PlaygroundRunResult; compareTo: string | null }) {
  const diff = compareTo ? wordDiff(compareTo, r.output) : null
  return (
    <div className="panel" data-testid={`result-${r.model}`}>
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span style={{ fontFamily: 'var(--font-mono)' }}>{r.model}</span>
        <span style={{ fontSize: 10, color: 'var(--ink-3)' }}>{summarize(r)}</span>
      </div>
      <div className="panel-body" style={{ padding: 12 }}>
        {r.error && <p style={{ color: 'var(--red)', fontSize: 11 }}>{r.error}</p>}
        {diff ? (
          <pre style={{ fontSize: 11, fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', margin: 0 }}>
            {diff.map((t, i) => (
              <span
                key={i}
                style={{
                  background: t.op === 'add' ? 'rgba(0,200,0,0.15)' : t.op === 'remove' ? 'rgba(220,0,0,0.15)' : undefined,
                  textDecoration: t.op === 'remove' ? 'line-through' : undefined,
                }}
              >
                {t.text}
              </span>
            ))}
          </pre>
        ) : (
          <pre style={{ fontSize: 11, fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', margin: 0 }}>{r.output}</pre>
        )}
      </div>
    </div>
  )
}
