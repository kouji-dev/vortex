import { InteractionRequiredAuthError } from '@azure/msal-browser'

import { apiTokenRequest, getAuthMode } from '~/auth/msalConfig'
import { getMsalInstance } from '~/auth/msalInstance'

export async function getAuthHeaders(): Promise<HeadersInit> {
  const mode = getAuthMode()
  if (mode !== 'entra') {
    const t =
      import.meta.env.VITE_DEV_BEARER_TOKEN ??
      import.meta.env.VITE_DEV_TOKEN ??
      'devtoken'
    return { Authorization: `Bearer ${t}` }
  }

  const msal = getMsalInstance()
  if (!msal) {
    return {}
  }
  const account = msal.getActiveAccount() ?? msal.getAllAccounts()[0]
  if (!account) {
    return {}
  }
  try {
    const result = await msal.acquireTokenSilent({
      ...apiTokenRequest(),
      account,
    })
    return { Authorization: `Bearer ${result.accessToken}` }
  } catch (e) {
    if (e instanceof InteractionRequiredAuthError) {
      await msal.acquireTokenRedirect({
        ...apiTokenRequest(),
        account,
      })
    }
    throw e
  }
}

export async function authorizedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers)
  const auth = await getAuthHeaders()
  for (const [k, v] of Object.entries(auth)) {
    headers.set(k, v)
  }
  return fetch(input, { ...init, headers })
}
