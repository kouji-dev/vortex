import * as React from 'react'

import type { ChatStartersPayload } from '~/hooks/useChatStartersQuery'

type StartersPanelProps = {
  sections: ChatStartersPayload['sections'] | undefined
  setComposeDraft: React.Dispatch<React.SetStateAction<string>>
  /** `featured`: centered empty-state chips. `sidebar` (default): compact list. */
  variant?: 'sidebar' | 'featured'
}

export function StartersPanel({
  sections,
  setComposeDraft,
  variant = 'sidebar',
}: StartersPanelProps) {
  const isFeatured = variant === 'featured'

  return (
    <>
      {sections?.map((s) => (
        <div key={s.title} className={isFeatured ? 'mb-8 last:mb-0' : ''}>
          <p
            className={
              isFeatured
                ? 'mb-3 text-center text-xs font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400'
                : 'font-medium'
            }
          >
            {s.title}
          </p>
          {s.links && s.links.length > 0 && (
            <ul className={isFeatured ? 'mb-4 flex flex-wrap justify-center gap-x-4 gap-y-1' : 'mt-1 space-y-1'}>
              {s.links.map((l) => (
                <li key={l.href}>
                  <a
                    href={l.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={
                      isFeatured
                        ? 'text-xs text-neutral-600 underline decoration-neutral-400/80 underline-offset-2 transition hover:text-neutral-900 dark:text-neutral-400 dark:decoration-neutral-600 dark:hover:text-neutral-200'
                        : 'text-blue-600 underline decoration-dotted'
                    }
                  >
                    {l.label}
                  </a>
                </li>
              ))}
            </ul>
          )}
          <ul
            className={
              isFeatured ? 'flex flex-wrap justify-center gap-2' : 'mt-1 space-y-1'
            }
          >
            {s.prompts?.map((p) => (
              <li key={p} className={isFeatured ? 'max-w-full sm:max-w-[min(100%,20rem)]' : ''}>
                <button
                  type="button"
                  className={
                    isFeatured
                      ? 'w-full rounded-xl border border-neutral-200/90 bg-white px-3.5 py-2.5 text-left text-sm leading-snug text-neutral-800 shadow-sm transition hover:border-neutral-300 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-950/80 dark:text-neutral-100 dark:hover:border-neutral-600 dark:hover:bg-neutral-800/80'
                      : 'text-left underline decoration-dotted'
                  }
                  onClick={() => setComposeDraft(p)}
                >
                  {p}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </>
  )
}
