// frontend/src/components/chat/ModelPickerSheet.tsx
// Mobile bottom sheet for model + capability selection.
import { BookOpen, Brain, Check, Lock, Paperclip, Settings2, type LucideIcon } from 'lucide-react'
import * as React from 'react'
import { PrismLogo } from '~/components/brand'
import {
  ModelTuningModal,
  type SessionModelTuning,
  defaultTuningFromCatalog,
} from '~/components/chat/ModelTuningModal'
import { RequestAccessModal } from '~/components/chat/RequestAccessModal'
import type { CapabilityKey } from '~/components/chat/ChatComposerDock'
import type { CapabilityToggles, CatalogModelEntry } from '~/lib/chat-types'

const CAPABILITY_MENU: { key: CapabilityKey; label: string; Icon: LucideIcon }[] = [
  { key: 'reflection', label: 'Reflection', Icon: Brain },
  { key: 'research', label: 'Research', Icon: BookOpen },
]

type ModelPickerSheetProps = {
  open: boolean
  onClose: () => void

  // Model list
  sorted: CatalogModelEntry[]
  effectiveSlug: string
  modelsPending: boolean
  modelsError: Error | null
  onSelectModel: (slug: string, m: CatalogModelEntry) => void

  // Capabilities
  capabilities: CapabilityToggles
  onToggleCapability: (key: CapabilityKey) => void
  capabilityDisabled?: boolean
  capabilityDescriptions?: Record<CapabilityKey, string>

  // Bottom actions
  kbSlot?: React.ReactNode
  onLocalFilesChosen?: (files: File[]) => void
  attachDisabled?: boolean
  streaming?: boolean
  selectedCatalogModel: CatalogModelEntry | null
  tuning: SessionModelTuning
  onTuningChange: (t: SessionModelTuning) => void
}

export function ModelPickerSheet({
  open,
  onClose,
  sorted,
  effectiveSlug,
  modelsPending,
  modelsError,
  onSelectModel,
  capabilities,
  onToggleCapability,
  capabilityDisabled,
  capabilityDescriptions,
  kbSlot,
  onLocalFilesChosen,
  attachDisabled,
  streaming,
  selectedCatalogModel,
  tuning,
  onTuningChange,
}: ModelPickerSheetProps) {
  const [tuningOpen, setTuningOpen] = React.useState(false)
  const [requestAccessModel, setRequestAccessModel] = React.useState<CatalogModelEntry | null>(null)
  const attachInputRef = React.useRef<HTMLInputElement>(null)

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

      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-black/30 transition-opacity duration-200 ${open ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
        onClick={onClose}
        aria-hidden
      />

      {/* Sheet */}
      <div
        className={`fixed inset-x-0 bottom-0 z-50 rounded-t-2xl border-t border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-950 transition-transform duration-200 ease-out ${open ? 'translate-y-0' : 'translate-y-full'}`}
        role="dialog"
        aria-modal="true"
        aria-label="Composer options"
        aria-hidden={!open}
      >
        <div aria-hidden className="mx-auto mt-2 h-1 w-10 rounded-full bg-neutral-300 dark:bg-neutral-700" />

        {/* ── Model list ──────────────────────────────────── */}
        <div className="px-4 pb-1 pt-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-neutral-400">Model</p>
        </div>
        {modelsPending && <PrismLogo state="loading" size={16} className="mx-4 my-2" />}
        {modelsError && (
          <p className="px-4 py-2 text-xs text-amber-600 dark:text-amber-400">Failed to load models</p>
        )}
        <div
          className="max-h-64 overflow-y-scroll overscroll-contain"
          style={{ WebkitOverflowScrolling: 'touch' } as React.CSSProperties}
        >
          {sorted.map((m) => {
            const isSelected = m.slug === effectiveSlug
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
                      onClose()
                    }
                    return
                  }
                  onSelectModel(m.slug, m)
                }}
                className={`flex w-full items-center justify-between px-4 py-3 text-sm disabled:opacity-40 ${isSelected ? 'bg-neutral-100 dark:bg-neutral-800' : 'hover:bg-neutral-50 dark:hover:bg-neutral-900'}`}
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

        {/* ── Bottom actions ────────────────────────────────── */}
        <div className="flex items-center gap-2 px-4 py-3">
          {onLocalFilesChosen != null && (
            <>
              <input
                ref={attachInputRef}
                type="file"
                multiple
                className="sr-only"
                accept=".txt,.md,text/plain,text/markdown"
                disabled={Boolean(attachDisabled) || Boolean(streaming)}
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? [])
                  e.target.value = ''
                  if (files.length) {
                    onLocalFilesChosen(files)
                    onClose()
                  }
                }}
              />
              <button
                type="button"
                className="flex h-10 items-center gap-2 rounded-xl border border-neutral-200 px-3 text-sm text-neutral-700 hover:bg-neutral-50 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-900"
                aria-label="Attach files"
                disabled={Boolean(attachDisabled) || Boolean(streaming)}
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
              onClose()
            }}
          >
            <Settings2 className="size-4" strokeWidth={2} />
            Settings
          </button>
        </div>

        <div aria-hidden className="shrink-0" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }} />
      </div>
    </>
  )
}
