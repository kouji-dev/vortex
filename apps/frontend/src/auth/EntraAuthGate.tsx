import { InteractionStatus } from '@azure/msal-browser'
import { useIsAuthenticated, useMsal } from '@azure/msal-react'
import * as React from 'react'

import { apiTokenRequest } from './msalConfig'

/**
 * When VITE_AUTH_MODE=entra, redirects unauthenticated users to Microsoft login.
 */
export function EntraAuthGate({ children }: { children: React.ReactNode }) {
  const { instance, inProgress } = useMsal()
  const isAuthenticated = useIsAuthenticated()

  React.useEffect(() => {
    if (inProgress !== InteractionStatus.None) {
      return
    }
    if (!isAuthenticated) {
      const { scopes } = apiTokenRequest()
      void instance.loginRedirect({
        scopes: scopes.length > 0 ? scopes : ['openid', 'profile'],
      })
    }
  }, [instance, inProgress, isAuthenticated])

  if (!isAuthenticated) {
    return (
      <div className="p-4 text-sm text-neutral-600 dark:text-neutral-400">
        Signing in…
      </div>
    )
  }

  return <>{children}</>
}
