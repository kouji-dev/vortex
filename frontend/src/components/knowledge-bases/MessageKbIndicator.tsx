import * as Popover from '@radix-ui/react-popover'

import type { UsedKbEntry } from '~/lib/chat-types'

export interface MessageKbIndicatorProps {
  usedKbs: UsedKbEntry[]
}

export function MessageKbIndicator({ usedKbs }: MessageKbIndicatorProps) {
  if (!usedKbs || usedKbs.length === 0) return null

  const allCitations = usedKbs.flatMap((kb) => kb.citations ?? [])

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

          {allCitations.length > 0 && (
            <div className="mt-2 border-t border-neutral-700 pt-2">
              <p className="mb-1 text-[10px] font-medium text-neutral-400">Sources</p>
              <div className="flex flex-wrap gap-1">
                {allCitations.map((c, i) => (
                  <button
                    key={i}
                    type="button"
                    className="inline-flex items-center gap-1 rounded border border-neutral-600 px-1.5 py-0.5 text-[10px] text-neutral-300 transition-colors hover:bg-neutral-700"
                    title={[c.source, c.section].filter(Boolean).join(' — ')}
                    onClick={() => {
                      const ref = [c.source, c.section].filter(Boolean).join(' › ')
                      void navigator.clipboard.writeText(ref)
                    }}
                  >
                    {c.source}
                    {c.section && (
                      <span className="text-neutral-500">› {c.section}</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
