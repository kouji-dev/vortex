import * as React from 'react'
import { useNavigate, useLocation } from '@tanstack/react-router'
import { getAuthMode } from '~/auth/msalConfig'
import { tokenStore } from '~/auth/tokenStore'

const UNPROTECTED = ['/login', '/register', '/setup']

/**
 * Redirects unauthenticated users to /login when VITE_AUTH_MODE=local.
 * No-ops in dev/entra modes (those have their own auth mechanisms).
 * Must be called inside a component that runs on every route (e.g. root layout).
 */
export function useAuthRedirect(): void {
  const navigate = useNavigate()
  const location = useLocation()

  React.useEffect(() => {
    if (typeof window === 'undefined') return
    if (getAuthMode() !== 'local') return
    if (UNPROTECTED.some((p) => location.pathname.startsWith(p))) return

    const token = tokenStore.getAccess()
    if (!token) {
      navigate({ to: '/login', replace: true })
    }
  }, [location.pathname, navigate])
}
