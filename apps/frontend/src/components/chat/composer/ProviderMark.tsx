import type { CatalogModelEntry } from '~/lib/chat-types'

export function providerInitialFromModelId(apiModelId?: string): string {
  if (!apiModelId) return '◆'
  const s = apiModelId.toLowerCase()
  if (s.includes('claude') || s.includes('anthropic')) return 'A'
  if (s.includes('gpt') || s.includes('openai') || s.startsWith('o1') || s.startsWith('o3') || s.startsWith('o4')) return 'O'
  if (s.includes('gemini') || s.includes('google')) return 'G'
  if (s.includes('azure')) return 'Z'
  return apiModelId.slice(0, 1).toUpperCase()
}

export function ProviderMark({ model }: { model: CatalogModelEntry | null | undefined }) {
  return (
    <span
      aria-hidden
      className="inline-flex size-3.5 items-center justify-center rounded-[3px] font-mono text-[9px] font-semibold"
      style={{
        background: 'var(--bg-2)',
        border: '1px solid var(--line)',
        color: 'var(--ink-2)',
      }}
    >
      {providerInitialFromModelId(model?.api_model_id)}
    </span>
  )
}
