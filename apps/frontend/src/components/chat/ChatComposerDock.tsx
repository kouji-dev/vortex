import {
  BookOpen,
  Brain,
  ChevronsUpDown,
  Lock,
  Paperclip,
  Settings2,
  type LucideIcon,
} from 'lucide-react'
import * as React from 'react'

import { AttachmentChips } from '~/components/chat/composer/AttachmentChips'
import { ProviderMark } from '~/components/chat/composer/ProviderMark'
import { SendStopButton } from '~/components/chat/composer/SendStopButton'
import {
  CAPABILITY_LABELS,
  type CapabilityKey,
  type ChatComposerProps,
} from '~/components/chat/composer/types'
import { useComposerState } from '~/components/chat/composer/useComposerState'
import { useTextareaAutosize } from '~/components/chat/composer/useTextareaAutosize'
import {
  ModelTuningModal,
  defaultTuningFromCatalog,
} from '~/components/chat/ModelTuningModal'
import { RequestAccessModal } from '~/components/chat/RequestAccessModal'
import type { CatalogModelEntry } from '~/lib/chat-types'

export { ProviderMark, providerInitialFromModelId } from '~/components/chat/composer/ProviderMark'
export { resolveSelectedCatalogModel } from '~/components/chat/composer/resolveSelectedCatalogModel'
export type { CapabilityKey } from '~/components/chat/composer/types'

const DESKTOP_MAX_LINES = 4

const CAPABILITY_PILLS: { key: CapabilityKey; Icon: LucideIcon }[] = [
  { key: 'reflection', Icon: Brain },
  { key: 'research', Icon: BookOpen },
]

