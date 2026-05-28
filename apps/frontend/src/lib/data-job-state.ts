/**
 * Pure state helpers for GDPR export/delete jobs.
 */
import type { DataDeleteJob, DataExportJob, DataJobStatus } from './admin-types'

export type JobStateClass = 'pending' | 'running' | 'completed' | 'failed' | 'unknown'

export function jobStateClass(status: string): JobStateClass {
  switch (status) {
    case 'pending':
    case 'running':
    case 'completed':
    case 'failed':
      return status as JobStateClass
    default:
      return 'unknown'
  }
}

export function isTerminal(status: string): boolean {
  return status === 'completed' || status === 'failed'
}

/** Format scope payload for the deletion confirmation modal. */
export function describeDeleteScope(scope: Record<string, unknown>): string {
  const subject = scope.subject
  if (subject === 'org') return 'all data in this organisation'
  if (subject === 'user') {
    const id = scope.user_id
    return `data for user ${id ?? '(unknown)'}`
  }
  return `scope ${JSON.stringify(scope)}`
}

/** Build the confirmation text the admin must type verbatim. */
export const DELETE_CONFIRMATION_PHRASE = 'delete my data'

export function deleteConfirmed(typed: string): boolean {
  return typed.trim().toLowerCase() === DELETE_CONFIRMATION_PHRASE
}

export interface JobSummary {
  id: string
  status: DataJobStatus | string
  requestedAt: string
  completedAt: string | null
  resultUrl?: string | null
  scopeLabel?: string
}

export function summarizeExport(job: DataExportJob): JobSummary {
  return {
    id: job.id,
    status: job.status,
    requestedAt: job.requested_at,
    completedAt: job.completed_at,
    resultUrl: job.result_url,
  }
}

export function summarizeDelete(job: DataDeleteJob): JobSummary {
  return {
    id: job.id,
    status: job.status,
    requestedAt: job.requested_at,
    completedAt: job.completed_at,
    scopeLabel: describeDeleteScope(job.scope_json),
  }
}
