import * as React from 'react'
import type { CatalogModelEntry } from '~/lib/chat-types'
import { catalogModelByStoredModel, portalDefaultCatalogModel } from '~/hooks/useCatalogModelsQuery'

export type UseModelsReturn = {
  /** Models sorted by sort_order then id. */
  sorted: CatalogModelEntry[]
  /** The catalog row matching the currently stored model slug, or null. */
  selectedModel: CatalogModelEntry | null
  /** The portal default model, or null. */
  defaultModel: CatalogModelEntry | null
  /** Human-readable label for the current model (falls back to raw stored value). */
  modelLabel: string
  /**
   * The slug used for "is this row selected?" comparisons in the picker UI.
   * Uses the default model slug when chatModel is empty.
   */
  effectiveSlug: string
  /** Call with a plain slug (no prefix). Fires onSelectChatModel + onCommitChatModel. */
  selectModel: (slug: string) => void
}

export function useModels({
  models,
  chatModel,
  onSelectChatModel,
  onCommitChatModel,
}: {
  models: CatalogModelEntry[] | undefined
  chatModel: string
  onSelectChatModel: (modelId: string) => void
  onCommitChatModel?: (modelId: string) => void
}): UseModelsReturn {
  const sorted = React.useMemo(
    () =>
      models == null
        ? []
        : [...models].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id),
    [models],
  )

  const selectedModel = chatModel === '' ? null : (catalogModelByStoredModel(models, chatModel) ?? null)
  const defaultModel = React.useMemo(() => portalDefaultCatalogModel(models) ?? null, [models])

  const modelLabel =
    chatModel === ''
      ? (defaultModel?.display_name ?? 'Model')
      : (selectedModel?.display_name ?? chatModel)

  const effectiveSlug =
    chatModel === ''
      ? (defaultModel?.slug ?? '')
      : (selectedModel?.slug ?? '')

  const selectModel = React.useCallback(
    (slug: string) => {
      onSelectChatModel(slug)
      onCommitChatModel?.(slug)
    },
    [onSelectChatModel, onCommitChatModel],
  )

  return { sorted, selectedModel, defaultModel, modelLabel, effectiveSlug, selectModel }
}
