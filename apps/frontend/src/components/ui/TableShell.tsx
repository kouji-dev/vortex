import * as React from 'react'

type TableShellProps = {
  children: React.ReactNode
  className?: string
  containerRef?: React.RefObject<HTMLDivElement | null>
}

export function TableShell({ children, className, containerRef }: TableShellProps) {
  return (
    <div
      ref={containerRef}
      className={[
        'min-h-0 overflow-auto rounded-xl border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-950',
        className ?? '',
      ].join(' ')}
    >
      {children}
    </div>
  )
}

