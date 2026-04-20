import { ArrowUp, Square } from 'lucide-react'

type SendStopButtonProps = {
  streaming: boolean
  onSubmit: () => void
  onStop: () => void
  canSubmit: boolean
  sendTestId?: string
  iconSize?: 'sm' | 'md'
}

export function SendStopButton({
  streaming,
  onSubmit,
  onStop,
  canSubmit,
  sendTestId,
  iconSize = 'sm',
}: SendStopButtonProps) {
  const iconClass = iconSize === 'md' ? 'size-3.5' : 'size-3'
  if (streaming) {
    return (
      <button
        type="button"
        className="btn btn-sm"
        style={{ color: 'var(--err)' }}
        aria-label="Stop generating"
        onClick={onStop}
      >
        <Square className={iconClass} strokeWidth={2} fill="currentColor" aria-hidden />
        Stop
      </button>
    )
  }
  return (
    <button
      type="button"
      className="btn btn-primary btn-sm"
      disabled={!canSubmit}
      aria-label="Send message"
      data-testid={sendTestId}
      onClick={onSubmit}
    >
      <ArrowUp className={iconClass} strokeWidth={2.5} aria-hidden />
      Send
    </button>
  )
}
