// Workers domain types. Mirrors server/api/src/ai_portal/workers/schemas.py.

export type TaskStatus =
  | 'queued'
  | 'planning'
  | 'awaiting_plan_approval'
  | 'executing'
  | 'awaiting_pr_approval'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'paused'

export type TriggerSource =
  | 'chat'
  | 'rest_api'
  | 'jira_webhook'
  | 'linear_webhook'
  | 'github_issue_comment'
  | 'github_pr_comment'
  | 'schedule_cron'

export type EventKind =
  | 'agent_thought'
  | 'tool_call'
  | 'tool_result'
  | 'file_changed'
  | 'shell_output'
  | 'pr_created'
  | 'error'
  | 'phase_changed'
  | 'approval_requested'
  | 'user_message'
  | 'cost_update'
  | 'egress_blocked'
  | 'secret_blocked'

export interface WorkerTask {
  id: string
  org_id: string
  pool_id: string | null
  title: string
  description: string
  repo: string | null
  base_branch: string
  status: TaskStatus
  trigger_source: TriggerSource
  created_by: string | null
  created_at: string
  completed_at: string | null
}

export interface WorkerRun {
  id: string
  task_id: string
  attempt_no: number
  status: string
  started_at: string
  ended_at: string | null
  cost_cents: number
  error: string | null
}

export interface WorkerEvent {
  id: string
  kind: EventKind | string
  ts: string
  payload: Record<string, unknown>
}

export interface WorkerArtifact {
  id: string
  run_id: string
  kind: string
  ref: string
  meta: Record<string, unknown>
  created_at: string
}

export interface WorkerApproval {
  id: string
  task_id: string
  kind: 'plan' | 'pr' | 'budget'
  requested_at: string
  decided_at: string | null
  decided_by: string | null
  decision: 'approve' | 'reject' | null
  reason: string | null
  required_approvers: number
}

export interface WorkerPool {
  id: string
  org_id: string
  name: string
  template: string
  sandbox_provider: string
  repo_allow_list: string[]
  budget_cents_per_task: number
  default_model: string
  settings: Record<string, unknown>
  enabled: boolean
  created_at: string
}

export interface SubmitTaskRequest {
  title: string
  description?: string
  repo: string
  base_branch?: string
  pool_id?: string | null
  trigger_source?: TriggerSource
  extra?: Record<string, unknown>
}

export interface CreatePoolRequest {
  name: string
  template?: string
  sandbox_provider?: string
  repo_allow_list?: string[]
  budget_cents_per_task?: number
  default_model?: string
  settings?: Record<string, unknown>
  enabled?: boolean
}

// ── worker instances (worker-centric "a worker IS a task") ────────

export type WorkerState =
  | 'idle'
  | 'provisioning'
  | 'running'
  | 'error'
  | 'stopped'

export type WorkerMode = 'interactive' | 'autonomous'
export type WorkerRuntime = 'claude' | 'codex'
export type InstanceRunStatus = 'running' | 'error' | 'finished' | 'success'
export type WorkerMessageRole = 'user' | 'agent' | 'system'

export interface Worker {
  id: string
  org_id: string
  pool_id: string | null
  name: string
  state: WorkerState
  mode: WorkerMode
  model: string
  runtime: WorkerRuntime
  connector: Record<string, unknown>
  repo_url: string | null
  sandbox_id: string | null
  trigger_source: string | null
  created_by: string | null
  created_at: string
  last_active_at: string | null
}

export interface InstanceRun {
  id: string
  worker_id: string
  seq_no: number
  user_message: string
  status: InstanceRunStatus
  started_at: string
  ended_at: string | null
  cost_cents: number
  error: string | null
}

export interface RunChange {
  id: string
  run_id: string
  file_path: string
  change_kind: string
  additions: number
  deletions: number
  diff_ref: string
}

export interface WorkerChatMessage {
  id: string
  worker_id: string
  run_id: string | null
  role: WorkerMessageRole
  content: string
  ts: string
}

export interface SpawnWorkerRequest {
  name: string
  model: string
  mode?: WorkerMode
  runtime?: WorkerRuntime
  connector?: Record<string, unknown>
  repo_url?: string | null
  pool_id?: string | null
  skills?: string[]
  trigger_source?: string | null
  trigger_payload?: Record<string, unknown>
}
