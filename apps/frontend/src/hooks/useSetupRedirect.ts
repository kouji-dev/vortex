import * as React from 'react'
import { useNavigate, useLocation } from '@tanstack/react-router'
import { getApiBase } from '~/lib/api-base'

/**
 * Polls /health once on mount. If the backend responds 503 (selfhosted, not yet set up),
 * redirects to /login (setup flow removed; handled by backend wizard).
 * Retries require user navigation (intentional — avoids hammering the backend on startup).
 */
export function useSetupRedirect(): void {
  const navigate = useNavigate()
  const location = useLocation()

  React.useEffect(() => {
    if (typeof window === 'undefined') return
    if (location.pathname === '/login') return

    const controller = new AbortController()
    const apiBase = getApiBase()

    fetch(`${apiBase}/health`, { signal: controller.signal })
      .then((res) => {
        if (res.status === 503) {
          // Backend not ready — send to login; no dedicated setup wizard in frontend.
          navigate({ to: '/login', replace: true })
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
