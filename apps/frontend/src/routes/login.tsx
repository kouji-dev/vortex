import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { Link } from '@tanstack/react-router'
import * as React from 'react'
import { tokenStore } from '~/auth/tokenStore'
import { AuthShell } from '~/components/auth/AuthShell'
import { AuthFormCard } from '~/components/auth/AuthFormCard'

export const Route = createFileRoute('/login')({
  component: LoginPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function LoginPage() {
  const navigate = useNavigate()
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
        throw new Error(data.detail ?? 'Login failed')
      }
      const data = await res.json()
      tokenStore.set(data.access_token, data.refresh_token)
      navigate({ to: '/' })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell heroTagline="Ask anything. Know everything.">
      <AuthFormCard
        title="Sign in"
        subtitle="Use your work email."
        footer={
          <>
            New here?{' '}
            <Link to="/register" search={{ invite: undefined }} className="text-accent">
              Create an account
            </Link>
          </>
        }
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
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
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink-2">
              Password
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
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
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </AuthFormCard>
    </AuthShell>
  )
}
