import { createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import { createApiKey, fetchApiKeys, revokeApiKey } from '~/lib/admin-api'
import type { ApiKeySummary, CreateApiKeyRequest, CreateApiKeyResponse, RateLimits } from '~/lib/admin-types'
import { SCOPE_CATALOG, labelForScope, validateScopes } from '~/lib/api-key-scopes'

export const Route = createFileRoute('/admin/api-keys')({
  component: ApiKeysPage,
})

function ApiKeysPage() {
  const qc = useQueryClient()
  const list = useQuery({ queryKey: ['admin', 'api-keys'], queryFn: fetchApiKeys })
  const [creating, setCreating] = React.useState(false)
  const [justCreated, setJustCreated] = React.useState<CreateApiKeyResponse | null>(null)

  const createMut = useMutation({
    mutationFn: createApiKey,
    onSuccess: (resp) => {
      qc.invalidateQueries({ queryKey: ['admin', 'api-keys'] })
      setJustCreated(resp)
      setCreating(false)
    },
  })

  const revokeMut = useMutation({
    mutationFn: revokeApiKey,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'api-keys'] }),
  })

  return (
    <div className="panel" data-testid="admin-api-keys">
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>API Keys</span>
        <button className="btn btn-primary" onClick={() => setCreating(true)} data-testid="admin-api-keys-new">
          New key
        </button>
      </div>

      <div className="panel-body" style={{ padding: 16 }}>
        {list.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
        {list.error && <p style={{ fontSize: 12, color: 'var(--red)' }}>{(list.error as Error).message}</p>}

        {list.data && list.data.length === 0 && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No keys yet. Create one to start.</p>
        )}

        {list.data && list.data.length > 0 && (
          <KeysTable keys={list.data} onRevoke={(id) => { if (confirm('Revoke this key? Calls using it will fail immediately.')) revokeMut.mutate(id) }} />
        )}

        {creating && (
          <CreateKeyDialog
            saving={createMut.isPending}
            error={createMut.error?.message ?? null}
            onCancel={() => setCreating(false)}
            onSubmit={(req) => createMut.mutate(req)}
          />
        )}

        {justCreated && (
          <SecretOnceDialog
            response={justCreated}
            onClose={() => setJustCreated(null)}
          />
        )}
      </div>
    </div>
  )
}

