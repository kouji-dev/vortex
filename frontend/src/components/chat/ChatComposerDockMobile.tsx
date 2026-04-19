// frontend/src/components/chat/ChatComposerDockMobile.tsx
import { ArrowUp, SlidersHorizontal, Square, X } from 'lucide-react'
import * as React from 'react'

import { ModelPickerSheet } from '~/components/chat/ModelPickerSheet'
import { useModels } from '~/hooks/useModels'
import type { CapabilityToggles, CatalogModelEntry } from '~/lib/chat-types'
import type { CapabilityKey } from '~/components/chat/ChatComposerDock'
import type { SessionModelTuning } from '~/components/chat/ModelTuningModal'

const COMPOSER_TEXTAREA_MAX_LINES = 6

type ChatComposerDockMobileProps = {
  models: CatalogModelEntry[] | undefined
  modelsPending: boolean
  modelsError: Error | null
  chatModel: string
  onSelectChatModel: (modelId: string) => void
  onCommitChatModel?: (modelId: string) => void
  modelSelectDisabled?: boolean
  capabilities: CapabilityToggles
  onToggleCapability: (key: CapabilityKey) => void
  capabilityDisabled?: boolean
  capabilityDescriptions?: Record<CapabilityKey, string>
  composeDraft: string
  setComposeDraft: (v: string) => void
  onSubmit: () => void
  streaming: boolean
  onStop: () => void
  inputThemed: string
  composerDisabled?: boolean
  kbSlot?: React.ReactNode
  selectedCatalogModel: CatalogModelEntry | null
  tuning: SessionModelTuning
  onTuningChange: (t: SessionModelTuning) => void
  pendingServerAttachments?: { id: number; name: string }[]
  pendingLocalFileNames?: string[]
  onRemoveServerAttachment?: (id: number) => void
  onRemoveLocalFile?: (index: number) => void
  onLocalFilesChosen?: (files: File[]) => void
  attachDisabled?: boolean
}

