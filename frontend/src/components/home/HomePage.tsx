import { getAuthMode } from '~/auth/msalConfig'
import { useHealthQuery } from '~/hooks/useHealthQuery'
import { useMeQuery } from '~/hooks/useMeQuery'
import { ComingSoonCard } from '~/components/home/ComingSoonCard'
import { FeatureCard } from '~/components/home/FeatureCard'
import { SessionProfileCard } from '~/components/home/SessionProfileCard'
import { SystemStatusCard } from '~/components/home/SystemStatusCard'

function authModeMismatchHint(
  viteMode: 'dev' | 'entra',
  apiMode: 'dev' | 'entra' | undefined,
): string | null {
  if (apiMode == null || viteMode === apiMode) {
    return null
  }
  if (viteMode === 'dev' && apiMode === 'entra') {
    return (
      'This app is in dev auth (static bearer token), but the API reports auth_mode=entra. ' +
      'The API will try to parse your token as a Microsoft JWT and /api/me will fail. ' +
      'Set AUTH_MODE=dev in the API environment (check for AUTH_MODE=entra in your shell, IDE, or Docker), ' +
      'restart the API, or switch the SPA to VITE_AUTH_MODE=entra.'
    )
  }
  return (
    'This app uses Entra (MSAL), but the API reports auth_mode=dev. ' +
    'Set AUTH_MODE=entra on the API and restart, or set VITE_AUTH_MODE=dev with matching DEV_BEARER_TOKEN values.'
  )
}

export function HomePage() {
  const health = useHealthQuery()
  const me = useMeQuery()
  const viteAuth = getAuthMode()
  const mismatch =
    health.isSuccess && health.data
      ? authModeMismatchHint(viteAuth, health.data.auth_mode)
      : null

  return (
    <div className="mx-auto min-h-0 w-full max-w-4xl flex-1 space-y-8 overflow-y-auto overscroll-contain p-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-100">
          Home
        </h1>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          Pick a feature or review connection and account status.
        </p>
      </header>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-neutral-500">
          Features
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <FeatureCard
            to="/chat/conversations"
            title="Chat"
            description="Conversations with streaming replies, models from the catalog, and thread settings."
          />
          <FeatureCard
            to="/knowledge-bases"
            title="Knowledge bases"
            description="Corpora for RAG: connectors, uploads, and documents—attach bases to chats for grounded answers."
          />
          <ComingSoonCard
            title="More features"
            description="Additional modules will appear here as the portal grows."
          />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-neutral-500">
          Status
        </h2>
        {mismatch && (
          <div
            className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100"
            role="status"
          >
            {mismatch}
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <SystemStatusCard health={health} />
          <SessionProfileCard me={me} />
        </div>
      </section>
    </div>
  )
}
