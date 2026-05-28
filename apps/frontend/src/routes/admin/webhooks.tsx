import { createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import {
  createWebhook,
  deleteWebhook,
  fetchWebhookDeliveries,
  fetchWebhookEventTypes,
  fetchWebhooks,
  replayWebhookDelivery,
} from '~/lib/admin-api'
import type {
  Webhook,
  WebhookCreated,
  WebhookCreateRequest,
  WebhookDelivery,
  WebhookEventType,
} from '~/lib/admin-types'
import { deliveryColor, deliveryZone, validateEventTypes, validateWebhookUrl } from '~/lib/webhook-form'

export const Route = createFileRoute('/admin/webhooks')({
  component: WebhooksPage,
})

function WebhooksPage() {
  const qc = useQueryClient()
  const list = useQuery({ queryKey: ['admin', 'webhooks'], queryFn: fetchWebhooks })
  const eventTypes = useQuery({
    queryKey: ['admin', 'webhook-event-types'],
    queryFn: fetchWebhookEventTypes,
  })
  const [creating, setCreating] = React.useState(false)
  const [secretShown, setSecretShown] = React.useState<WebhookCreated | null>(null)
  const [expanded, setExpanded] = React.useState<string | null>(null)

  const createMut = useMutation({
    mutationFn: createWebhook,
    onSuccess: (resp) => {
      qc.invalidateQueries({ queryKey: ['admin', 'webhooks'] })
      setSecretShown(resp)
      setCreating(false)
    },
  })

  const rmMut = useMutation({
    mutationFn: deleteWebhook,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'webhooks'] }),
  })

  return (
    <div className="panel" data-testid="admin-webhooks">
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Webhooks</span>
        <button
          className="btn btn-primary"
          onClick={() => setCreating(true)}
          data-testid="admin-webhooks-new"
        >
          New webhook
        </button>
      </div>

      <div className="panel-body" style={{ padding: 16 }}>
        {list.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
        {list.error && <p style={{ fontSize: 12, color: 'var(--red)' }}>{(list.error as Error).message}</p>}
        {list.data && list.data.length === 0 && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No webhooks yet. Create one to receive events.</p>
        )}
        {list.data && list.data.length > 0 && (
          <WebhooksTable
            webhooks={list.data}
            expanded={expanded}
            onExpand={(id) => setExpanded(id === expanded ? null : id)}
            onDelete={(id) => {
              if (confirm('Delete this webhook? Deliveries will stop.')) rmMut.mutate(id)
            }}
          />
        )}

        {creating && (
          <CreateWebhookDialog
            saving={createMut.isPending}
            error={createMut.error?.message ?? null}
            eventTypes={eventTypes.data?.items ?? []}
            onCancel={() => setCreating(false)}
            onSubmit={(r) => createMut.mutate(r)}
          />
        )}

        {secretShown && (
          <SecretOnceDialog response={secretShown} onClose={() => setSecretShown(null)} />
        )}
      </div>
    </div>
  )
}

function WebhooksTable({
  webhooks,
  expanded,
  onExpand,
  onDelete,
}: {
  webhooks: Webhook[]
  expanded: string | null
  onExpand: (id: string) => void
  onDelete: (id: string) => void
}) {
  return (
    <div className="tbl" data-testid="admin-webhooks-table">
      <div
        className="audit-row"
        style={{
          gridTemplateColumns: '1.4fr 1fr 90px 110px 110px',
          background: 'var(--bg-2)',
          borderBottom: '1px solid var(--line)',
          fontWeight: 600,
          fontSize: 10,
          color: 'var(--ink-3)',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        <span>URL</span><span>Events</span><span>Status</span><span /><span />
      </div>
      {webhooks.map((w) => (
        <React.Fragment key={w.id}>
          <div
            className="audit-row"
            style={{ gridTemplateColumns: '1.4fr 1fr 90px 110px 110px' }}
            data-testid={`admin-webhooks-row-${w.id}`}
          >
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'var(--font-mono)', fontSize: 11 }}>{w.url}</span>
            <span className="meta" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {w.event_types.slice(0, 3).join(', ')}{w.event_types.length > 3 ? ` +${w.event_types.length - 3}` : ''}
            </span>
            <span className="meta" style={{ color: w.enabled ? 'var(--ink-2)' : 'var(--red)' }}>
              {w.enabled ? 'enabled' : 'disabled'}
            </span>
            <button
              className="btn btn-sm"
              onClick={() => onExpand(w.id)}
              data-testid={`admin-webhooks-deliveries-${w.id}`}
            >
              {expanded === w.id ? 'Hide' : 'Deliveries'}
            </button>
            <button
              className="btn btn-sm"
              style={{ color: 'var(--red)' }}
              onClick={() => onDelete(w.id)}
            >
              Delete
            </button>
          </div>
          {expanded === w.id && <DeliveriesPanel webhookId={w.id} />}
        </React.Fragment>
      ))}
    </div>
  )
}

