import ReactMarkdown from 'react-markdown'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'
import * as React from 'react'

import { CODE_BLOCK_FALLBACK_PRE_CLASS } from '~/components/chat/codeBlockConstants'
import { getShikiHighlighter } from '~/components/chat/shikiHighlighter'

const ShikiCodeBlockLazy = React.lazy(() => import('~/components/chat/ShikiCodeBlock'))

// Kick off the Shiki chunk + grammar bundle as soon as a chat message renders,
// so by the time the first fenced code block mounts, both the lazy chunk and
// the highlighter are usually ready and we skip the uncoloured fallback flash.
void import('~/components/chat/ShikiCodeBlock')
void getShikiHighlighter()

function stringifyMdChildren(node: React.ReactNode): string {
  if (node == null) return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(stringifyMdChildren).join('')
  if (React.isValidElement(node)) {
    const p = node.props as { children?: React.ReactNode }
    return stringifyMdChildren(p.children)
  }
  return ''
}

/** Fenced code block: `pre` > `code.language-xxx`. */
function extractFenceFromPreChildren(children: React.ReactNode): {
  langId: string
  code: string
} | null {
  const arr = React.Children.toArray(children)
  const first = arr[0]
  if (!React.isValidElement(first)) return null
  const props = first.props as { className?: string; children?: React.ReactNode }
  const className = String(props.className ?? '')
  if (!className.includes('language-')) return null
  const m = /language-([^\s]+)/.exec(className)
  const langId = m?.[1] ?? ''
  const code = stringifyMdChildren(props.children).replace(/\n$/, '')
  return { langId, code }
}

const markdownComponents: Components = {
  p: ({ children }) => (
    <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="mb-2 list-disc space-y-1 pl-5">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-2 list-decimal space-y-1 pl-5">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  h1: ({ children }) => (
    <h1 className="mb-2 mt-3 text-lg font-semibold first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2 mt-3 text-base font-semibold first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-1 mt-2 text-sm font-semibold first:mt-0">{children}</h3>
  ),
  hr: () => <hr className="my-3 border-neutral-300 dark:border-neutral-600" />,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-neutral-400 pl-3 italic text-neutral-600 dark:border-neutral-500 dark:text-neutral-400">
      {children}
    </blockquote>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-600 underline decoration-blue-600/50 hover:decoration-blue-600 dark:text-blue-400 dark:decoration-blue-400/50"
    >
      {children}
    </a>
  ),
  /** Model-generated `![]()` is not rendered (privacy / hot-link / SSRF). See delivery memo Step 1 decisions. */
  img: () => null,
  pre: ({ children }) => {
    const fence = extractFenceFromPreChildren(children)
    if (fence) {
      return (
        <React.Suspense
          fallback={<pre className={CODE_BLOCK_FALLBACK_PRE_CLASS}>{fence.code}</pre>}
        >
          <ShikiCodeBlockLazy code={fence.code} languageHint={fence.langId} />
        </React.Suspense>
      )
    }
    return (
      <pre className="my-2 overflow-x-auto rounded-md border border-neutral-200 bg-neutral-100 p-3 text-sm dark:border-neutral-700 dark:bg-neutral-900">
        {children}
      </pre>
    )
  },
  code: ({ className, children, ...props }) => {
    const isBlock = typeof className === 'string' && className.includes('language-')
    if (isBlock) {
      return (
        <code className={`${className ?? ''} font-mono text-[0.9em]`} {...props}>
          {children}
        </code>
      )
    }
    return (
      <code
        className="rounded bg-neutral-200/90 px-1 py-0.5 font-mono text-[0.9em] dark:bg-neutral-800"
        {...props}
      >
        {children}
      </code>
    )
  },
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="border-collapse border border-neutral-300 text-sm dark:border-neutral-600">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-neutral-100 dark:bg-neutral-800">{children}</thead>,
  th: ({ children }) => (
    <th className="border border-neutral-300 px-2 py-1 text-left font-medium dark:border-neutral-600">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-neutral-300 px-2 py-1 align-top dark:border-neutral-600">
      {children}
    </td>
  ),
}

type MarkdownMessageProps = {
  content: string
  className?: string
  /** When true, shows a soft cursor and keeps layout stable while chunks arrive. */
  streaming?: boolean
}

export function MarkdownMessage({
  content,
  className,
  streaming = false,
}: MarkdownMessageProps) {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={markdownComponents}
      >
        {content}
      </ReactMarkdown>
      {streaming && (
        <span className="mt-2 flex items-center gap-1.5" aria-hidden>
          <span className="inline-block h-[1.05em] w-px animate-pulse rounded-full bg-current opacity-60" />
          <span className="inline-block h-1 w-1 animate-pulse rounded-full bg-current opacity-40 [animation-delay:120ms]" />
          <span className="inline-block h-1 w-1 animate-pulse rounded-full bg-current opacity-40 [animation-delay:240ms]" />
        </span>
      )}
    </div>
  )
}
