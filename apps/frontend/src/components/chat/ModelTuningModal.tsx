import { X } from 'lucide-react'
import * as React from 'react'

import type { CatalogModelEntry } from '~/lib/chat-types'

export type SessionModelTuning = {
  reasoningEffort: string
  temperature: number
  maxOutputTokens: number
}

export function defaultTuningFromCatalog(m: CatalogModelEntry | null): SessionModelTuning {
  if (m == null) {
    return { reasoningEffort: 'default', temperature: 1, maxOutputTokens: 4096 }
  }
  const r = m.model_settings.reasoning
  const effort =
    r.default_effort ??
    r.efforts_available[0] ??
    'default'
  const t = m.model_settings.sampling.temperature
  const tok = m.model_settings.sampling.max_output_tokens
  return {
    reasoningEffort: effort,
    temperature: t?.default ?? 1,
    maxOutputTokens: tok.default,
  }
}

type ModelTuningModalProps = {
  model: CatalogModelEntry | null
  open: boolean
  onClose: () => void
  tuning: SessionModelTuning
  onTuningChange: (next: SessionModelTuning) => void
}

/**
 * Session-only sampling / reasoning UI. Values are not sent to the API yet (stream body
 * does not include temperature); shown so the product matches the target UX.
 */
export function ModelTuningModal({
  model,
  open,
  onClose,
  tuning,
  onTuningChange,
}: ModelTuningModalProps) {
  React.useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const r = model?.model_settings.reasoning
  const tempRange = model?.model_settings.sampling.temperature
  const tokRange = model?.model_settings.sampling.max_output_tokens

  return (
    <div
      className="fixed inset-0 z-60 flex items-end justify-center p-0 md:items-center md:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tuning-title"
      style={{ background: 'color-mix(in oklch, var(--ink) 45%, transparent)' }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="flex max-h-[min(92dvh,calc(100dvh-env(safe-area-inset-bottom)))] w-full max-w-lg flex-col overflow-hidden md:max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--panel)',
          border: '1px solid var(--line)',
          borderBottom: 'none',
          borderTopLeftRadius: 12,
          borderTopRightRadius: 12,
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        <style>{`@media (min-width: 768px) { .vx-tuning-shell { border-bottom: 1px solid var(--line); border-radius: var(--radius); } }`}</style>
        <div
          aria-hidden
          className="mx-auto mb-4 mt-2 h-1 w-10 shrink-0 rounded-full md:hidden"
          style={{ background: 'var(--line-2)' }}
        />

        {/* Header */}
        <div
          className="flex items-start justify-between gap-2 px-4 py-3"
          style={{ borderBottom: '1px solid var(--line-2)' }}
        >
          <div>
            <p className="mono" style={{ fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Session settings
            </p>
            <h2
              id="tuning-title"
              style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', margin: '2px 0 0' }}
            >
              Model settings
            </h2>
            {model && (
              <p style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 2 }}>{model.display_name}</p>
            )}
          </div>
          <button
            type="button"
            className="btn btn-xs"
            onClick={onClose}
            aria-label="Close"
            autoFocus
            style={{ padding: 4, width: 24, height: 24 }}
          >
            <X className="size-3" aria-hidden />
          </button>
        </div>

        {/* Body */}
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <p
            style={{
              fontSize: 11,
              color: 'var(--warn)',
              padding: '8px 10px',
              borderRadius: 4,
              background: 'color-mix(in oklch, var(--warn) 12%, var(--panel))',
              border: '1px solid color-mix(in oklch, var(--warn) 30%, var(--line))',
            }}
          >
            Applies to this browser session only. Sampling and reasoning are not yet persisted
            server-side — the portal still uses server defaults for generation.
          </p>

          <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
            {model && r?.supported && r.efforts_available.length > 0 && (
              <div className="form-row" style={{ marginBottom: 0, maxWidth: 'none' }}>
                <label>Reasoning effort</label>
                <select
                  className="select"
                  value={tuning.reasoningEffort}
                  onChange={(e) =>
                    onTuningChange({ ...tuning, reasoningEffort: e.target.value })
                  }
                >
                  {r.efforts_available.map((eff) => (
                    <option key={eff} value={eff}>
                      {eff}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {model && tempRange != null && (
              <div className="form-row" style={{ marginBottom: 0, maxWidth: 'none' }}>
                <div
                  className="mb-1 flex items-baseline justify-between"
                  style={{ fontSize: 12, fontWeight: 500, color: 'var(--ink)' }}
                >
                  <span>Temperature</span>
                  <span
                    className="mono"
                    style={{
                      fontSize: 11,
                      color: 'var(--ink-3)',
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {tuning.temperature.toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  className="w-full"
                  style={{ accentColor: 'var(--accent)' }}
                  min={tempRange.min}
                  max={tempRange.max}
                  step={0.01}
                  value={Math.min(tempRange.max, Math.max(tempRange.min, tuning.temperature))}
                  onChange={(e) =>
                    onTuningChange({
                      ...tuning,
                      temperature: Number.parseFloat(e.target.value),
                    })
                  }
                />
                <p className="hint">Allowed {tempRange.min}–{tempRange.max}</p>
              </div>
            )}

            {model && tokRange != null && (
              <div className="form-row" style={{ marginBottom: 0, maxWidth: 'none' }}>
                <label>Max output tokens</label>
                <input
                  type="number"
                  className="select"
                  style={{ backgroundImage: 'none', paddingRight: 10 }}
                  min={tokRange.min}
                  max={tokRange.max}
                  value={tuning.maxOutputTokens}
                  onChange={(e) =>
                    onTuningChange({
                      ...tuning,
                      maxOutputTokens: Number.parseInt(e.target.value, 10) || tokRange.min,
                    })
                  }
                />
                <p className="hint">Allowed {tokRange.min}–{tokRange.max}</p>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div
          className="flex justify-end gap-2 px-4 py-3"
          style={{ borderTop: '1px solid var(--line-2)' }}
        >
          <button type="button" className="btn btn-sm" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={onClose}>
            Done
          </button>
        </div>

        <div className="shrink-0" aria-hidden style={{ paddingBottom: 'env(safe-area-inset-bottom)' }} />
      </div>
    </div>
  )
}
