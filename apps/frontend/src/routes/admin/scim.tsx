import { createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import {
  createScimEndpoint,
  fetchScimEndpoints,
  revokeScimEndpoint,
  upsertScimGroupRole,
} from '~/lib/admin-api'
import { getApiBase } from '~/lib/api-base'
import type {
  ScimEndpoint,
  ScimEndpointCreated,
  ScimEndpointCreateRequest,
  ScimGroupRoleMapRequest,
  ScimPreset,
} from '~/lib/admin-types'
import {
  SCIM_PRESETS,
  SCIM_ROLE_OPTIONS,
  scimBaseUrl,
  validateEndpointName,
  validateGroupDisplayName,
} from '~/lib/scim-form'

export const Route = createFileRoute('/admin/scim')({
  component: ScimPage,
})

function ScimPage() {
  const qc = useQueryClient()
  const list = useQuery({ queryKey: ['admin', 'scim'], queryFn: fetchScimEndpoints })
  const [creating, setCreating] = React.useState(false)
  const [secretShown, setSecretShown] = React.useState<ScimEndpointCreated | null>(null)
  const [mappingFor, setMappingFor] = React.useState<ScimEndpoint | null>(null)

  const createMut = useMutation({
    mutationFn: createScimEndpoint,
    onSuccess: (resp) => {
      qc.invalidateQueries({ queryKey: ['admin', 'scim'] })
      setSecretShown(resp)
      setCreating(false)
    },
  })

  const revokeMut = useMutation({
    mutationFn: revokeScimEndpoint,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'scim'] }),
  })

  return (
    <div className="panel" data-testid="admin-scim">
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>SCIM</span>
        <button className="btn btn-primary" onClick={() => setCreating(true)} data-testid="admin-scim-new">
          New endpoint
        </button>
      </div>

      <div className="panel-body" style={{ padding: 16 }}>
        {list.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
        {list.error && <p style={{ fontSize: 12, color: 'var(--red)' }}>{(list.error as Error).message}</p>}
        {list.data && list.data.length === 0 && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No SCIM endpoints yet. Mint one to provision users from your IdP.</p>
        )}
        {list.data && list.data.length > 0 && (
          <EndpointsTable
            rows={list.data}
            onRevoke={(id) => {
              if (confirm('Revoke this SCIM endpoint? Provisioning will stop immediately.')) revokeMut.mutate(id)
            }}
            onMap={(row) => setMappingFor(row)}
          />
        )}

        {creating && (
          <CreateDialog
            saving={createMut.isPending}
            error={createMut.error?.message ?? null}
            onCancel={() => setCreating(false)}
            onSubmit={(r) => createMut.mutate(r)}
          />
        )}

        {secretShown && (
          <TokenOnceDialog response={secretShown} onClose={() => setSecretShown(null)} />
        )}

        {mappingFor && (
          <GroupMappingDialog endpoint={mappingFor} onClose={() => setMappingFor(null)} />
        )}
      </div>
    </div>
  )
}

function EndpointsTable({
  rows,
  onRevoke,
  onMap,
}: {
  rows: ScimEndpoint[]
  onRevoke: (id: string) => void
  onMap: (row: ScimEndpoint) => void
}) {
  return (
    <div className="tbl" data-testid="admin-scim-table">
      <div
        className="audit-row"
        style={{
          gridTemplateColumns: '1fr 120px 130px 130px 100px 90px 90px',
          background: 'var(--bg-2)',
          borderBottom: '1px solid var(--line)',
          fontWeight: 600,
          fontSize: 10,
          color: 'var(--ink-3)',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        <span>Name</span><span>Preset</span><span>Last sync</span><span>Created</span><span>Status</span><span /><span />
      </div>
      {rows.map((r) => {
        const revoked = r.revoked_at != null
        return (
          <div key={r.id} className="audit-row" style={{ gridTemplateColumns: '1fr 120px 130px 130px 100px 90px 90px' }}>
            <span style={{ color: 'var(--ink)' }}>{r.name}</span>
            <span className="meta">{r.preset}</span>
            <span className="meta">{r.last_sync_at ? new Date(r.last_sync_at).toLocaleString() : 'never'}</span>
            <span className="meta">{new Date(r.created_at).toLocaleDateString()}</span>
            <span className="meta" style={{ color: revoked ? 'var(--red)' : 'var(--ink-2)' }}>
              {revoked ? 'revoked' : r.enabled ? 'active' : 'disabled'}
            </span>
            <button className="btn btn-sm" disabled={revoked} onClick={() => onMap(r)}>
              Groups
            </button>
            <button
              className="btn btn-sm"
              disabled={revoked}
              onClick={() => onRevoke(r.id)}
              style={{ color: revoked ? 'var(--ink-3)' : 'var(--red)' }}
            >
              Revoke
            </button>
          </div>
        )
      })}
    </div>
  )
}

function CreateDialog({
  saving,
  error,
  onSubmit,
  onCancel,
}: {
  saving: boolean
  error: string | null
  onSubmit: (req: ScimEndpointCreateRequest) => void
  onCancel: () => void
}) {
  const [name, setName] = React.useState('')
  const [preset, setPreset] = React.useState<ScimPreset>('generic')
  const [localError, setLocalError] = React.useState<string | null>(null)

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const err = validateEndpointName(name)
    if (err) {
      setLocalError(err)
      return
    }
    setLocalError(null)
    onSubmit({ name: name.trim(), preset })
  }

  return (
    <Modal title="New SCIM endpoint" onClose={onCancel} testId="admin-scim-create-dialog">
      <form onSubmit={submit}>
        <Field label="Name">
          <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Production" style={inputStyle} />
        </Field>
        <Field label="Preset">
          <select value={preset} onChange={(e) => setPreset(e.target.value as ScimPreset)} style={inputStyle}>
            {SCIM_PRESETS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label} — {p.blurb}
              </option>
            ))}
          </select>
        </Field>
        {(error || localError) && <p style={{ fontSize: 11, color: 'var(--red)', marginBottom: 8 }}>{error || localError}</p>}
        <DialogActions saving={saving} onCancel={onCancel} submitLabel="Create" />
      </form>
    </Modal>
  )
}

