import * as React from 'react'

export interface ActiveKbSummary {
  id: number
  name: string
  document_count?: number
  last_synced_at?: string | null
}

export interface KbsToolbarButtonProps {
  activeCount: number
  activeKbs?: ActiveKbSummary[]
  onOpen: () => void
}

function formatLastSynced(lastSyncedAt: string): string {
  const date = new Date(lastSyncedAt)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60_000)
  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  return `${diffDays}d ago`
}

export function KbsToolbarButton({ activeCount, activeKbs, onOpen }: KbsToolbarButtonProps) {
  const [hovered, setHovered] = React.useState(false)
  const isActive = activeCount > 0

  return (
    <span
      className="relative inline-flex items-center"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        type="button"
        onClick={onOpen}
        className={[
          'flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs transition-colors',
          isActive
            ? 'border-blue-500 text-blue-400 hover:bg-blue-500/10'
            : 'border-neutral-600 text-neutral-400 hover:border-neutral-500 hover:text-neutral-300',
        ].join(' ')}
        aria-label={isActive ? `${activeCount} knowledge base${activeCount !== 1 ? 's' : ''} active` : 'Knowledge bases'}
      >
        <span>📚</span>
        <span>{isActive ? `${activeCount} KBs active` : 'KBs'}</span>
      </button>

      {/* Hover popover — only shown when KBs are active */}
      {isActive && hovered && (
        <div
          className="absolute bottom-full left-1/2 z-50 mb-2 w-72 -translate-x-1/2 rounded-lg border border-neutral-700 bg-neutral-800 p-3 shadow-xl"
          role="tooltip"
        >
          {/* Arrow */}
          <div className="absolute -bottom-1.5 left-1/2 -translate-x-1/2">
            <div className="h-2.5 w-2.5 rotate-45 border-b border-r border-neutral-700 bg-neutral-800" />
          </div>

          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-neutral-400">
            Active knowledge bases
          </p>

          {activeKbs && activeKbs.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {activeKbs.map((kb) => (
                <li key={kb.id} className="flex flex-col gap-0.5">
                  <div className="flex items-center gap-1.5">
                    {/* Green status dot */}
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-green-500" />
                    <span className="text-xs font-medium text-neutral-100">{kb.name}</span>
                  </div>
                  <div className="ml-3 flex flex-wrap gap-x-3 text-[10px] text-neutral-400">
                    {kb.document_count !== undefined && (
                      <span>
                        <span className="text-neutral-300">{kb.document_count}</span> doc
                        {kb.document_count !== 1 ? 's' : ''}
                      </span>
                    )}
                    {kb.last_synced_at && (
                      <span>synced {formatLastSynced(kb.last_synced_at)}</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-neutral-400">{activeCount} KB{activeCount !== 1 ? 's' : ''} active</p>
          )}

          <p className="mt-3 border-t border-neutral-700 pt-2 text-[10px] text-neutral-500">
            Hover the 📚 icon on AI responses to see which KB was used
          </p>
        </div>
      )}
    </span>
  )
}
