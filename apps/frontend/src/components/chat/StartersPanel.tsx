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
                ? 'mb-3 text-center font-mono text-[10px] font-semibold uppercase tracking-[0.08em]'
                : 'font-medium'
            }
            style={isFeatured ? { color: 'var(--ink-3)' } : undefined}
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
                        ? 'text-xs underline underline-offset-2 transition'
                        : 'underline decoration-dotted'
                    }
                    style={isFeatured ? { color: 'var(--ink-2)' } : { color: 'var(--accent)' }}
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
                      ? 'starter-chip w-full text-left text-[13px] leading-snug'
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
