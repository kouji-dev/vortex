import * as Popover from '@radix-ui/react-popover'

import type { UsedKbEntry } from '~/lib/chat-types'

export interface MessageKbIndicatorProps {
  usedKbs: UsedKbEntry[]
}

export function MessageKbIndicator({ usedKbs }: MessageKbIndicatorProps) {
  if (!usedKbs || usedKbs.length === 0) return null

  return (
    <Popover.Root modal={false}>
      <Popover.Trigger asChild>
        <button
          type="button"
          data-testid="message-kb-indicator-trigger"
          className="inline-flex cursor-pointer select-none border-0 bg-transparent p-0 text-[10px] leading-none text-green-500 underline-offset-2 hover:underline"
          aria-label="Knowledge bases used — show details"
        >
          📚
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top"
          align="center"
          sideOffset={6}
          collisionPadding={8}
          data-testid="message-kb-indicator-popover"
          className="z-100 w-72 rounded-lg border border-neutral-700 bg-neutral-800 p-3 text-left shadow-xl outline-none"
          onCloseAutoFocus={(e) => e.preventDefault()}
        >
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-neutral-400">
            Knowledge bases used
          </p>

          <ul className="flex max-h-64 flex-col gap-2 overflow-y-auto">
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
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
