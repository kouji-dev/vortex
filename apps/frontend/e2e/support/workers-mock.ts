/**
 * Browser-level Workers (agentic tasks) mocks for E2E.
 *
 * Mocks task create/list and the agent run SSE stream at the browser via
 * `page.route()` — no real sandbox provisioning or agent-loop LLM.
 */
import type { Page, Route } from '@playwright/test'

export type WorkerEvent =
  | { event_type: 'agent_thought'; thought: string }
  | { event_type: 'tool_call'; tool: string; input: Record<string, unknown> }
  | { event_type: 'tool_result'; tool: string; output: Record<string, unknown> }
  | { event_type: 'final'; text: string }
  | { event_type: 'done' }

export interface InstallWorkersMockOpts {
  taskId?: string
  runId?: string
  prompt?: string
  /** Ordered SSE events for the run stream. Defaults to a canned thought→tool→final→done. */
  events?: WorkerEvent[]
}

/** Default agent run script: thought → tool_call → tool_result → thought → final → done. */
export function defaultWorkerEvents(): WorkerEvent[] {
  return [
    { event_type: 'agent_thought', thought: 'I should call fetch_url to retrieve a cat fact.' },
    { event_type: 'tool_call', tool: 'fetch_url', input: { url: 'https://cat-fact.example/today' } },
    { event_type: 'tool_result', tool: 'fetch_url', output: { status: 200, body: 'Cats sleep 16h/day.' } },
    { event_type: 'agent_thought', thought: 'Now I will summarise the result for the user.' },
    { event_type: 'final', text: 'Cats sleep about 16 hours per day.' },
    { event_type: 'done' },
  ]
}

/**
 * Route `**­/api/workers/tasks**` (POST create + GET list) and the run SSE stream.
 * Returns an async cleanup fn.
 */
export async function installWorkersMock(
  page: Page,
  opts: InstallWorkersMockOpts = {},
): Promise<() => Promise<void>> {
  const taskId = opts.taskId ?? 'task_suite_1'
  const runId = opts.runId ?? 'run_suite_1'
  const prompt = opts.prompt ?? 'fetch latest cat fact'
  const events = opts.events ?? defaultWorkerEvents()

  const tasksRoute = '**/api/workers/tasks**'
  const runStreamRoute = `**/api/workers/runs/${runId}/stream`

  const taskRecord = {
    id: taskId,
    run_id: runId,
    status: 'running',
    prompt,
    created_at: new Date().toISOString(),
  }

  await page.route(tasksRoute, async (route: Route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(taskRecord),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [taskRecord], total: 1 }),
    })
  })

  await page.route(runStreamRoute, async (route: Route) => {
    const body = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('')
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body })
  })

  return async () => {
    await page.unroute(tasksRoute).catch(() => undefined)
    await page.unroute(runStreamRoute).catch(() => undefined)
  }
}
