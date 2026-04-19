import * as React from 'react'
import { authorizedFetch } from '~/lib/authorizedFetch'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

interface RetentionPolicy {
  conversation_retention_days: number | null
  audit_retention_days: number
  usage_retention_days: number
  upload_retention_days: number | null
  legal_hold: boolean
}

export function RetentionPanel() {
  const [policy, setPolicy] = React.useState<RetentionPolicy | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [saved, setSaved] = React.useState(false)

  // Draft state
  const [convDays, setConvDays] = React.useState<string>('')
  const [auditDays, setAuditDays] = React.useState<string>('2555')
  const [usageDays, setUsageDays] = React.useState<string>('2555')
  const [uploadDays, setUploadDays] = React.useState<string>('')
  const [legalHold, setLegalHold] = React.useState(false)

  // GDPR purge
  const [purgeUserId, setPurgeUserId] = React.useState('')
  const [purging, setPurging] = React.useState(false)
  const [purgeError, setPurgeError] = React.useState<string | null>(null)
  const [purgeConfirm, setPurgeConfirm] = React.useState(false)

  React.useEffect(() => {
    setLoading(true)
    authorizedFetch(`${API_BASE}/api/admin/retention/policy`)
      .then((r) => r.json())
      .then((pol: RetentionPolicy) => {
        setPolicy(pol)
        setConvDays(pol.conversation_retention_days?.toString() ?? '')
        setAuditDays(pol.audit_retention_days.toString())
        setUsageDays(pol.usage_retention_days.toString())
        setUploadDays(pol.upload_retention_days?.toString() ?? '')
        setLegalHold(pol.legal_hold)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  async function save() {
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      const res = await authorizedFetch(`${API_BASE}/api/admin/retention/policy`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_retention_days: convDays === '' ? null : parseInt(convDays, 10),
          audit_retention_days: parseInt(auditDays, 10) || 2555,
          usage_retention_days: parseInt(usageDays, 10) || 2555,
          upload_retention_days: uploadDays === '' ? null : parseInt(uploadDays, 10),
          legal_hold: legalHold,
        }),
      })
      if (!res.ok) throw new Error((await res.json()).detail ?? 'Save failed')
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function purgeUser() {
    if (!purgeConfirm) {
      setPurgeConfirm(true)
      return
    }
    const uid = parseInt(purgeUserId, 10)
    if (isNaN(uid)) {
      setPurgeError('Enter a valid user ID')
      return
    }
    setPurging(true)
    setPurgeError(null)
    try {
      const res = await authorizedFetch(`${API_BASE}/api/admin/retention/users/${uid}/data`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error((await res.json()).detail ?? 'Purge failed')
      setPurgeUserId('')
      setPurgeConfirm(false)
      alert(`User ${uid} data purged.`)
    } catch (e: unknown) {
      setPurgeError(e instanceof Error ? e.message : 'Purge failed')
    } finally {
      setPurging(false)
    }
  }

  if (loading) return <p style={{ padding: 16, fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>

  // Suppress unused variable warning
  void policy

  return (
    <div>
      <div className="panel-head" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span>Data Retention</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {saved && <span style={{ fontSize: 12, color: 'var(--green, #22c55e)' }}>Saved</span>}
          {error && <span style={{ fontSize: 12, color: 'var(--red)' }}>{error}</span>}
          <button onClick={save} disabled={saving} className="btn btn-primary btn-sm">
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      <div className="panel-body">
        {/* Legal hold */}
        <div className="policy-row" style={{
          gridTemplateColumns: '1fr auto',
          padding: '12px 14px',
          marginBottom: 16,
          border: `1px solid ${legalHold ? 'var(--orange, #f59e0b)' : 'var(--line)'}`,
          borderRadius: 4,
          background: legalHold ? 'color-mix(in srgb, var(--orange, #f59e0b) 8%, var(--bg))' : 'var(--bg)',
        }}>
          <div>
            <div className="title">Legal hold</div>
            <div className="meta">When enabled, the retention sweeper skips all records for this org. Overrides all schedules.</div>
          </div>
          <button
            onClick={() => setLegalHold((v) => !v)}
            className={`switch${legalHold ? ' on' : ''}`}
            aria-label="Toggle legal hold"
          />
        </div>

        {/* Retention fields */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
          <RetentionField label="Conversations" description="Days to keep conversations + messages. Blank = never delete." value={convDays} onChange={setConvDays} />
          <RetentionField label="Uploads" description="Days to keep file uploads (disk + DB). Blank = never delete." value={uploadDays} onChange={setUploadDays} />
          <RetentionField label="Audit log" description="Days to retain audit events. Default 2555 (7 years)." value={auditDays} onChange={setAuditDays} />
          <RetentionField label="Usage data" description="Days to retain token/cost usage rows. Default 2555 (7 years)." value={usageDays} onChange={setUsageDays} />
        </div>

        {/* GDPR purge */}
        <div style={{ border: '1px solid color-mix(in srgb, var(--red) 40%, var(--line))', borderRadius: 4, padding: '14px', background: 'color-mix(in srgb, var(--red) 5%, var(--bg))' }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--red)', marginBottom: 4 }}>GDPR — Purge user data</div>
          <p style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--font-mono)', marginBottom: 10, opacity: 0.8 }}>
            Permanently deletes all conversations, uploads, and memories for this user. Usage rows anonymised. Cannot be undone.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type="number"
              placeholder="User ID"
              value={purgeUserId}
              onChange={(e) => { setPurgeUserId(e.target.value); setPurgeConfirm(false) }}
              style={{ width: 100, borderRadius: 3, border: '1px solid color-mix(in srgb, var(--red) 40%, var(--line))', background: 'var(--bg)', color: 'var(--ink)', padding: '3px 8px', fontSize: 12 }}
            />
            <button
              onClick={purgeUser}
              disabled={purging || !purgeUserId}
              className="btn btn-sm"
              style={{ background: purgeConfirm ? 'var(--red)' : undefined, color: purgeConfirm ? '#fff' : 'var(--red)', borderColor: 'color-mix(in srgb, var(--red) 40%, var(--line))' }}
            >
              {purging ? 'Purging…' : purgeConfirm ? 'Confirm purge' : 'Purge'}
            </button>
          </div>
          {purgeError && <p style={{ marginTop: 6, fontSize: 11, color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>{purgeError}</p>}
        </div>
      </div>
    </div>
  )
}

function RetentionField({
  label,
  description,
  value,
  onChange,
}: {
  label: string
  description: string
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div style={{ border: '1px solid var(--line)', borderRadius: 4, padding: '10px 12px' }}>
      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--ink)', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 10, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', marginBottom: 8 }}>{description}</div>
      <input
        type="number"
        min="1"
        placeholder="Never"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ width: '100%', borderRadius: 3, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '3px 8px', fontSize: 12 }}
      />
      {value && (
        <p style={{ marginTop: 4, fontSize: 10, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>
          {value} days ≈ {(parseInt(value, 10) / 365).toFixed(1)} years
        </p>
      )}
    </div>
  )
}