function TokenOnceDialog({
  response,
  onClose,
}: {
  response: ScimEndpointCreated
  onClose: () => void
}) {
  const [copiedTok, setCopiedTok] = React.useState(false)
  const [copiedUrl, setCopiedUrl] = React.useState(false)
  const url = scimBaseUrl(getApiBase(), response.id)

  async function copy(value: string, kind: 'tok' | 'url') {
    await navigator.clipboard.writeText(value)
    if (kind === 'tok') {
      setCopiedTok(true)
      setTimeout(() => setCopiedTok(false), 1500)
    } else {
      setCopiedUrl(true)
      setTimeout(() => setCopiedUrl(false), 1500)
    }
  }

  return (
    <Modal title="Endpoint created — copy now" onClose={onClose} testId="admin-scim-token-dialog">
      <p style={{ fontSize: 12, color: 'var(--ink-2)', marginBottom: 10 }}>
        The bearer token will <strong>not be shown again</strong>. Configure it in your IdP now.
      </p>

      <Field label="Tenant URL">
        <div style={{ display: 'flex', gap: 8 }}>
          <code data-testid="admin-scim-tenant-url" style={codeStyle}>{url}</code>
          <button type="button" className="btn btn-sm" onClick={() => copy(url, 'url')}>
            {copiedUrl ? 'Copied' : 'Copy'}
          </button>
        </div>
      </Field>

      <Field label="Bearer token">
        <div style={{ display: 'flex', gap: 8 }}>
          <code data-testid="admin-scim-token-value" style={codeStyle}>{response.token}</code>
          <button type="button" className="btn btn-sm" onClick={() => copy(response.token, 'tok')}>
            {copiedTok ? 'Copied' : 'Copy'}
          </button>
        </div>
      </Field>

      <button type="button" className="btn btn-primary" onClick={onClose} style={{ marginTop: 8 }}>
        I have saved it
      </button>
    </Modal>
  )
}

function GroupMappingDialog({
  endpoint,
  onClose,
}: {
  endpoint: ScimEndpoint
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [displayName, setDisplayName] = React.useState('')
  const [roleName, setRoleName] = React.useState<typeof SCIM_ROLE_OPTIONS[number]>('member')
  const [localError, setLocalError] = React.useState<string | null>(null)

  const upsert = useMutation({
    mutationFn: (req: ScimGroupRoleMapRequest) => upsertScimGroupRole(endpoint.id, req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'scim'] })
      setDisplayName('')
      setLocalError(null)
    },
  })

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const err = validateGroupDisplayName(displayName)
    if (err) {
      setLocalError(err)
      return
    }
    setLocalError(null)
    upsert.mutate({ display_name: displayName.trim(), role_name: roleName })
  }

  return (
    <Modal title={`Group → role mapping for ${endpoint.name}`} onClose={onClose} testId="admin-scim-mapping-dialog">
      <p style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 12 }}>
        Map a SCIM group display name to a system role. Users provisioned into the group inherit the role.
      </p>
      <form onSubmit={submit}>
        <Field label="Group display name">
          <input
            required
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="ai-portal-admins"
            style={inputStyle}
            data-testid="admin-scim-group-name"
          />
        </Field>
        <Field label="Role">
          <select
            value={roleName}
            onChange={(e) => setRoleName(e.target.value as typeof SCIM_ROLE_OPTIONS[number])}
            style={inputStyle}
            data-testid="admin-scim-group-role"
          >
            {SCIM_ROLE_OPTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </Field>
        {(upsert.error || localError) && (
          <p style={{ fontSize: 11, color: 'var(--red)', marginBottom: 8 }}>
            {upsert.error ? (upsert.error as Error).message : localError}
          </p>
        )}
        <DialogActions saving={upsert.isPending} onCancel={onClose} submitLabel="Save mapping" />
      </form>
    </Modal>
  )
}

const inputStyle: React.CSSProperties = {
  borderRadius: 4,
  border: '1px solid var(--line)',
  background: 'var(--bg)',
  color: 'var(--ink)',
  padding: '4px 8px',
  fontSize: 12,
}

const codeStyle: React.CSSProperties = {
  flex: 1,
  padding: 8,
  borderRadius: 4,
  border: '1px solid var(--line)',
  background: 'var(--bg-2)',
  color: 'var(--ink)',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  wordBreak: 'break-all',
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, marginBottom: 10 }}>
      {label}
      {children}
    </label>
  )
}

function DialogActions({
  saving,
  onCancel,
  submitLabel = 'Save',
}: {
  saving: boolean
  onCancel: () => void
  submitLabel?: string
}) {
  return (
    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
      <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : submitLabel}</button>
      <button type="button" className="btn btn-sm" onClick={onCancel}>Cancel</button>
    </div>
  )
}

function Modal({
  title,
  children,
  onClose,
  testId,
}: {
  title: string
  children: React.ReactNode
  onClose: () => void
  testId?: string
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      data-testid={testId}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 8, padding: 20, width: '90%', maxWidth: 560, maxHeight: '85vh', overflowY: 'auto' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600 }}>{title}</h3>
          <button type="button" onClick={onClose} className="btn btn-sm" aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}
