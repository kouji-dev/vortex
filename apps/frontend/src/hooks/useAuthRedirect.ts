import * as React from 'react'
import { useNavigate, useLocation } from '@tanstack/react-router'
import { tokenStore } from '~/auth/tokenStore'

const UNPROTECTED = ['/login', '/register', '/auth', '/invite']

/**
 * Redirects unauthenticated users to /login.
 * Skips auth routes (login, register, auth/callback, invite/*).
 * Must be called inside a component that runs on every route (e.g. root layout).
 */
export function useAuthRedirect(): void {
  const navigate = useNavigate()
  const location = useLocation()

  React.useEffect(() => {
    if (typeof window === 'undefined') return
    if (UNPROTECTED.some((p) => location.pathname.startsWith(p))) return

    const checkAuth = () => {
      const token = tokenStore.getAccess()
      if (!token) {
        navigate({ to: '/login', replace: true })
      }
    }

    checkAuth()

    window.addEventListener('storage', checkAuth)
    return () => window.removeEventListener('storage', checkAuth)
  }, [location.pathname, navigate])
}
