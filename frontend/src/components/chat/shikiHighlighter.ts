import type { BundledLanguage, Highlighter } from 'shiki'

let highlighterPromise: Promise<Highlighter> | null = null

/**
 * Lazy-loads Shiki (full grammar bundle) on first fenced code block so initial
 * chat JS stays out of the main chunk until highlighting is needed.
 */
export function getShikiHighlighter(): Promise<Highlighter> {
  if (!highlighterPromise) {
    highlighterPromise = import('shiki').then(({ getSingletonHighlighter, bundledLanguages }) =>
      getSingletonHighlighter({
        themes: ['github-light', 'github-dark'],
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
  theme: 'github-light' | 'github-dark',
): Promise<string> {
  const { bundledLanguages, bundledLanguagesAlias } = await import('shiki')
  const lang = resolveShikiLanguage(fenceId, bundledLanguages, bundledLanguagesAlias)
  try {
    return highlighter.codeToHtml(code, { lang, theme })
  } catch {
    return highlighter.codeToHtml(code, { lang: 'console', theme })
  }
}
