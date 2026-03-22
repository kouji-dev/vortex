import type { PublicClientApplication } from '@azure/msal-browser'

let _client: PublicClientApplication | null = null

export function registerMsalClient(app: PublicClientApplication | null) {
  _client = app
}

export function getMsalInstance(): PublicClientApplication | null {
  return _client
}
