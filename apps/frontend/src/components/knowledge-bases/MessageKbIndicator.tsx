import { Library } from 'lucide-react'

import type { UsedKbEntry } from '~/lib/chat-types'

export type MessageKbIndicatorProps = {
  usedKbs: UsedKbEntry[]
}

/** KB icon in the message header; hover (or focus) shows which knowledge bases contributed. */
export function MessageKbIndicator({ usedKbs }: MessageKbIndicatorProps) {
  if (usedKbs.length === 0) return null

  return (
    <div className="group relative inline-flex">
      <button
        type="button"
        data-testid="message-kb-indicator-trigger"
        className="relative z-10 rounded p-1 text-neutral-500 transition-colors hover:bg-neutral-200/70 hover:text-neutral-800 dark:text-neutral-400 dark:hover:bg-neutral-700/60 dark:hover:text-neutral-200"
        aria-label={`Used ${usedKbs.length} knowledge base${usedKbs.length === 1 ? '' : 's'}`}
        aria-haspopup="true"
      >
        <Library className="size-3.5" strokeWidth={2} aria-hidden />
      </button>
      <div
        data-testid="message-kb-indicator-popover"
        className="pointer-events-none absolute right-0 top-full z-20 -mt-1 w-max max-w-[min(18rem,calc(100vw-2rem))] translate-y-0 rounded-md border border-neutral-200 bg-white py-1.5 pl-2 pr-2.5 text-left text-xs shadow-md opacity-0 transition-opacity duration-100 dark:border-neutral-700 dark:bg-neutral-950 group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100"
        role="tooltip"
      >
        <p className="mb-1 font-medium text-neutral-600 dark:text-neutral-400">Knowledge bases</p>
        <ul className="space-y-1 text-neutral-800 dark:text-neutral-200">
          {usedKbs.map((kb) => (
            <li key={kb.kb_id} className="leading-snug">
              <span className="font-medium">{kb.kb_name}</span>
              {typeof kb.chunks_used === 'number' && kb.chunks_used > 0 ? (
                <span className="text-neutral-500 dark:text-neutral-500">
                  {' '}
                  · {kb.chunks_used} chunk{kb.chunks_used === 1 ? '' : 's'}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
