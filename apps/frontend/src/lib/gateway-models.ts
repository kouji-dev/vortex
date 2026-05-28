// Pure helpers for the Gateway Models catalog page.

import type { ModelCapabilities, ModelInfo } from './gateway-types'

/** Cents per 1k tokens formatted as a $ string. */
export function formatPricePerK(cents: number): string {
  const dollars = cents / 100
  if (dollars >= 1) return `$${dollars.toFixed(2)}/1k`
  if (dollars >= 0.01) return `$${dollars.toFixed(3)}/1k`
  return `$${dollars.toFixed(4)}/1k`
}

/** Compact capability tag list, ordered by importance. */
const CAP_ORDER: (keyof ModelCapabilities)[] = [
  'streaming',
  'tools',
  'vision',
  'thinking',
  'cache',
  'json_mode',
]

export function capabilityTags(caps: ModelCapabilities | undefined): string[] {
  if (!caps) return []
  const out: string[] = []
  for (const k of CAP_ORDER) if (caps[k]) out.push(k)
  return out
}

export interface ModelFilter {
  provider?: string
  capability?: keyof ModelCapabilities
  search?: string
  includeDeprecated?: boolean
}

export function filterModels(models: readonly ModelInfo[], f: ModelFilter): ModelInfo[] {
  const q = (f.search ?? '').trim().toLowerCase()
  return models.filter((m) => {
    if (!f.includeDeprecated && m.deprecated_at) return false
    if (f.provider && m.provider !== f.provider) return false
    if (f.capability && !m.capabilities?.[f.capability]) return false
    if (q) {
      const hay = `${m.model_id} ${m.display_name} ${m.provider}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
}

/**
 * Sort by provider, then model_id ascending.
 * Stable for equal keys (input order preserved).
 */
export function sortModels(models: readonly ModelInfo[]): ModelInfo[] {
  return [...models].sort((a, b) => {
    if (a.provider !== b.provider) return a.provider.localeCompare(b.provider)
    return a.model_id.localeCompare(b.model_id)
  })
}
