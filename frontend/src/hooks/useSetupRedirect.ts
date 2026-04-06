import * as React from 'react'
import { useNavigate, useLocation } from '@tanstack/react-router'
import { getAuthMode } from '~/auth/msalConfig'
import { getApiBase } from '~/lib/api-base'

/**
 * Polls /health once on mount. If the backend responds 503 (selfhosted, not yet set up),
 * redirects to /setup. No-ops in dev/entra modes.
 */
export function useSetupRedirect(): void {
  const navigate = useNavigate()
  const location = useLocation()

  React.useEffect(() => {
    if (typeof window === 'undefined') return
    if (getAuthMode() !== 'local') return
    if (location.pathname === '/setup') return

    const apiBase = getApiBase()
    fetch(`${apiBase}/health`).then((res) => {
      if (res.status === 503) {
        navigate({ to: '/setup', replace: true })
      }
    }).catch(() => {
      // network error — don't redirect, let the app show error state
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // run once on mount only
}
