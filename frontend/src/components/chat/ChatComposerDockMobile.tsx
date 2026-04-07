// frontend/src/components/chat/ChatComposerDockMobile.tsx
import { ArrowUp, Lock, Paperclip, Settings2, Sparkles, Square, X } from 'lucide-react'
import * as React from 'react'

import {
  ModelTuningModal,
  type SessionModelTuning,
  defaultTuningFromCatalog,
} from '~/components/chat/ModelTuningModal'
import { RequestAccessModal } from '~/components/chat/RequestAccessModal'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select'
import type { CapabilityToggles, CatalogModelEntry } from '~/lib/chat-types'
import {
  catalogModelByStoredModel,
  portalDefaultCatalogModel,
} from '~/hooks/useCatalogModelsQuery'
import type { CapabilityKey } from '~/components/chat/ChatComposerDock'

const CATALOG_SELECT_PREFIX = 'catalog:' as const
const COMPOSER_TEXTAREA_MAX_LINES = 6

const CAPABILITY_MENU: { key: CapabilityKey; label: string }[] = [
  { key: 'reflection', label: 'Reflection' },
  { key: 'research', label: 'Research' },
  { key: 'web', label: 'Web stance' },
]

function CapabilityTag({
  label,
  onRemove,
  disabled,
}: {
  label: string
  onRemove: () => void
  disabled?: boolean
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-neutral-200 bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-800 dark:border-neutral-600 dark:bg-neutral-800 dark:text-neutral-200">
      {label}
      <button
        type="button"
        className="rounded-full p-0.5 text-neutral-500 hover:bg-neutral-200 hover:text-neutral-800 dark:hover:bg-neutral-700 dark:hover:text-neutral-100"
        aria-label={`Remove ${label}`}
        disabled={disabled}
        onClick={onRemove}
      >
        <X className="h-3 w-3" strokeWidth={2.5} />
      </button>
    </span>
  )
}

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
  modelSelectDisabled,
  capabilities,
  onToggleCapability,
  capabilityDisabled,
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
  const [tuningOpen, setTuningOpen] = React.useState(false)
  const [capsOpen, setCapsOpen] = React.useState(false)
  const [requestAccessModel, setRequestAccessModel] = React.useState<CatalogModelEntry | null>(null)
  const [modelSelectOpen, setModelSelectOpen] = React.useState(false)
  const composeTextareaRef = React.useRef<HTMLTextAreaElement>(null)
  const attachInputRef = React.useRef<HTMLInputElement>(null)

  const sorted = React.useMemo(
    () =>
      models == null
        ? []
        : [...models].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id),
    [models],
  )

  const storedCatalogRow =
    chatModel === '' ? null : catalogModelByStoredModel(models, chatModel)
  const defaultCatalogRow = React.useMemo(() => portalDefaultCatalogModel(models), [models])
  const selectValue =
    chatModel === ''
      ? defaultCatalogRow != null
        ? `${CATALOG_SELECT_PREFIX}${defaultCatalogRow.slug}`
        : ''
      : storedCatalogRow != null
        ? `${CATALOG_SELECT_PREFIX}${storedCatalogRow.slug}`
        : chatModel
  const modelLabel =
    chatModel === ''
      ? (defaultCatalogRow?.display_name ?? 'Model')
      : (storedCatalogRow?.display_name ?? chatModel)

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

  const handleModelSelectChange = (v: string) => {
    const id = v.startsWith(CATALOG_SELECT_PREFIX) ? v.slice(CATALOG_SELECT_PREFIX.length) : v
    onSelectChatModel(id)
    onCommitChatModel?.(id)
  }

  const canSubmit = !composerDisabled && !streaming && composeDraft.trim().length > 0
  const hasActiveCaps = capabilities.reflection || capabilities.research || capabilities.web

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

      {/* Capability sheet backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-black/30 transition-opacity duration-200 ${capsOpen ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
        onClick={() => setCapsOpen(false)}
        aria-hidden
      />

      {/* Capability sheet */}
      <div
        className={`fixed bottom-0 inset-x-0 z-50 rounded-t-2xl border-t border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-950 transition-transform duration-200 ease-out ${capsOpen ? 'translate-y-0' : 'translate-y-full'}`}
        aria-hidden={!capsOpen}
      >
        <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-neutral-300 dark:bg-neutral-700" />
        <p className="px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wide text-neutral-400">
          Capabilities
        </p>
        {CAPABILITY_MENU.map(({ key, label }) => {
          const on = capabilities[key]
          return (
            <button
              key={key}
              type="button"
              disabled={capabilityDisabled}
              onClick={() => { onToggleCapability(key); setCapsOpen(false) }}
              className="flex w-full items-center justify-between px-4 py-3.5 text-sm text-neutral-800 hover:bg-neutral-50 disabled:opacity-50 dark:text-neutral-200 dark:hover:bg-neutral-900"
            >
              <span className={on ? 'font-semibold' : ''}>{label}</span>
              {on && (
                <span className="size-2 rounded-full bg-neutral-900 dark:bg-neutral-100" />
              )}
            </button>
          )
        })}
        <div style={{ paddingBottom: 'env(safe-area-inset-bottom)' }} className="pb-2" />
      </div>

      {/* Composer */}
      <div
        className="border-t border-neutral-200 bg-white px-3 pt-2 dark:border-neutral-800 dark:bg-neutral-950"
        style={{ paddingBottom: 'max(0.5rem, env(safe-area-inset-bottom))' }}
      >
        {/* Active capability tags */}
        {hasActiveCaps && (
          <div className="mb-2 flex flex-wrap gap-1">
            {capabilities.reflection && (
              <CapabilityTag label="Reflection" disabled={capabilityDisabled} onRemove={() => onToggleCapability('reflection')} />
            )}
            {capabilities.research && (
              <CapabilityTag label="Research" disabled={capabilityDisabled} onRemove={() => onToggleCapability('research')} />
            )}
            {capabilities.web && (
              <CapabilityTag label="Web stance" disabled={capabilityDisabled} onRemove={() => onToggleCapability('web')} />
            )}
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
        <div className={`flex items-end gap-2 rounded-2xl border px-3 py-2 ${inputThemed}`}>
          <textarea
            ref={composeTextareaRef}
            className="min-h-0 flex-1 resize-none bg-transparent text-sm leading-snug outline-none placeholder:text-neutral-400"
            value={composeDraft}
            onChange={(e) => setComposeDraft(e.target.value)}
            placeholder="Message…"
            disabled={Boolean(composerDisabled) || streaming}
            rows={1}
            maxLength={maxInputChars}
            aria-label="Message"
          />
          {streaming ? (
            <button
              type="button"
              className="mb-0.5 flex size-8 shrink-0 items-center justify-center rounded-full border border-red-300 text-red-700 dark:border-red-800 dark:text-red-400"
              aria-label="Stop generating"
              onClick={onStop}
            >
              <Square className="size-3.5 fill-current" strokeWidth={2} />
            </button>
          ) : (
            <button
              type="button"
              className="mb-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-neutral-900 text-white shadow-sm disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900"
              disabled={!canSubmit}
              aria-label="Send message"
              onClick={onSubmit}
            >
              <ArrowUp className="size-4" strokeWidth={2.5} />
            </button>
          )}
        </div>

        {/* Icon tray */}
        <div className="mt-2 flex items-center gap-2">
          {onLocalFilesChosen != null && (
            <>
              <input
                ref={attachInputRef}
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
                className="flex h-11 w-11 items-center justify-center rounded-xl border border-neutral-200 text-neutral-600 hover:bg-neutral-50 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-900"
                aria-label="Attach files"
                disabled={Boolean(attachDisabled) || streaming}
                onClick={() => attachInputRef.current?.click()}
              >
                <Paperclip className="size-5" strokeWidth={2} />
              </button>
            </>
          )}

          <button
            type="button"
            className="flex h-11 w-11 items-center justify-center rounded-xl border border-neutral-200 text-neutral-600 hover:bg-neutral-50 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-900"
            aria-label="Toggle capabilities"
            disabled={capabilityDisabled}
            onClick={() => setCapsOpen(true)}
          >
            <Sparkles className="size-5" strokeWidth={2} />
          </button>

          <div className="min-w-0 flex-1">
            <label className="sr-only" htmlFor="chat-model-select-mobile">Model</label>
            <Select
              open={modelSelectOpen}
              onOpenChange={setModelSelectOpen}
              value={selectValue || undefined}
              onValueChange={handleModelSelectChange}
              disabled={modelSelectDisabled || modelsPending || sorted.length === 0}
            >
              <SelectTrigger
                id="chat-model-select-mobile"
                data-testid="chat-model-select"
                title={modelLabel}
                className="h-11 w-full border-neutral-200 px-3 text-xs dark:border-neutral-700 [&_svg]:size-3"
              >
                <SelectValue placeholder={modelLabel} />
              </SelectTrigger>
              <SelectContent position="popper" side="top" sideOffset={6} align="start">
                {!modelsPending &&
                  sorted.map((m) => {
                    const actionable =
                      m.can_request_access || Boolean(m.request_access_url)
                    if (m.accessible) {
                      return (
                        <SelectItem
                          key={m.id}
                          value={`${CATALOG_SELECT_PREFIX}${m.slug}`}
                          textValue={m.display_name}
                        >
                          {m.display_name}
                        </SelectItem>
                      )
                    }
                    return (
                      <SelectItem
                        key={m.id}
                        value={`${CATALOG_SELECT_PREFIX}${m.slug}`}
                        disabled
                        textValue={m.display_name}
                        itemSuffix={
                          actionable ? (
                            <button
                              type="button"
                              className="inline-flex size-6 shrink-0 items-center justify-center rounded-sm text-neutral-600 hover:bg-neutral-200/80 dark:text-neutral-400 dark:hover:bg-neutral-800"
                              aria-label={`Request access to ${m.display_name}`}
                              onPointerDown={(e) => {
                                e.preventDefault()
                                e.stopPropagation()
                              }}
                              onClick={(e) => {
                                e.preventDefault()
                                e.stopPropagation()
                                setModelSelectOpen(false)
                                if (m.request_access_url) {
                                  window.open(
                                    m.request_access_url,
                                    '_blank',
                                    'noopener,noreferrer',
                                  )
                                } else {
                                  setRequestAccessModel(m)
                                }
                              }}
                            >
                              <Lock className="size-3" strokeWidth={2} />
                            </button>
                          ) : undefined
                        }
                      >
                        {actionable ? m.display_name : `${m.display_name} (locked)`}
                      </SelectItem>
                    )
                  })}
              </SelectContent>
            </Select>
            {modelsError && (
              <p className="mt-0.5 text-[10px] text-amber-600 dark:text-amber-400">Catalog failed</p>
            )}
          </div>

          {kbSlot != null && <div className="shrink-0">{kbSlot}</div>}

          <button
            type="button"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-neutral-200 text-neutral-600 hover:bg-neutral-50 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-900"
            aria-label="Model settings"
            disabled={!selectedCatalogModel}
            onClick={() => {
              if (selectedCatalogModel) onTuningChange(defaultTuningFromCatalog(selectedCatalogModel))
              setTuningOpen(true)
            }}
          >
            <Settings2 className="size-5" strokeWidth={2} />
          </button>
        </div>
      </div>
    </>
  )
}
