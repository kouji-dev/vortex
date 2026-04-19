import { getAuthMode } from '~/auth/msalConfig'
import { useHealthQuery } from '~/hooks/useHealthQuery'
import { useMeQuery } from '~/hooks/useMeQuery'
import { ComingSoonCard } from '~/components/home/ComingSoonCard'
import { FeatureCard } from '~/components/home/FeatureCard'
import { SessionProfileCard } from '~/components/home/SessionProfileCard'
import { SystemStatusCard } from '~/components/home/SystemStatusCard'

function authModeMismatchHint(
  viteMode: 'dev' | 'entra' | 'local',
  apiDeploymentMode: 'dev' | 'saas' | 'selfhosted' | undefined,
  apiAuthMode: 'dev' | 'entra' | undefined,
): string | null {
  // local VITE mode is correct for saas/selfhosted backends
  if (viteMode === 'local') {
    if (apiDeploymentMode === 'dev') {
      return (
        'VITE_AUTH_MODE=local but the API is running in deployment_mode=dev. ' +
        'Set DEPLOYMENT_MODE=saas or selfhosted on the API, or set VITE_AUTH_MODE=dev.'
      )
    }
    return null
  }
  if (apiAuthMode == null || viteMode === apiAuthMode) return null
  if (viteMode === 'dev' && apiAuthMode === 'entra') {
    return (
      'This app is in dev auth (static bearer token), but the API reports auth_mode=entra. ' +
      'Set AUTH_MODE=dev in the API environment and restart, or switch the SPA to VITE_AUTH_MODE=entra.'
    )
  }
  return (
    'This app uses Entra (MSAL), but the API reports auth_mode=dev. ' +
    'Set AUTH_MODE=entra on the API and restart, or set VITE_AUTH_MODE=dev.'
  )
}

export function HomePage() {
  const health = useHealthQuery()
  const me = useMeQuery()
  const viteAuth = getAuthMode()
  const mismatch =
    health.isSuccess && health.data
      ? authModeMismatchHint(viteAuth, health.data.deployment_mode, health.data.auth_mode)
      : null

  return (
    <div className="page-enter mx-auto min-h-0 w-full max-w-4xl flex-1 space-y-8 overflow-y-auto overscroll-contain p-4 md:p-6">
      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-ink-3">
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
          <FeatureCard
            to="/memories"
            title="Memories"
            description="Persistent facts the assistant remembers about you—auto-learned or manually added."
          />
          <ComingSoonCard
            title="More features"
            description="Additional modules will appear here as the portal grows."
          />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-ink-3">
          Status
        </h2>
        {mismatch && (
          <div
            className="mb-4 rounded-lg border border-warn/40 bg-warn/10 p-4 text-sm text-ink"
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
