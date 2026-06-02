import { useQuery } from '@tanstack/react-query'

import { listGitIntegrations, type GitIntegration } from '~/lib/git-integrations-api'

export const GIT_INTEGRATIONS_QUERY_KEY = ['workers', 'git-integrations'] as const

export function useGitIntegrationsQuery() {
  return useQuery<GitIntegration[]>({
    queryKey: GIT_INTEGRATIONS_QUERY_KEY,
    queryFn: listGitIntegrations,
  })
}
