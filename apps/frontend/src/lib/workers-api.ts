// Workers HTTP client — mirrors server/api/src/ai_portal/workers/router.py.

import { authorizedFetch } from './authorizedFetch'
import { getApiBase } from './api-base'
import type {
  CreatePoolRequest,
  SubmitTaskRequest,
  WorkerApproval,
  WorkerArtifact,
  WorkerPool,
  WorkerRun,
  WorkerTask,
} from './workers-types'

function v1(path: string): string {
  return `${getApiBase()}/api${path}`
}

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: string | undefined
    try {
      const body = (await res.clone().json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // swallow
    }
    throw new Error(detail ? `HTTP ${res.status}: ${detail}` : `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

async function asOk(res: Response): Promise<void> {
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

// ── tasks ───────────────────────────────────────────────────────

export async function listTasks(opts?: {
  pool_id?: string | null
  status?: string | null
  limit?: number
}): Promise<WorkerTask[]> {
  const qs = new URLSearchParams()
  if (opts?.pool_id) qs.set('pool_id', opts.pool_id)
  if (opts?.status) qs.set('status', opts.status)
  if (opts?.limit) qs.set('limit', String(opts.limit))
  const url = v1(`/v1/workers/tasks${qs.toString() ? `?${qs}` : ''}`)
  return asJson(await authorizedFetch(url))
}

export async function getTask(id: string): Promise<WorkerTask> {
  return asJson(await authorizedFetch(v1(`/v1/workers/tasks/${id}`)))
}

export async function submitTask(body: SubmitTaskRequest): Promise<WorkerTask> {
  return asJson(
    await authorizedFetch(v1('/v1/workers/tasks'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

export async function cancelTask(id: string, reason?: string): Promise<WorkerTask> {
  return asJson(
    await authorizedFetch(v1(`/v1/workers/tasks/${id}/cancel`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    }),
  )
}

export async function pauseTask(id: string): Promise<WorkerTask> {
  return asJson(
    await authorizedFetch(v1(`/v1/workers/tasks/${id}/pause`), { method: 'POST' }),
  )
}

export async function resumeTask(id: string): Promise<WorkerTask> {
  return asJson(
    await authorizedFetch(v1(`/v1/workers/tasks/${id}/resume`), { method: 'POST' }),
  )
}

export async function sendMessage(id: string, text: string): Promise<void> {
  await asOk(
    await authorizedFetch(v1(`/v1/workers/tasks/${id}/message`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),
  )
}

export async function listRuns(id: string): Promise<WorkerRun[]> {
  return asJson(await authorizedFetch(v1(`/v1/workers/tasks/${id}/runs`)))
}

export async function listArtifacts(id: string): Promise<WorkerArtifact[]> {
  return asJson(await authorizedFetch(v1(`/v1/workers/tasks/${id}/artifacts`)))
}

export async function listApprovals(id: string): Promise<WorkerApproval[]> {
  return asJson(await authorizedFetch(v1(`/v1/workers/tasks/${id}/approvals`)))
}

export async function decideApproval(
  approval_id: string,
  decision: 'approve' | 'reject',
  reason?: string,
): Promise<WorkerApproval> {
  return asJson(
    await authorizedFetch(v1(`/v1/workers/approvals/${approval_id}/decide`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, reason }),
    }),
  )
}

// ── pools ───────────────────────────────────────────────────────

export async function listPools(): Promise<WorkerPool[]> {
  return asJson(await authorizedFetch(v1('/v1/workers/pools')))
}

export async function createPool(body: CreatePoolRequest): Promise<WorkerPool> {
  return asJson(
    await authorizedFetch(v1('/v1/workers/pools'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

export async function deletePool(id: string): Promise<void> {
  await asOk(await authorizedFetch(v1(`/v1/workers/pools/${id}`), { method: 'DELETE' }))
}

// ── SSE URL ─────────────────────────────────────────────────────

/** Build the SSE URL for a task's event stream. */
export function workerEventsUrl(taskId: string, afterTs?: string): string {
  const qs = afterTs ? `?after_ts=${encodeURIComponent(afterTs)}` : ''
  return v1(`/v1/workers/tasks/${taskId}/events${qs}`)
}
