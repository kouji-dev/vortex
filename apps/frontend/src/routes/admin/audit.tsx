import { createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import * as React from 'react'
import { auditExportUrl, fetchAuditEvents } from '~/lib/admin-api'
import type { AuditEvent } from '~/lib/admin-types'
import { isRangeValid, normalizeAuditFilter, type AuditFilterUiInputs } from '~/lib/audit-filter'

export const Route = createFileRoute('/admin/audit')({
  component: AuditPage,
})

const EMPTY_INPUTS: AuditFilterUiInputs = {
  action: '',
  actor: '',
  resourceType: '',
  resourceId: '',
  fromDate: '',
  toDate: '',
}

function AuditPage() {
  const [inputs, setInputs] = React.useState<AuditFilterUiInputs>(EMPTY_INPUTS)
  const [applied, setApplied] = React.useState<AuditFilterUiInputs>(EMPTY_INPUTS)

  const valid = isRangeValid(inputs.fromDate, inputs.toDate)
  const filter = normalizeAuditFilter(applied)

  const page = useQuery({
    queryKey: ['admin', 'audit', filter],
    queryFn: () => fetchAuditEvents(filter),
  })

  function update<K extends keyof AuditFilterUiInputs>(k: K, v: AuditFilterUiInputs[K]) {
    setInputs({ ...inputs, [k]: v })
  }

  function apply(e: React.FormEvent) {
    e.preventDefault()
    if (!valid) return
    setApplied(inputs)
  }

  function reset() {
    setInputs(EMPTY_INPUTS)
    setApplied(EMPTY_INPUTS)
  }

  return (
    <div className="panel" data-testid="admin-audit">
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Audit log</span>
        <a
          className="btn btn-sm"
          href={auditExportUrl(filter)}
          target="_blank"
          rel="noopener"
          data-testid="admin-audit-export"
        >
          Export CSV
        </a>
      </div>

      <div className="panel-body" style={{ padding: 16 }}>
        <form
          onSubmit={apply}
          data-testid="admin-audit-filters"
          style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr) auto', gap: 8, alignItems: 'end' }}
        >
          <FilterInput label="Action" value={inputs.action} onChange={(v) => update('action', v)} placeholder="org:update" />
          <FilterInput label="Actor" value={inputs.actor} onChange={(v) => update('actor', v)} placeholder="user id or email" />
          <FilterInput label="Resource type" value={inputs.resourceType} onChange={(v) => update('resourceType', v)} placeholder="org, kb, …" />
          <div />

          <FilterInput label="Resource id" value={inputs.resourceId} onChange={(v) => update('resourceId', v)} placeholder="any id" />
          <FilterInput label="From" type="date" value={inputs.fromDate} onChange={(v) => update('fromDate', v)} />
          <FilterInput label="To" type="date" value={inputs.toDate} onChange={(v) => update('toDate', v)} />
          <div style={{ display: 'flex', gap: 6 }}>
            <button type="submit" className="btn btn-primary" disabled={!valid}>Apply</button>
            <button type="button" className="btn btn-sm" onClick={reset}>Reset</button>
          </div>
        </form>

        {!valid && (
          <p style={{ marginTop: 8, fontSize: 11, color: 'var(--red)' }}>
            From date must be before or equal to To date.
          </p>
        )}

        <div style={{ marginTop: 16 }}>
          {page.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
          {page.error && <p style={{ fontSize: 12, color: 'var(--red)' }}>{(page.error as Error).message}</p>}
          {page.data && <AuditTable events={page.data.items} />}
          {page.data && page.data.items.length === 0 && (
            <p style={{ marginTop: 12, fontSize: 12, color: 'var(--ink-3)' }}>No events match these filters.</p>
          )}
        </div>
      </div>
    </div>
  )
}

function FilterInput({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  type?: 'text' | 'date'
}) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
      {label}
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12, textTransform: 'none', letterSpacing: 'normal' }}
      />
    </label>
  )
}

function AuditTable({ events }: { events: AuditEvent[] }) {
  return (
    <div className="tbl" data-testid="admin-audit-table">
      <div className="audit-row" style={{ gridTemplateColumns: '170px 160px 160px 1fr 170px', background: 'var(--bg-2)', borderBottom: '1px solid var(--line)', fontWeight: 600, fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        <span>Time</span><span>Action</span><span>Actor</span><span>Resource</span><span>Payload</span>
      </div>
      {events.map((ev) => (
        <div key={ev.id} className="audit-row" style={{ gridTemplateColumns: '170px 160px 160px 1fr 170px' }}>
          <span className="ts">{new Date(ev.ts).toLocaleString()}</span>
          <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>{ev.action}</span>
          <span className="meta" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {ev.actor_email ?? ev.actor_id ?? ev.actor_kind}
          </span>
          <span className="meta" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {ev.resource_type ? `${ev.resource_type}${ev.resource_id ? `:${ev.resource_id}` : ''}` : '—'}
          </span>
          <span className="meta" style={{ fontFamily: 'var(--font-mono)', fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {JSON.stringify(ev.payload)}
          </span>
        </div>
      ))}
    </div>
  )
}
