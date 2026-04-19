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

  if (loading) return <p className="text-sm text-gray-500">Loading...</p>

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Data Retention</h2>
        <div className="flex items-center gap-3">
          {saved && <span className="text-sm text-green-600 dark:text-green-400">Saved</span>}
          {error && <span className="text-sm text-red-500">{error}</span>}
          <button
            onClick={save}
            disabled={saving}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      {/* Legal hold banner */}
      <div className={`rounded-xl border px-4 py-3 flex items-center justify-between ${legalHold ? 'border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950' : 'border-gray-100 dark:border-gray-800'}`}>
        <div>
          <p className="text-sm font-medium text-gray-900 dark:text-white">Legal hold</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">When enabled, the retention sweeper skips all records for this org. Overrides all retention schedules.</p>
        </div>
        <button
          onClick={() => setLegalHold((v) => !v)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${legalHold ? 'bg-amber-500' : 'bg-gray-200 dark:bg-gray-700'}`}
        >
          <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${legalHold ? 'translate-x-6' : 'translate-x-1'}`} />
        </button>
      </div>

      {/* Retention fields */}
      <div className="grid gap-4 sm:grid-cols-2">
        <RetentionField
          label="Conversations"
          description="Days to keep conversations + messages. Blank = never delete."
          value={convDays}
          onChange={setConvDays}
        />
        <RetentionField
          label="Uploads"
          description="Days to keep file uploads (disk + DB). Blank = never delete."
          value={uploadDays}
          onChange={setUploadDays}
        />
        <RetentionField
          label="Audit log"
          description="Days to retain audit events. Default 2555 (7 years)."
          value={auditDays}
          onChange={setAuditDays}
        />
        <RetentionField
          label="Usage data"
          description="Days to retain token/cost usage rows. Default 2555 (7 years)."
          value={usageDays}
          onChange={setUsageDays}
        />
      </div>

      {/* GDPR purge */}
      <section className="rounded-xl border border-red-100 bg-red-50 px-4 py-4 dark:border-red-900/40 dark:bg-red-950/30">
        <h3 className="mb-1 text-sm font-semibold text-red-700 dark:text-red-400">GDPR — Purge user data</h3>
        <p className="mb-3 text-xs text-red-600 dark:text-red-400">
          Permanently deletes all conversations, uploads, and memories for this user. Usage rows are anonymised. This cannot be undone.
        </p>
        <div className="flex items-center gap-2">
          <input
            type="number"
            placeholder="User ID"
            value={purgeUserId}
            onChange={(e) => { setPurgeUserId(e.target.value); setPurgeConfirm(false) }}
            className="w-32 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm dark:border-red-800 dark:bg-gray-900 dark:text-white"
          />
          <button
            onClick={purgeUser}
            disabled={purging || !purgeUserId}
            className={`rounded-lg px-4 py-1.5 text-sm font-semibold text-white transition-colors disabled:opacity-50 ${purgeConfirm ? 'bg-red-700 hover:bg-red-800' : 'bg-red-500 hover:bg-red-600'}`}
          >
            {purging ? 'Purging…' : purgeConfirm ? 'Confirm purge' : 'Purge'}
          </button>
        </div>
        {purgeError && <p className="mt-2 text-xs text-red-600 dark:text-red-400">{purgeError}</p>}
      </section>
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
    <div className="rounded-xl border border-gray-100 dark:border-gray-800 px-4 py-3">
      <label className="block text-sm font-medium text-gray-900 dark:text-white mb-1">{label}</label>
      <p className="text-xs text-gray-400 mb-2">{description}</p>
      <input
        type="number"
        min="1"
        placeholder="Never"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white"
      />
      {value && <p className="mt-1 text-xs text-gray-400">{value} days ≈ {(parseInt(value, 10) / 365).toFixed(1)} years</p>}
    </div>
  )
}
