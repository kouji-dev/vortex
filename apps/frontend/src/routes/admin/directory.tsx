import { Select } from '~/components/ui/select'
import { createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import {
  createLdapConnection,
  deleteLdapConnection,
  fetchLdapConnections,
  testLdapConnection,
} from '~/lib/admin-api'
import type { CreateLdapConnectionRequest, LdapConnection, LdapKind, LdapTlsMode } from '~/lib/admin-types'

export const Route = createFileRoute('/admin/directory')({
  component: DirectoryPage,
})

const KINDS: { value: LdapKind; label: string }[] = [
  { value: 'ldap', label: 'Generic LDAP' },
  { value: 'active_directory', label: 'Active Directory' },
]

const TLS: { value: LdapTlsMode; label: string }[] = [
  { value: 'none', label: 'None (plain)' },
  { value: 'starttls', label: 'StartTLS' },
  { value: 'ldaps', label: 'LDAPS' },
]

function DirectoryPage() {
  const qc = useQueryClient()
  const list = useQuery({ queryKey: ['admin', 'ldap'], queryFn: fetchLdapConnections })
  const [creating, setCreating] = React.useState(false)
  const [testResult, setTestResult] = React.useState<Record<string, string>>({})

  const invalidate = () => qc.invalidateQueries({ queryKey: ['admin', 'ldap'] })

  const createMut = useMutation({
    mutationFn: createLdapConnection,
    onSuccess: () => { invalidate(); setCreating(false) },
  })
  const deleteMut = useMutation({ mutationFn: deleteLdapConnection, onSuccess: invalidate })
  const testMut = useMutation({
    mutationFn: testLdapConnection,
    onSuccess: (res, id) =>
      setTestResult((p) => ({ ...p, [id]: res.ok ? 'ok' : `failed: ${res.message ?? 'unknown'}` })),
  })

  return (
    <div className="panel" data-testid="admin-directory">
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Directory / LDAP</span>
        <button className="btn btn-primary" onClick={() => setCreating(true)} data-testid="admin-directory-new">
          New connection
        </button>
      </div>

      <div className="panel-body" style={{ padding: 16 }}>
        {list.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
        {list.error && <p style={{ fontSize: 12, color: 'var(--red)' }}>{(list.error as Error).message}</p>}

        {list.data && list.data.length === 0 && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>
            No directory connections. Add one to enable LDAP / Active Directory bind login.
          </p>
        )}

        {list.data && list.data.length > 0 && (
          <ConnectionsTable
            connections={list.data}
            testResult={testResult}
            testing={testMut.isPending ? (testMut.variables as string) : null}
            onTest={(id) => testMut.mutate(id)}
            onDelete={(id) => { if (confirm('Delete this connection?')) deleteMut.mutate(id) }}
          />
        )}

        {creating && (
          <CreateConnectionDialog
            saving={createMut.isPending}
            error={createMut.error?.message ?? null}
            onCancel={() => setCreating(false)}
            onSubmit={(req) => createMut.mutate(req)}
          />
        )}
      </div>
    </div>
  )
}

function ConnectionsTable({
  connections,
  testResult,
  testing,
  onTest,
  onDelete,
}: {
  connections: LdapConnection[]
  testResult: Record<string, string>
  testing: string | null
  onTest: (id: string) => void
  onDelete: (id: string) => void
}) {
  return (
    <div className="tbl" data-testid="admin-directory-table">
      <div className="audit-row" style={{ gridTemplateColumns: '1fr 130px 1fr 90px 140px', background: 'var(--bg-2)', borderBottom: '1px solid var(--line)', fontWeight: 600, fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        <span>Name</span><span>Kind</span><span>Host</span><span>TLS</span><span />
      </div>
      {connections.map((c) => (
        <div key={c.id} className="audit-row" style={{ gridTemplateColumns: '1fr 130px 1fr 90px 140px' }} data-testid={`admin-directory-row-${c.id}`}>
          <span style={{ color: 'var(--ink)' }}>{c.name}</span>
          <span className="meta">{c.kind}</span>
          <span className="meta" style={{ fontFamily: 'var(--font-mono)' }}>{c.host}:{c.port}</span>
          <span className="meta">{c.tls_mode}</span>
          <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <button
              className="btn btn-sm"
              onClick={() => onTest(c.id)}
              disabled={testing === c.id}
              data-testid={`admin-directory-test-${c.id}`}
            >
              {testing === c.id ? 'Testing…' : 'Test'}
            </button>
            <button className="btn btn-sm" style={{ color: 'var(--red)' }} onClick={() => onDelete(c.id)}>
              Delete
            </button>
            {testResult[c.id] && (
              <span
                data-testid={`admin-directory-test-result-${c.id}`}
                style={{ fontSize: 10, color: testResult[c.id] === 'ok' ? 'var(--green, #16a34a)' : 'var(--red)' }}
              >
                {testResult[c.id] === 'ok' ? '✓' : '✕'}
              </span>
            )}
          </span>
        </div>
      ))}
    </div>
  )
}

function CreateConnectionDialog({
  saving,
  error,
  onSubmit,
  onCancel,
}: {
  saving: boolean
  error: string | null
  onSubmit: (req: CreateLdapConnectionRequest) => void
  onCancel: () => void
}) {
  const [form, setForm] = React.useState<CreateLdapConnectionRequest>({
    name: '',
    kind: 'ldap',
    host: '',
    bind_dn: '',
    bind_secret: '',
    base_dn: '',
    tls_mode: 'none',
  })

  function set<K extends keyof CreateLdapConnectionRequest>(k: K, v: CreateLdapConnectionRequest[K]) {
    setForm((p) => ({ ...p, [k]: v }))
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      data-testid="admin-directory-create-dialog"
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 8, padding: 20, width: '90%', maxWidth: 560, maxHeight: '85vh', overflowY: 'auto' }}
      >
        <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>New directory connection</h3>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            onSubmit(form)
          }}
        >
          <Field label="Name">
            <input required value={form.name} onChange={(e) => set('name', e.target.value)} data-testid="admin-directory-name" style={inputStyle} />
          </Field>
          <Field label="Kind">
            <Select value={form.kind} onChange={(e) => set('kind', e.target.value as LdapKind)} size="sm" inline>
              {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
            </Select>
          </Field>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 8 }}>
            <Field label="Host">
              <input required value={form.host} onChange={(e) => set('host', e.target.value)} placeholder="ldap.acme.com" data-testid="admin-directory-host" style={inputStyle} />
            </Field>
            <Field label="Port (optional)">
              <input type="number" value={form.port ?? ''} onChange={(e) => set('port', e.target.value ? Number(e.target.value) : null)} style={inputStyle} />
            </Field>
          </div>
          <Field label="TLS">
            <Select value={form.tls_mode} onChange={(e) => set('tls_mode', e.target.value as LdapTlsMode)} size="sm" inline>
              {TLS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </Select>
          </Field>
          <Field label="Bind DN (service account)">
            <input required value={form.bind_dn} onChange={(e) => set('bind_dn', e.target.value)} placeholder="cn=svc,dc=acme,dc=com" style={inputStyle} />
          </Field>
          <Field label="Bind secret">
            <input required type="password" value={form.bind_secret} onChange={(e) => set('bind_secret', e.target.value)} data-testid="admin-directory-bind-secret" style={inputStyle} />
          </Field>
          <Field label="Base DN">
            <input required value={form.base_dn} onChange={(e) => set('base_dn', e.target.value)} placeholder="dc=acme,dc=com" style={inputStyle} />
          </Field>
          <Field label="User filter (optional)">
            <input value={form.user_filter ?? ''} onChange={(e) => set('user_filter', e.target.value)} placeholder="(uid={username})" style={inputStyle} />
          </Field>

          {error && <p style={{ fontSize: 11, color: 'var(--red)', marginBottom: 8 }}>{error}</p>}

          <div style={{ display: 'flex', gap: 8 }}>
            <button type="submit" className="btn btn-primary" disabled={saving} data-testid="admin-directory-create-submit">
              {saving ? 'Saving…' : 'Create'}
            </button>
            <button type="button" className="btn btn-sm" onClick={onCancel}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  borderRadius: 4,
  border: '1px solid var(--line)',
  background: 'var(--bg)',
  color: 'var(--ink)',
  padding: '4px 8px',
  fontSize: 12,
  width: '100%',
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, marginBottom: 12 }}>
      {label}
      {children}
    </label>
  )
}
