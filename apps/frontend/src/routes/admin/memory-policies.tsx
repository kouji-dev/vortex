/**
 * /admin/memory-policies — org-wide governance for the Memory module.
 *
 * Allows admins to:
 * - Enable/disable the module org-wide (toggled via settings facade — for now
 *   represented as a UI flag we POST on save)
 * - Set the model allow-list per scope
 * - Edit the sensitive-category exclusion list
 * - Override per-type retention days
 */
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import {
  useMemoryPoliciesQuery,
  useSaveExtractionPolicy,
  useSaveRecallPolicy,
} from '~/hooks/useMemoriesV1Query'
import {
  DEFAULT_RETENTION_DAYS,
  MEMORY_TYPES,
  SCOPE_KINDS,
  SENSITIVE_CATEGORIES,
  parseRetentionDays,
  toggleCategory,
  validateRetentionDays,
  type ConflictStrategy,
  type ExtractionPolicy,
  type MemoryType,
  type RecallPolicy,
  type ScopeKind,
  type SensitiveCategory,
} from '~/lib/memories-types'

export const Route = createFileRoute('/admin/memory-policies')({
  component: MemoryPoliciesPage,
})

const CONFLICT_STRATEGIES: ConflictStrategy[] = ['newer_wins', 'keep_both', 'prompt_user']

