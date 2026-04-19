import * as React from 'react'

import { CODE_BLOCK_FALLBACK_PRE_CLASS } from '~/components/chat/codeBlockConstants'
import { getShikiHighlighter, highlightCodeToHtml } from '~/components/chat/shikiHighlighter'
import { usePrefersColorSchemeDark } from '~/components/chat/usePrefersColorSchemeDark'

const shellClass =
  'my-2 overflow-x-auto rounded-md border border-neutral-200 text-[13px] leading-relaxed dark:border-neutral-700 ' +
  '[&_pre.shiki]:m-0 [&_pre.shiki]:overflow-x-auto [&_pre.shiki]:rounded-md [&_pre.shiki]:p-3 ' +
  '[&_pre.shiki]:text-[13px] [&_code]:font-mono'

type ShikiCodeBlockProps = {
  code: string
  /** Language id from markdown fence (e.g. `ts`, `python`). */
  languageHint: string
}

export function ShikiCodeBlock({ code, languageHint }: ShikiCodeBlockProps) {
  const prefersDark = usePrefersColorSchemeDark()
  const theme = prefersDark ? 'github-dark' : 'github-light'
  const [html, setHtml] = React.useState<string | null>(null)

  React.useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const hi = await getShikiHighlighter()
        const out = await highlightCodeToHtml(hi, code, languageHint, theme)
        if (!cancelled) setHtml(out)
      } catch {
        if (!cancelled) setHtml(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [code, languageHint, theme])

  if (html == null) {
    return <pre className={CODE_BLOCK_FALLBACK_PRE_CLASS}>{code}</pre>
  }

  return (
    <div
      className={shellClass}
      // Shiki output is generated locally from user/assistant markdown only.
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

export default ShikiCodeBlock