export function ChatComposerDock({
  models,
  modelsPending,
  modelsError,
  chatModel,
  onSelectChatModel,
  onCommitChatModel,
  modelSelectDisabled,
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
  const [requestAccessModel, setRequestAccessModel] = React.useState<CatalogModelEntry | null>(null)
  const [tuningOpen, setTuningOpen] = React.useState(false)
  const [modelMenuOpen, setModelMenuOpen] = React.useState(false)
  const composeTextareaRef = React.useRef<HTMLTextAreaElement>(null)
  const attachInputRef = React.useRef<HTMLInputElement>(null)
  const modelPillRef = React.useRef<HTMLDivElement>(null)

  const {
    sorted, selectedModel: storedCatalogRow, defaultModel: defaultCatalogRow,
    modelLabel, selectModel,
    maxInputChars, hasAttachments,
  } = useComposerState({
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

  useTextareaAutosize(composeTextareaRef, composeDraft, DESKTOP_MAX_LINES)

  const activeModel = storedCatalogRow ?? defaultCatalogRow ?? null
  const effortLabel = (selectedCatalogModel?.model_settings as { reasoning_effort?: string } | undefined)
    ?.reasoning_effort

  React.useEffect(() => {
    if (!modelMenuOpen) return
    const onDoc = (e: MouseEvent) => {
      const el = modelPillRef.current
      if (el && e.target instanceof Node && !el.contains(e.target)) setModelMenuOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [modelMenuOpen])

  const openTuning = () => {
    if (selectedCatalogModel) onTuningChange(defaultTuningFromCatalog(selectedCatalogModel))
    setTuningOpen(true)
  }

  const handlePickModel = (m: CatalogModelEntry) => {
    if (!m.accessible) {
      if (m.request_access_url) {
        window.open(m.request_access_url, '_blank', 'noopener,noreferrer')
      } else if (m.can_request_access) {
        setRequestAccessModel(m)
      }
      return
    }
    selectModel(m.slug)
    setModelMenuOpen(false)
  }

  const canSubmit = !composerDisabled && !streaming && composeDraft.trim().length > 0

  return (
    <>
      <RequestAccessModal
        model={requestAccessModel}
        open={requestAccessModel != null}
        onClose={() => setRequestAccessModel(null)}
      />
      <ModelTuningModal
        model={selectedCatalogModel}
        open={tuningOpen}
        onClose={() => setTuningOpen(false)}
        tuning={tuning}
        onTuningChange={onTuningChange}
      />

      <div className="composer-wrap">
        <div className="composer">
          {/* Pills row ───────────────────────────────────────────────── */}
          <div className="composer-pills">
            {/* Model pill */}
            <div className="pill-wrap" ref={modelPillRef}>
              <button
                type="button"
                data-testid="chat-model-select"
                className="composer-pill"
                title={modelLabel}
                disabled={
                  modelSelectDisabled ||
                  modelsPending ||
                  sorted.length === 0 ||
                  (chatModel === '' && defaultCatalogRow == null)
                }
                onClick={() => setModelMenuOpen((v) => !v)}
                aria-haspopup="menu"
                aria-expanded={modelMenuOpen}
              >
                <ProviderMark model={activeModel} />
                <span className="pill-label-full">{modelLabel}</span>
                {effortLabel && <span className="pill-effort">{effortLabel}</span>}
                <ChevronsUpDown className="size-3" strokeWidth={2} />
              </button>
              {modelMenuOpen && (
                <>
                  <div className="menu-scrim" onClick={() => setModelMenuOpen(false)} />
                  <div className="menu model-menu" role="listbox" aria-label="Model catalog">
                    <div className="menu-head">
                      <span>Model catalog</span>
                      <span className="mono muted">
                        {sorted.filter((m) => m.accessible).length} entitled
                      </span>
                    </div>
                    <div className="menu-scroll">
                      {sorted.map((m) => {
                        const isActive = storedCatalogRow?.id === m.id
                        const actionable = m.can_request_access || Boolean(m.request_access_url)
                        return (
                          <div
                            key={m.id}
                            role="option"
                            aria-selected={isActive}
                            tabIndex={0}
                            className={`model-menu-row ${isActive ? 'active' : ''} ${
                              m.accessible ? '' : 'opacity-60'
                            }`}
                            onClick={() => handlePickModel(m)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault()
                                handlePickModel(m)
                              }
                            }}
                          >
                            <ProviderMark model={m} />
                            <div className="mm-main">
                              <div className="mm-name">
                                {m.display_name}
                                {!m.accessible && !actionable && ' (locked)'}
                              </div>
                              <div className="mm-meta">
                                {m.api_model_id}
                              </div>
                            </div>
                            {!m.accessible && actionable && (
                              <Lock className="size-3" strokeWidth={2} />
                            )}
                          </div>
                        )
                      })}
                    </div>
                    <div className="menu-foot">
                      <button
                        type="button"
                        className="link-btn"
                        onClick={() => {
                          setModelMenuOpen(false)
                          openTuning()
                        }}
                      >
                        <Settings2 className="size-3" strokeWidth={2} />
                        Model settings
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* Capability pills */}
            {CAPABILITY_PILLS.map(({ key, Icon }) => {
              const label = CAPABILITY_LABELS[key]
              return (
                <button
                  key={key}
                  type="button"
                  data-testid={`capability-pill-${key}`}
                  className={`composer-pill ${capabilities[key] ? 'on' : ''}`}
                  title={capabilityDescriptions?.[key] ?? label}
                  disabled={capabilityDisabled}
                  aria-pressed={capabilities[key]}
                  onClick={() => onToggleCapability(key)}
                >
                  <Icon className="size-3" strokeWidth={2} />
                  <span className="pill-label-full">{label}</span>
                </button>
              )
            })}

            {/* KB picker injected by parent */}
            {kbSlot != null && <div className="pill-wrap">{kbSlot}</div>}

            <span className="pill-spacer" />

            {/* Attach paperclip (ghost pill) */}
            {onLocalFilesChosen != null && (
              <>
                <input
                  ref={attachInputRef}
                  data-testid="chat-attach-file-input"
                  type="file"
                  multiple
                  className="sr-only"
                  accept=".txt,.md,text/plain,text/markdown"
                  disabled={Boolean(attachDisabled) || streaming}
                  onChange={(e) => {
                    const files = Array.from(e.target.files ?? [])
                    e.target.value = ''
                    if (files.length) onLocalFilesChosen(files)
                  }}
                />
                <button
                  type="button"
                  className="composer-pill ghost"
                  aria-label="Attach files"
                  title="Attach file (.txt, .md)"
                  disabled={Boolean(attachDisabled) || streaming}
                  onClick={() => attachInputRef.current?.click()}
                >
                  <Paperclip className="size-3" strokeWidth={2} />
                </button>
              </>
            )}
          </div>

          {/* Attachments list ─────────────────────────────────────────── */}
          {hasAttachments && (
            <div
              data-testid="chat-composer-attachments"
              className="flex flex-wrap items-center gap-1.5"
              style={{ padding: '6px 12px 0' }}
            >
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

          {/* Textarea ─────────────────────────────────────────────────── */}
          <div className="composer-input">
            <textarea
              ref={composeTextareaRef}
              value={composeDraft}
              onChange={(e) => setComposeDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault()
                  if (canSubmit) onSubmit()
                }
              }}
              placeholder={`Message ${modelLabel}…`}
              disabled={Boolean(composerDisabled) || streaming}
              rows={1}
              maxLength={maxInputChars}
              aria-label="Message"
            />
          </div>

          {/* Foot: hints + send ────────────────────────────────────────── */}
          <div className="composer-foot">
            <div className="composer-hints">
              <kbd>⌃↵</kbd> send · <kbd>↵</kbd> newline
              {modelsError && (
                <span style={{ color: 'var(--warn)', marginLeft: 10 }}>
                  · catalog failed to load
                </span>
              )}
            </div>
            <div className="composer-send">
              <SendStopButton
                streaming={streaming}
                onSubmit={onSubmit}
                onStop={onStop}
                canSubmit={canSubmit}
                sendTestId="chat-send-button"
              />
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
