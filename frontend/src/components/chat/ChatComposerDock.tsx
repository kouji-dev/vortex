import { Lock, Plus, Send, Settings2, Square, X } from 'lucide-react'
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

const CATALOG_SELECT_PREFIX = 'catalog:' as const

const COMPOSER_TEXTAREA_MAX_LINES = 4

export type CapabilityKey = 'reflection' | 'research' | 'web'

const CAPABILITY_MENU: { key: CapabilityKey; label: string }[] = [
  { key: 'reflection', label: 'Reflection' },
  { key: 'research', label: 'Research' },
  { key: 'web', label: 'Web stance' },
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
}

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
}: ChatComposerDockProps) {
  const [requestAccessModel, setRequestAccessModel] = React.useState<CatalogModelEntry | null>(
    null,
  )
  const [tuningOpen, setTuningOpen] = React.useState(false)
  const [plusOpen, setPlusOpen] = React.useState(false)
  const [modelSelectOpen, setModelSelectOpen] = React.useState(false)
  const plusWrapRef = React.useRef<HTMLDivElement>(null)
  const composeTextareaRef = React.useRef<HTMLTextAreaElement>(null)

  const defaultCatalogRow = React.useMemo(() => portalDefaultCatalogModel(models), [models])
  const sorted = React.useMemo(
    () =>
      models == null
        ? []
        : [...models].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id),
    [models],
  )

  React.useEffect(() => {
    if (!plusOpen) return
    const onDoc = (e: MouseEvent) => {
      const el = plusWrapRef.current
      if (el && e.target instanceof Node && !el.contains(e.target)) setPlusOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [plusOpen])

  const selectModel = (id: string) => {
    onSelectChatModel(id)
    onCommitChatModel?.(id)
  }

  const handleModelSelectChange = (v: string) => {
    if (v === '__auto__') selectModel('')
    else if (v.startsWith(CATALOG_SELECT_PREFIX))
      selectModel(v.slice(CATALOG_SELECT_PREFIX.length))
    else selectModel(v)
  }

  const openTuning = () => {
    setPlusOpen(false)
    if (selectedCatalogModel) {
      onTuningChange(defaultTuningFromCatalog(selectedCatalogModel))
    }
    setTuningOpen(true)
  }

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

  const storedCatalogRow =
    chatModel === '' ? null : catalogModelByStoredModel(models, chatModel)
  const orphanCustomModel =
    chatModel !== '' &&
    !sorted.some((m) => m.slug === chatModel) &&
    !sorted.some((m) => m.api_model_id === chatModel)
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

      <div className="rounded-xl border border-neutral-200 bg-white shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
        <div className="p-2 pb-1.5">
          <textarea
            ref={composeTextareaRef}
            className={`min-h-0 w-full resize-none rounded-lg border px-2.5 py-2 text-sm leading-snug ${inputThemed}`}
            value={composeDraft}
            onChange={(e) => setComposeDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                if (!streaming && !composerDisabled && composeDraft.trim()) onSubmit()
              }
            }}
            placeholder="Message the assistant… (Shift+Enter for newline)"
            disabled={Boolean(composerDisabled) || streaming}
            rows={1}
            maxLength={maxInputChars}
            aria-label="Message"
          />
          <p className="mt-1 text-right text-[10px] tabular-nums text-neutral-400 dark:text-neutral-500">
            {composeDraft.length.toLocaleString()} / {maxInputChars.toLocaleString()}
          </p>
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-neutral-100 px-2 py-1.5 dark:border-neutral-800">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
            <div className="relative shrink-0" ref={plusWrapRef}>
            <button
              type="button"
              className="flex size-8 items-center justify-center rounded-lg border border-neutral-200 text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-900"
              aria-expanded={plusOpen}
              aria-haspopup="menu"
              aria-label="Add options"
              onClick={() => setPlusOpen((o) => !o)}
            >
              <Plus className="size-4" strokeWidth={2} />
            </button>
            {plusOpen && (
              <div
                className="absolute bottom-full left-0 z-50 mb-1 min-w-[200px] rounded-lg border border-neutral-200 bg-white py-0.5 shadow-lg dark:border-neutral-700 dark:bg-neutral-950"
                role="menu"
              >
                <p className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-neutral-400">
                  Capabilities
                </p>
                {CAPABILITY_MENU.map(({ key, label }) => {
                  const on = capabilities[key]
                  return (
                    <button
                      key={key}
                      type="button"
                      role="menuitem"
                      disabled={capabilityDisabled}
                      className="flex w-full px-2.5 py-1.5 text-left text-xs hover:bg-neutral-100 disabled:opacity-50 dark:hover:bg-neutral-900"
                      onClick={() => {
                        onToggleCapability(key)
                        setPlusOpen(false)
                      }}
                    >
                      <span className={on ? 'font-medium text-neutral-900 dark:text-neutral-100' : ''}>
                        {label}
                      </span>
                      {on && (
                        <span className="ml-auto text-xs text-neutral-400">on</span>
                      )}
                    </button>
                  )
                })}
                <div className="my-0.5 border-t border-neutral-100 dark:border-neutral-800" />
                <button
                  type="button"
                  role="menuitem"
                  className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left text-xs hover:bg-neutral-100 dark:hover:bg-neutral-900"
                  onClick={openTuning}
                >
                  <Settings2 className="size-3.5 shrink-0" />
                  Model settings
                </button>
              </div>
            )}
            </div>

            <div className="min-w-0">
            <label className="sr-only" htmlFor="chat-model-select">
              Model
            </label>
            <Select
              open={modelSelectOpen}
              onOpenChange={setModelSelectOpen}
              value={selectValue || undefined}
              onValueChange={handleModelSelectChange}
              disabled={
                modelSelectDisabled ||
                modelsPending ||
                sorted.length === 0 ||
                (chatModel === '' && defaultCatalogRow == null)
              }
            >
              <SelectTrigger
                id="chat-model-select"
                data-testid="chat-model-select"
                title={modelLabel}
                className="h-7 w-max max-w-44 border-neutral-200/90 px-1.5 py-0 text-[11px] leading-tight sm:max-w-52 dark:border-neutral-700 [&_svg]:size-3"
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
                {!modelsPending && orphanCustomModel && (
                  <SelectItem value={chatModel}>{chatModel} (custom)</SelectItem>
                )}
              </SelectContent>
            </Select>
            {modelsError && (
              <p className="mt-0.5 w-full text-[10px] leading-tight text-amber-600 dark:text-amber-400">
                Catalog failed to load
              </p>
            )}
            </div>

            {(capabilities.reflection ||
              capabilities.research ||
              capabilities.web) && (
              <div className="flex min-w-0 flex-wrap items-center gap-1">
                {capabilities.reflection && (
                  <CapabilityTag
                    label="Reflection"
                    disabled={capabilityDisabled}
                    onRemove={() => onToggleCapability('reflection')}
                  />
                )}
                {capabilities.research && (
                  <CapabilityTag
                    label="Research"
                    disabled={capabilityDisabled}
                    onRemove={() => onToggleCapability('research')}
                  />
                )}
                {capabilities.web && (
                  <CapabilityTag
                    label="Web stance"
                    disabled={capabilityDisabled}
                    onRemove={() => onToggleCapability('web')}
                  />
                )}
              </div>
            )}
          </div>

          {kbSlot != null && <div className="shrink-0">{kbSlot}</div>}

          <div className="shrink-0">
            {streaming ? (
              <button
                type="button"
                className="flex size-8 items-center justify-center rounded-lg border border-red-300 text-red-700 dark:border-red-800 dark:text-red-400"
                aria-label="Stop generating"
                onClick={onStop}
              >
                <Square className="size-3.5 fill-current" strokeWidth={2} />
              </button>
            ) : (
              <button
                type="button"
                className="flex size-8 items-center justify-center rounded-lg bg-neutral-900 text-white shadow-sm disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900"
                disabled={composerDisabled || !composeDraft.trim()}
                aria-label="Send message"
                onClick={onSubmit}
              >
                <Send className="size-4" strokeWidth={2} />
              </button>
            )}
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

/** @deprecated Use individual capability toggles; kept for any external use. */
export type CapabilityMode = 'none' | 'reflection' | 'research' | 'web'

export function capabilityModeFromToggles(c: CapabilityToggles): CapabilityMode {
  if (c.reflection) return 'reflection'
  if (c.research) return 'research'
  if (c.web) return 'web'
  return 'none'
}

export function togglesFromCapabilityMode(m: CapabilityMode): CapabilityToggles {
  return {
    reflection: m === 'reflection',
    research: m === 'research',
    web: m === 'web',
  }
}
