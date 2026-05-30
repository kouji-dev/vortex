import { createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import {
  addTeamMember,
  createTeam,
  deleteTeam,
  fetchMembers,
  fetchTeamKeyCount,
  fetchTeamMembers,
  fetchTeams,
  fetchTeamUsage,
  removeTeamMember,
} from '~/lib/admin-api'
import type { OrgMember, Team } from '~/lib/admin-types'

export const Route = createFileRoute('/admin/teams')({
  component: TeamsPage,
})

function TeamsPage() {
  const qc = useQueryClient()
  const teams = useQuery({ queryKey: ['admin', 'teams'], queryFn: fetchTeams })
  const [selected, setSelected] = React.useState<string | null>(null)
  const [creating, setCreating] = React.useState(false)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['admin', 'teams'] })

  const createMut = useMutation({
    mutationFn: createTeam,
    onSuccess: (t) => {
      invalidate()
      setCreating(false)
      setSelected(t.id)
    },
  })
  const deleteMut = useMutation({
    mutationFn: deleteTeam,
    onSuccess: () => {
      invalidate()
      setSelected(null)
    },
  })

  return (
    <div className="panel" data-testid="admin-teams">
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Teams</span>
        <button className="btn btn-primary" onClick={() => setCreating(true)} data-testid="admin-teams-new">
          New team
        </button>
      </div>

      <div className="panel-body" style={{ padding: 16 }}>
        {teams.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
        {teams.error && <p style={{ fontSize: 12, color: 'var(--red)' }}>{(teams.error as Error).message}</p>}

        {teams.data && teams.data.length === 0 && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No teams yet. Create one to group members.</p>
        )}

        {teams.data && teams.data.length > 0 && (
          <TeamsTable
            teams={teams.data}
            selected={selected}
            onSelect={(id) => setSelected(id === selected ? null : id)}
            onDelete={(id) => {
              if (confirm('Delete this team? Members keep their personal keys.')) deleteMut.mutate(id)
            }}
          />
        )}

        {selected && <TeamDetail teamId={selected} />}

        {creating && (
          <CreateTeamDialog
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

function TeamsTable({
  teams,
  selected,
  onSelect,
  onDelete,
}: {
  teams: Team[]
  selected: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
}) {
  return (
    <div className="tbl" data-testid="admin-teams-table">
      <div className="audit-row" style={{ gridTemplateColumns: '1fr 1fr 100px 80px', background: 'var(--bg-2)', borderBottom: '1px solid var(--line)', fontWeight: 600, fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        <span>Name</span><span>Slug</span><span>Members</span><span />
      </div>
      {teams.map((t) => (
        <div
          key={t.id}
          className={`audit-row${selected === t.id ? ' active' : ''}`}
          style={{ gridTemplateColumns: '1fr 1fr 100px 80px', cursor: 'pointer', background: selected === t.id ? 'var(--bg-2)' : undefined }}
          onClick={() => onSelect(t.id)}
          data-testid={`admin-team-row-${t.slug}`}
        >
          <span style={{ color: 'var(--ink)' }}>{t.name}</span>
          <span className="meta" style={{ fontFamily: 'var(--font-mono)' }}>{t.slug}</span>
          <span className="meta">{t.member_count}</span>
          <button
            className="btn btn-sm"
            style={{ color: 'var(--red)' }}
            onClick={(e) => { e.stopPropagation(); onDelete(t.id) }}
            data-testid={`admin-team-delete-${t.slug}`}
          >
            Delete
          </button>
        </div>
      ))}
    </div>
  )
}

function TeamDetail({ teamId }: { teamId: string }) {
  const qc = useQueryClient()
  const members = useQuery({ queryKey: ['admin', 'team-members', teamId], queryFn: () => fetchTeamMembers(teamId) })
  const orgMembers = useQuery({ queryKey: ['admin', 'members'], queryFn: fetchMembers })
  const keyCount = useQuery({ queryKey: ['admin', 'team-keys', teamId], queryFn: () => fetchTeamKeyCount(teamId) })
  const usage = useQuery({ queryKey: ['admin', 'team-usage', teamId], queryFn: () => fetchTeamUsage(teamId) })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['admin', 'team-members', teamId] })
    qc.invalidateQueries({ queryKey: ['admin', 'team-keys', teamId] })
    qc.invalidateQueries({ queryKey: ['admin', 'team-usage', teamId] })
    qc.invalidateQueries({ queryKey: ['admin', 'teams'] })
  }

  const addMut = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: string | null }) =>
      addTeamMember(teamId, { user_id: userId, role }),
    onSuccess: invalidate,
  })
  const removeMut = useMutation({
    mutationFn: (userId: number) => removeTeamMember(teamId, userId),
    onSuccess: invalidate,
  })

  const memberIds = new Set((members.data ?? []).map((m) => m.user_id))
  const addable = (orgMembers.data ?? []).filter((m: OrgMember) => !memberIds.has(Number(m.user_id)))

  return (
    <section style={{ marginTop: 20, borderTop: '1px solid var(--line)', paddingTop: 16 }} data-testid="admin-team-detail">
      <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
        <Stat label="Members" value={keyCount.data?.member_count ?? members.data?.length ?? 0} testId="admin-team-stat-members" />
        <Stat label="API keys" value={keyCount.data?.key_count ?? 0} testId="admin-team-stat-keys" />
        <Stat label="Cost (USD)" value={usage.data ? `$${usage.data.cost_usd.toFixed(2)}` : '—'} testId="admin-team-stat-cost" />
        <Stat label="Tokens in" value={usage.data?.input_tokens ?? 0} testId="admin-team-stat-tokens" />
      </div>

      <h4 style={{ fontSize: 11, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
        Members
      </h4>
      {members.data && members.data.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No members yet.</p>
      )}
      {members.data && members.data.length > 0 && (
        <div className="tbl" data-testid="admin-team-members-table">
          {members.data.map((m) => (
            <div key={m.id} className="audit-row" style={{ gridTemplateColumns: '1fr 120px 80px' }}>
              <span style={{ color: 'var(--ink)' }}>{m.email ?? `user #${m.user_id}`}</span>
              <span className="meta">{m.role ?? '—'}</span>
              <button
                className="btn btn-sm"
                style={{ color: 'var(--red)' }}
                onClick={() => removeMut.mutate(m.user_id)}
                data-testid={`admin-team-member-remove-${m.user_id}`}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      <AddMemberRow
        addable={addable}
        disabled={addMut.isPending}
        onAdd={(userId, role) => addMut.mutate({ userId, role: role || null })}
      />
    </section>
  )
}

function AddMemberRow({
  addable,
  disabled,
  onAdd,
}: {
  addable: OrgMember[]
  disabled: boolean
  onAdd: (userId: number, role: string) => void
}) {
  const [userId, setUserId] = React.useState('')
  const [role, setRole] = React.useState('')

  return (
    <form
      data-testid="admin-team-add-member-form"
      style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 10 }}
      onSubmit={(e) => {
        e.preventDefault()
        if (userId) onAdd(Number(userId), role)
        setUserId('')
        setRole('')
      }}
    >
      <select
        value={userId}
        onChange={(e) => setUserId(e.target.value)}
        required
        data-testid="admin-team-add-member-select"
        style={{ flex: 1, borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
      >
        <option value="">Add a member…</option>
        {addable.map((m) => (
          <option key={m.user_id} value={m.user_id}>{m.email}</option>
        ))}
      </select>
      <input
        value={role}
        onChange={(e) => setRole(e.target.value)}
        placeholder="team role (optional)"
        style={{ width: 160, borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
      />
      <button type="submit" className="btn btn-sm" disabled={disabled || !userId}>Add</button>
    </form>
  )
}

function Stat({ label, value, testId }: { label: string; value: React.ReactNode; testId?: string }) {
  return (
    <div className="kpi" data-testid={testId} style={{ border: '1px solid var(--line)', borderRadius: 6, padding: '8px 12px', minWidth: 90 }}>
      <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink)' }}>{value}</div>
      <div style={{ fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
    </div>
  )
}

function CreateTeamDialog({
  saving,
  error,
  onSubmit,
  onCancel,
}: {
  saving: boolean
  error: string | null
  onSubmit: (req: { slug: string; name: string; description?: string }) => void
  onCancel: () => void
}) {
  const [name, setName] = React.useState('')
  const [slug, setSlug] = React.useState('')
  const [description, setDescription] = React.useState('')

  return (
    <div
      role="dialog"
      aria-modal="true"
      data-testid="admin-teams-create-dialog"
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 8, padding: 20, width: '90%', maxWidth: 460 }}
      >
        <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>New team</h3>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            onSubmit({ slug, name, description: description || undefined })
          }}
        >
          <Field label="Name">
            <input
              required
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                if (!slug) setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''))
              }}
              placeholder="Engineering"
              data-testid="admin-teams-create-name"
              style={inputStyle}
            />
          </Field>
          <Field label="Slug">
            <input
              required
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="engineering"
              data-testid="admin-teams-create-slug"
              style={inputStyle}
            />
          </Field>
          <Field label="Description (optional)">
            <input value={description} onChange={(e) => setDescription(e.target.value)} style={inputStyle} />
          </Field>

          {error && <p style={{ fontSize: 11, color: 'var(--red)', marginBottom: 8 }}>{error}</p>}

          <div style={{ display: 'flex', gap: 8 }}>
            <button type="submit" className="btn btn-primary" disabled={saving} data-testid="admin-teams-create-submit">
              {saving ? 'Creating…' : 'Create'}
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
