import { useQuery } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import type { CatalogModelEntry } from '~/lib/chat-types'
import { getAuthHeaders } from '~/lib/authorizedFetch'

export const catalogModelsQueryKey = ['catalog-models'] as const

export function useCatalogModelsQuery() {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: catalogModelsQueryKey,
    queryFn: async () => {
      const res = await fetch(`${apiBase}/api/models`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<CatalogModelEntry[]>
    },
  })
}

/** Matches backend seed preference when conversation model is unset. */
export function suggestedPortalDefaultModel(
  models: CatalogModelEntry[] | undefined,
): CatalogModelEntry | null {
  if (models == null || models.length === 0) return null
  const prefer = (
    slug: string,
  ): CatalogModelEntry | undefined =>
    models.find((m) => m.slug === slug && m.accessible)
  return (
    prefer('anthropic-claude-opus-4-6') ??
    prefer('openai-o3-mini') ??
    models.find((m) => m.accessible) ??
    models[0] ??
    null
  )
}

/** Prefer ``is_default`` from ``GET /api/models``; fallback for stale clients or empty catalog. */
export function portalDefaultCatalogModel(
  models: CatalogModelEntry[] | undefined,
): CatalogModelEntry | null {
  if (models == null || models.length === 0) return null
  const flagged = models.filter((m) => m.is_default)
  if (flagged.length === 1) return flagged[0]
  if (flagged.length > 1) {
    return [...flagged].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)[0]
  }
  return suggestedPortalDefaultModel(models)
}

export function catalogModelByLitellmId(
  models: CatalogModelEntry[] | undefined,
  litellmModelId: string,
): CatalogModelEntry | undefined {
  if (!models || !litellmModelId.trim()) return undefined
  return models.find((m) => m.litellm_model_id === litellmModelId)
}

/** Resolves ``conversation.model``: catalog slug, or legacy LiteLLM id (first row if ambiguous). */
export function catalogModelByStoredModel(
  models: CatalogModelEntry[] | undefined,
  stored: string,
): CatalogModelEntry | undefined {
  if (!models || !stored.trim()) return undefined
  const bySlug = models.find((m) => m.slug === stored)
  if (bySlug) return bySlug
  const litellmMatches = models.filter((m) => m.litellm_model_id === stored)
  if (litellmMatches.length === 0) return undefined
  const sorted = [...litellmMatches].sort(
    (a, b) => a.sort_order - b.sort_order || a.id - b.id,
  )
  return sorted[0]
}
