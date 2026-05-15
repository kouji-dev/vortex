import { ExternalLink } from 'lucide-react'

import type { ThreadItem } from '~/lib/chat-types'

type Props = { item: ThreadItem & { kind: 'citation' } }

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

export function CitationItem({ item }: Props) {
  const { url, title, snippet } = item.data
  const domain = domainOf(url)
  // For Gemini grounding the `title` is already a domain string; for other
  // providers it's a page title. Use the longer of the two as primary label.
  const label = title && title.trim() && title.trim() !== domain ? title.trim() : domain
  const showSecondary = label !== domain ? domain : null
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      data-testid="citation-item"
      className="flex items-start gap-2 rounded border border-[color:var(--line)] bg-[color:var(--bg-2)] px-2 py-1 text-xs leading-snug hover:border-[color:var(--accent)] hover:bg-[color:var(--panel)] transition-colors"
    >
      <ExternalLink className="mt-0.5 size-3 shrink-0 opacity-60" strokeWidth={2} />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="flex items-baseline gap-1.5 truncate">
          <span className="truncate font-medium" style={{ color: 'var(--ink)' }}>
            {label}
          </span>
          {showSecondary && (
            <span className="mono shrink-0 text-[10px]" style={{ color: 'var(--ink-3)' }}>
              {showSecondary}
            </span>
          )}
        </span>
        {snippet && (
          <span className="line-clamp-2" style={{ color: 'var(--ink-2)' }}>
            {snippet}
          </span>
        )}
      </span>
    </a>
  )
}
