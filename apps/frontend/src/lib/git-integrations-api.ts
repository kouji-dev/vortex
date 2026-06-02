import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'

export type GitRepo = {
  id: string
  full_name: string
  default_branch: string
  enabled: boolean
}

export type GitIntegration = {
  id: string
  kind: string
  account_login: string | null
  scope: 'user' | 'org'
  auth_type: string
  enabled: boolean
  repos: GitRepo[]
}

export type ConnectGitIntegrationBody = {
  kind: 'github'
  scope: 'user' | 'org'
  token: string
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const apiBase = getApiBase()
  const res = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      ...(init.headers as Record<string, string> | undefined),
      ...(await getAuthHeaders()),
    },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res
}

export async function listGitIntegrations(): Promise<GitIntegration[]> {
  const res = await apiFetch('/v1/workers/git-integrations')
  return res.json() as Promise<GitIntegration[]>
}

export async function connectGitIntegration(body: ConnectGitIntegrationBody): Promise<GitIntegration> {
  const res = await apiFetch('/v1/workers/git-integrations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return res.json() as Promise<GitIntegration>
}

export async function deleteGitIntegration(id: string): Promise<void> {
  await apiFetch(`/v1/workers/git-integrations/${id}`, { method: 'DELETE' })
}

export async function setEnabledRepos(id: string, enabledFullNames: string[]): Promise<GitRepo[]> {
  const res = await apiFetch(`/v1/workers/git-integrations/${id}/repos`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled_full_names: enabledFullNames }),
  })
  return res.json() as Promise<GitRepo[]>
}
