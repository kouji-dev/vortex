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

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="mono"
      style={{
        fontSize: 10,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        color: 'var(--ink-3)',
        margin: 0,
        padding: '10px 14px 4px',
        fontWeight: 500,
      }}
    >
      {children}
    </p>
  )
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
        className={`fixed inset-0 z-40 transition-opacity duration-200 ${open ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
        onClick={onClose}
        aria-hidden
        style={{ background: 'color-mix(in oklch, var(--ink) 45%, transparent)' }}
      />

      {/* Sheet */}
      <div
        className={`fixed inset-x-0 bottom-0 z-50 transition-transform duration-200 ease-out ${open ? 'translate-y-0' : 'translate-y-full'}`}
        role="dialog"
        aria-modal="true"
        aria-label="Composer options"
        aria-hidden={!open}
        style={{
          background: 'var(--panel)',
          borderTop: '1px solid var(--line)',
          borderTopLeftRadius: 14,
          borderTopRightRadius: 14,
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        <div
          aria-hidden
          className="mx-auto mt-2 h-1 w-10 rounded-full"
          style={{ background: 'var(--line-2)' }}
        />

        {/* ── Model list ──────────────────────────────────── */}
        <SectionLabel>Model</SectionLabel>
        {modelsPending && <PrismLogo state="loading" size={16} className="mx-4 my-2" />}
        {modelsError && (
          <p className="px-4 py-2" style={{ fontSize: 12, color: 'var(--warn)' }}>
            Failed to load models
          </p>
        )}
        <div
          className="max-h-64 overflow-y-auto overscroll-contain"
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
                className="flex w-full items-center justify-between disabled:opacity-40"
                style={{
                  padding: '12px 14px',
                  fontSize: 13,
                  background: isSelected ? 'var(--hl)' : 'transparent',
                  color: 'var(--ink)',
                  borderBottom: '1px solid var(--line-2)',
                }}
              >
                <span style={{ fontWeight: isSelected ? 600 : 400 }}>
                  {m.display_name}
                </span>
                <span className="flex items-center gap-2">
                  {!m.accessible && actionable && (
                    <Lock className="size-3.5" strokeWidth={2} style={{ color: 'var(--ink-3)' }} />
                  )}
                  {isSelected && (
                    <Check className="size-4" strokeWidth={2.5} style={{ color: 'var(--accent)' }} />
                  )}
                </span>
              </button>
            )
          })}
        </div>

        {/* ── Capabilities ─────────────────────────────────── */}
        <SectionLabel>Capabilities</SectionLabel>
        {CAPABILITY_MENU.map(({ key, label, Icon }) => {
          const on = capabilities[key]
          const desc = capabilityDescriptions?.[key]
          return (
            <button
              key={key}
              type="button"
              disabled={capabilityDisabled}
              onClick={() => onToggleCapability(key)}
              className="flex w-full items-center justify-between disabled:opacity-50"
              style={{
                padding: '12px 14px',
                fontSize: 13,
                color: 'var(--ink)',
                borderBottom: '1px solid var(--line-2)',
                background: on ? 'color-mix(in oklch, var(--accent) 8%, var(--panel))' : 'transparent',
              }}
            >
              <span className="flex items-center gap-3">
                <Icon
                  className="size-4 shrink-0"
                  strokeWidth={2}
                  style={{ color: on ? 'var(--accent)' : 'var(--ink-3)' }}
                />
                <span className="flex flex-col gap-0.5 text-left">
                  <span style={{ fontWeight: on ? 600 : 400, color: on ? 'var(--accent)' : 'var(--ink)' }}>
                    {label}
                  </span>
                  {desc && (
                    <span style={{ fontSize: 11.5, lineHeight: 1.4, color: 'var(--ink-3)' }}>
                      {desc}
                    </span>
                  )}
                </span>
              </span>
              {on && (
                <Check className="size-4 shrink-0" strokeWidth={2.5} style={{ color: 'var(--accent)' }} />
              )}
            </button>
          )
        })}

        {/* ── Bottom actions ────────────────────────────────── */}
        <div
          className="flex items-center gap-2"
          style={{
            padding: '10px 14px',
            borderTop: '1px solid var(--line)',
            background: 'var(--bg)',
          }}
        >
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
                className="btn btn-sm"
                aria-label="Attach files"
                disabled={Boolean(attachDisabled) || Boolean(streaming)}
                onClick={() => attachInputRef.current?.click()}
              >
                <Paperclip className="size-3.5" strokeWidth={2} aria-hidden />
                Attach
              </button>
            </>
          )}

          {kbSlot != null && <div className="shrink-0">{kbSlot}</div>}

          <div className="flex-1" />

          <button
            type="button"
            className="btn btn-sm"
            aria-label="Model settings"
            disabled={!selectedCatalogModel}
            onClick={() => {
              if (selectedCatalogModel) onTuningChange(defaultTuningFromCatalog(selectedCatalogModel))
              setTuningOpen(true)
              onClose()
            }}
          >
            <Settings2 className="size-3.5" strokeWidth={2} aria-hidden />
            Settings
          </button>
        </div>

        <div aria-hidden className="shrink-0" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }} />
      </div>
    </>
  )
}
