import { createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import {
  fetchInvitations,
  fetchMembers,
  inviteMember,
  removeMember,
  revokeInvitation,
  updateMemberRole,
} from '~/lib/admin-api'
import type { MemberRole, OrgInvitation, OrgMember } from '~/lib/admin-types'

export const Route = createFileRoute('/admin/members')({
  component: MembersPage,
})

const ROLES: MemberRole[] = ['owner', 'admin', 'member', 'viewer']

function MembersPage() {
  const qc = useQueryClient()
  const members = useQuery({ queryKey: ['admin', 'members'], queryFn: fetchMembers })
  const invites = useQuery({ queryKey: ['admin', 'invitations'], queryFn: fetchInvitations })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['admin', 'members'] })
    qc.invalidateQueries({ queryKey: ['admin', 'invitations'] })
  }

  const inviteMut = useMutation({ mutationFn: inviteMember, onSuccess: invalidate })
  const updateMut = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: MemberRole }) =>
      updateMemberRole(userId, { role }),
    onSuccess: invalidate,
  })
  const removeMut = useMutation({ mutationFn: removeMember, onSuccess: invalidate })
  const revokeMut = useMutation({ mutationFn: revokeInvitation, onSuccess: invalidate })

  return (
    <div className="panel" data-testid="admin-members">
      <div className="panel-head">Members</div>
      <div className="panel-body" style={{ padding: 16 }}>
        <InviteForm
          loading={inviteMut.isPending}
          error={inviteMut.error?.message ?? null}
          onSubmit={(req) => inviteMut.mutate(req)}
        />

        <section style={{ marginTop: 20 }}>
          <h3 style={{ fontSize: 12, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
            Active ({members.data?.length ?? 0})
          </h3>
          {members.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
          {members.error && <ErrorLine msg={(members.error as Error).message} />}
          {members.data && (
            <MembersTable
              members={members.data}
              onChangeRole={(userId, role) => updateMut.mutate({ userId, role })}
              onRemove={(userId) => {
                if (confirm('Remove this member? Their sessions and keys are revoked.')) {
                  removeMut.mutate(userId)
                }
              }}
            />
          )}
        </section>

        <section style={{ marginTop: 24 }}>
          <h3 style={{ fontSize: 12, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
            Pending invitations ({invites.data?.length ?? 0})
          </h3>
          {invites.data && invites.data.length === 0 && (
            <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No pending invitations.</p>
          )}
          {invites.data && invites.data.length > 0 && (
            <InvitationsTable invites={invites.data} onRevoke={(id) => revokeMut.mutate(id)} />
          )}
        </section>
      </div>
    </div>
  )
}

function ErrorLine({ msg }: { msg: string }) {
  return <p style={{ fontSize: 12, color: 'var(--red)' }}>{msg}</p>
}

function InviteForm({
  loading,
  error,
  onSubmit,
}: {
  loading: boolean
  error: string | null
  onSubmit: (req: { email: string; role: MemberRole }) => void
}) {
  const [email, setEmail] = React.useState('')
  const [role, setRole] = React.useState<MemberRole>('member')

  function submit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit({ email, role })
    setEmail('')
  }

  return (
    <form
      onSubmit={submit}
      data-testid="admin-members-invite-form"
      style={{ display: 'flex', gap: 8, alignItems: 'center' }}
    >
      <input
        required
        type="email"
        placeholder="colleague@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        style={{ flex: 1, borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
      />
      <select
        value={role}
        onChange={(e) => setRole(e.target.value as MemberRole)}
        style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
      >
        {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
      </select>
      <button type="submit" className="btn btn-primary" disabled={loading}>
        {loading ? 'Inviting…' : 'Invite'}
      </button>
      {error && <span style={{ fontSize: 11, color: 'var(--red)' }}>{error}</span>}
    </form>
  )
}

function MembersTable({
  members,
  onChangeRole,
  onRemove,
}: {
  members: OrgMember[]
  onChangeRole: (userId: string, role: MemberRole) => void
  onRemove: (userId: string) => void
}) {
  return (
    <div className="tbl" data-testid="admin-members-table">
      <div className="audit-row" style={{ gridTemplateColumns: '1fr 1fr 120px 120px 80px', background: 'var(--bg-2)', borderBottom: '1px solid var(--line)', fontWeight: 600, fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        <span>Email</span><span>Name</span><span>Role</span><span>Last active</span><span />
      </div>
      {members.map((m) => (
        <div key={m.user_id} className="audit-row" style={{ gridTemplateColumns: '1fr 1fr 120px 120px 80px' }}>
          <span style={{ color: 'var(--ink)' }}>{m.email}</span>
          <span style={{ color: 'var(--ink-2)' }}>{m.name ?? '—'}</span>
          <select
            value={m.role}
            onChange={(e) => onChangeRole(m.user_id, e.target.value as MemberRole)}
            data-testid={`admin-member-role-${m.user_id}`}
            style={{ borderRadius: 3, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '2px 6px', fontSize: 11 }}
          >
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <span className="meta">{m.last_active_at ? new Date(m.last_active_at).toLocaleDateString() : '—'}</span>
          <button
            className="btn btn-sm"
            style={{ color: 'var(--red)' }}
            onClick={() => onRemove(m.user_id)}
            data-testid={`admin-member-remove-${m.user_id}`}
          >
            Remove
          </button>
        </div>
      ))}
    </div>
  )
}

function InvitationsTable({
  invites,
  onRevoke,
}: {
  invites: OrgInvitation[]
  onRevoke: (id: string) => void
}) {
  return (
    <div className="tbl" data-testid="admin-invitations-table">
      <div className="audit-row" style={{ gridTemplateColumns: '1fr 120px 120px 80px', background: 'var(--bg-2)', borderBottom: '1px solid var(--line)', fontWeight: 600, fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        <span>Email</span><span>Role</span><span>Expires</span><span />
      </div>
      {invites.map((inv) => (
        <div key={inv.id} className="audit-row" style={{ gridTemplateColumns: '1fr 120px 120px 80px' }}>
          <span style={{ color: 'var(--ink)' }}>{inv.email}</span>
          <span className="meta">{inv.role}</span>
          <span className="meta">{new Date(inv.expires_at).toLocaleDateString()}</span>
          <button
            className="btn btn-sm"
            style={{ color: 'var(--red)' }}
            onClick={() => onRevoke(inv.id)}
          >
            Revoke
          </button>
        </div>
      ))}
    </div>
  )
}
