import * as React from 'react'
import { useNavigate, useLocation } from '@tanstack/react-router'
import { getAuthMode } from '~/auth/msalConfig'
import { getApiBase } from '~/lib/api-base'

/**
 * Polls /health once on mount. If the backend responds 503 (selfhosted, not yet set up),
 * redirects to /setup. No-ops in dev/entra modes.
 * Retries require user navigation (intentional — avoids hammering the backend on startup).
 */
export function useSetupRedirect(): void {
  const navigate = useNavigate()
  const location = useLocation()

  React.useEffect(() => {
    if (typeof window === 'undefined') return
    if (getAuthMode() !== 'local') return
    if (location.pathname === '/setup') return

    const controller = new AbortController()
    const apiBase = getApiBase()

    fetch(`${apiBase}/health`, { signal: controller.signal })
      .then((res) => {
        if (res.status === 503) {
          navigate({ to: '/setup', replace: true })
        }
      })
      .catch((err) => {
        if ((err as { name?: string }).name !== 'AbortError') {
          // network error — don't redirect, let the app show error state
        }
      })

    return () => controller.abort()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // run once on mount only
}
