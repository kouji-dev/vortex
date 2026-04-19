import { useState, useEffect } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { PrismLogo } from '~/components/brand'

import { getApiBase } from '~/lib/api-base'
import type { HealthResponse } from '~/lib/health-types'

type SystemStatusCardProps = {
  health: UseQueryResult<HealthResponse>
}

export function SystemStatusCard({ health }: SystemStatusCardProps) {
  const [apiBase, setApiBase] = useState('')
  useEffect(() => { setApiBase(getApiBase()) }, [])
  return (
    <div className="rounded-xl border border-neutral-200 bg-neutral-50/80 p-5 dark:border-neutral-800 dark:bg-neutral-900/50">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">API</h2>
      <p className="mt-1 text-xs text-neutral-500">
        <code className="rounded bg-neutral-200/80 px-1 dark:bg-neutral-800">{apiBase}/health</code>
      </p>
      {health.isPending && <PrismLogo state="loading" size={16} className="mt-3" />}
      {health.isError && (
        <p className="mt-3 text-sm text-red-600">{(health.error as Error).message}</p>
      )}
      {health.isSuccess && (
        <div className="mt-3 space-y-1 text-sm text-green-700 dark:text-green-400">
          <p>
            Status: <strong>{health.data.status}</strong>
          </p>
          {health.data.auth_mode != null && (
            <p className="text-neutral-700 dark:text-neutral-300">
              API auth: <strong>{health.data.auth_mode}</strong>
            </p>
          )}
        </div>
      )}
    </div>
  )
}
