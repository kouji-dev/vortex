import { createFileRoute, useNavigate, useSearch } from '@tanstack/react-router'
import { Link } from '@tanstack/react-router'
import * as React from 'react'
import { tokenStore } from '~/auth/tokenStore'
import { AuthShell } from '~/components/auth/AuthShell'
import { AuthFormCard } from '~/components/auth/AuthFormCard'

export const Route = createFileRoute('/register')({
  validateSearch: (search: Record<string, unknown>) => ({
    invite: typeof search.invite === 'string' ? search.invite : undefined,
  }),
  component: RegisterPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function RegisterPage() {
  const navigate = useNavigate()
  const search = useSearch({ from: '/register' })
  const inviteToken = search.invite

  const [email, setEmail] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [confirm, setConfirm] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }
    setLoading(true)
    try {
      const endpoint = inviteToken ? '/auth/accept-invite' : '/auth/register'
      const body = inviteToken
        ? { token: inviteToken, password }
        : { email, password }

      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? 'Registration failed')
      }
      const data = await res.json()
      tokenStore.set(data.access_token, data.refresh_token)
      navigate({ to: '/' })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

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
        {!inviteToken && (
          <>
            <div className="auth-sso-row" style={{ marginBottom: 14 }}>
              <button type="button" className="sso-btn" disabled title="Microsoft Entra SSO">
                <svg width="16" height="16" viewBox="0 0 23 23">
                  <path fill="#f25022" d="M1 1h10v10H1z"/>
                  <path fill="#00a4ef" d="M1 12h10v10H1z"/>
                  <path fill="#7fba00" d="M12 1h10v10H12z"/>
                  <path fill="#ffb900" d="M12 12h10v10H12z"/>
                </svg>
                Sign up with Entra
              </button>
              <button type="button" className="sso-btn" disabled title="Google Workspace SSO">
                <svg width="16" height="16" viewBox="0 0 18 18">
                  <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.17-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"/>
                  <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.91-2.26c-.81.54-1.84.86-3.05.86-2.34 0-4.32-1.58-5.03-3.71H.96v2.33A9 9 0 0 0 9 18z"/>
                  <path fill="#FBBC05" d="M3.97 10.71A5.4 5.4 0 0 1 3.68 9c0-.6.1-1.17.29-1.71V4.96H.96A9 9 0 0 0 0 9c0 1.45.35 2.83.96 4.04l3.01-2.33z"/>
                  <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A9 9 0 0 0 9 0 9 9 0 0 0 .96 4.96L3.97 7.3C4.68 5.16 6.66 3.58 9 3.58z"/>
                </svg>
                Sign up with Google
              </button>
            </div>
            <div className="auth-divider">or use email</div>
          </>
        )}

        <form onSubmit={handleSubmit}>
          {!inviteToken && (
            <div className="auth-field">
              <div className="auth-label">Work email</div>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input"
                placeholder="you@company.com"
                autoComplete="email"
              />
            </div>
          )}
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
