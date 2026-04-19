import {
  ArrowUp,
  BookOpen,
  Brain,
  ChevronsUpDown,
  Lock,
  Paperclip,
  Settings2,
  Square,
  X,
  type LucideIcon,
} from 'lucide-react'
import * as React from 'react'

import {
  ModelTuningModal,
  type SessionModelTuning,
  defaultTuningFromCatalog,
} from '~/components/chat/ModelTuningModal'
import { RequestAccessModal } from '~/components/chat/RequestAccessModal'
import type { CapabilityToggles, CatalogModelEntry } from '~/lib/chat-types'
import { catalogModelByStoredModel, portalDefaultCatalogModel } from '~/hooks/useCatalogModelsQuery'
import { useModels } from '~/hooks/useModels'

const COMPOSER_TEXTAREA_MAX_LINES = 4

export type CapabilityKey = 'reflection' | 'research'

const CAPABILITY_PILLS: { key: CapabilityKey; label: string; Icon: LucideIcon }[] = [
  { key: 'reflection', label: 'Reflection', Icon: Brain },
  { key: 'research', label: 'Research', Icon: BookOpen },
]

type ChatComposerDockProps = {
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
}: ChatComposerDockProps) {
  const [requestAccessModel, setRequestAccessModel] = React.useState<CatalogModelEntry | null>(null)
  const [tuningOpen, setTuningOpen] = React.useState(false)
  const [modelMenuOpen, setModelMenuOpen] = React.useState(false)
  const composeTextareaRef = React.useRef<HTMLTextAreaElement>(null)
  const attachInputRef = React.useRef<HTMLInputElement>(null)
  const modelPillRef = React.useRef<HTMLDivElement>(null)

  const { sorted, selectedModel: storedCatalogRow, defaultModel: defaultCatalogRow, modelLabel, selectModel } = useModels({
    models,
    chatModel,
    onSelectChatModel,
    onCommitChatModel,
  })

  const activeModel = storedCatalogRow ?? defaultCatalogRow ?? null
  const effortLabel = (selectedCatalogModel?.model_settings as { reasoning_effort?: string } | undefined)
    ?.reasoning_effort

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
    const padY = (parseFloat(styles.paddingTop) || 0) + (parseFloat(styles.paddingBottom) || 0)
    const borderY =
      (parseFloat(styles.borderTopWidth) || 0) + (parseFloat(styles.borderBottomWidth) || 0)
    const maxPx = lineHeight * COMPOSER_TEXTAREA_MAX_LINES + padY + borderY
    const contentH = el.scrollHeight
    el.style.height = `${Math.min(contentH, maxPx)}px`
    el.style.overflowY = contentH > maxPx ? 'auto' : 'hidden'
  }, [composeDraft])

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

  const hasAttachments =
    (pendingServerAttachments != null && pendingServerAttachments.length > 0) ||
    (pendingLocalFileNames != null && pendingLocalFileNames.length > 0)

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
            {CAPABILITY_PILLS.map(({ key, label, Icon }) => (
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
            ))}

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
              {pendingServerAttachments?.map((a) => (
                <span
                  key={`srv-${a.id}`}
                  className="attach-chip"
                  title={a.name}
                >
                  <Paperclip className="size-3" strokeWidth={2} />
                  <span className="max-w-[12rem] truncate">{a.name}</span>
                  <button
                    type="button"
                    className="link-btn"
                    aria-label={`Remove ${a.name}`}
                    disabled={Boolean(attachDisabled) || streaming}
                    onClick={() => onRemoveServerAttachment?.(a.id)}
                  >
                    <X className="size-3" strokeWidth={2.5} />
                  </button>
                </span>
              ))}
              {pendingLocalFileNames?.map((name, i) => (
                <span key={`loc-${i}-${name}`} className="attach-chip" title={name}>
                  <Paperclip className="size-3" strokeWidth={2} />
                  <span className="max-w-[12rem] truncate">{name}</span>
                  <button
                    type="button"
                    className="link-btn"
                    aria-label={`Remove ${name}`}
                    disabled={Boolean(attachDisabled) || streaming}
                    onClick={() => onRemoveLocalFile?.(i)}
                  >
                    <X className="size-3" strokeWidth={2.5} />
                  </button>
                </span>
              ))}
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
                  if (!streaming && !composerDisabled && composeDraft.trim()) onSubmit()
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
              {streaming ? (
                <button
                  type="button"
                  className="btn btn-sm"
                  style={{ color: 'var(--err)' }}
                  aria-label="Stop generating"
                  onClick={onStop}
                >
                  <Square className="size-3" strokeWidth={2} fill="currentColor" />
                  Stop
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={composerDisabled || !composeDraft.trim()}
                  aria-label="Send message"
                  data-testid="chat-send-button"
                  onClick={onSubmit}
                >
                  <ArrowUp className="size-3" strokeWidth={2.5} />
                  Send
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

export function resolveSelectedCatalogModel(
  models: CatalogModelEntry[] | undefined,
  storedModel: string,
): CatalogModelEntry | null {
  if (storedModel.trim()) {
    return catalogModelByStoredModel(models, storedModel) ?? null
  }
  return portalDefaultCatalogModel(models)
}
