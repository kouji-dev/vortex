import { X } from 'lucide-react'
import * as React from 'react'

import type { CatalogModelEntry } from '~/lib/chat-types'

type RequestAccessModalProps = {
  model: CatalogModelEntry | null
  open: boolean
  onClose: () => void
}

/**
 * UI-only: collects a reason for requesting model access. Backend wiring comes later.
 */
export function RequestAccessModal({ model, open, onClose }: RequestAccessModalProps) {
  const [reason, setReason] = React.useState('')

  React.useEffect(() => {
    if (open) setReason('')
  }, [open, model?.id])

  if (!open || model == null) return null

  const submit = () => {
    window.alert(
      `Request access (not sent yet — API pending)\n\nModel: ${model.display_name}\nReason:\n${reason.trim() || '(none)'}`,
    )
    onClose()
  }

  return (
    <div
      className="fixed inset-0 z-60 flex items-end justify-center bg-black/45 p-0 md:items-center md:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="req-access-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="flex max-h-[min(92dvh,calc(100dvh-env(safe-area-inset-bottom)))] w-full max-w-md flex-col overflow-hidden rounded-t-2xl border border-b-0 border-neutral-200 bg-white shadow-xl dark:border-neutral-700 dark:bg-neutral-950 md:max-h-[90vh] md:rounded-xl md:border-b"
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-neutral-300 dark:bg-neutral-700 md:hidden"
          aria-hidden
        />
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <div className="flex items-start justify-between gap-2">
            <h2 id="req-access-title" className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
              Request access
            </h2>
            <button
              type="button"
              className="rounded p-1 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-900"
              onClick={onClose}
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
            <span className="font-medium text-neutral-800 dark:text-neutral-200">{model.display_name}</span>
            {model.description ? ` — ${model.description}` : null}
          </p>
          <label className="mt-3 block text-xs font-medium text-neutral-500">Why do you need this model?</label>
          <textarea
            className="mt-1 min-h-[100px] w-full rounded-lg border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-900"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Short justification for your admin or approver…"
          />
          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              className="rounded-lg border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-600"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="button"
              className="rounded-lg bg-neutral-900 px-3 py-1.5 text-sm text-white dark:bg-neutral-100 dark:text-neutral-900"
              onClick={submit}
            >
              Submit request
            </button>
          </div>
        </div>
        <div className="shrink-0 pb-safe" aria-hidden />
      </div>
    </div>
  )
}
