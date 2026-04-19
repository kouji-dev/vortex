import * as React from 'react'
import { authorizedFetch } from '~/lib/authorizedFetch'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

interface UsageRow {
  group_key: string
  input_tokens: number
  output_tokens: number
  cached_input_tokens: number
  cost_usd: string
  message_count: number
}

interface UsageSummary {
  start: string
  end: string
  group_by: string
  rows: UsageRow[]
  total_cost_usd: string
  total_messages: number
}

export function UsagePanel() {
  const [summary, setSummary] = React.useState<UsageSummary | null>(null)
  const [groupBy, setGroupBy] = React.useState<'model' | 'user' | 'capability'>('model')
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    setLoading(true)
    setError(null)
    authorizedFetch(`${API_BASE}/api/admin/usage/summary?group_by=${groupBy}`)
      .then((r) => r.json())
      .then(setSummary)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [groupBy])

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Usage & Cost (last 30 days)</h2>
        <select
          value={groupBy}
          onChange={(e) => setGroupBy(e.target.value as typeof groupBy)}
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white"
        >
          <option value="model">By model</option>
          <option value="user">By user</option>
          <option value="capability">By capability</option>
        </select>
      </div>

      {error && <p className="mb-4 text-sm text-red-500">{error}</p>}

      {summary && (
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Stat label="Total cost" value={`$${parseFloat(summary.total_cost_usd).toFixed(4)}`} />
          <Stat label="Total messages" value={summary.total_messages.toLocaleString()} />
          <Stat label="Models / groups" value={summary.rows.length.toString()} />
        </div>
      )}

      {loading && <p className="text-sm text-gray-500">Loading...</p>}

      {summary && summary.rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-gray-100 dark:border-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-800 text-left text-xs text-gray-500 dark:text-gray-400">
                <th className="px-4 py-2 font-medium">Group</th>
                <th className="px-4 py-2 font-medium text-right">Messages</th>
                <th className="px-4 py-2 font-medium text-right">Input tokens</th>
                <th className="px-4 py-2 font-medium text-right">Output tokens</th>
                <th className="px-4 py-2 font-medium text-right">Cached</th>
                <th className="px-4 py-2 font-medium text-right">Cost (USD)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 dark:divide-gray-800/50">
              {summary.rows.map((row) => (
                <tr key={row.group_key} className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
                  <td className="px-4 py-2 font-mono text-xs text-gray-700 dark:text-gray-300 max-w-[200px] truncate">{row.group_key}</td>
                  <td className="px-4 py-2 text-right text-gray-700 dark:text-gray-300">{row.message_count.toLocaleString()}</td>
                  <td className="px-4 py-2 text-right text-gray-700 dark:text-gray-300">{row.input_tokens.toLocaleString()}</td>
                  <td className="px-4 py-2 text-right text-gray-700 dark:text-gray-300">{row.output_tokens.toLocaleString()}</td>
                  <td className="px-4 py-2 text-right text-green-600 dark:text-green-400">{row.cached_input_tokens.toLocaleString()}</td>
                  <td className="px-4 py-2 text-right font-medium text-gray-900 dark:text-white">${parseFloat(row.cost_usd).toFixed(6)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {summary && summary.rows.length === 0 && !loading && (
        <p className="text-sm text-gray-500">No usage data for this period.</p>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white px-4 py-3 dark:border-gray-800 dark:bg-gray-900">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className="mt-1 text-xl font-semibold text-gray-900 dark:text-white">{value}</p>
    </div>
  )
}
