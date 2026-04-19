import * as React from 'react'
import { authorizedFetch } from '~/lib/authorizedFetch'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

interface AuditEvent {
  id: number
  actor_user_id: number | null
  actor_type: string
  event_type: string
  resource_type: string
  resource_id: string | null
  action: string
  created_at: string
}

interface AuditResponse {
  total: number
  items: AuditEvent[]
}

export function AuditLogPanel() {
  const [data, setData] = React.useState<AuditResponse | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [filterType, setFilterType] = React.useState('')

  const load = React.useCallback(() => {
    setLoading(true)
    setError(null)
    const params = new URLSearchParams({ limit: '100' })
    if (filterType) params.set('event_type', filterType)
    authorizedFetch(`${API_BASE}/api/admin/audit?${params}`)
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [filterType])

  React.useEffect(() => { load() }, [load])

  function exportCsv() {
    window.open(`${API_BASE}/api/admin/audit/export?fmt=csv`, '_blank')
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          Audit Log {data && <span className="text-sm font-normal text-gray-500">({data.total} events)</span>}
        </h2>
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Filter by event type..."
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white w-44"
          />
          <button
            onClick={exportCsv}
            className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            Export CSV
          </button>
        </div>
      </div>

      {error && <p className="mb-4 text-sm text-red-500">{error}</p>}
      {loading && <p className="text-sm text-gray-500">Loading...</p>}

      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-gray-100 dark:border-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-800 text-left text-xs text-gray-500 dark:text-gray-400">
                <th className="px-4 py-2 font-medium">Time</th>
                <th className="px-4 py-2 font-medium">Event</th>
                <th className="px-4 py-2 font-medium">Resource</th>
                <th className="px-4 py-2 font-medium">Action</th>
                <th className="px-4 py-2 font-medium">Actor</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 dark:divide-gray-800/50">
              {data.items.map((ev) => (
                <tr key={ev.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
                  <td className="px-4 py-2 text-xs text-gray-500 whitespace-nowrap">
                    {new Date(ev.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-indigo-600 dark:text-indigo-400">{ev.event_type}</td>
                  <td className="px-4 py-2 text-xs text-gray-700 dark:text-gray-300">
                    {ev.resource_type}{ev.resource_id ? ` #${ev.resource_id}` : ''}
                  </td>
                  <td className="px-4 py-2 text-xs text-gray-700 dark:text-gray-300 capitalize">{ev.action}</td>
                  <td className="px-4 py-2 text-xs text-gray-500">
                    {ev.actor_user_id ? `user:${ev.actor_user_id}` : ev.actor_type}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.items.length === 0 && !loading && (
        <p className="text-sm text-gray-500">No audit events.</p>
      )}
    </div>
  )
}
