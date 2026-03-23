import { MsalProvider } from '@azure/msal-react'
import { PublicClientApplication } from '@azure/msal-browser'
import * as React from 'react'

import { buildMsalConfig } from './msalConfig'
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

  return (
    <MsalProvider instance={instance}>
      <EntraAuthGate>{children}</EntraAuthGate>
    </MsalProvider>
  )
}