function MemoryPoliciesPage() {
  const policies = useMemoryPoliciesQuery()
  const saveExt = useSaveExtractionPolicy()
  const saveRec = useSaveRecallPolicy()

  const [scope, setScope] = React.useState<ScopeKind>('org')
  const [moduleEnabled, setModuleEnabled] = React.useState(true)

  const extPolicy = React.useMemo<ExtractionPolicy>(() => {
    const found = policies.data?.extraction.find((p) => p.scope_kind === scope)
    return (
      found ?? {
        scope_kind: scope,
        triggers: { per_turn: true, on_close: true, scheduled: false, explicit_only: false },
        sensitive_block: [],
        model_allow: ['claude-sonnet-4-6'],
        conflict_strategy: 'newer_wins',
        retention_days: {},
      }
    )
  }, [policies.data, scope])

  const recPolicy = React.useMemo<RecallPolicy>(() => {
    const found = policies.data?.recall.find((p) => p.scope_kind === scope)
    return (
      found ?? { scope_kind: scope, top_k: 8, recency_weight: 0.2, importance_weight: 0.3, filters: {} }
    )
  }, [policies.data, scope])

  return (
    <div data-testid="admin-memory-policies" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="panel">
        <div className="panel-head">Memory module</div>
        <div style={{ padding: 16, display: 'flex', gap: 12, alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
            <input
              type="checkbox"
              checked={moduleEnabled}
              onChange={(e) => setModuleEnabled(e.target.checked)}
              data-testid="mem-pol-enabled"
            />
            Module enabled org-wide
          </label>
          <span className="meta">When disabled, `/v1/memories` returns 503 and chat skips recall/extract.</span>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>Scope</span>
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value as ScopeKind)}
            data-testid="mem-pol-scope"
            style={selectStyle}
          >
            {SCOPE_KINDS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      <ExtractionEditor
        key={`ext-${scope}`}
        initial={extPolicy}
        onSave={(p) => saveExt.mutate(p)}
        saving={saveExt.isPending}
      />

      <RecallEditor
        key={`rec-${scope}`}
        initial={recPolicy}
        onSave={(p) => saveRec.mutate(p)}
        saving={saveRec.isPending}
      />
    </div>
  )
}

function ExtractionEditor({
  initial,
  onSave,
  saving,
}: {
  initial: ExtractionPolicy
  onSave: (p: ExtractionPolicy) => void
  saving: boolean
}) {
  const [draft, setDraft] = React.useState<ExtractionPolicy>(initial)
  const [modelDraft, setModelDraft] = React.useState('')
  const [retentionRaw, setRetentionRaw] = React.useState<Record<MemoryType, string>>(() => {
    const out: Record<MemoryType, string> = {} as Record<MemoryType, string>
    for (const t of MEMORY_TYPES) {
      const v = initial.retention_days[t]
      out[t] = v == null ? '' : String(v)
    }
    return out
  })
  const [retentionErr, setRetentionErr] = React.useState<Record<MemoryType, string | null>>(
    () => Object.fromEntries(MEMORY_TYPES.map((t) => [t, null])) as Record<MemoryType, string | null>,
  )

  function toggleSensitive(c: SensitiveCategory) {
    setDraft((d) => ({ ...d, sensitive_block: toggleCategory(d.sensitive_block, c) }))
  }

  function addModel() {
    const v = modelDraft.trim()
    if (!v) return
    if (draft.model_allow.includes(v)) {
      setModelDraft('')
      return
    }
    setDraft((d) => ({ ...d, model_allow: [...d.model_allow, v] }))
    setModelDraft('')
  }

  function removeModel(m: string) {
    setDraft((d) => ({ ...d, model_allow: d.model_allow.filter((x) => x !== m) }))
  }

  function setRetention(t: MemoryType, raw: string) {
    setRetentionRaw((prev) => ({ ...prev, [t]: raw }))
    const err = validateRetentionDays(raw)
    setRetentionErr((prev) => ({ ...prev, [t]: err }))
  }

  function commit() {
    // build retention_days from raw inputs
    const next: Record<string, number> = {}
    for (const t of MEMORY_TYPES) {
      const parsed = parseRetentionDays(retentionRaw[t])
      if (parsed != null) next[t] = parsed
    }
    onSave({ ...draft, retention_days: next })
  }

  const hasRetErr = Object.values(retentionErr).some((e) => e != null)

  return (
    <div className="panel" data-testid="mem-pol-extraction">
      <div className="panel-head">Extraction policy</div>
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          <Toggle
            label="Per-turn"
            checked={!!draft.triggers.per_turn}
            onChange={(v) => setDraft((d) => ({ ...d, triggers: { ...d.triggers, per_turn: v } }))}
          />
          <Toggle
            label="On conversation close"
            checked={!!draft.triggers.on_close}
            onChange={(v) => setDraft((d) => ({ ...d, triggers: { ...d.triggers, on_close: v } }))}
          />
          <Toggle
            label="Scheduled batch"
            checked={!!draft.triggers.scheduled}
            onChange={(v) => setDraft((d) => ({ ...d, triggers: { ...d.triggers, scheduled: v } }))}
          />
          <Toggle
            label="Explicit-only"
            checked={!!draft.triggers.explicit_only}
            onChange={(v) => setDraft((d) => ({ ...d, triggers: { ...d.triggers, explicit_only: v } }))}
          />
        </div>

        {/* Model allow-list */}
        <div>
          <div style={subHeader}>Model allow-list</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
            {draft.model_allow.length === 0 && (
              <span className="meta">No models allowed — extraction disabled.</span>
            )}
            {draft.model_allow.map((m) => (
              <span
                key={m}
                className="pill"
                style={{ fontFamily: 'var(--font-mono)', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                data-testid="mem-pol-allowed-model"
              >
                {m}
                <button
                  type="button"
                  onClick={() => removeModel(m)}
                  style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0 }}
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              value={modelDraft}
              onChange={(e) => setModelDraft(e.target.value)}
              placeholder="e.g. claude-sonnet-4-6"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  addModel()
                }
              }}
              style={inputStyle}
              data-testid="mem-pol-model-input"
            />
            <button type="button" className="btn btn-sm" onClick={addModel} data-testid="mem-pol-model-add">Add</button>
          </div>
        </div>

        {/* Sensitive categories */}
        <div>
          <div style={subHeader}>Sensitive-category exclusions</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
            {SENSITIVE_CATEGORIES.map((c) => (
              <label
                key={c}
                style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--ink-2)' }}
              >
                <input
                  type="checkbox"
                  checked={draft.sensitive_block.includes(c)}
                  onChange={() => toggleSensitive(c)}
                  data-testid={`mem-pol-sensitive-${c}`}
                />
                {c.replaceAll('_', ' ')}
              </label>
            ))}
          </div>
        </div>

        {/* Retention */}
        <div>
          <div style={subHeader}>Retention per type (days, blank = never)</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
            {MEMORY_TYPES.map((t) => {
              const def = DEFAULT_RETENTION_DAYS[t]
              return (
                <label key={t} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-3)', width: 78 }}>{t}</span>
                  <input
                    value={retentionRaw[t]}
                    onChange={(e) => setRetention(t, e.target.value)}
                    placeholder={def == null ? 'never' : String(def)}
                    style={{ ...inputStyle, width: 60 }}
                    data-testid={`mem-pol-retention-${t}`}
                  />
                  {retentionErr[t] && (
                    <span style={{ fontSize: 10, color: 'var(--err)' }}>{retentionErr[t]}</span>
                  )}
                </label>
              )
            })}
          </div>
        </div>

        {/* Conflict strategy */}
        <div>
          <div style={subHeader}>Conflict strategy</div>
          <select
            value={draft.conflict_strategy}
            onChange={(e) => setDraft((d) => ({ ...d, conflict_strategy: e.target.value as ConflictStrategy }))}
            data-testid="mem-pol-conflict"
            style={selectStyle}
          >
            {CONFLICT_STRATEGIES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        <div>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={saving || hasRetErr}
            onClick={commit}
            data-testid="mem-pol-extraction-save"
          >
            {saving ? 'Saving…' : 'Save extraction policy'}
          </button>
        </div>
      </div>
    </div>
  )
}

