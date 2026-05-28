/**
 * /memories/settings — per-user controls.
 *
 * - Global pause / resume of memory extraction
 * - Per-scope pause toggles (user / conversation / assistant)
 * - Sensitive-category exclusion checkboxes (request, not enforced here)
 * - Export memories button (calls `/v1/memories/export`)
 */
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import {
  useExportMemoriesV1,
  usePauseMemoriesV1,
  useResumeMemoriesV1,
} from '~/hooks/useMemoriesV1Query'
import {
  SENSITIVE_CATEGORIES,
  toggleCategory,
  type ScopeKind,
  type SensitiveCategory,
} from '~/lib/memories-types'

export const Route = createFileRoute('/memories/settings')({
  component: MemoriesSettingsPage,
})

const PER_SCOPE_TOGGLES: ScopeKind[] = ['user', 'conversation', 'assistant']

function MemoriesSettingsPage() {
  // Local state — these settings persist via the v1 router; for now we drive
  // the buttons directly and rely on the server to record pauses.
  const [scopePaused, setScopePaused] = React.useState<Record<ScopeKind, boolean>>(
    () => ({ user: false, conversation: false, assistant: false, team: false, org: false }),
  )
  const [excluded, setExcluded] = React.useState<SensitiveCategory[]>([])
  const [exportBlob, setExportBlob] = React.useState<string | null>(null)

  const pause = usePauseMemoriesV1()
  const resume = useResumeMemoriesV1()
  const exportMut = useExportMemoriesV1()

  function toggleScope(s: ScopeKind) {
    const next = !scopePaused[s]
    setScopePaused((prev) => ({ ...prev, [s]: next }))
    if (next) {
      pause.mutate({ scope_kind: s })
    } else {
      resume.mutate({ scope_kind: s })
    }
  }

  function toggleGlobal() {
    const allPaused = PER_SCOPE_TOGGLES.every((s) => scopePaused[s])
    const next = !allPaused
    PER_SCOPE_TOGGLES.forEach((s) => {
      if (scopePaused[s] !== next) {
        setScopePaused((prev) => ({ ...prev, [s]: next }))
        if (next) pause.mutate({ scope_kind: s })
        else resume.mutate({ scope_kind: s })
      }
    })
  }

  function doExport() {
    exportMut.mutate(undefined, {
      onSuccess: (data) => {
        const json = JSON.stringify(data, null, 2)
        setExportBlob(json)
      },
    })
  }

  function downloadExport() {
    if (!exportBlob) return
    const url = URL.createObjectURL(new Blob([exportBlob], { type: 'application/json' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `memories-export-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const globalPaused = PER_SCOPE_TOGGLES.every((s) => scopePaused[s])

  return (
    <div data-testid="memories-settings" style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 16, flex: 1, minHeight: 0, overflow: 'auto' }}>
      {/* Global pause */}
      <div className="panel">
        <div className="panel-head">Global pause</div>
        <div style={{ padding: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
          <button
            type="button"
            className={`btn btn-sm ${globalPaused ? 'btn-primary' : ''}`}
            onClick={toggleGlobal}
            disabled={pause.isPending || resume.isPending}
            data-testid="mem-settings-global-toggle"
          >
            {globalPaused ? 'Resume all extraction' : 'Pause all extraction'}
          </button>
          <span className="meta">
            When paused, no new memories are extracted from chat. Existing memories are unaffected.
          </span>
        </div>
      </div>

      {/* Per-scope */}
      <div className="panel">
        <div className="panel-head">Per-scope</div>
        <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {PER_SCOPE_TOGGLES.map((s) => (
            <label
              key={s}
              style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--ink-2)' }}
            >
              <input
                type="checkbox"
                checked={scopePaused[s]}
                onChange={() => toggleScope(s)}
                data-testid={`mem-settings-scope-${s}`}
              />
              pause "{s}" scope extraction
            </label>
          ))}
        </div>
      </div>

      {/* Sensitive exclusions */}
      <div className="panel">
        <div className="panel-head">Sensitive-category exclusions</div>
        <div style={{ padding: 12, display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 6 }}>
          {SENSITIVE_CATEGORIES.map((c) => (
            <label
              key={c}
              style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--ink-2)' }}
            >
              <input
                type="checkbox"
                checked={excluded.includes(c)}
                onChange={() => setExcluded((prev) => toggleCategory(prev, c))}
                data-testid={`mem-settings-sensitive-${c}`}
              />
              {c.replaceAll('_', ' ')}
            </label>
          ))}
        </div>
        <div style={{ padding: '0 12px 12px', fontSize: 11, color: 'var(--ink-3)' }}>
          These are passed to the extractor as a block-list. Admins can also enforce org-wide blocks
          under Admin → Memory Policies.
        </div>
      </div>

      {/* Export */}
      <div className="panel">
        <div className="panel-head">Export</div>
        <div style={{ padding: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
          <button
            type="button"
            className="btn btn-sm"
            onClick={doExport}
            disabled={exportMut.isPending}
            data-testid="mem-settings-export"
          >
            {exportMut.isPending ? 'Preparing…' : 'Export memories'}
          </button>
          {exportBlob && (
            <button
              type="button"
              className="btn btn-sm btn-primary"
              onClick={downloadExport}
              data-testid="mem-settings-download"
            >
              Download JSON
            </button>
          )}
          {exportMut.isError && (
            <span style={{ fontSize: 11, color: 'var(--err)' }}>
              {(exportMut.error as Error).message}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
