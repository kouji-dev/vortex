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
    <div className="rounded-xl border border-line bg-bg-2 p-5">
      <h2 className="text-lg font-semibold text-ink">API</h2>
      <p className="mt-1 text-xs text-ink-3">
        <code className="rounded bg-bg px-1">{apiBase}/health</code>
      </p>
      {health.isPending && <PrismLogo state="loading" size={16} className="mt-3" />}
      {health.isError && (
        <p className="mt-3 text-sm text-err">{(health.error as Error).message}</p>
      )}
      {health.isSuccess && (
        <div className="mt-3 space-y-1 text-sm text-ok">
          <p>
            Status: <strong>{health.data.status}</strong>
          </p>
          {health.data.auth_mode != null && (
            <p className="text-ink-2">
              API auth: <strong>{health.data.auth_mode}</strong>
            </p>
          )}
        </div>
      )}
    </div>
  )
}
