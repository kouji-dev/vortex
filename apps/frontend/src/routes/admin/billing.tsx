import { createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import { fetchInvoices, fetchSubscription, patchSubscription } from '~/lib/admin-api'
import type { Invoice, Subscription } from '~/lib/admin-types'
import {
  formatCents,
  groupInvoicesByYear,
  PLAN_OPTIONS,
  subscriptionStatusLabel,
} from '~/lib/billing-format'

export const Route = createFileRoute('/admin/billing')({
  component: BillingPage,
})

function BillingPage() {
  const qc = useQueryClient()
  const sub = useQuery({ queryKey: ['admin', 'billing', 'subscription'], queryFn: fetchSubscription })
  const invoices = useQuery({ queryKey: ['admin', 'billing', 'invoices'], queryFn: fetchInvoices })

  const patch = useMutation({
    mutationFn: patchSubscription,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'billing', 'subscription'] }),
  })

  const [pickingPlan, setPickingPlan] = React.useState(false)

  return (
    <div className="panel" data-testid="admin-billing">
      <div className="panel-head">
        <span>Billing</span>
      </div>

      <div className="panel-body" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 24 }}>
        <section data-testid="admin-billing-subscription">
          <h3 style={{ fontSize: 12, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
            Subscription
          </h3>
          {sub.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
          {sub.error && <p style={{ fontSize: 12, color: 'var(--red)' }}>{(sub.error as Error).message}</p>}
          {!sub.isPending && !sub.data && (
            <SubscriptionEmpty
              onPick={() => setPickingPlan(true)}
              picking={pickingPlan}
              saving={patch.isPending}
              error={patch.error?.message ?? null}
              onSubmit={(code, seats) => patch.mutate({ plan_code: code, seats })}
              onCancel={() => setPickingPlan(false)}
            />
          )}
          {sub.data && (
            <SubscriptionCard
              s={sub.data}
              picking={pickingPlan}
              onPick={() => setPickingPlan(true)}
              onCancel={() => setPickingPlan(false)}
              saving={patch.isPending}
              error={patch.error?.message ?? null}
              onChangePlan={(code, seats) => {
                setPickingPlan(false)
                patch.mutate({ plan_code: code, seats })
              }}
              onCancelSub={() => {
                if (confirm('Cancel this subscription at period end?')) patch.mutate({ cancel: true })
              }}
            />
          )}
        </section>

        <section data-testid="admin-billing-invoices">
          <h3 style={{ fontSize: 12, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
            Invoices
          </h3>
          {invoices.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
          {invoices.error && <p style={{ fontSize: 12, color: 'var(--red)' }}>{(invoices.error as Error).message}</p>}
          {invoices.data && invoices.data.items.length === 0 && (
            <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No invoices yet.</p>
          )}
          {invoices.data && invoices.data.items.length > 0 && <InvoiceTable items={invoices.data.items} />}
        </section>
      </div>
    </div>
  )
}

function SubscriptionCard({
  s,
  picking,
  onPick,
  onCancel,
  saving,
  error,
  onChangePlan,
  onCancelSub,
}: {
  s: Subscription
  picking: boolean
  onPick: () => void
  onCancel: () => void
  saving: boolean
  error: string | null
  onChangePlan: (code: string, seats: number) => void
  onCancelSub: () => void
}) {
  const portalUrl = `https://billing.stripe.com/p/login`
  return (
    <div
      className="panel"
      style={{ padding: 16, border: '1px solid var(--line)', background: 'var(--bg-2)' }}
      data-testid="admin-billing-current-plan"
    >
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr) auto', gap: 16, alignItems: 'center' }}>
        <Kv label="Plan" value={s.plan_code} />
        <Kv label="Kind" value={s.plan_kind} />
        <Kv label="Seats" value={String(s.seats)} />
        <Kv
          label="Status"
          value={subscriptionStatusLabel(s)}
          color={s.canceled_at ? 'var(--red)' : s.status === 'active' ? 'var(--accent)' : 'var(--ink-2)'}
        />
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-sm" onClick={onPick} data-testid="admin-billing-change-plan">Change plan</button>
          <a
            className="btn btn-sm"
            href={portalUrl}
            target="_blank"
            rel="noopener"
            data-testid="admin-billing-portal-link"
          >
            Manage in Stripe
          </a>
          {!s.canceled_at && (
            <button className="btn btn-sm" style={{ color: 'var(--red)' }} onClick={onCancelSub} data-testid="admin-billing-cancel">
              Cancel
            </button>
          )}
        </div>
      </div>
      {picking && (
        <PlanPicker
          currentPlan={s.plan_code}
          currentSeats={s.seats}
          saving={saving}
          error={error}
          onSubmit={onChangePlan}
          onCancel={onCancel}
        />
      )}
    </div>
  )
}

function SubscriptionEmpty({
  onPick,
  picking,
  saving,
  error,
  onSubmit,
  onCancel,
}: {
  onPick: () => void
  picking: boolean
  saving: boolean
  error: string | null
  onSubmit: (code: string, seats: number) => void
  onCancel: () => void
}) {
  return (
    <div style={{ padding: 16, border: '1px solid var(--line)', borderRadius: 4, background: 'var(--bg-2)' }} data-testid="admin-billing-empty">
      <p style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 8 }}>
        No active subscription. Pick a plan to enable paid features.
      </p>
      {!picking && (
        <button className="btn btn-primary" onClick={onPick} data-testid="admin-billing-pick-plan">Pick plan</button>
      )}
      {picking && (
        <PlanPicker currentPlan={null} currentSeats={1} saving={saving} error={error} onSubmit={onSubmit} onCancel={onCancel} />
      )}
    </div>
  )
}

function PlanPicker({
  currentPlan,
  currentSeats,
  saving,
  error,
  onSubmit,
  onCancel,
}: {
  currentPlan: string | null
  currentSeats: number
  saving: boolean
  error: string | null
  onSubmit: (code: string, seats: number) => void
  onCancel: () => void
}) {
  const [plan, setPlan] = React.useState(currentPlan ?? PLAN_OPTIONS[0].code)
  const [seats, setSeats] = React.useState(currentSeats)

  return (
    <div style={{ marginTop: 12, padding: 12, border: '1px solid var(--line)', borderRadius: 4 }} data-testid="admin-billing-plan-picker">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {PLAN_OPTIONS.map((p) => (
          <label
            key={p.code}
            style={{
              display: 'flex',
              gap: 10,
              alignItems: 'center',
              padding: 8,
              border: '1px solid var(--line)',
              borderRadius: 4,
              cursor: 'pointer',
              background: plan === p.code ? 'var(--bg)' : 'transparent',
            }}
          >
            <input
              type="radio"
              name="plan"
              value={p.code}
              checked={plan === p.code}
              onChange={() => setPlan(p.code)}
              data-testid={`admin-billing-plan-${p.code}`}
            />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, color: 'var(--ink)' }}>{p.label}</div>
              <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>{p.blurb}</div>
            </div>
            <span className="meta">{p.kind}</span>
          </label>
        ))}
      </div>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, marginTop: 12, maxWidth: 180 }}>
        Seats
        <input
          type="number"
          min={1}
          value={seats}
          onChange={(e) => setSeats(Math.max(1, Number(e.target.value)))}
          style={{ borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '4px 8px', fontSize: 12 }}
          data-testid="admin-billing-seats"
        />
      </label>
      {error && <p style={{ fontSize: 11, color: 'var(--red)', marginTop: 8 }}>{error}</p>}
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button className="btn btn-primary" onClick={() => onSubmit(plan, seats)} disabled={saving} data-testid="admin-billing-submit">
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button className="btn btn-sm" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}

