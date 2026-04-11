// frontend/src/components/chat/ChatComposerDockMobile.tsx
import { ArrowUp, BookOpen, Brain, Check, Lock, Paperclip, Settings2, SlidersHorizontal, Square, X, type LucideIcon } from 'lucide-react'
import * as React from 'react'
import { PrismLogo } from '~/components/brand'

import {
  ModelTuningModal,
  type SessionModelTuning,
  defaultTuningFromCatalog,
} from '~/components/chat/ModelTuningModal'
import { RequestAccessModal } from '~/components/chat/RequestAccessModal'
import type { CapabilityToggles, CatalogModelEntry } from '~/lib/chat-types'
import {
  catalogModelByStoredModel,
  portalDefaultCatalogModel,
} from '~/hooks/useCatalogModelsQuery'
import type { CapabilityKey } from '~/components/chat/ChatComposerDock'

const CATALOG_SELECT_PREFIX = 'catalog:' as const
const COMPOSER_TEXTAREA_MAX_LINES = 6

const CAPABILITY_MENU: { key: CapabilityKey; label: string; Icon: LucideIcon }[] = [
  { key: 'reflection', label: 'Reflection', Icon: Brain },
  { key: 'research', label: 'Research', Icon: BookOpen },
]

function CapabilityTag({
  label,
  icon: Icon,
  onRemove,
  disabled,
}: {
  label: string
  icon: LucideIcon
  onRemove: () => void
  disabled?: boolean
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-neutral-200 bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-800 dark:border-neutral-600 dark:bg-neutral-800 dark:text-neutral-200">
      <Icon className="h-3 w-3 shrink-0" strokeWidth={2} />
      {label}
      <button
        type="button"
        className="rounded-full p-0.5 text-neutral-500 hover:bg-neutral-200 hover:text-neutral-800 dark:hover:bg-neutral-700 dark:hover:text-neutral-100"
        aria-label={`Remove ${label}`}
        disabled={disabled}
        onClick={onRemove}
      >
        <X className="size-2.5" strokeWidth={2.5} />
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
  const [configOpen, setConfigOpen] = React.useState(false)
  const [tuningOpen, setTuningOpen] = React.useState(false)
  const [requestAccessModel, setRequestAccessModel] = React.useState<CatalogModelEntry | null>(null)
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
  const modelLabel =
    chatModel === ''
      ? (defaultCatalogRow?.display_name ?? 'Model')
      : (storedCatalogRow?.display_name ?? chatModel)

  const effectiveModelSlug =
    chatModel === ''
      ? (defaultCatalogRow?.slug ?? '')
      : (storedCatalogRow?.slug ?? '')

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

  const handleModelSelect = (slug: string, m: CatalogModelEntry) => {
    if (!m.accessible) return
    const id = `${CATALOG_SELECT_PREFIX}${slug}`
    onSelectChatModel(id)
    onCommitChatModel?.(id)
    setConfigOpen(false)
  }

  const canSubmit = !composerDisabled && !streaming && composeDraft.trim().length > 0
  const hasActiveCaps = capabilities.reflection || capabilities.research

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

      {/* Config sheet backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-black/30 transition-opacity duration-200 ${configOpen ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
        onClick={() => setConfigOpen(false)}
        aria-hidden
      />

      {/* Config sheet */}
      <div
        className={`fixed inset-x-0 bottom-0 z-50 rounded-t-2xl border-t border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-950 transition-transform duration-200 ease-out ${configOpen ? 'translate-y-0' : 'translate-y-full'}`}
        role="dialog"
        aria-modal="true"
        aria-label="Composer options"
        aria-hidden={!configOpen}
      >
        <div aria-hidden className="mx-auto mt-2 h-1 w-10 rounded-full bg-neutral-300 dark:bg-neutral-700" />

        {/* ── Model picker ──────────────────────────────────── */}
        <div className="px-4 pb-1 pt-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-neutral-400">Model</p>
        </div>
        {modelsPending && <PrismLogo state="loading" size={16} className="mx-4 my-2" />}
        {modelsError && (
          <p className="px-4 py-2 text-xs text-amber-600 dark:text-amber-400">Failed to load models</p>
        )}
        <div className="max-h-48 overflow-y-auto">
          {sorted.map((m) => {
            const isSelected = m.slug === effectiveModelSlug
            const actionable = m.can_request_access || Boolean(m.request_access_url)
            return (
              <button
                key={m.id}
                type="button"
                disabled={!m.accessible && !actionable}
                onClick={() => {
                  if (!m.accessible) {
                    if (m.request_access_url) {
                      window.open(m.request_access_url, '_blank', 'noopener,noreferrer')
                    } else if (m.can_request_access) {
                      setRequestAccessModel(m)
                      setConfigOpen(false)
                    }
                    return
                  }
                  handleModelSelect(m.slug, m)
                }}
                className="flex w-full items-center justify-between px-4 py-3 text-sm hover:bg-neutral-50 disabled:opacity-40 dark:hover:bg-neutral-900"
              >
                <span className={isSelected ? 'font-semibold text-neutral-900 dark:text-neutral-100' : 'text-neutral-800 dark:text-neutral-200'}>
                  {m.display_name}
                </span>
                <span className="flex items-center gap-2">
                  {!m.accessible && actionable && (
                    <Lock className="size-3.5 text-neutral-400" strokeWidth={2} />
                  )}
                  {isSelected && (
                    <Check className="size-4 text-neutral-900 dark:text-neutral-100" strokeWidth={2.5} />
                  )}
                </span>
              </button>
            )
          })}
        </div>

        <div className="mx-4 my-1 border-t border-neutral-100 dark:border-neutral-800" />

        {/* ── Capabilities ─────────────────────────────────── */}
        <div className="px-4 pb-1 pt-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-neutral-400">Capabilities</p>
        </div>
        {CAPABILITY_MENU.map(({ key, label, Icon }) => {
          const on = capabilities[key]
          const desc = capabilityDescriptions?.[key]
          return (
            <button
              key={key}
              type="button"
              disabled={capabilityDisabled}
              onClick={() => onToggleCapability(key)}
              className="flex w-full items-center justify-between px-4 py-3 text-sm text-neutral-800 hover:bg-neutral-50 disabled:opacity-50 dark:text-neutral-200 dark:hover:bg-neutral-900"
            >
              <span className="flex items-center gap-3">
                <Icon className="size-4 shrink-0 text-neutral-500 dark:text-neutral-400" strokeWidth={2} />
                <span className="flex flex-col gap-0.5 text-left">
                  <span className={on ? 'font-semibold text-neutral-900 dark:text-neutral-100' : ''}>{label}</span>
                  {desc && (
                    <span className="text-xs leading-snug text-neutral-500 dark:text-neutral-400">{desc}</span>
                  )}
                </span>
              </span>
              {on && <Check className="size-4 shrink-0 text-neutral-900 dark:text-neutral-100" strokeWidth={2.5} />}
            </button>
          )
        })}

        <div className="mx-4 my-1 border-t border-neutral-100 dark:border-neutral-800" />

        {/* ── Bottom actions row ────────────────────────────── */}
        <div className="flex items-center gap-2 px-4 py-3">
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
                  if (files.length) { onLocalFilesChosen(files); setConfigOpen(false) }
                }}
              />
              <button
                type="button"
                className="flex h-10 items-center gap-2 rounded-xl border border-neutral-200 px-3 text-sm text-neutral-700 hover:bg-neutral-50 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-900"
                aria-label="Attach files"
                disabled={Boolean(attachDisabled) || streaming}
                onClick={() => attachInputRef.current?.click()}
              >
                <Paperclip className="size-4" strokeWidth={2} />
                Attach
              </button>
            </>
          )}

          {kbSlot != null && (
            <div className="shrink-0 [&_button]:h-10 [&_button]:rounded-xl [&_button]:px-3 [&_button]:text-sm">{kbSlot}</div>
          )}

          <div className="flex-1" />

          <button
            type="button"
            className="flex h-10 items-center gap-2 rounded-xl border border-neutral-200 px-3 text-sm text-neutral-700 hover:bg-neutral-50 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-900"
            aria-label="Model settings"
            disabled={!selectedCatalogModel}
            onClick={() => {
              if (selectedCatalogModel) onTuningChange(defaultTuningFromCatalog(selectedCatalogModel))
              setTuningOpen(true)
              setConfigOpen(false)
            }}
          >
            <Settings2 className="size-4" strokeWidth={2} />
            Settings
          </button>
        </div>

        <div aria-hidden className="shrink-0" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }} />
      </div>

      {/* ── Composer bar ───────────────────────────────────────── */}
      <div
        className="border-t border-neutral-200 bg-white px-3 pt-2 dark:border-neutral-800 dark:bg-neutral-950"
        style={{ paddingBottom: 'max(0.5rem, env(safe-area-inset-bottom))' }}
      >
        {/* Active capability tags */}
        {hasActiveCaps && (
          <div className="mb-2 flex flex-wrap gap-1">
            {CAPABILITY_MENU.filter(({ key }) => capabilities[key]).map(({ key, label, Icon }) => (
              <CapabilityTag key={key} label={label} icon={Icon} disabled={capabilityDisabled} onRemove={() => onToggleCapability(key)} />
            ))}
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

        {/* Textarea pill — config · message · send all inside one border */}
        <div className={`flex items-center rounded-2xl border px-2 py-1.5 ${inputThemed}`}>
          {/* Config button — left, borderless, merged */}
          <button
            type="button"
            onClick={() => setConfigOpen(true)}
            className="flex size-7 shrink-0 items-center justify-center rounded-full text-neutral-400 hover:bg-neutral-100 hover:text-neutral-600 disabled:opacity-30 dark:hover:bg-neutral-800 dark:hover:text-neutral-300"
            aria-label="Composer options"
            disabled={Boolean(composerDisabled) && !streaming}
          >
            <SlidersHorizontal className="size-3.5" strokeWidth={2} />
          </button>

          {/* Textarea */}
          <textarea
            ref={composeTextareaRef}
            className="mx-2 min-h-0 flex-1 resize-none bg-transparent text-sm leading-snug outline-none placeholder:text-neutral-400"
            value={composeDraft}
            onChange={(e) => setComposeDraft(e.target.value)}
            placeholder="Message Vortex…"
            disabled={Boolean(composerDisabled) || streaming}
            rows={1}
            maxLength={maxInputChars}
            aria-label="Message"
          />

          {/* Send / stop button — right, small filled circle */}
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
