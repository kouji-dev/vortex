/**
 * Thin fetch client for the RAG management surface.
 *
 * No retries, no caching — that's React Query's job. All calls auth via the
 * shared bearer-from-MSAL header and surface non-2xx as thrown errors.
 */

import { getApiBase } from './api-base'
import { getAuthHeaders } from './authorizedFetch'
import type {
  AnalyticsOverview,
  EvalRecord,
  EvalRunOut,
  EvalTestSet,
  PlaygroundResponse,
  PlaygroundSession,
  PlaygroundSettings,
} from './rag-types'

async function ragFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${getApiBase()}${path}`, {
    ...init,
    headers: {
      'content-type': 'application/json',
      ...(await getAuthHeaders()),
      ...(init?.headers ?? {}),
    },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `${res.status} ${res.statusText}`)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

// ── evals ──────────────────────────────────────────────────────────────

export function listEvals(kbId: number): Promise<EvalTestSet[]> {
  return ragFetch(`/api/kbs/${kbId}/evals`)
}

export function createEval(
  kbId: number,
  body: { name: string; records: EvalRecord[]; judge_model?: string | null; judge_temperature?: number },
): Promise<EvalTestSet> {
  return ragFetch(`/api/kbs/${kbId}/evals`, { method: 'POST', body: JSON.stringify(body) })
}

export function getEval(kbId: number, evalId: string): Promise<EvalTestSet> {
  return ragFetch(`/api/kbs/${kbId}/evals/${evalId}`)
}

export function updateEval(
  kbId: number,
  evalId: string,
  body: { name: string; records: EvalRecord[]; judge_model?: string | null; judge_temperature?: number },
): Promise<EvalTestSet> {
  return ragFetch(`/api/kbs/${kbId}/evals/${evalId}`, { method: 'PATCH', body: JSON.stringify(body) })
}

export function deleteEval(kbId: number, evalId: string): Promise<void> {
  return ragFetch(`/api/kbs/${kbId}/evals/${evalId}`, { method: 'DELETE' })
}

export function runEval(
  kbId: number,
  evalId: string,
  body: { snapshot_id?: string | null; regression_threshold?: number; primary_metric?: string },
): Promise<EvalRunOut> {
  return ragFetch(`/api/kbs/${kbId}/evals/${evalId}/run`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function listRuns(kbId: number, evalId: string): Promise<EvalRunOut[]> {
  return ragFetch(`/api/kbs/${kbId}/evals/${evalId}/runs`)
}

// ── playground ─────────────────────────────────────────────────────────

export function runPlayground(
  kbId: number,
  body: { query: string; settings?: Partial<PlaygroundSettings>; save?: boolean },
): Promise<PlaygroundResponse> {
  return ragFetch(`/api/kbs/${kbId}/playground`, { method: 'POST', body: JSON.stringify(body) })
}

export function listPlaygroundSessions(kbId: number): Promise<PlaygroundSession[]> {
  return ragFetch(`/api/kbs/${kbId}/playground/sessions`)
}

export function getPlaygroundSession(kbId: number, sessionId: string): Promise<PlaygroundSession> {
  return ragFetch(`/api/kbs/${kbId}/playground/sessions/${sessionId}`)
}

export function deletePlaygroundSession(kbId: number, sessionId: string): Promise<void> {
  return ragFetch(`/api/kbs/${kbId}/playground/sessions/${sessionId}`, { method: 'DELETE' })
}

// ── analytics ──────────────────────────────────────────────────────────

export function getAnalytics(kbId: number, windowDays = 30): Promise<AnalyticsOverview> {
  return ragFetch(`/api/kbs/${kbId}/analytics?window_days=${windowDays}`)
}

export function submitFeedback(
  kbId: number,
  body: { rating: 'up' | 'down'; query_id?: string; chunk_id?: string; comment?: string },
): Promise<{ id: string }> {
  return ragFetch(`/api/kbs/${kbId}/feedback`, { method: 'POST', body: JSON.stringify(body) })
}
