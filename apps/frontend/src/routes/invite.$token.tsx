import { createFileRoute, useNavigate } from '@tanstack/react-router'
import * as React from 'react'
import { tokenStore } from '~/auth/tokenStore'
import { authorizedFetch } from '~/lib/authorizedFetch'
import { AuthShell } from '~/components/auth/AuthShell'
import { AuthFormCard } from '~/components/auth/AuthFormCard'

export const Route = createFileRoute('/invite/$token')({
  component: InviteAcceptPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

/**
 * Invite-accept landing page.
 *
 * Email link: /invite/<token>
 *
 * Flow:
 *   - If not authenticated → redirect to /login?redirect=/invite/<token>
 *   - If authenticated → POST /auth/invites/<token>/accept → redirect to /
 */
function InviteAcceptPage() {
  const { token } = Route.useParams()
  const navigate = useNavigate()
  const [status, setStatus] = React.useState<'idle' | 'accepting' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (typeof window === 'undefined') return

    const accessToken = tokenStore.getAccess()
    if (!accessToken) {
      // Not logged in — redirect to login with this page as the return destination.
      void navigate({ to: '/login', search: { redirect: `/invite/${token}` }, replace: true })
      return
    }

    // Authenticated — accept the invite.
    setStatus('accepting')

    authorizedFetch(`${API_BASE}/api/v1/auth/invites/${token}/accept`, { method: 'POST' })
      .then(async (res) => {
        if (res.status === 409) {
          // Already accepted — just redirect to home.
          void navigate({ to: '/', replace: true })
          return
        }
        if (!res.ok) {
          const data = await res.json().catch(() => ({}))
          throw new Error(
            (data as { detail?: string }).detail ?? `Server error ${res.status}`,
          )
        }
        // Success — land in the org home.
        void navigate({ to: '/', replace: true })
      })
      .catch((err: unknown) => {
        setStatus('error')
        setErrorMsg(err instanceof Error ? err.message : 'Failed to accept invite')
      })
  }, [token, navigate])

  if (status === 'error') {
    return (
      <AuthShell heroTagline="Join your workspace.">
        <AuthFormCard title="Invite error" subtitle="Could not accept this invite.">
          <p className="auth-error">{errorMsg}</p>
          <div className="mt-4 flex gap-3">
            <a href="/login" className="btn btn-primary btn-full" style={{ textAlign: 'center' }}>
              Sign in with a different account
            </a>
          </div>
        </AuthFormCard>
      </AuthShell>
    )
  }

  return (
    <AuthShell heroTagline="Join your workspace.">
      <AuthFormCard title="Accepting invite…" subtitle="Please wait while we set up your access.">
        <div className="flex items-center justify-center py-6">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        </div>
      </AuthFormCard>
    </AuthShell>
  )
}
