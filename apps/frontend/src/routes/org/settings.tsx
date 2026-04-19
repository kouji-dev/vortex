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

type Tab = 'members' | 'usage' | 'audit' | 'policies' | 'retention'
const TABS: { id: Tab; label: string }[] = [
  { id: 'members', label: 'Members' },
  { id: 'usage', label: 'Usage' },
  { id: 'audit', label: 'Audit Log' },
  { id: 'policies', label: 'Policies' },
  { id: 'retention', label: 'Retention' },
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
    <div className="page-enter mx-auto max-w-4xl px-4 py-10">
      <h1 className="mb-6 text-2xl font-bold text-gray-900 dark:text-white">
        Organization settings
        {orgName && <span className="ml-2 text-gray-400 font-normal">— {orgName}</span>}
      </h1>

      {/* Tab bar */}
      <div className="mb-8 flex gap-1 border-b border-gray-100 dark:border-gray-800">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.id
                ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'members' && <MembersTab />}
      {tab === 'usage' && <UsagePanel />}
      {tab === 'audit' && <AuditLogPanel />}
      {tab === 'policies' && <RbacPolicyPanel />}
      {tab === 'retention' && <RetentionPanel />}
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
      .then(setMembers)
      .catch(() => null)
    authorizedFetch(`${API_BASE}/api/orgs/me/invites`)
      .then((r) => r.json())
      .then(setInvites)
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
    <div>
      <section className="mb-10">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Members</h2>
        <div className="divide-y divide-gray-100 rounded-xl border border-gray-100 dark:divide-gray-800 dark:border-gray-800">
          {members.map((m) => (
            <div key={m.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <p className="text-sm font-medium text-gray-900 dark:text-white">{m.email}</p>
              </div>
              <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium capitalize text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                {m.role}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-10">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Invite member</h2>
        <form onSubmit={sendInvite} className="flex gap-3">
          <input
            type="email"
            required
            placeholder="colleague@example.com"
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-white"
          />
          <select
            value={inviteRole}
            onChange={(e) => setInviteRole(e.target.value as 'member' | 'admin')}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white"
          >
            <option value="member">Member</option>
            <option value="admin">Admin</option>
          </select>
          <button
            type="submit"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
          >
            Invite
          </button>
        </form>
        {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
      </section>

      {invites.length > 0 && (
        <section>
          <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Pending invites</h2>
          <div className="divide-y divide-gray-100 rounded-xl border border-gray-100 dark:divide-gray-800 dark:border-gray-800">
            {invites.map((inv) => (
              <div key={inv.id} className="flex items-center justify-between px-4 py-3">
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{inv.invited_email}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">{inv.role}</p>
                </div>
                <button
                  onClick={() => revokeInvite(inv.id)}
                  className="text-xs text-red-500 hover:text-red-700 dark:hover:text-red-400"
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
