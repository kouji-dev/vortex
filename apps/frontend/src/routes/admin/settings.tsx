import { createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import {
  fetchModuleFlags,
  fetchSettings,
  patchModuleFlags,
  patchSettings,
} from '~/lib/admin-api'
import type { ModuleFlagsMap } from '~/lib/admin-types'
import {
  AUTH_FIELDS,
  castValue,
  diffSettings,
  GENERAL_FIELDS,
  KNOWN_MODULES,
  NOTIFICATIONS_FIELDS,
  RETENTION_FIELDS,
  SETTINGS_TABS,
  type SettingsField,
  type SettingsTab,
  validateNumberField,
} from '~/lib/settings-form'

export const Route = createFileRoute('/admin/settings')({
  component: SettingsPage,
})

function SettingsPage() {
  const [tab, setTab] = React.useState<SettingsTab>('general')

  return (
    <div className="panel" data-testid="admin-settings">
      {/* Section title comes from the ModuleShell ribbon; no duplicate header here. */}
      <div className="panel-body" style={{ padding: 0 }}>
        <div
          role="tablist"
          aria-label="Settings tabs"
          style={{ display: 'flex', borderBottom: '1px solid var(--line)' }}
          data-testid="admin-settings-tabs"
        >
          {SETTINGS_TABS.map((t) => {
            const active = tab === t.value
            return (
              <button
                key={t.value}
                role="tab"
                aria-selected={active}
                onClick={() => setTab(t.value)}
                data-testid={`admin-settings-tab-${t.value}`}
                style={{
                  background: 'transparent',
                  border: 'none',
                  borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
                  color: active ? 'var(--ink)' : 'var(--ink-3)',
                  padding: '10px 16px',
                  fontSize: 12,
                  fontWeight: active ? 600 : 400,
                  cursor: 'pointer',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {t.label}
              </button>
            )
          })}
        </div>

        <div style={{ padding: 16 }}>
          {tab === 'general' && <KvTab title="General" fields={GENERAL_FIELDS} testId="admin-settings-general" />}
          {tab === 'modules' && <ModulesTab />}
          {tab === 'notifications' && <KvTab title="Notifications" fields={NOTIFICATIONS_FIELDS} testId="admin-settings-notifications" />}
          {tab === 'retention' && <KvTab title="Retention" fields={RETENTION_FIELDS} testId="admin-settings-retention" />}
          {tab === 'auth' && <KvTab title="Auth policy" fields={AUTH_FIELDS} testId="admin-settings-auth" />}
        </div>
      </div>
    </div>
  )
}

function KvTab({ fields, testId }: { title: string; fields: SettingsField[]; testId: string }) {
  const qc = useQueryClient()
  const all = useQuery({ queryKey: ['admin', 'settings'], queryFn: fetchSettings })
  const [edited, setEdited] = React.useState<Record<string, unknown> | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  const current = React.useMemo(() => {
    const out: Record<string, unknown> = {}
    if (!all.data) return out
    for (const f of fields) {
      const v = all.data.settings[f.key]
      out[f.key] = v ?? (f.type === 'boolean' ? false : f.type === 'number' ? null : '')
    }
    return out
  }, [all.data, fields])

  // Reset edits when data changes
  React.useEffect(() => {
    if (all.data) setEdited(null)
  }, [all.data])

  const view = edited ?? current
  const dirty = edited != null && Object.keys(diffSettings(current, edited)).length > 0

  const save = useMutation({
    mutationFn: (patch: Record<string, unknown>) => patchSettings(patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'settings'] })
      setEdited(null)
    },
  })

  function setField(field: SettingsField, raw: string | boolean) {
    if (field.type === 'number' && typeof raw === 'string') {
      const err = validateNumberField(raw)
      setError(err)
      if (err) return
    } else {
      setError(null)
    }
    const next = { ...(edited ?? current), [field.key]: castValue(field, raw) }
    setEdited(next)
  }

  function submit() {
    if (!edited) return
    const patch = diffSettings(current, edited)
    save.mutate(patch)
  }

  if (all.isPending) return <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>
  if (all.error) return <p style={{ fontSize: 12, color: 'var(--red)' }}>{(all.error as Error).message}</p>

  return (
    <div data-testid={testId}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 600 }}>
        {fields.map((f) => (
          <FieldRow key={f.key} field={f} value={view[f.key]} onChange={(v) => setField(f, v)} />
        ))}
      </div>
      {(error || save.error) && (
        <p style={{ fontSize: 11, color: 'var(--red)', marginTop: 12 }}>
          {error ?? (save.error as Error).message}
        </p>
      )}
      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        <button
          className="btn btn-primary"
          disabled={!dirty || save.isPending}
          onClick={submit}
          data-testid={`${testId}-save`}
        >
          {save.isPending ? 'Saving…' : 'Save'}
        </button>
        <button className="btn btn-sm" disabled={!dirty} onClick={() => setEdited(null)}>Revert</button>
      </div>
    </div>
  )
}