function KeysTable({ keys, onRevoke }: { keys: ApiKeySummary[]; onRevoke: (id: string) => void }) {
  return (
    <div className="tbl" data-testid="admin-api-keys-table">
      <div className="audit-row" style={{ gridTemplateColumns: '1fr 130px 1fr 110px 110px 80px', background: 'var(--bg-2)', borderBottom: '1px solid var(--line)', fontWeight: 600, fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        <span>Name</span><span>Prefix</span><span>Scopes</span><span>Last used</span><span>Status</span><span />
      </div>
      {keys.map((k) => {
        const revoked = k.revoked_at != null
        return (
          <div key={k.id} className="audit-row" style={{ gridTemplateColumns: '1fr 130px 1fr 110px 110px 80px' }}>
            <span style={{ color: 'var(--ink)' }}>{k.name}</span>
            <span className="meta" style={{ fontFamily: 'var(--font-mono)' }}>{k.prefix}…</span>
            <span className="meta" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {k.scopes.slice(0, 3).join(', ')}{k.scopes.length > 3 ? ` +${k.scopes.length - 3}` : ''}
            </span>
            <span className="meta">{k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : 'never'}</span>
            <span className="meta" style={{ color: revoked ? 'var(--red)' : 'var(--ink-2)' }}>
              {revoked ? 'revoked' : 'active'}
            </span>
            <button
              className="btn btn-sm"
              disabled={revoked}
              onClick={() => onRevoke(k.id)}
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

function CreateKeyDialog({
  saving,
  error,
  onSubmit,
  onCancel,
}: {
  saving: boolean
  error: string | null
  onSubmit: (req: CreateApiKeyRequest) => void
  onCancel: () => void
}) {
  const [name, setName] = React.useState('')
  const [scopes, setScopes] = React.useState<string[]>([])
  const [expiresAt, setExpiresAt] = React.useState('')
  const [rpm, setRpm] = React.useState('')
  const [tpm, setTpm] = React.useState('')
  const [concurrency, setConcurrency] = React.useState('')
  const [localError, setLocalError] = React.useState<string | null>(null)

  function toggle(scope: string) {
    setScopes((prev) => prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope])
  }

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const err = validateScopes(scopes)
    if (err) {
      setLocalError(err)
      return
    }
    setLocalError(null)
    const rate: RateLimits = {}
    if (rpm) rate.rpm = Number(rpm)
    if (tpm) rate.tpm = Number(tpm)
    if (concurrency) rate.concurrency = Number(concurrency)
    onSubmit({
      name,
      scopes,
      rate_limits: Object.keys(rate).length ? rate : null,
      expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
    })
  }

  return (
    <Modal title="New API key" onClose={onCancel} testId="admin-api-keys-create-dialog">
      <form onSubmit={submit}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, marginBottom: 12 }}>
          Name
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="ci-bot"
            style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, marginBottom: 12 }}>
          Expires (optional, max 1 year)
          <input
            type="date"
            value={expiresAt}
            onChange={(e) => setExpiresAt(e.target.value)}
            style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
          />
        </label>

        <fieldset style={{ border: '1px solid var(--line)', borderRadius: 4, padding: 8, marginBottom: 12 }} data-testid="admin-api-keys-rate-limits">
          <legend style={{ padding: '0 6px', fontSize: 11, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Rate limits (optional)
          </legend>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11 }}>
              RPM
              <input
                type="number"
                min="0"
                value={rpm}
                onChange={(e) => setRpm(e.target.value)}
                placeholder="60"
                data-testid="admin-api-keys-rate-rpm"
                style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11 }}>
              TPM
              <input
                type="number"
                min="0"
                value={tpm}
                onChange={(e) => setTpm(e.target.value)}
                placeholder="100000"
                data-testid="admin-api-keys-rate-tpm"
                style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11 }}>
              Concurrency
              <input
                type="number"
                min="0"
                value={concurrency}
                onChange={(e) => setConcurrency(e.target.value)}
                placeholder="4"
                data-testid="admin-api-keys-rate-concurrency"
                style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
              />
            </label>
          </div>
        </fieldset>

        <fieldset style={{ border: '1px solid var(--line)', borderRadius: 4, padding: 8, marginBottom: 12 }}>
          <legend style={{ padding: '0 6px', fontSize: 11, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Scopes
          </legend>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
            {SCOPE_CATALOG.map((g) => (
              <div key={g.module}>
                <div style={{ fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                  {g.module}
                </div>
                {g.scopes.map((s) => (
                  <label key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, padding: '2px 0', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={scopes.includes(s.key)}
                      onChange={() => toggle(s.key)}
                      data-testid={`admin-api-keys-scope-${s.key}`}
                    />
                    <span>{s.label}</span>
                    <code style={{ fontSize: 10, color: 'var(--ink-3)' }}>{s.key}</code>
                  </label>
                ))}
              </div>
            ))}
          </div>
        </fieldset>

        {(error || localError) && (
          <p style={{ fontSize: 11, color: 'var(--red)', marginBottom: 8 }}>{error || localError}</p>
        )}

        <div style={{ display: 'flex', gap: 8 }}>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Creating…' : 'Create'}
          </button>
          <button type="button" className="btn btn-sm" onClick={onCancel}>Cancel</button>
        </div>
      </form>
    </Modal>
  )
}

function SecretOnceDialog({
  response,
  onClose,
}: {
  response: CreateApiKeyResponse
  onClose: () => void
}) {
  const [copied, setCopied] = React.useState(false)

  async function copy() {
    await navigator.clipboard.writeText(response.plaintext)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <Modal title="Key created — copy it now" onClose={onClose} testId="admin-api-keys-secret-dialog">
      <p style={{ fontSize: 12, color: 'var(--ink-2)', marginBottom: 10 }}>
        This secret will <strong>not be shown again</strong>. Copy it now and store it securely.
      </p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <code
          data-testid="admin-api-keys-secret-value"
          style={{
            flex: 1,
            padding: 8,
            borderRadius: 4,
            border: '1px solid var(--line)',
            background: 'var(--bg-2)',
            color: 'var(--ink)',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            wordBreak: 'break-all',
          }}
        >
          {response.plaintext}
        </code>
        <button type="button" className="btn btn-sm" onClick={copy}>
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>

      <p style={{ fontSize: 11, color: 'var(--ink-3)', marginBottom: 12 }}>
        Scopes: {response.key.scopes.map(labelForScope).join(', ')}
      </p>

      <button type="button" className="btn btn-primary" onClick={onClose}>
        I&apos;ve saved it
      </button>
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
          maxWidth: 560,
          maxHeight: '85vh',
          overflowY: 'auto',
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
