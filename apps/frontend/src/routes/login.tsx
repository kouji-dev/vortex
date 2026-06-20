import { createFileRoute, useNavigate, useSearch } from '@tanstack/react-router'
import { Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import * as React from 'react'
import { tokenStore } from '~/auth/tokenStore'
import { AuthShell } from '~/components/auth/AuthShell'
import { AuthFormCard } from '~/components/auth/AuthFormCard'
import { fetchAuthConfig } from '~/lib/admin-api'
import { socialButtons, showPasswordForm } from '~/lib/auth-strategies'
import { safeRedirect } from '~/lib/safe-redirect'

export const Route = createFileRoute('/login')({
  validateSearch: (search: Record<string, unknown>) => ({
    redirect: typeof search.redirect === 'string' ? search.redirect : undefined,
  }),
  component: LoginPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function LoginPage() {
  const navigate = useNavigate()
  const search = useSearch({ from: '/login' })
  const redirectTo = safeRedirect(search.redirect)

  const authConfig = useQuery({
    queryKey: ['auth-config'],
    queryFn: fetchAuthConfig,
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
  const cfg = authConfig.data
  const social = socialButtons(cfg, API_BASE)
  const passwordOn = showPasswordForm(cfg)
  const [email, setEmail] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error((data as { detail?: string }).detail ?? 'Login failed')
      }
      const data = await res.json() as { access_token: string; refresh_token: string }
      tokenStore.set(data.access_token, data.refresh_token)
      navigate({ to: redirectTo })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell heroTagline="Ask anything. Know everything.">
      <AuthFormCard
        eyebrow="Sign in"
        title="Welcome back."
        subtitle="Continue to your workspace."
        footer={
          <>
            New to Vortex?{' '}
            <Link to="/register" search={{ invite: undefined, email: undefined }} className="text-accent">
              Create an account
            </Link>
          </>
        }
      >
        {/* Social login buttons — only those the deployment enables */}
        {social.length > 0 && (
          <div className="auth-social-row" data-testid="auth-social-row" style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
            {social.map((s) => (
              <a
                key={s.provider}
                href={s.startUrl}
                className="sso-btn"
                data-testid={`auth-social-${s.provider}`}
                style={{ textDecoration: 'none', justifyContent: 'center' }}
              >
                Continue with {s.label}
              </a>
            ))}
          </div>
        )}

        {passwordOn && <div className="auth-divider">or use email</div>}

        {passwordOn && (
        <form onSubmit={handleSubmit} data-testid="auth-password-form">
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
          <div className="auth-field">
            <div className="auth-label">
              Password
              <span style={{ flex: 1 }} />
            </div>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input"
              placeholder="••••••••"
              autoComplete="current-password"
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
            {loading ? 'Signing in…' : 'Continue to workspace'}
          </button>
        </form>
        )}
      </AuthFormCard>
    </AuthShell>
  )
}
