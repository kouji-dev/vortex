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
    <AuthShell heroTagline="Set up your workspace in minutes.">
      <AuthFormCard
        title={inviteToken ? 'Accept invite' : 'Create account'}
        subtitle={inviteToken ? undefined : 'Free while in beta. No credit card required.'}
        footer={
          <>
            Already have an account?{' '}
            <Link to="/login" className="text-accent">
              Sign in
            </Link>
          </>
        }
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {!inviteToken && (
            <div>
              <label className="mb-1.5 block text-sm font-medium text-ink-2">
                Email
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="textarea h-10 min-h-0 resize-none py-0 px-3 leading-[38px] text-ink bg-panel border-line"
                placeholder="you@example.com"
              />
            </div>
          )}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink-2">
              Password
            </label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="textarea h-10 min-h-0 resize-none py-0 px-3 leading-[38px] text-ink bg-panel border-line"
              placeholder="Min. 8 characters"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink-2">
              Confirm password
            </label>
            <input
              type="password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="textarea h-10 min-h-0 resize-none py-0 px-3 leading-[38px] text-ink bg-panel border-line"
              placeholder="••••••••"
            />
          </div>
          {error && (
            <p className="rounded bg-err/10 px-3 py-2 text-sm text-err">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary h-10 w-full justify-center text-sm disabled:opacity-50"
          >
            {loading ? 'Creating account…' : inviteToken ? 'Accept & sign in' : 'Create account'}
          </button>
        </form>
      </AuthFormCard>
    </AuthShell>
  )
}
