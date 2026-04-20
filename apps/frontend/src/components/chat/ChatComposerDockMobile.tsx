import { SlidersHorizontal, X } from 'lucide-react'
import * as React from 'react'

import { AttachmentChips } from '~/components/chat/composer/AttachmentChips'
import { SendStopButton } from '~/components/chat/composer/SendStopButton'
import {
  CAPABILITY_LABELS,
  type CapabilityKey,
  type ChatComposerProps,
} from '~/components/chat/composer/types'
import { useComposerState } from '~/components/chat/composer/useComposerState'
import { useTextareaAutosize } from '~/components/chat/composer/useTextareaAutosize'
import { ModelPickerSheet } from '~/components/chat/ModelPickerSheet'

const MOBILE_MAX_LINES = 6

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
}: ChatComposerProps) {
  const [sheetOpen, setSheetOpen] = React.useState(false)
  const composeTextareaRef = React.useRef<HTMLTextAreaElement>(null)

  const { sorted, effectiveSlug, selectModel, maxInputChars, hasAttachments } = useComposerState({
    models,
    chatModel,
    onSelectChatModel,
    onCommitChatModel,
    selectedCatalogModel,
    composeDraft,
    setComposeDraft,
    pendingServerAttachments,
    pendingLocalFileNames,
  })

  useTextareaAutosize(composeTextareaRef, composeDraft, MOBILE_MAX_LINES)

  const openSheet = () => {
    // Blur keyboard first; delay sheet open until after iOS dismiss animation (~300ms)
    // so button positions are stable when the user taps a model row.
    composeTextareaRef.current?.blur()
    setTimeout(() => setSheetOpen(true), 300)
  }

  const canSubmit = !composerDisabled && !streaming && composeDraft.trim().length > 0
  const hasActiveCaps = capabilities.reflection || capabilities.research
  const showPillRow = hasActiveCaps || hasAttachments

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

      <div
        className="composer-wrap"
        style={{ paddingBottom: 'max(10px, env(safe-area-inset-bottom))' }}
      >
        <div className="composer">
          {showPillRow && (
            <div className="composer-pills">
              {(['reflection', 'research'] as CapabilityKey[])
                .filter((key) => capabilities[key])
                .map((key) => (
                  <span key={key} className="composer-pill on">
                    <span>{CAPABILITY_LABELS[key]}</span>
                    <button
                      type="button"
                      className="link-btn"
                      style={{ color: 'inherit', marginLeft: 2 }}
                      aria-label={`Remove ${CAPABILITY_LABELS[key]}`}
                      disabled={capabilityDisabled}
                      onClick={() => onToggleCapability(key)}
                    >
                      <X className="size-3" strokeWidth={2.5} />
                    </button>
                  </span>
                ))}
              <AttachmentChips
                pendingServerAttachments={pendingServerAttachments}
                pendingLocalFileNames={pendingLocalFileNames}
                onRemoveServerAttachment={onRemoveServerAttachment}
                onRemoveLocalFile={onRemoveLocalFile}
                attachDisabled={attachDisabled}
                streaming={streaming}
              />
            </div>
          )}

          <div className="composer-input">
            <textarea
              ref={composeTextareaRef}
              value={composeDraft}
              onChange={(e) => setComposeDraft(e.target.value)}
              placeholder="Message Vortex…"
              disabled={Boolean(composerDisabled) || streaming}
              rows={1}
              maxLength={maxInputChars}
              aria-label="Message"
            />
          </div>

          <div className="composer-foot">
            <div className="composer-send" style={{ gap: 6 }}>
              <button
                type="button"
                className="composer-pill"
                onClick={openSheet}
                aria-label="Composer options"
                disabled={Boolean(composerDisabled) && !streaming}
              >
                <SlidersHorizontal className="size-3.5" strokeWidth={2} aria-hidden />
              </button>
              {modelsError && (
                <span className="mono muted" style={{ color: 'var(--warn)', fontSize: 10 }}>
                  catalog failed
                </span>
              )}
            </div>
            <div className="composer-send">
              <SendStopButton
                streaming={streaming}
                onSubmit={onSubmit}
                onStop={onStop}
                canSubmit={canSubmit}
                iconSize="md"
              />
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