function FieldRow({
  field,
  value,
  onChange,
}: {
  field: SettingsField
  value: unknown
  onChange: (v: string | boolean) => void
}) {
  if (field.type === 'boolean') {
    return (
      <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12 }}>
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          data-testid={`admin-settings-field-${field.key}`}
        />
        <span style={{ color: 'var(--ink)' }}>{field.label}</span>
        {field.description && <span className="meta" style={{ marginLeft: 'auto' }}>{field.description}</span>}
      </label>
    )
  }
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11 }}>
      <span style={{ color: 'var(--ink-2)' }}>
        {field.label}
        {field.description && <span className="meta" style={{ marginLeft: 8 }}>{field.description}</span>}
      </span>
      <input
        type={field.type === 'number' ? 'number' : 'text'}
        value={value == null ? '' : String(value)}
        onChange={(e) => onChange(e.target.value)}
        data-testid={`admin-settings-field-${field.key}`}
        style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
      />
    </label>
  )
}

function ModulesTab() {
  const qc = useQueryClient()
  const data = useQuery({ queryKey: ['admin', 'module-flags'], queryFn: fetchModuleFlags })

  const patch = useMutation({
    mutationFn: (modules: ModuleFlagsMap['modules']) => {
      const body: Record<string, { enabled?: boolean }> = {}
      for (const [k, v] of Object.entries(modules)) body[k] = { enabled: v.enabled }
      return patchModuleFlags(body)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'module-flags'] }),
  })

  if (data.isPending) return <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>
  if (data.error) return <p style={{ fontSize: 12, color: 'var(--red)' }}>{(data.error as Error).message}</p>

  const current = data.data?.modules ?? {}

  function toggle(module: string) {
    const existing = current[module] ?? { enabled: true, gates: {} }
    const next = { ...current, [module]: { ...existing, enabled: !existing.enabled } }
    patch.mutate(next)
  }

  return (
    <div data-testid="admin-settings-modules">
      <p style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 12 }}>
        Toggle modules on or off for this organisation. Disabled modules return 503 to API callers.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxWidth: 500 }}>
        {KNOWN_MODULES.map((m) => {
          const flag = current[m] ?? { enabled: true, gates: {} }
          return (
            <label
              key={m}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '8px 12px',
                border: '1px solid var(--line)',
                borderRadius: 4,
                background: 'var(--bg-2)',
              }}
            >
              <input
                type="checkbox"
                checked={flag.enabled}
                onChange={() => toggle(m)}
                disabled={patch.isPending}
                data-testid={`admin-settings-module-${m}`}
              />
              <span style={{ fontSize: 12, color: 'var(--ink)', fontFamily: 'var(--font-mono)', flex: 1 }}>{m}</span>
              <span className="meta" style={{ color: flag.enabled ? 'var(--accent)' : 'var(--red)' }}>
                {flag.enabled ? 'enabled' : 'disabled'}
              </span>
            </label>
          )
        })}
      </div>
      {patch.error && (
        <p style={{ fontSize: 11, color: 'var(--red)', marginTop: 12 }}>{(patch.error as Error).message}</p>
      )}
    </div>
  )
}
