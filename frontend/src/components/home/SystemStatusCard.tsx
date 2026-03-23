import type { UseQueryResult } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'

type SystemStatusCardProps = {
  health: UseQueryResult<{ status: string }>
}

export function SystemStatusCard({ health }: SystemStatusCardProps) {
  const apiBase = getApiBase()
  return (
    <div className="rounded-xl border border-neutral-200 bg-neutral-50/80 p-5 dark:border-neutral-800 dark:bg-neutral-900/50">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">API</h2>
      <p className="mt-1 text-xs text-neutral-500">
        <code className="rounded bg-neutral-200/80 px-1 dark:bg-neutral-800">{apiBase}/health</code>
      </p>
      {health.isPending && <p className="mt-3 text-sm text-neutral-500">Checking…</p>}
      {health.isError && (
        <p className="mt-3 text-sm text-red-600">{(health.error as Error).message}</p>
      )}
      {health.isSuccess && (
        <p className="mt-3 text-sm text-green-700 dark:text-green-400">
          Status: <strong>{health.data.status}</strong>
        </p>
      )}
    </div>
  )
}
