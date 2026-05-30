// Workers HTTP client — mirrors server/api/src/ai_portal/workers/router.py.

import { authorizedFetch } from './authorizedFetch'
import { getApiBase } from './api-base'
import type {
  CreatePoolRequest,
  InstanceRun,
  RunChange,
  SpawnWorkerRequest,
  SubmitTaskRequest,
  Worker,
  WorkerApproval,
  WorkerArtifact,
  WorkerChatMessage,
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

export async function updatePool(
  id: string,
  patch: Partial<CreatePoolRequest>,
): Promise<WorkerPool> {
  return asJson(
    await authorizedFetch(v1(`/v1/workers/pools/${id}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }),
  )
}

// ── replay ──────────────────────────────────────────────────────

export async function replayTask(id: string): Promise<WorkerTask> {
  return asJson(
    await authorizedFetch(v1(`/v1/workers/tasks/${id}/replay`), { method: 'POST' }),
  )
}

// ── SSE URL ─────────────────────────────────────────────────────

/** Build the SSE URL for a task's event stream. */
export function workerEventsUrl(taskId: string, afterTs?: string): string {
  const qs = afterTs ? `?after_ts=${encodeURIComponent(afterTs)}` : ''
  return v1(`/v1/workers/tasks/${taskId}/events${qs}`)
}

// ── worker instances (worker-centric "a worker IS a task") ───────

export async function listWorkers(opts?: {
  state?: string | null
  limit?: number
}): Promise<Worker[]> {
  const qs = new URLSearchParams()
  if (opts?.state) qs.set('state', opts.state)
  if (opts?.limit) qs.set('limit', String(opts.limit))
  const url = v1(`/v1/workers/instances${qs.toString() ? `?${qs}` : ''}`)
  return asJson(await authorizedFetch(url))
}

export async function getWorker(id: string): Promise<Worker> {
  return asJson(await authorizedFetch(v1(`/v1/workers/instances/${id}`)))
}

export async function spawnWorker(body: SpawnWorkerRequest): Promise<Worker> {
  return asJson(
    await authorizedFetch(v1('/v1/workers/instances'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

export async function stopWorker(id: string): Promise<Worker> {
  return asJson(
    await authorizedFetch(v1(`/v1/workers/instances/${id}/stop`), {
      method: 'POST',
    }),
  )
}

/** Send a user message to a worker — starts a new run. */
export async function messageWorker(id: string, text: string): Promise<InstanceRun> {
  return asJson(
    await authorizedFetch(v1(`/v1/workers/instances/${id}/message`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),
  )
}

export async function listWorkerRuns(id: string): Promise<InstanceRun[]> {
  return asJson(await authorizedFetch(v1(`/v1/workers/instances/${id}/runs`)))
}

export async function listWorkerMessages(id: string): Promise<WorkerChatMessage[]> {
  return asJson(
    await authorizedFetch(v1(`/v1/workers/instances/${id}/messages`)),
  )
}

export async function listRunChanges(runId: string): Promise<RunChange[]> {
  return asJson(await authorizedFetch(v1(`/v1/workers/runs/${runId}/changes`)))
}

export async function decidePermission(
  workerId: string,
  promptId: string,
  decision: 'allow' | 'deny',
  reason?: string,
): Promise<{ ok: boolean; delivered: boolean }> {
  return asJson(
    await authorizedFetch(
      v1(`/v1/workers/instances/${workerId}/permissions/${promptId}`),
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, reason }),
      },
    ),
  )
}

/** Build the SSE URL for a worker's agent stdio stream (STUB on backend). */
export function workerStreamUrl(workerId: string): string {
  return v1(`/v1/workers/instances/${workerId}/stream`)
}