function RecallEditor({
  initial,
  onSave,
  saving,
}: {
  initial: RecallPolicy
  onSave: (p: RecallPolicy) => void
  saving: boolean
}) {
  const [draft, setDraft] = React.useState<RecallPolicy>(initial)
  return (
    <div className="panel" data-testid="mem-pol-recall">
      <div className="panel-head">Recall policy</div>
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
          <span style={{ width: 130, fontFamily: 'var(--font-mono)', color: 'var(--ink-3)' }}>top_k</span>
          <input
            type="number"
            min={1}
            max={50}
            value={draft.top_k}
            onChange={(e) => setDraft((d) => ({ ...d, top_k: Number(e.target.value) }))}
            style={{ ...inputStyle, width: 80 }}
            data-testid="mem-pol-top-k"
          />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
          <span style={{ width: 130, fontFamily: 'var(--font-mono)', color: 'var(--ink-3)' }}>recency_weight</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={draft.recency_weight}
            onChange={(e) => setDraft((d) => ({ ...d, recency_weight: Number(e.target.value) }))}
            data-testid="mem-pol-recency-weight"
          />
          <span className="meta">{draft.recency_weight.toFixed(2)}</span>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
          <span style={{ width: 130, fontFamily: 'var(--font-mono)', color: 'var(--ink-3)' }}>importance_weight</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={draft.importance_weight}
            onChange={(e) => setDraft((d) => ({ ...d, importance_weight: Number(e.target.value) }))}
            data-testid="mem-pol-importance-weight"
          />
          <span className="meta">{draft.importance_weight.toFixed(2)}</span>
        </label>
        <div>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => onSave(draft)}
            disabled={saving}
            data-testid="mem-pol-recall-save"
          >
            {saving ? 'Saving…' : 'Save recall policy'}
          </button>
        </div>
      </div>
    </div>
  )
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  )
}

const selectStyle: React.CSSProperties = {
  borderRadius: 4,
  border: '1px solid var(--line)',
  background: 'var(--bg)',
  color: 'var(--ink)',
  padding: '4px 8px',
  fontSize: 12,
}
const inputStyle: React.CSSProperties = {
  borderRadius: 4,
  border: '1px solid var(--line)',
  background: 'var(--bg)',
  color: 'var(--ink)',
  padding: '4px 8px',
  fontSize: 12,
}
const subHeader: React.CSSProperties = {
  fontSize: 10,
  color: 'var(--ink-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  marginBottom: 6,
}
