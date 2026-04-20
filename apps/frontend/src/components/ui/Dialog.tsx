import { X } from 'lucide-react'
import * as React from 'react'

const SCRIM_STYLE = {
  background: 'color-mix(in oklch, var(--ink) 45%, transparent)',
}

type DialogSize = 'sm' | 'md' | 'lg'

const MAX_WIDTH: Record<DialogSize, string> = {
  sm: '24rem',
  md: '32rem',
  lg: '40rem',
}

type DialogProps = {
  open: boolean
  onClose: () => void
  /** Accessible title rendered in the header. Omit to provide your own <DialogHeader>. */
  title?: React.ReactNode
  /** aria-labelledby id. If omitted, one is generated. */
  labelledBy?: string
  size?: DialogSize
  /** Close on scrim click. Default true. */
  dismissOnScrimClick?: boolean
  /** Close on Escape. Default true. */
  dismissOnEscape?: boolean
  /** Footer row rendered at the bottom of the panel. */
  footer?: React.ReactNode
  children?: React.ReactNode
  /** Extra class on the panel (e.g. wider form dialogs). */
  panelClassName?: string
  /** Override the default close button in the header. */
  hideCloseButton?: boolean
}

export function Dialog({
  open,
  onClose,
  title,
  labelledBy,
  size = 'md',
  dismissOnScrimClick = true,
  dismissOnEscape = true,
  footer,
  children,
  panelClassName,
  hideCloseButton,
}: DialogProps) {
  const autoId = React.useId()
  const titleId = labelledBy ?? (title ? `dialog-title-${autoId}` : undefined)

  React.useEffect(() => {
    if (!open || !dismissOnEscape) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, dismissOnEscape, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-60 flex items-end justify-center p-0 md:items-center md:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      style={SCRIM_STYLE}
      onClick={(e) => {
        if (!dismissOnScrimClick) return
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className={`flex max-h-[min(92dvh,calc(100dvh-env(safe-area-inset-bottom)))] w-full flex-col overflow-hidden rounded-t-2xl border md:max-h-[90vh] md:rounded-xl ${panelClassName ?? ''}`}
        style={{
          background: 'var(--panel)',
          borderColor: 'var(--line)',
          boxShadow: 'var(--shadow-md)',
          maxWidth: MAX_WIDTH[size],
        }}
      >
        {title != null && (
          <DialogHeader titleId={titleId} onClose={hideCloseButton ? undefined : onClose}>
            {title}
          </DialogHeader>
        )}
        {children}
        {footer != null && <DialogFooter>{footer}</DialogFooter>}
      </div>
    </div>
  )
}

type DialogHeaderProps = {
  children: React.ReactNode
  titleId?: string
  onClose?: () => void
}

export function DialogHeader({ children, titleId, onClose }: DialogHeaderProps) {
  return (
    <div
      className="flex shrink-0 items-center justify-between px-4 py-3"
      style={{ borderBottom: '1px solid var(--line)' }}
    >
      <h2
        id={titleId}
        className="text-sm font-semibold"
        style={{ color: 'var(--ink)' }}
      >
        {children}
      </h2>
      {onClose && (
        <button
          type="button"
          className="btn btn-sm btn-ghost"
          aria-label="Close"
          onClick={onClose}
          style={{ padding: '0 6px' }}
        >
          <X className="size-3.5" strokeWidth={2} aria-hidden />
        </button>
      )}
    </div>
  )
}

export function DialogBody({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={`flex-1 overflow-y-auto px-4 py-3 ${className ?? ''}`}>{children}</div>
  )
}

export function DialogFooter({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={`flex shrink-0 items-center justify-end gap-2 px-4 py-3 ${className ?? ''}`}
      style={{
        borderTop: '1px solid var(--line)',
        background: 'var(--bg-2)',
      }}
    >
      {children}
    </div>
  )
}