function Kv({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{ fontSize: 13, color: color ?? 'var(--ink)', fontWeight: 600 }}>{value}</div>
    </div>
  )
}

function InvoiceTable({ items }: { items: Invoice[] }) {
  const groups = groupInvoicesByYear(items)
  return (
    <div data-testid="admin-billing-invoice-table">
      {groups.map((g) => (
        <div key={g.year} style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--ink-3)', marginBottom: 6 }}>{g.year || 'Undated'}</div>
          <div className="tbl">
            <div
              className="audit-row"
              style={{
                gridTemplateColumns: '160px 130px 1fr 100px 100px 80px',
                background: 'var(--bg-2)',
                borderBottom: '1px solid var(--line)',
                fontWeight: 600,
                fontSize: 10,
                color: 'var(--ink-3)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              <span>Issued</span><span>External id</span><span>Memo</span><span>Status</span><span>Amount</span><span />
            </div>
            {g.items.map((inv) => (
              <div key={inv.id} className="audit-row" style={{ gridTemplateColumns: '160px 130px 1fr 100px 100px 80px' }}>
                <span className="ts">{inv.issued_at ? new Date(inv.issued_at).toLocaleDateString() : '—'}</span>
                <span className="meta" style={{ fontFamily: 'var(--font-mono)' }}>{inv.external_id ?? '—'}</span>
                <span className="meta" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{inv.memo ?? '—'}</span>
                <span className="meta">{inv.status}</span>
                <span style={{ color: 'var(--ink)' }}>{formatCents(inv.amount_cents, inv.currency)}</span>
                {inv.pdf_url ? (
                  <a className="btn btn-sm" href={inv.pdf_url} target="_blank" rel="noopener">PDF</a>
                ) : <span />}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
