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
  if (!open) return null

  const r = model?.model_settings.reasoning
  const tempRange = model?.model_settings.sampling.temperature
  const tokRange = model?.model_settings.sampling.max_output_tokens

  return (
    <div
      className="fixed inset-0 z-60 flex items-end justify-center bg-black/45 p-0 md:items-center md:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tuning-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="flex max-h-[min(92dvh,calc(100dvh-env(safe-area-inset-bottom)))] w-full max-w-lg flex-col overflow-hidden rounded-t-2xl border border-b-0 border-neutral-200 bg-white shadow-xl dark:border-neutral-700 dark:bg-neutral-950 md:max-h-[90vh] md:rounded-xl md:border-b"
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="mx-auto mb-4 mt-2 h-1 w-10 shrink-0 rounded-full bg-neutral-300 dark:bg-neutral-700 md:hidden"
          aria-hidden
        />
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h2 id="tuning-title" className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
                Model settings
              </h2>
              {model && (
                <p className="mt-0.5 text-sm text-neutral-500">{model.display_name}</p>
              )}
            </div>
            <button
              type="button"
              className="rounded p-1 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-900"
              onClick={onClose}
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <p className="mt-2 rounded-md bg-amber-50 px-2 py-1.5 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
            These options apply in this browser session only. API persistence for sampling and
            reasoning is not wired yet — the portal still uses server defaults for generation.
          </p>

          <div className="mt-4 space-y-4">
            {model && r?.supported && r.efforts_available.length > 0 && (
              <div>
                <label className="mb-1 block text-xs font-medium text-neutral-500">Reasoning effort</label>
                <select
                  className="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-900"
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
              <div>
                <div className="mb-1 flex justify-between text-xs font-medium text-neutral-500">
                  <span>Temperature</span>
                  <span className="tabular-nums text-neutral-400">{tuning.temperature.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  className="w-full accent-neutral-800 dark:accent-neutral-200"
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
                <p className="mt-0.5 text-[10px] text-neutral-400">
                  Allowed {tempRange.min}–{tempRange.max}
                </p>
              </div>
            )}

            {model && tokRange != null && (
              <div>
                <label className="mb-1 block text-xs font-medium text-neutral-500">
                  Max output tokens
                </label>
                <input
                  type="number"
                  className="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-900"
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
                <p className="mt-0.5 text-[10px] text-neutral-400">
                  Allowed {tokRange.min}–{tokRange.max}
                </p>
              </div>
            )}
          </div>

          <div className="mt-6 flex justify-end">
            <button
              type="button"
              className="rounded-lg bg-neutral-900 px-4 py-2 text-sm text-white dark:bg-neutral-100 dark:text-neutral-900"
              onClick={onClose}
            >
              Done
            </button>
          </div>
        </div>
        <div className="shrink-0 pb-safe" aria-hidden />
      </div>
    </div>
  )
}
