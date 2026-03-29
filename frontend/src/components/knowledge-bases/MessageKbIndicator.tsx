import * as React from 'react'

import type { UsedKbEntry } from '~/lib/chat-types'

export interface MessageKbIndicatorProps {
  usedKbs: UsedKbEntry[]
}

export function MessageKbIndicator({ usedKbs }: MessageKbIndicatorProps) {
  const [visible, setVisible] = React.useState(false)

  if (!usedKbs || usedKbs.length === 0) return null

  return (
    <span
      className="relative inline-flex items-center"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      {/* Trigger icon */}
      <span
        className="cursor-default select-none text-[10px] leading-none text-green-500"
        aria-label="Knowledge bases used"
      >
        📚
      </span>

      {/* Popover — shown on hover, positioned above */}
      {visible && (
        <div
          className="absolute bottom-full left-1/2 z-50 mb-1.5 w-72 -translate-x-1/2 rounded-lg border border-neutral-700 bg-neutral-800 p-3 shadow-xl"
          role="tooltip"
        >
          {/* Arrow */}
          <div className="absolute -bottom-1.5 left-1/2 -translate-x-1/2">
            <div className="h-2.5 w-2.5 rotate-45 border-b border-r border-neutral-700 bg-neutral-800" />
          </div>

          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-neutral-400">
            Knowledge bases used
          </p>

          <ul className="flex flex-col gap-2">
            {usedKbs.map((kb) => (
              <li key={kb.kb_id} className="flex flex-col gap-0.5">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] leading-none">📄</span>
                  <span className="text-xs font-medium text-neutral-100">{kb.kb_name}</span>
                </div>
                <div className="ml-[19px] flex flex-wrap gap-x-3 text-[10px] text-neutral-400">
                  <span>
                    <span className="text-neutral-300">{kb.chunks_used}</span> chunk
                    {kb.chunks_used !== 1 ? 's' : ''}
                  </span>
                  <span>
                    top score{' '}
                    <span className="text-neutral-300">{kb.top_score.toFixed(2)}</span>
                  </span>
                </div>
                {kb.sections.length > 0 && (
                  <div className="ml-[19px] text-[10px] text-neutral-400">
                    {kb.sections.length === 1 ? (
                      <span>{kb.sections[0]}</span>
                    ) : (
                      <ul className="list-inside list-disc space-y-0.5">
                        {kb.sections.map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </span>
  )
}
