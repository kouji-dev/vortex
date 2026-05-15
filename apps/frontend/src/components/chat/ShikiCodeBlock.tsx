import * as React from 'react'

import { CODE_BLOCK_FALLBACK_PRE_CLASS } from '~/components/chat/codeBlockConstants'
import {
  getShikiHighlighter,
  highlightCodeToHtml,
  type ShikiThemeId,
} from '~/components/chat/shikiHighlighter'
import { useTheme } from '~/hooks/useTheme'

type ShikiCodeBlockProps = {
  code: string
  /** Language id from markdown fence (e.g. `ts`, `python`). */
  languageHint: string
}

// Friendly labels for common ids; anything else falls back to the raw id.
const LANGUAGE_LABELS: Record<string, string> = {
  js: 'JavaScript',
  jsx: 'JSX',
  ts: 'TypeScript',
  tsx: 'TSX',
  py: 'Python',
  python: 'Python',
  rs: 'Rust',
  rust: 'Rust',
  go: 'Go',
  rb: 'Ruby',
  ruby: 'Ruby',
  sh: 'Shell',
  bash: 'Bash',
  zsh: 'Zsh',
  ps: 'PowerShell',
  powershell: 'PowerShell',
  sql: 'SQL',
  json: 'JSON',
  yaml: 'YAML',
  yml: 'YAML',
  toml: 'TOML',
  html: 'HTML',
  css: 'CSS',
  scss: 'SCSS',
  md: 'Markdown',
  markdown: 'Markdown',
  diff: 'Diff',
  c: 'C',
  cpp: 'C++',
  'c++': 'C++',
  cs: 'C#',
  csharp: 'C#',
  java: 'Java',
  kt: 'Kotlin',
  kotlin: 'Kotlin',
  swift: 'Swift',
  php: 'PHP',
  ex: 'Elixir',
  elixir: 'Elixir',
  hs: 'Haskell',
  lua: 'Lua',
  zig: 'Zig',
  dockerfile: 'Dockerfile',
  graphql: 'GraphQL',
  gql: 'GraphQL',
  xml: 'XML',
  ini: 'INI',
  env: 'Env',
  console: 'Console',
}

function labelFor(langId: string): string {
  const raw = langId.trim().toLowerCase()
  if (!raw) return 'Plain'
  return LANGUAGE_LABELS[raw] ?? raw
}

export function ShikiCodeBlock({ code, languageHint }: ShikiCodeBlockProps) {
  const [theme] = useTheme()
  const shikiTheme: ShikiThemeId = theme === 'dark' ? 'one-dark-pro' : 'github-light'
  const [html, setHtml] = React.useState<string | null>(null)
  const [copied, setCopied] = React.useState(false)
  const copyResetRef = React.useRef<number | null>(null)

  React.useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const hi = await getShikiHighlighter()
        const out = await highlightCodeToHtml(hi, code, languageHint, shikiTheme)
        if (!cancelled) setHtml(out)
      } catch {
        if (!cancelled) setHtml(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [code, languageHint, shikiTheme])

  React.useEffect(() => {
    return () => {
      if (copyResetRef.current != null) window.clearTimeout(copyResetRef.current)
    }
  }, [])

  const handleCopy = React.useCallback(() => {
    void navigator.clipboard.writeText(code).then(() => {
      setCopied(true)
      if (copyResetRef.current != null) window.clearTimeout(copyResetRef.current)
      copyResetRef.current = window.setTimeout(() => setCopied(false), 1500)
    })
  }, [code])

  // While Shiki loads, show a plain block styled to match the final dark
  // shell — no jarring colour transition when highlighting resolves.
  const body =
    html == null ? (
      <pre
        className={
          'm-0 overflow-x-auto py-3 pl-12 pr-4 font-mono text-[13.5px] leading-[1.55] ' +
          (theme === 'dark' ? 'text-neutral-200' : 'text-neutral-800')
        }
      >
        {code}
      </pre>
    ) : (
      <div
        className={
          'shiki-block ' +
          // Inner <pre> owns the horizontal scroll; outer figure has no overflow.
          '[&_pre.shiki]:m-0 [&_pre.shiki]:overflow-x-auto [&_pre.shiki]:py-3 ' +
          '[&_pre.shiki]:!bg-transparent ' +
          // `code` is inline-block + min-w-full so it stretches to at least the
          // visible width; `.line` is block so each row inherits that full
          // width — line backgrounds / hovers / future highlights cover the
          // whole row instead of just the glyphs. Padding lives on `.line`
          // (not on `pre`) so it scrolls with the content.
          '[&_pre.shiki_>_code]:inline-block [&_pre.shiki_>_code]:min-w-full ' +
          // Collapse the literal "\n" text nodes Shiki emits between `.line`
          // blocks (otherwise they render as extra inter-row vertical space).
          '[&_pre.shiki_>_code]:text-[0px] [&_pre.shiki_>_code]:leading-none ' +
          '[&_pre.shiki_.line]:block [&_pre.shiki_.line]:pr-4 ' +
          '[&_pre.shiki_.line]:text-[13.5px] [&_pre.shiki_.line]:leading-[1.55] ' +
          '[&_code]:font-mono'
        }
        // Shiki output is generated locally from user/assistant markdown only.
        dangerouslySetInnerHTML={{ __html: html }}
      />
    )

  return (
    <figure
      className={
        'my-3 overflow-hidden rounded-lg border ' +
        (theme === 'dark'
          ? 'border-white/10 bg-[#282c34] shadow-[0_8px_24px_-12px_rgba(0,0,0,0.6)]'
          : 'border-neutral-200 bg-[#fafafa] shadow-[0_4px_14px_-8px_rgba(0,0,0,0.12)]')
      }
    >
      <figcaption
        className={
          'flex items-center justify-between gap-3 px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider select-none ' +
          (theme === 'dark'
            ? 'border-b border-white/5 bg-black/20 text-neutral-400'
            : 'border-b border-neutral-200 bg-neutral-100/70 text-neutral-500')
        }
      >
        <span className="font-mono normal-case tracking-normal">{labelFor(languageHint)}</span>
        <button
          type="button"
          onClick={handleCopy}
          className={
            'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wider transition-colors ' +
            (theme === 'dark'
              ? 'text-neutral-400 hover:bg-white/10 hover:text-neutral-100'
              : 'text-neutral-500 hover:bg-neutral-200 hover:text-neutral-800')
          }
          aria-label={copied ? 'Copied' : 'Copy code'}
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </figcaption>
      {body}
    </figure>
  )
}

export default ShikiCodeBlock
