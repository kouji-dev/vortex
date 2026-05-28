import { createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import {
  createIdpConnection,
  deleteIdpConnection,
  fetchIdpConnections,
  updateIdpConnection,
} from '~/lib/admin-api'
import type { IdpConnection, IdpKind } from '~/lib/admin-types'
import { getIdpFields, validateIdpConfig } from '~/lib/idp-config'

export const Route = createFileRoute('/admin/sso')({
  component: SsoPage,
})

const KINDS: { value: IdpKind; label: string }[] = [
  { value: 'oidc', label: 'Generic OIDC' },
  { value: 'saml', label: 'Generic SAML' },
  { value: 'entra', label: 'Microsoft Entra ID' },
  { value: 'okta', label: 'Okta' },
  { value: 'google', label: 'Google Workspace' },
]

function SsoPage() {
  const qc = useQueryClient()
  const list = useQuery({ queryKey: ['admin', 'idp'], queryFn: fetchIdpConnections })
  const [editing, setEditing] = React.useState<IdpConnection | 'new' | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['admin', 'idp'] })

  const createMut = useMutation({ mutationFn: createIdpConnection, onSuccess: () => { invalidate(); setEditing(null) } })
  const updateMut = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Parameters<typeof updateIdpConnection>[1] }) =>
      updateIdpConnection(id, patch),
    onSuccess: invalidate,
  })
  const deleteMut = useMutation({ mutationFn: deleteIdpConnection, onSuccess: invalidate })

  return (
    <div className="panel" data-testid="admin-sso">
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>SSO / Identity Providers</span>
        <button
          className="btn btn-primary"
          onClick={() => setEditing('new')}
          data-testid="admin-sso-add"
        >
          Add connection
        </button>
      </div>

      <div className="panel-body" style={{ padding: 16 }}>
        {list.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
        {list.error && <p style={{ fontSize: 12, color: 'var(--red)' }}>{(list.error as Error).message}</p>}

        {list.data && list.data.length === 0 && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No IdP connections configured.</p>
        )}

        {list.data && list.data.length > 0 && (
          <div className="tbl">
            <div className="audit-row" style={{ gridTemplateColumns: '1fr 100px 1fr 80px 110px 100px', background: 'var(--bg-2)', borderBottom: '1px solid var(--line)', fontWeight: 600, fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <span>Name</span><span>Kind</span><span>Domain</span><span>Enabled</span><span>SSO required</span><span />
            </div>
            {list.data.map((c) => (
              <div key={c.id} className="audit-row" style={{ gridTemplateColumns: '1fr 100px 1fr 80px 110px 100px' }}>
                <span style={{ color: 'var(--ink)' }}>{c.name}</span>
                <span className="meta">{c.kind}</span>
                <span className="meta">{c.domain ?? '—'}</span>
                <Toggle
                  checked={c.enabled}
                  onChange={(v) => updateMut.mutate({ id: c.id, patch: { enabled: v } })}
                  testId={`admin-sso-enabled-${c.id}`}
                />
                <Toggle
                  checked={c.sso_required}
                  onChange={(v) => updateMut.mutate({ id: c.id, patch: { sso_required: v } })}
                  testId={`admin-sso-required-${c.id}`}
                />
                <div style={{ display: 'flex', gap: 4 }}>
                  <button className="btn btn-sm" onClick={() => setEditing(c)}>Edit</button>
                  <button
                    className="btn btn-sm"
                    style={{ color: 'var(--red)' }}
                    onClick={() => { if (confirm(`Delete connection "${c.name}"?`)) deleteMut.mutate(c.id) }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {editing && (
          <IdpForm
            initial={editing === 'new' ? null : editing}
            saving={createMut.isPending || updateMut.isPending}
            error={(createMut.error || updateMut.error)?.message ?? null}
            onCancel={() => setEditing(null)}
            onSave={(values) => {
              if (editing === 'new') {
                createMut.mutate(values)
              } else {
                updateMut.mutate({ id: editing.id, patch: values })
              }
            }}
          />
        )}
      </div>
    </div>
  )
}

function Toggle({
  checked,
  onChange,
  testId,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  testId?: string
}) {
  return (
    <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 11 }}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        data-testid={testId}
      />
      <span className="meta">{checked ? 'on' : 'off'}</span>
    </label>
  )
}

function IdpForm({
  initial,
  saving,
  error,
  onSave,
  onCancel,
}: {
  initial: IdpConnection | null
  saving: boolean
  error: string | null
  onSave: (v: {
    kind: IdpKind
    name: string
    domain: string | null
    config: Record<string, string>
    enabled: boolean
    sso_required: boolean
  }) => void
  onCancel: () => void
}) {
  const [kind, setKind] = React.useState<IdpKind>(initial?.kind ?? 'oidc')
  const [name, setName] = React.useState(initial?.name ?? '')
  const [domain, setDomain] = React.useState(initial?.domain ?? '')
  const [enabled, setEnabled] = React.useState(initial?.enabled ?? true)
  const [ssoRequired, setSsoRequired] = React.useState(initial?.sso_required ?? false)
  const [config, setConfig] = React.useState<Record<string, string>>(initial?.config ?? {})
  const [validationErrors, setValidationErrors] = React.useState<string[]>([])

  const fields = getIdpFields(kind)

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const missing = validateIdpConfig(kind, config)
    if (missing.length > 0) {
      setValidationErrors(missing)
      return
    }
    setValidationErrors([])
    onSave({
      kind,
      name,
      domain: domain.trim() || null,
      config,
      enabled,
      sso_required: ssoRequired,
    })
  }

  return (
    <form
      onSubmit={submit}
      data-testid="admin-sso-form"
      style={{ marginTop: 20, padding: 16, border: '1px solid var(--line)', borderRadius: 6, background: 'var(--bg-2)' }}
    >
      <h3 style={{ fontSize: 13, marginBottom: 12 }}>{initial ? `Edit ${initial.name}` : 'New IdP connection'}</h3>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11 }}>
          Provider
          <select
            value={kind}
            onChange={(e) => { setKind(e.target.value as IdpKind); setConfig({}) }}
            disabled={!!initial}
            style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
          >
            {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
          </select>
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11 }}>
          Display name
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Acme SSO"
            style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, gridColumn: 'span 2' }}>
          Email domain (for auto-routing, optional)
          <input
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="acme.com"
            style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
          />
        </label>

        {fields.map((f) => (
          <label
            key={f.key}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
              fontSize: 11,
              gridColumn: f.type === 'textarea' ? 'span 2' : undefined,
            }}
          >
            {f.label}{f.required ? ' *' : ''}
            {f.type === 'textarea' ? (
              <textarea
                required={f.required}
                value={config[f.key] ?? ''}
                onChange={(e) => setConfig({ ...config, [f.key]: e.target.value })}
                placeholder={f.placeholder}
                rows={4}
                style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12, fontFamily: 'var(--font-mono)' }}
              />
            ) : (
              <input
                required={f.required}
                type={f.type}
                value={config[f.key] ?? ''}
                onChange={(e) => setConfig({ ...config, [f.key]: e.target.value })}
                placeholder={f.placeholder}
                style={{
                  borderRadius: 4,
                  border: validationErrors.includes(f.key) ? '1px solid var(--red)' : '1px solid var(--line)',
                  background: 'var(--bg)',
                  color: 'var(--ink)',
                  padding: '4px 8px',
                  fontSize: 12,
                }}
              />
            )}
          </label>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 16, marginTop: 12 }}>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Enabled
        </label>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
          <input type="checkbox" checked={ssoRequired} onChange={(e) => setSsoRequired(e.target.checked)} />
          Require SSO (block password login)
        </label>
      </div>

      {error && <p style={{ marginTop: 8, fontSize: 11, color: 'var(--red)' }}>{error}</p>}
      {validationErrors.length > 0 && (
        <p style={{ marginTop: 8, fontSize: 11, color: 'var(--red)' }}>
          Missing required: {validationErrors.join(', ')}
        </p>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? 'Saving…' : initial ? 'Save' : 'Create'}
        </button>
        <button type="button" className="btn btn-sm" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}