export function ChatComposerDockMobile({
  models,
  modelsPending,
  modelsError,
  chatModel,
  onSelectChatModel,
  onCommitChatModel,
  capabilities,
  onToggleCapability,
  capabilityDisabled,
  capabilityDescriptions,
  composeDraft,
  setComposeDraft,
  onSubmit,
  streaming,
  onStop,
  inputThemed,
  composerDisabled,
  kbSlot,
  selectedCatalogModel,
  tuning,
  onTuningChange,
  pendingServerAttachments,
  pendingLocalFileNames,
  onRemoveServerAttachment,
  onRemoveLocalFile,
  onLocalFilesChosen,
  attachDisabled,
}: ChatComposerDockMobileProps) {
  const [sheetOpen, setSheetOpen] = React.useState(false)
  const composeTextareaRef = React.useRef<HTMLTextAreaElement>(null)

  const { sorted, effectiveSlug, selectModel } = useModels({
    models,
    chatModel,
    onSelectChatModel,
    onCommitChatModel,
  })

  const maxInputChars = React.useMemo(() => {
    const cap = selectedCatalogModel?.model_settings.limits?.max_input_chars
    if (typeof cap === 'number' && cap >= 1024) return cap
    return 500_000
  }, [selectedCatalogModel])

  React.useEffect(() => {
    if (composeDraft.length <= maxInputChars) return
    setComposeDraft(composeDraft.slice(0, maxInputChars))
  }, [maxInputChars, composeDraft, setComposeDraft])

  React.useLayoutEffect(() => {
    const el = composeTextareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const styles = getComputedStyle(el)
    const lh = parseFloat(styles.lineHeight)
    const lineHeight = Number.isFinite(lh) && lh > 0 ? lh : 20
    const padY =
      (parseFloat(styles.paddingTop) || 0) + (parseFloat(styles.paddingBottom) || 0)
    const borderY =
      (parseFloat(styles.borderTopWidth) || 0) +
      (parseFloat(styles.borderBottomWidth) || 0)
    const maxPx = lineHeight * COMPOSER_TEXTAREA_MAX_LINES + padY + borderY
    const contentH = el.scrollHeight
    el.style.height = `${Math.min(contentH, maxPx)}px`
    el.style.overflowY = contentH > maxPx ? 'auto' : 'hidden'
  }, [composeDraft])

  const openSheet = () => {
    // Blur keyboard first; delay sheet open until after iOS dismiss animation (~300ms)
    // so button positions are stable when the user taps a model row.
    composeTextareaRef.current?.blur()
    setTimeout(() => setSheetOpen(true), 300)
  }

  const canSubmit = !composerDisabled && !streaming && composeDraft.trim().length > 0
  const hasActiveCaps = capabilities.reflection || capabilities.research

  return (
    <>
      <ModelPickerSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        sorted={sorted}
        effectiveSlug={effectiveSlug}
        modelsPending={modelsPending}
        modelsError={modelsError}
        onSelectModel={(slug, m) => {
          if (!m.accessible) return
          selectModel(slug)
        }}
        capabilities={capabilities}
        onToggleCapability={onToggleCapability}
        capabilityDisabled={capabilityDisabled}
        capabilityDescriptions={capabilityDescriptions}
        kbSlot={kbSlot}
        onLocalFilesChosen={onLocalFilesChosen}
        attachDisabled={attachDisabled}
        streaming={streaming}
        selectedCatalogModel={selectedCatalogModel}
        tuning={tuning}
        onTuningChange={onTuningChange}
      />

      {/* ── Composer bar ───────────────────────────────────────── */}
      <div
        className="border-t border-neutral-200 bg-white px-3 pt-2 dark:border-neutral-800 dark:bg-neutral-950"
        style={{ paddingBottom: 'max(0.5rem, env(safe-area-inset-bottom))' }}
      >
        {/* Active capability tags */}
        {hasActiveCaps && (
          <div className="mb-2 flex flex-wrap gap-1">
            {(['reflection', 'research'] as CapabilityKey[])
              .filter((key) => capabilities[key])
              .map((key) => {
                const label = key === 'reflection' ? 'Reflection' : 'Research'
                return (
                  <span key={key} className="inline-flex items-center gap-1 rounded-full border border-neutral-200 bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-800 dark:border-neutral-600 dark:bg-neutral-800 dark:text-neutral-200">
                    {label}
                    <button
                      type="button"
                      className="rounded-full p-0.5 text-neutral-500 hover:bg-neutral-200 hover:text-neutral-800 dark:hover:bg-neutral-700 dark:hover:text-neutral-100"
                      aria-label={`Remove ${label}`}
                      disabled={capabilityDisabled}
                      onClick={() => onToggleCapability(key)}
                    >
                      <X className="size-2.5" strokeWidth={2.5} />
                    </button>
                  </span>
                )
              })}
          </div>
        )}

        {/* Attachment chips */}
        {((pendingServerAttachments?.length ?? 0) > 0 || (pendingLocalFileNames?.length ?? 0) > 0) && (
          <div className="mb-2 flex flex-wrap gap-1">
            {pendingServerAttachments?.map((a) => (
              <span key={`srv-${a.id}`} className="inline-flex max-w-[min(100%,14rem)] items-center gap-1 truncate rounded-md border border-neutral-200 bg-neutral-50 px-2 py-0.5 text-xs text-neutral-800 dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-200">
                <span className="min-w-0 truncate">{a.name}</span>
                <button type="button" className="shrink-0 rounded p-0.5 text-neutral-500 hover:bg-neutral-200 dark:hover:bg-neutral-800" aria-label={`Remove ${a.name}`} disabled={Boolean(attachDisabled) || streaming} onClick={() => onRemoveServerAttachment?.(a.id)}>
                  <X className="size-3" strokeWidth={2.5} />
                </button>
              </span>
            ))}
            {pendingLocalFileNames?.map((name, i) => (
              <span key={`loc-${i}-${name}`} className="inline-flex max-w-[min(100%,14rem)] items-center gap-1 truncate rounded-md border border-neutral-200 bg-neutral-50 px-2 py-0.5 text-xs text-neutral-800 dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-200">
                <span className="min-w-0 truncate">{name}</span>
                <button type="button" className="shrink-0 rounded p-0.5 text-neutral-500 hover:bg-neutral-200 dark:hover:bg-neutral-800" aria-label={`Remove ${name}`} disabled={Boolean(attachDisabled) || streaming} onClick={() => onRemoveLocalFile?.(i)}>
                  <X className="size-3" strokeWidth={2.5} />
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Textarea pill */}
        <div className={`flex items-center rounded-2xl border px-2 py-1.5 ${inputThemed}`}>
          <button
            type="button"
            onClick={openSheet}
            className="flex size-7 shrink-0 items-center justify-center rounded-full text-neutral-400 hover:bg-neutral-100 hover:text-neutral-600 disabled:opacity-30 dark:hover:bg-neutral-800 dark:hover:text-neutral-300"
            aria-label="Composer options"
            disabled={Boolean(composerDisabled) && !streaming}
          >
            <SlidersHorizontal className="size-3.5" strokeWidth={2} />
          </button>

          <textarea
            ref={composeTextareaRef}
            className="mx-2 min-h-0 flex-1 resize-none bg-transparent text-base leading-snug outline-none placeholder:text-neutral-400"
            value={composeDraft}
            onChange={(e) => setComposeDraft(e.target.value)}
            placeholder="Message Vortex…"
            disabled={Boolean(composerDisabled) || streaming}
            rows={1}
            maxLength={maxInputChars}
            aria-label="Message"
          />

          {streaming ? (
            <button
              type="button"
              className="flex size-7 shrink-0 items-center justify-center rounded-full border border-red-300 text-red-600 dark:border-red-800 dark:text-red-400"
              aria-label="Stop generating"
              onClick={onStop}
            >
              <Square className="size-3 fill-current" strokeWidth={2} />
            </button>
          ) : (
            <button
              type="button"
              className="flex size-7 shrink-0 items-center justify-center rounded-full bg-neutral-900 text-white disabled:opacity-30 dark:bg-neutral-100 dark:text-neutral-900"
              disabled={!canSubmit}
              aria-label="Send message"
              onClick={onSubmit}
            >
              <ArrowUp className="size-3.5" strokeWidth={2.5} />
            </button>
          )}
        </div>
      </div>
    </>
  )
}
