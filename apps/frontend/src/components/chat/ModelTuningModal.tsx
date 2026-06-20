import { Select } from '~/components/ui/select'
import * as React from 'react'

import { Dialog, DialogBody } from '~/components/ui/Dialog'
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
  const r = model?.model_settings.reasoning
  const tempRange = model?.model_settings.sampling.temperature
  const tokRange = model?.model_settings.sampling.max_output_tokens

  const title = (
    <span className="flex flex-col leading-tight">
      <span className="mono text-[10px] font-medium uppercase tracking-wide" style={{ color: 'var(--ink-3)' }}>
        Session settings
      </span>
      <span>Model settings</span>
      {model && (
        <span className="mt-0.5 text-[11px] font-normal" style={{ color: 'var(--ink-3)' }}>
          {model.display_name}
        </span>
      )}
    </span>
  )

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      labelledBy="tuning-title"
      size="lg"
      footer={
        <>
          <button type="button" className="btn btn-sm" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn-sm btn-primary" onClick={onClose}>
            Done
          </button>
        </>
      }
    >
      <DialogBody>
        <p
          className="text-[11px]"
          style={{
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

        <div className="mt-4 flex flex-col gap-4">
          {model && r?.supported && r.efforts_available.length > 0 && (
            <div className="form-row !mb-0 !max-w-none">
              <label>Reasoning effort</label>
              <Select
                className="select"
                value={tuning.reasoningEffort}
                onChange={(e) =>
                  onTuningChange({ ...tuning, reasoningEffort: e.target.value })
                }
              size="sm"
              inline
              >
                {r.efforts_available.map((eff) => (
                  <option key={eff} value={eff}>
                    {eff}
                  </option>
                ))}
              </Select>
            </div>
          )}

          {model && tempRange != null && (
            <div className="form-row !mb-0 !max-w-none">
              <div
                className="mb-1 flex items-baseline justify-between text-xs font-medium"
                style={{ color: 'var(--ink)' }}
              >
                <span>Temperature</span>
                <span
                  className="mono text-[11px]"
                  style={{ color: 'var(--ink-3)', fontVariantNumeric: 'tabular-nums' }}
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
            <div className="form-row !mb-0 !max-w-none">
              <label>Max output tokens</label>
              <input
                type="number"
                className="input"
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
      </DialogBody>
    </Dialog>
  )
}
