/**
 * Workers → Integrations (Git providers + issue trackers).
 *
 * GitHub is fully interactive (connect/disconnect/repo picker).
 * All other providers show a disabled "Coming soon" button.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import { Select } from '~/components/ui/select'
import { GIT_INTEGRATIONS_QUERY_KEY, useGitIntegrationsQuery } from '~/hooks/useGitIntegrationsQuery'
import {
  connectGitIntegration,
  deleteGitIntegration,
  setEnabledRepos,
  type GitIntegration,
  type GitRepo,
} from '~/lib/git-integrations-api'

export const Route = createFileRoute('/workers/integrations')({
  component: IntegrationsPage,
})

const GIT_PROVIDERS = [
  { id: 'github', name: 'GitHub', sub: 'Org App or PAT' },
  { id: 'gitlab', name: 'GitLab', sub: 'self-hosted or cloud' },
  { id: 'bitbucket', name: 'Bitbucket', sub: 'cloud' },
  { id: 'gitea', name: 'Gitea', sub: 'self-hosted' },
  { id: 'azure_devops', name: 'Azure DevOps', sub: 'cloud + server' },
] as const

const ISSUE_PROVIDERS = [
  { id: 'jira_cloud', name: 'Jira Cloud', sub: 'webhook + label trigger' },
  { id: 'linear', name: 'Linear', sub: 'GraphQL webhook' },
  { id: 'github_issues', name: 'GitHub Issues', sub: 'comment /worker do this' },
  { id: 'gitlab_issues', name: 'GitLab Issues', sub: 'webhook' },
  { id: 'azure_boards', name: 'Azure Boards', sub: 'webhook' },
] as const

function IntegrationsPage() {
  const { data: integrations = [], isLoading } = useGitIntegrationsQuery()

  const githubIntegration = integrations.find((i) => i.kind === 'github') ?? null

  return (
    <div data-testid="workers-integrations">
      <h2 style={{ margin: '0 0 12px 0', fontSize: 14 }}>Git providers</h2>
      <div className="wk-cards" style={{ marginBottom: 16 }}>
        {GIT_PROVIDERS.map((p) => {
          if (p.id === 'github') {
            return (
              <GitHubCard
                key="github"
                integration={githubIntegration}
                loading={isLoading}
              />
            )
          }
          return (
            <ComingSoonCard key={p.id} id={p.id} name={p.name} sub={p.sub} />
          )
        })}
      </div>

      <h2 style={{ margin: '0 0 12px 0', fontSize: 14 }}>Issue trackers</h2>
      <div className="wk-cards">
        {ISSUE_PROVIDERS.map((p) => (
          <ComingSoonCard key={p.id} id={p.id} name={p.name} sub={p.sub} />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// GitHub card — interactive connect / manage
// ---------------------------------------------------------------------------

function GitHubCard({
  integration,
  loading,
}: {
  integration: GitIntegration | null
  loading: boolean
}) {
  const [showForm, setShowForm] = React.useState(false)

  return (
    <div
      className="wk-card"
      data-testid="wk-integration-github"
      style={{ gridColumn: integration ? '1 / -1' : undefined }}
    >
      <div className="wk-card-label">github</div>
      <div className="wk-card-value" style={{ fontSize: 14 }}>
        GitHub
      </div>
      <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 4 }}>Org App or PAT</div>

      {loading ? (
        <p style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 8 }}>Loading…</p>
      ) : integration ? (
        <ConnectedView integration={integration} />
      ) : showForm ? (
        <ConnectForm onCancel={() => setShowForm(false)} onConnected={() => setShowForm(false)} />
      ) : (
        <button
          className="btn btn-sm btn-primary"
          style={{ marginTop: 8 }}
          data-testid="wk-git-connect-github"
          onClick={() => setShowForm(true)}
        >
          Connect
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Connect form
// ---------------------------------------------------------------------------

function ConnectForm({
  onCancel,
  onConnected,
}: {
  onCancel: () => void
  onConnected: () => void
}) {
  const qc = useQueryClient()
  const [scope, setScope] = React.useState<'user' | 'org'>('user')
  const [token, setToken] = React.useState('')
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null)

  const connectMut = useMutation({
    mutationFn: () => connectGitIntegration({ kind: 'github', scope, token }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: GIT_INTEGRATIONS_QUERY_KEY })
      onConnected()
    },
    onError: (err: Error) => {
      // Try to extract a user-friendly message from the JSON error body
      let msg = err.message
      try {
        const parsed = JSON.parse(msg) as { detail?: string | Array<{ msg: string }> }
        if (typeof parsed.detail === 'string') msg = parsed.detail
        else if (Array.isArray(parsed.detail)) msg = parsed.detail.map((d) => d.msg).join(', ')
      } catch {
        // raw string — use as-is
      }
      setErrorMsg(msg)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!token.trim() || connectMut.isPending) return
    setErrorMsg(null)
    connectMut.mutate()
  }

  return (
    <form onSubmit={handleSubmit} style={{ marginTop: 12 }}>
      <div className="form-row" style={{ marginBottom: 8 }}>
        <label style={{ fontSize: 11, color: 'var(--ink-2)', display: 'block', marginBottom: 4 }}>
          Scope
        </label>
        <Select
          size="sm"
          inline
          value={scope}
          onChange={(e) => setScope(e.target.value as 'user' | 'org')}
          data-testid="wk-git-scope"
        >
          <option value="user">My account</option>
          <option value="org">Organization</option>
        </Select>
      </div>

      <div className="form-row" style={{ marginBottom: 8 }}>
        <label style={{ fontSize: 11, color: 'var(--ink-2)', display: 'block', marginBottom: 4 }}>
          Personal access token
        </label>
        <input
          className="input input-mono"
          type="password"
          data-testid="wk-git-token"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="ghp_…"
          autoComplete="off"
          required
          style={{ width: '100%' }}
        />
      </div>

      {errorMsg && (
        <p
          style={{ fontSize: 11, color: 'var(--err)', marginBottom: 8 }}
          role="alert"
        >
          {errorMsg}
        </p>
      )}

      <div style={{ display: 'flex', gap: 6 }}>
        <button
          type="submit"
          className="btn btn-sm btn-primary"
          data-testid="wk-git-connect-submit"
          disabled={!token.trim() || connectMut.isPending}
        >
          {connectMut.isPending ? 'Connecting…' : 'Connect'}
        </button>
        <button
          type="button"
          className="btn btn-sm"
          onClick={onCancel}
          disabled={connectMut.isPending}
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Connected view — shows account login + repo list + disconnect
// ---------------------------------------------------------------------------

function ConnectedView({ integration }: { integration: GitIntegration }) {
  const qc = useQueryClient()

  const disconnectMut = useMutation({
    mutationFn: () => deleteGitIntegration(integration.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: GIT_INTEGRATIONS_QUERY_KEY }),
  })

  const repoMut = useMutation({
    mutationFn: (fullNames: string[]) => setEnabledRepos(integration.id, fullNames),
    onSuccess: () => qc.invalidateQueries({ queryKey: GIT_INTEGRATIONS_QUERY_KEY }),
  })

  const toggleRepo = (repo: GitRepo) => {
    const current = integration.repos.filter((r) => r.enabled).map((r) => r.full_name)
    const next = repo.enabled
      ? current.filter((n) => n !== repo.full_name)
      : [...current, repo.full_name]
    repoMut.mutate(next)
  }

  return (
    <div style={{ marginTop: 10 }}>
      <p
        data-testid="wk-git-connected"
        style={{ fontSize: 12, color: 'var(--ink)', marginBottom: 8 }}
      >
        Connected as{' '}
        <strong>@{integration.account_login ?? 'unknown'}</strong>
        {' · '}
        <span style={{ color: 'var(--ink-3)' }}>{integration.scope}</span>
      </p>

      {integration.repos.length > 0 && (
        <div
          style={{
            border: '1px solid var(--line)',
            borderRadius: 4,
            marginBottom: 10,
            maxHeight: 200,
            overflowY: 'auto',
          }}
        >
          {integration.repos.map((repo) => (
            <label
              key={repo.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '5px 10px',
                fontSize: 12,
                borderBottom: '1px solid var(--line)',
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={repo.enabled}
                onChange={() => toggleRepo(repo)}
                disabled={repoMut.isPending}
                data-testid={`wk-git-repo-${repo.full_name.replace('/', '-')}`}
              />
              <span className="mono" style={{ color: 'var(--ink)' }}>
                {repo.full_name}
              </span>
              <span style={{ fontSize: 10, color: 'var(--ink-3)', marginLeft: 'auto' }}>
                {repo.default_branch}
              </span>
            </label>
          ))}
        </div>
      )}

      {integration.repos.length === 0 && (
        <p style={{ fontSize: 11, color: 'var(--ink-3)', marginBottom: 8 }}>
          No repositories found. Add repos to your PAT scope and reconnect.
        </p>
      )}

      <button
        className="btn btn-sm"
        style={{ color: 'var(--err)', borderColor: 'var(--err)' }}
        onClick={() => disconnectMut.mutate()}
        disabled={disconnectMut.isPending}
        data-testid="wk-git-disconnect"
      >
        {disconnectMut.isPending ? 'Disconnecting…' : 'Disconnect'}
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Generic coming-soon card for all other providers
// ---------------------------------------------------------------------------

function ComingSoonCard({ id, name, sub }: { id: string; name: string; sub: string }) {
  return (
    <div className="wk-card" data-testid={`wk-integration-${id}`}>
      <div className="wk-card-label">{id}</div>
      <div className="wk-card-value" style={{ fontSize: 14 }}>
        {name}
      </div>
      <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 4 }}>{sub}</div>
      <button
        className="btn btn-sm"
        style={{ marginTop: 8 }}
        disabled
        title="Coming soon"
      >
        Coming soon
      </button>
    </div>
  )
}
