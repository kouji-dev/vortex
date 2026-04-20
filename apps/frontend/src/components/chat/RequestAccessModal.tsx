import * as React from 'react'

import { Dialog, DialogBody } from '~/components/ui/Dialog'
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
    <Dialog
      open={open}
      onClose={onClose}
      title="Request access"
      labelledBy="req-access-title"
      size="md"
      footer={
        <>
          <button type="button" className="btn btn-sm" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn-sm btn-primary" onClick={submit}>
            Submit request
          </button>
        </>
      }
    >
      <DialogBody>
        <p className="text-sm" style={{ color: 'var(--ink-2)' }}>
          <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{model.display_name}</span>
          {model.description ? ` — ${model.description}` : null}
        </p>
        <div className="form-row mt-3 !mb-0">
          <label>Why do you need this model?</label>
          <textarea
            className="textarea"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Short justification for your admin or approver…"
            rows={4}
          />
        </div>
      </DialogBody>
    </Dialog>
  )
}
