import { MsalProvider } from '@azure/msal-react'
import { PublicClientApplication } from '@azure/msal-browser'
import * as React from 'react'

import { buildMsalConfig, getEntraApiScope } from './msalConfig'
import { EntraAuthGate } from './EntraAuthGate'
import { registerMsalClient } from './msalInstance'

/**
 * Initializes MSAL on the client, handles redirect, and gates routes behind Entra sign-in.
 */
export function EntraRoot({ children }: { children: React.ReactNode }) {
  const [instance, setInstance] = React.useState<PublicClientApplication | null>(
    null,
  )

  React.useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }
    const app = new PublicClientApplication(buildMsalConfig())
    registerMsalClient(app)
    void app
      .initialize()
      .then(() => {
        app.setActiveAccount(app.getAllAccounts()[0] ?? null)
        return app.handleRedirectPromise()
      })
      .then(() => {
        setInstance(app)
      })
      .catch(() => {
        setInstance(app)
      })
    // Do not registerMsalClient(null) here: React Strict Mode remounts effects and
    // clearing the singleton races with in-flight authorizedFetch / React Query.
    return () => {}
  }, [])

  if (!instance) {
    return (
      <div className="p-4 text-sm text-neutral-600 dark:text-neutral-400">
        Loading authentication…
      </div>
    )
  }

  if (!getEntraApiScope()) {
    return (
      <div className="p-4 text-sm text-red-700 dark:text-red-300">
        <p className="font-medium">Entra: missing API scope</p>
        <p className="mt-2 text-neutral-700 dark:text-neutral-300">
          Set{' '}
          <code className="rounded bg-neutral-200 px-1 dark:bg-neutral-800">
            VITE_ENTRA_API_SCOPE
          </code>{' '}
          in{' '}
          <code className="rounded bg-neutral-200 px-1 dark:bg-neutral-800">
            frontend/.env
          </code>{' '}
          to the delegated scope you exposed on the API app (for example{' '}
          <code className="rounded bg-neutral-200 px-1 dark:bg-neutral-800">
            api://&lt;api-app-id&gt;/access_as_user
          </code>
          ). Without it, MSAL can issue a token whose audience is the SPA app, and{' '}
          <code className="rounded bg-neutral-200 px-1 dark:bg-neutral-800">/api/me</code>{' '}
          returns 401.
        </p>
      </div>
    )
  }

  return (
    <MsalProvider instance={instance}>
      <EntraAuthGate>{children}</EntraAuthGate>
    </MsalProvider>
  )
}
