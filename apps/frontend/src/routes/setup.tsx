import { createFileRoute, useNavigate } from '@tanstack/react-router'
import * as React from 'react'
import { tokenStore } from '~/auth/tokenStore'
import { AuthShell } from '~/components/auth/AuthShell'
import { AuthFormCard } from '~/components/auth/AuthFormCard'

export const Route = createFileRoute('/setup')({
  component: SetupPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function SetupPage() {
  const navigate = useNavigate()
  const [orgName, setOrgName] = React.useState('')
  const [email, setEmail] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ org_name: orgName, admin_email: email, admin_password: password }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? 'Setup failed')
      }
      // Auto-login after setup
      const loginRes = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (loginRes.ok) {
        const tokens = await loginRes.json()
        tokenStore.set(tokens.access_token, tokens.refresh_token)
      }
      navigate({ to: '/' })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Setup failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell heroTagline="First run — bootstrap your org.">
      <AuthFormCard
        title="Set up AI Portal"
        subtitle="Create your organization and admin account to get started."
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink-2">
              Organization name
            </label>
            <input
              type="text"
              required
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              className="textarea h-10 min-h-0 resize-none py-0 px-3 leading-[38px] text-ink bg-panel border-line"
              placeholder="Acme Corp"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink-2">
              Admin email
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="textarea h-10 min-h-0 resize-none py-0 px-3 leading-[38px] text-ink bg-panel border-line"
              placeholder="admin@example.com"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink-2">
              Admin password
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
            {loading ? 'Setting up…' : 'Initialize instance'}
          </button>
        </form>
      </AuthFormCard>
    </AuthShell>
  )
}
