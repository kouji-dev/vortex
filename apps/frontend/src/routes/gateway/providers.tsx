import { createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import {
  createProviderCredential,
  deleteProviderCredential,
  fetchProviderCredentials,
  probeProviderHealth,
} from '~/lib/gateway-api'
import {
  PROVIDER_CATALOG,
  healthBadge,
  providerLabel,
  validateCredentialLabel,
  validateCredentialSecret,
} from '~/lib/gateway-providers'
import type { ProviderCredential, ProviderKind } from '~/lib/gateway-types'

export const Route = createFileRoute('/gateway/providers')({
  component: ProvidersPage,
})

function ProvidersPage() {
  const qc = useQueryClient()
  const list = useQuery({ queryKey: ['gateway', 'providers'], queryFn: fetchProviderCredentials })
  const [adding, setAdding] = React.useState(false)

  const createMut = useMutation({
    mutationFn: createProviderCredential,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['gateway', 'providers'] })
      setAdding(false)
    },
  })

  const delMut = useMutation({
    mutationFn: deleteProviderCredential,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gateway', 'providers'] }),
  })

  const healthMut = useMutation({
    mutationFn: probeProviderHealth,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gateway', 'providers'] }),
  })

  return (
    <div className="panel" data-testid="gw-providers">
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>Providers</span>
        <button className="btn btn-primary" onClick={() => setAdding(true)} data-testid="gw-providers-new">
          Add credential
        </button>
      </div>
      <div className="panel-body" style={{ padding: 16 }}>
        {list.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
        {list.error && (
          <p style={{ fontSize: 12, color: 'var(--red)' }}>{(list.error as Error).message}</p>
        )}
        {list.data && (
          <ProvidersTable
            creds={list.data}
            onDelete={(id) => {
              if (confirm('Delete this credential? Calls using it will fail until replaced.')) {
                delMut.mutate(id)
              }
            }}
            onProbe={(id) => healthMut.mutate(id)}
            busyProbeId={healthMut.isPending ? healthMut.variables : null}
          />
        )}
        {adding && (
          <AddCredentialDialog
            onCancel={() => setAdding(false)}
            saving={createMut.isPending}
            error={createMut.error?.message ?? null}
            onSubmit={(req) => createMut.mutate(req)}
          />
        )}
      </div>
    </div>
  )
}

function ProvidersTable({
  creds,
  onDelete,
  onProbe,
  busyProbeId,
}: {
  creds: ProviderCredential[]
  onDelete: (id: string) => void
  onProbe: (id: string) => void
  busyProbeId: string | undefined | null
}) {
  if (creds.length === 0) {
    return (
      <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>
        No provider credentials yet. Add one to start routing requests.
      </p>
    )
  }
  return (
    <div className="tbl" data-testid="gw-providers-table">
      <div className="audit-row" style={headerRow}>
        <span>Provider</span>
        <span>Label</span>
        <span>Health</span>
        <span>Last probe</span>
        <span />
      </div>
      {creds.map((c) => {
        const badge = healthBadge(c)
        return (
          <div key={c.id} className="audit-row" style={dataRow}>
            <span style={{ color: 'var(--ink)' }}>{providerLabel(c.provider)}</span>
            <span className="meta" style={{ fontFamily: 'var(--font-mono)' }}>{c.label}</span>
            <span>
              <span
                className={`gw-badge ${badge === 'healthy' ? 'ok' : badge === 'unhealthy' ? 'bad' : 'warn'}`}
                data-testid={`gw-providers-health-${c.id}`}
              >
                {badge}
              </span>
            </span>
            <span className="meta">
              {c.last_health_at ? new Date(c.last_health_at).toLocaleString() : 'never'}
            </span>
            <span style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
              <button
                className="btn btn-sm"
                onClick={() => onProbe(c.id)}
                disabled={busyProbeId === c.id}
              >
                {busyProbeId === c.id ? 'Probing…' : 'Probe'}
              </button>
              <button
                className="btn btn-sm"
                onClick={() => onDelete(c.id)}
                style={{ color: 'var(--red)' }}
              >
                Delete
              </button>
            </span>
          </div>
        )
      })}
    </div>
  )
}

function AddCredentialDialog({
  onCancel,
  saving,
  error,
  onSubmit,
}: {
  onCancel: () => void
  saving: boolean
  error: string | null
  onSubmit: (req: { provider: ProviderKind | string; label?: string; secret: string }) => void
}) {
  const [provider, setProvider] = React.useState<ProviderKind | string>('anthropic')
  const [label, setLabel] = React.useState('')
  const [secret, setSecret] = React.useState('')
  const [localError, setLocalError] = React.useState<string | null>(null)

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const labelErr = validateCredentialLabel(label)
    const secretErr = validateCredentialSecret(secret)
    if (labelErr) {
      setLocalError(labelErr)
      return
    }
    if (secretErr) {
      setLocalError(secretErr)
      return
    }
    setLocalError(null)
    onSubmit({ provider, label: label || undefined, secret })
  }

  return (
    <Modal title="Add provider credential" onClose={onCancel} testId="gw-providers-add-dialog">
      <form onSubmit={submit}>
        <label style={fieldRow}>
          Provider
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="gw-input"
            data-testid="gw-providers-provider"
          >
            {PROVIDER_CATALOG.map((p) => (
              <option key={p.kind} value={p.kind}>{p.label}</option>
            ))}
          </select>
        </label>
        <label style={fieldRow}>
          Label (optional)
          <input
            className="gw-input"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="default"
            data-testid="gw-providers-label"
          />
        </label>
        <label style={fieldRow}>
          API secret
          <input
            type="password"
            className="gw-input"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="sk-…"
            data-testid="gw-providers-secret"
            required
          />
        </label>
        {(error || localError) && (
          <p style={{ fontSize: 11, color: 'var(--red)', marginBottom: 8 }}>{error ?? localError}</p>
        )}
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="btn btn-sm" onClick={onCancel}>Cancel</button>
        </div>
      </form>
    </Modal>
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
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--bg)',
          border: '1px solid var(--line)',
          borderRadius: 8,
          padding: 20,
          width: '90%',
          maxWidth: 460,
        }}
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

const headerRow: React.CSSProperties = {
  gridTemplateColumns: '180px 160px 110px 1fr 160px',
  background: 'var(--bg-2)',
  borderBottom: '1px solid var(--line)',
  fontWeight: 600,
  fontSize: 10,
  color: 'var(--ink-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
}
const dataRow: React.CSSProperties = { gridTemplateColumns: '180px 160px 110px 1fr 160px' }
const fieldRow: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
  fontSize: 11,
  marginBottom: 12,
}