function DeliveriesPanel({ webhookId }: { webhookId: string }) {
  const qc = useQueryClient()
  const deliveries = useQuery({
    queryKey: ['admin', 'webhooks', webhookId, 'deliveries'],
    queryFn: () => fetchWebhookDeliveries(webhookId),
  })
  const replay = useMutation({
    mutationFn: (deliveryId: string) => replayWebhookDelivery(webhookId, deliveryId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ['admin', 'webhooks', webhookId, 'deliveries'] }),
  })

  return (
    <div
      style={{ padding: 12, background: 'var(--bg-2)', borderTop: '1px solid var(--line)' }}
      data-testid={`admin-webhooks-deliveries-panel-${webhookId}`}
    >
      <h4 style={{ fontSize: 11, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
        Recent deliveries
      </h4>
      {deliveries.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
      {deliveries.data && deliveries.data.items.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No deliveries yet.</p>
      )}
      {deliveries.data && deliveries.data.items.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {deliveries.data.items.map((d) => (
            <DeliveryRow key={d.id} d={d} onReplay={() => replay.mutate(d.id)} />
          ))}
        </div>
      )}
    </div>
  )
}

function DeliveryRow({ d, onReplay }: { d: WebhookDelivery; onReplay: () => void }) {
  const zone = deliveryZone(d)
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '170px 140px 90px 60px 1fr 80px',
        gap: 8,
        fontSize: 11,
        padding: '4px 0',
        borderBottom: '1px solid var(--line)',
      }}
    >
      <span className="ts">{new Date(d.created_at).toLocaleString()}</span>
      <span style={{ fontFamily: 'var(--font-mono)' }}>{d.event_type}</span>
      <span style={{ color: deliveryColor(zone), textTransform: 'uppercase', fontWeight: 600 }}>{zone}</span>
      <span className="meta">attempt {d.attempts}</span>
      <span className="meta" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {d.last_error ?? (d.last_response_status != null ? `HTTP ${d.last_response_status}` : '—')}
      </span>
      <button type="button" className="btn btn-sm" onClick={onReplay}>Replay</button>
    </div>
  )
}

function CreateWebhookDialog({
  saving,
  error,
  eventTypes,
  onSubmit,
  onCancel,
}: {
  saving: boolean
  error: string | null
  eventTypes: WebhookEventType[]
  onSubmit: (req: WebhookCreateRequest) => void
  onCancel: () => void
}) {
  const [url, setUrl] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [selected, setSelected] = React.useState<string[]>([])
  const [localError, setLocalError] = React.useState<string | null>(null)

  function toggle(key: string) {
    setSelected((prev) => (prev.includes(key) ? prev.filter((s) => s !== key) : [...prev, key]))
  }

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const urlErr = validateWebhookUrl(url)
    const evErr = validateEventTypes(selected)
    if (urlErr || evErr) {
      setLocalError(urlErr || evErr)
      return
    }
    setLocalError(null)
    onSubmit({ url: url.trim(), event_types: selected, description: description.trim() || null })
  }

  // Group event types by module for the picker.
  const groups: Record<string, WebhookEventType[]> = {}
  for (const et of eventTypes) {
    if (!groups[et.module]) groups[et.module] = []
    groups[et.module].push(et)
  }

  return (
    <Modal title="New webhook" onClose={onCancel} testId="admin-webhooks-create-dialog">
      <form onSubmit={submit}>
        <Field label="URL (https)">
          <input
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://hooks.example.com/ingest"
            style={inputStyle}
          />
        </Field>
        <Field label="Description (optional)">
          <input value={description} onChange={(e) => setDescription(e.target.value)} style={inputStyle} />
        </Field>
        <fieldset style={{ border: '1px solid var(--line)', borderRadius: 4, padding: 8, marginBottom: 12 }}>
          <legend style={{ padding: '0 6px', fontSize: 11, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Event types
          </legend>
          {Object.keys(groups).length === 0 && (
            <p style={{ fontSize: 11, color: 'var(--ink-3)' }}>No event types registered.</p>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
            {Object.entries(groups).map(([module, items]) => (
              <div key={module}>
                <div style={{ fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                  {module}
                </div>
                {items.map((et) => (
                  <label key={et.key} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, padding: '2px 0', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={selected.includes(et.key)}
                      onChange={() => toggle(et.key)}
                      data-testid={`admin-webhooks-event-${et.key}`}
                    />
                    <code style={{ fontSize: 10 }}>{et.key}</code>
                  </label>
                ))}
              </div>
            ))}
          </div>
        </fieldset>
        {(error || localError) && <p style={{ fontSize: 11, color: 'var(--red)', marginBottom: 8 }}>{error || localError}</p>}
        <DialogActions saving={saving} onCancel={onCancel} submitLabel="Create" />
      </form>
    </Modal>
  )
}

function SecretOnceDialog({
  response,
  onClose,
}: {
  response: WebhookCreated
  onClose: () => void
}) {
  const [copied, setCopied] = React.useState(false)
  async function copy() {
    await navigator.clipboard.writeText(response.secret)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <Modal title="Secret — copy it now" onClose={onClose} testId="admin-webhooks-secret-dialog">
      <p style={{ fontSize: 12, color: 'var(--ink-2)', marginBottom: 10 }}>
        Webhook secret will <strong>not be shown again</strong>. Store it for HMAC verification.
      </p>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <code
          data-testid="admin-webhooks-secret-value"
          style={{ flex: 1, padding: 8, borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg-2)', color: 'var(--ink)', fontFamily: 'var(--font-mono)', fontSize: 12, wordBreak: 'break-all' }}
        >
          {response.secret}
        </code>
        <button type="button" className="btn btn-sm" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
      </div>
      <button type="button" className="btn btn-primary" onClick={onClose}>I have saved it</button>
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
      <button type="submit" className="btn btn-primary" disabled={saving}>
        {saving ? 'Saving…' : submitLabel}
      </button>
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
        style={{ background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 8, padding: 20, width: '90%', maxWidth: 640, maxHeight: '85vh', overflowY: 'auto' }}
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
