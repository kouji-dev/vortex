import { createFileRoute, useNavigate, useSearch } from '@tanstack/react-router'
import { Link } from '@tanstack/react-router'
import * as React from 'react'
import { tokenStore } from '~/auth/tokenStore'
import { authorizedFetch } from '~/lib/authorizedFetch'
import { AuthShell } from '~/components/auth/AuthShell'
import { AuthFormCard } from '~/components/auth/AuthFormCard'

export const Route = createFileRoute('/register')({
  validateSearch: (search: Record<string, unknown>) => ({
    invite: typeof search.invite === 'string' ? search.invite : undefined,
    email: typeof search.email === 'string' ? search.email : undefined,
  }),
  component: RegisterPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function RegisterPage() {
  const navigate = useNavigate()
  const search = useSearch({ from: '/register' })
  const inviteToken = search.invite
  // Pre-populate email from query param (set when invite link carries the recipient email).
  const prefillEmail = search.email ?? ''

  const [email, setEmail] = React.useState(prefillEmail)
  const [password, setPassword] = React.useState('')
  const [confirm, setConfirm] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(false)

  // Keep email in sync if the prefill email arrives after first render.
  React.useEffect(() => {
    if (prefillEmail) setEmail(prefillEmail)
  }, [prefillEmail])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }
    setLoading(true)
    try {
      if (inviteToken) {
        // Invite flow: register the new user → store tokens → accept invite (authenticated).
        const regRes = await fetch(`${API_BASE}/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        })
        if (!regRes.ok) {
          const data = await regRes.json().catch(() => ({}))
          throw new Error((data as { detail?: string }).detail ?? 'Registration failed')
        }
        const regData = (await regRes.json()) as { access_token: string; refresh_token: string }
        tokenStore.set(regData.access_token, regData.refresh_token)

        // Accept the invite as the newly authenticated user.
        const acceptRes = await authorizedFetch(
          `${API_BASE}/auth/invites/${inviteToken}/accept`,
          { method: 'POST' },
        )
        if (!acceptRes.ok && acceptRes.status !== 409) {
          // 409 = already accepted — treat as success.
          const data = await acceptRes.json().catch(() => ({}))
          throw new Error((data as { detail?: string }).detail ?? 'Failed to accept invite')
        }
      } else {
        // Standard registration flow.
        const res = await fetch(`${API_BASE}/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        })
        if (!res.ok) {
          const data = await res.json().catch(() => ({}))
          throw new Error((data as { detail?: string }).detail ?? 'Registration failed')
        }
        const data = (await res.json()) as { access_token: string; refresh_token: string }
        tokenStore.set(data.access_token, data.refresh_token)
      }

      void navigate({ to: '/' })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  // Whether the email field should be locked (invite with known email).
  const emailLocked = inviteToken !== undefined && prefillEmail !== ''

  return (
    <AuthShell heroTagline="Ask anything. Know everything.">
      <AuthFormCard
        eyebrow={inviteToken ? 'Accept invite' : 'Create account'}
        title={inviteToken ? 'Join your workspace.' : 'Start your workspace.'}
        subtitle={inviteToken ? undefined : 'Free while in beta. No credit card required.'}
        footer={
          <>
            Already have an account?{' '}
            <Link to="/login" search={{ redirect: undefined }} className="text-accent">
              Sign in
            </Link>
          </>
        }
      >
        <form onSubmit={handleSubmit}>
          {/* Email field: always shown. In the invite flow it may be pre-filled
              and locked when the invite link encodes the recipient's address. */}
          <div className="auth-field">
            <div className="auth-label">Work email</div>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => !emailLocked && setEmail(e.target.value)}
              className="input"
              placeholder="you@company.com"
              autoComplete="email"
              readOnly={emailLocked}
              style={emailLocked ? { opacity: 0.6, cursor: 'default' } : undefined}
            />
          </div>
          <div className="auth-field">
            <div className="auth-label">Password</div>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input"
              placeholder="Min. 8 characters"
              autoComplete="new-password"
            />
          </div>
          <div className="auth-field">
            <div className="auth-label">Confirm password</div>
            <input
              type="password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="input"
              placeholder="••••••••"
              autoComplete="new-password"
            />
          </div>

          {error && (
            <p className="auth-error">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary btn-full"
            style={{ marginTop: 8 }}
          >
            {loading ? 'Creating account…' : inviteToken ? 'Accept & sign in' : 'Create account'}
          </button>
        </form>
      </AuthFormCard>
    </AuthShell>
  )
}
