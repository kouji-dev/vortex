import * as React from 'react'

import { useModels } from '~/hooks/useModels'
import type { CatalogModelEntry } from '~/lib/chat-types'

const DEFAULT_MAX_INPUT_CHARS = 500_000

type UseComposerStateOptions = {
  models: CatalogModelEntry[] | undefined
  chatModel: string
  onSelectChatModel: (modelId: string) => void
  onCommitChatModel?: (modelId: string) => void
  selectedCatalogModel: CatalogModelEntry | null
  composeDraft: string
  setComposeDraft: (v: string) => void
  pendingServerAttachments?: { id: number; name: string }[]
  pendingLocalFileNames?: string[]
}

export function useComposerState(opts: UseComposerStateOptions) {
  const {
    models,
    chatModel,
    onSelectChatModel,
    onCommitChatModel,
    selectedCatalogModel,
    composeDraft,
    setComposeDraft,
    pendingServerAttachments,
    pendingLocalFileNames,
  } = opts

  const modelsApi = useModels({ models, chatModel, onSelectChatModel, onCommitChatModel })

  const maxInputChars = React.useMemo(() => {
    const cap = selectedCatalogModel?.model_settings.limits?.max_input_chars
    if (typeof cap === 'number' && cap >= 1024) return cap
    return DEFAULT_MAX_INPUT_CHARS
  }, [selectedCatalogModel])

  React.useEffect(() => {
    if (composeDraft.length <= maxInputChars) return
    setComposeDraft(composeDraft.slice(0, maxInputChars))
  }, [maxInputChars, composeDraft, setComposeDraft])

  const hasAttachments =
    (pendingServerAttachments?.length ?? 0) > 0 || (pendingLocalFileNames?.length ?? 0) > 0

  return {
    ...modelsApi,
    maxInputChars,
    hasAttachments,
  }
}
