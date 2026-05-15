import type { BundledLanguage, Highlighter, ShikiTransformer } from 'shiki'

export type ShikiThemeId = 'one-dark-pro' | 'github-light'

/**
 * Splits each line's leading whitespace into `<span class="indent-guide">`
 * spans (one per indent unit) so CSS can paint VSCode-style vertical guides.
 * The remainder (whitespace that doesn't fit a whole unit) stays as text.
 */
const INDENT_UNIT = 2

const indentGuidesTransformer: ShikiTransformer = {
  name: 'ai-portal:indent-guides',
  line(lineNode) {
    if (!lineNode.children?.length) return
    const firstChild = lineNode.children[0]
    if (firstChild.type !== 'element') return
    const firstText = firstChild.children?.[0]
    if (!firstText || firstText.type !== 'text' || typeof firstText.value !== 'string') return
    const m = /^[ \t]+/.exec(firstText.value)
    if (!m) return
    const wsLen = m[0].length
    const count = Math.floor(wsLen / INDENT_UNIT)
    if (count === 0) return
    const remainder = wsLen - count * INDENT_UNIT

    // Strip the consumed whitespace from the original first text node.
    firstText.value = ' '.repeat(remainder) + firstText.value.slice(wsLen)

    const guides = Array.from({ length: count }, () => ({
      type: 'element' as const,
      tagName: 'span',
      properties: { class: 'indent-guide' },
      children: [],
    }))

    lineNode.children = [...guides, ...lineNode.children]
  },
}

let highlighterPromise: Promise<Highlighter> | null = null

/**
 * Lazy-loads Shiki (full grammar bundle) on first fenced code block so initial
 * chat JS stays out of the main chunk until highlighting is needed.
 */
export function getShikiHighlighter(): Promise<Highlighter> {
  if (!highlighterPromise) {
    highlighterPromise = import('shiki').then(({ getSingletonHighlighter, bundledLanguages }) =>
      getSingletonHighlighter({
        themes: ['one-dark-pro', 'github-light'],
        langs: Object.keys(bundledLanguages) as BundledLanguage[],
      }),
    )
  }
  return highlighterPromise
}

function resolveShikiLanguage(
  fenceId: string,
  bundledLanguages: Record<string, unknown>,
  bundledLanguagesAlias: Record<string, unknown>,
): BundledLanguage {
  const raw = fenceId.trim().toLowerCase()
  if (!raw) return 'console'
  if (raw in bundledLanguages) return raw as BundledLanguage
  if (raw in bundledLanguagesAlias) return raw as BundledLanguage
  return 'console'
}

export async function highlightCodeToHtml(
  highlighter: Highlighter,
  code: string,
  fenceId: string,
  theme: ShikiThemeId,
): Promise<string> {
  const { bundledLanguages, bundledLanguagesAlias } = await import('shiki')
  const lang = resolveShikiLanguage(fenceId, bundledLanguages, bundledLanguagesAlias)
  const transformers = [indentGuidesTransformer]
  try {
    return highlighter.codeToHtml(code, { lang, theme, transformers })
  } catch {
    return highlighter.codeToHtml(code, { lang: 'console', theme, transformers })
  }
}
