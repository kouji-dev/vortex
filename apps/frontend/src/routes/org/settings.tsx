import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'
import { authorizedFetch } from '~/lib/authorizedFetch'
import { UsagePanel } from '~/components/admin/UsagePanel'
import { AuditLogPanel } from '~/components/admin/AuditLogPanel'
import { RbacPolicyPanel } from '~/components/admin/RbacPolicyPanel'
import { RetentionPanel } from '~/components/admin/RetentionPanel'

export const Route = createFileRoute('/org/settings')({
  component: OrgSettingsPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

type Tab = 'rbac' | 'audit' | 'retention' | 'usage' | 'members'
const TABS: { id: Tab; label: string }[] = [
  { id: 'members', label: 'Members' },
  { id: 'rbac', label: 'Policies' },
  { id: 'audit', label: 'Audit Log' },
  { id: 'retention', label: 'Retention' },
  { id: 'usage', label: 'Usage' },
]

interface Member { id: number; email: string; role: string; is_verified: boolean }
interface Invite { id: number; invited_email: string; role: string; expires_at: string }

function OrgSettingsPage() {
  const [tab, setTab] = React.useState<Tab>('members')
  const [orgName, setOrgName] = React.useState('')

  React.useEffect(() => {
    authorizedFetch(`${API_BASE}/api/orgs/me`)
      .then((r) => r.json())
      .then((d) => setOrgName(d.name ?? ''))
      .catch(() => null)
  }, [])

  return (
    <div className="main-inner" data-testid="org-settings">
      <div className="screen-head">
        <div>
          <h1>
            Organization settings
            {orgName && <span style={{ marginLeft: 8, color: 'var(--ink-3)', fontWeight: 400 }}>— {orgName}</span>}
          </h1>
          <div className="sub">Members · policies · audit · retention · usage</div>
        </div>
      </div>

      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`tab${tab === t.id ? ' active' : ''}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="gov-grid" style={{ gridTemplateColumns: '1fr' }}>
        <div className="panel">
          {tab === 'members' && <MembersTab />}
          {tab === 'rbac' && <RbacPolicyPanel />}
          {tab === 'audit' && <AuditLogPanel />}
          {tab === 'retention' && <RetentionPanel />}
          {tab === 'usage' && <UsagePanel />}
        </div>
      </div>
    </div>
  )
}

function MembersTab() {
  const [members, setMembers] = React.useState<Member[]>([])
  const [invites, setInvites] = React.useState<Invite[]>([])
  const [inviteEmail, setInviteEmail] = React.useState('')
  const [inviteRole, setInviteRole] = React.useState<'member' | 'admin'>('member')
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    authorizedFetch(`${API_BASE}/api/orgs/me/members`)
      .then((r) => r.json())
      .then((d) => { if (Array.isArray(d)) setMembers(d) })
      .catch(() => null)
    authorizedFetch(`${API_BASE}/api/orgs/me/invites`)
      .then((r) => r.json())
      .then((d) => { if (Array.isArray(d)) setInvites(d) })
      .catch(() => null)
  }, [])

  async function sendInvite(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      const res = await authorizedFetch(`${API_BASE}/api/orgs/me/invites`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: inviteEmail, role: inviteRole }),
      })
      if (!res.ok) throw new Error((await res.json()).detail ?? 'Failed')
      const invite = await res.json()
      setInvites((prev) => [...prev, invite])
      setInviteEmail('')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to send invite')
    }
  }

  async function revokeInvite(id: number) {
    await authorizedFetch(`${API_BASE}/api/orgs/me/invites/${id}`, { method: 'DELETE' })
    setInvites((prev) => prev.filter((i) => i.id !== id))
  }

  return (
    <div className="panel-body" style={{ padding: 20 }}>
      <section style={{ marginBottom: 28 }}>
        <div className="panel-head">Members</div>
        <div className="divide-y divide-gray-100 rounded-xl border border-gray-100 dark:divide-gray-800 dark:border-gray-800">
          {members.map((m) => (
            <div key={m.id} className="policy-row">
              <div className="title">{m.email}</div>
              <span />
              <span className="meta">{m.is_verified ? 'verified' : 'unverified'}</span>
              <span className="meta" style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{m.role}</span>
            </div>
          ))}
        </div>
      </section>

      <section style={{ marginBottom: 28 }}>
        <div className="panel-head">Invite member</div>
        <form onSubmit={sendInvite} style={{ display: 'flex', gap: 8, padding: '12px 0' }}>
          <input
            type="email"
            required
            placeholder="colleague@example.com"
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            style={{ flex: 1, borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
          />
          <select
            value={inviteRole}
            onChange={(e) => setInviteRole(e.target.value as 'member' | 'admin')}
            style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
          >
            <option value="member">Member</option>
            <option value="admin">Admin</option>
          </select>
          <button type="submit" className="btn btn-primary">Invite</button>
        </form>
        {error && <p style={{ marginTop: 6, fontSize: 12, color: 'var(--red)' }}>{error}</p>}
      </section>

      {invites.length > 0 && (
        <section>
          <div className="panel-head">Pending invites</div>
          <div>
            {invites.map((inv) => (
              <div key={inv.id} className="policy-row">
                <div>
                  <div className="title">{inv.invited_email}</div>
                  <div className="meta">{inv.role}</div>
                </div>
                <span />
                <span />
                <button
                  onClick={() => revokeInvite(inv.id)}
                  className="btn btn-sm"
                  style={{ color: 'var(--red)' }}
                >
                  Revoke
                </button>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
