/**
 * Workers → Integrations (Git providers + issue trackers).
 *
 * Display-only stub for the v1 slice: shows the supported providers and a
 * "connect" placeholder. The actual CRUD lives behind /v1/workers/git-integrations
 * + /v1/workers/issue-tracker-integrations (server endpoints land later).
 */
import { createFileRoute } from '@tanstack/react-router'

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
  return (
    <div data-testid="workers-integrations">
      <h2 style={{ margin: '0 0 12px 0', fontSize: 14 }}>Git providers</h2>
      <div className="wk-cards" style={{ marginBottom: 16 }}>
        {GIT_PROVIDERS.map((p) => (
          <ProviderCard key={p.id} id={p.id} name={p.name} sub={p.sub} />
        ))}
      </div>

      <h2 style={{ margin: '0 0 12px 0', fontSize: 14 }}>Issue trackers</h2>
      <div className="wk-cards">
        {ISSUE_PROVIDERS.map((p) => (
          <ProviderCard key={p.id} id={p.id} name={p.name} sub={p.sub} />
        ))}
      </div>
    </div>
  )
}

function ProviderCard({ id, name, sub }: { id: string; name: string; sub: string }) {
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
        title="Configure via the API / settings yaml in v1"
      >
        Configure (CLI/API)
      </button>
    </div>
  )
}
