/**
 * Workers → Pools → Template editor.
 *
 * Edits the pool's ``settings_json`` blob — a free-form record used by
 * agent loop / sandbox / tool configuration. Validation + dirty-check
 * + diff logic live in ``~/lib/pool-template-logic`` so they unit-test
 * without React.
 */
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import * as api from '~/lib/workers-api'
import {
  formatSettings,
  isDirty,
  validateSettingsJson,
} from '~/lib/pool-template-logic'

export const Route = createFileRoute('/workers/pools/$id/template')({
  component: TemplateEditorPage,
})

function TemplateEditorPage() {
  const { id } = Route.useParams()
  const qc = useQueryClient()
  const navigate = useNavigate()

  const poolsQ = useQuery({
    queryKey: ['workers', 'pools'],
    queryFn: api.listPools,
  })
  const pool = (poolsQ.data ?? []).find((p) => p.id === id)

  const [draft, setDraft] = React.useState('')
  const [loaded, setLoaded] = React.useState(false)

  // Seed the textarea once the pool row arrives.
  React.useEffect(() => {
    if (!loaded && pool) {
      setDraft(formatSettings(pool.settings as Record<string, unknown>))
      setLoaded(true)
    }
  }, [pool, loaded])

  const saveMut = useMutation({
    mutationFn: async () => {
      const v = validateSettingsJson(draft)
      if (!v.ok) throw new Error(v.error)
      return api.updatePool(id, { settings: v.value })
    },
    onSuccess: (updated) => {
      qc.setQueryData<typeof poolsQ.data>(['workers', 'pools'], (old) =>
        (old ?? []).map((p) => (p.id === id ? updated : p)),
      )
      // Re-format on save so the textarea reflects the canonical value.
      setDraft(formatSettings(updated.settings as Record<string, unknown>))
    },
  })

  const validation = React.useMemo(() => validateSettingsJson(draft), [draft])
  const dirty = React.useMemo(
    () => isDirty(draft, (pool?.settings as Record<string, unknown>) ?? {}),
    [draft, pool],
  )

  if (poolsQ.isPending) {
    return (
      <div data-testid="wk-pool-template-editor" style={{ padding: 24 }}>
        Loading…
      </div>
    )
  }

  if (!pool) {
    return (
      <div data-testid="wk-pool-template-editor" style={{ padding: 24 }}>
        <p>Pool not found.</p>
        <Link to="/workers/pools" className="btn btn-sm">
          Back to pools
        </Link>
      </div>
    )
  }

  return (
    <div data-testid="wk-pool-template-editor" style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
        <h2 style={{ margin: 0, fontSize: 14 }}>
          Template — <span style={{ fontFamily: 'var(--font-mono)' }}>{pool.name}</span>
        </h2>
        <button
          className="btn btn-sm"
          style={{ marginLeft: 'auto' }}
          onClick={() => navigate({ to: '/workers/pools' })}
          data-testid="wk-pool-template-back"
        >
          ← Back
        </button>
      </div>

      <div className="wk-pane" style={{ padding: 12 }}>
        <p style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 0 }}>
          Free-form JSON object. Used by agent loop / sandbox / tool config.
          Keys are pool-specific; the server validates shape on save.
        </p>
        <textarea
          data-testid="wk-pool-template-textarea"
          spellCheck={false}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          style={{
            width: '100%',
            minHeight: 360,
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            padding: 10,
            borderRadius: 6,
          }}
        />
        {!validation.ok && (
          <div
            data-testid="wk-pool-template-error"
            style={{ color: 'var(--red, #c43c3c)', fontSize: 11, marginTop: 6 }}
          >
            {validation.error}
          </div>
        )}
        {saveMut.error && (
          <div
            data-testid="wk-pool-template-save-error"
            style={{ color: 'var(--red, #c43c3c)', fontSize: 11, marginTop: 6 }}
          >
            {(saveMut.error as Error).message}
          </div>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
          <button
            className="btn btn-sm"
            disabled={!dirty || saveMut.isPending}
            onClick={() => {
              if (pool) setDraft(formatSettings(pool.settings as Record<string, unknown>))
            }}
            data-testid="wk-pool-template-reset"
          >
            Reset
          </button>
          <button
            className="btn btn-sm btn-primary"
            disabled={!dirty || !validation.ok || saveMut.isPending}
            onClick={() => saveMut.mutate()}
            data-testid="wk-pool-template-save"
          >
            {saveMut.isPending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
