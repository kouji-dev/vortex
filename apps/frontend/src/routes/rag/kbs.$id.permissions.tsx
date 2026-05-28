/**
 * Q6 — Permissions: ACL test + allow-list browser.
 *
 * Calls `POST /api/kbs/{id}/permission-test` (Phase H5) to evaluate what
 * documents a target user would see. Shows the count + sample doc ids.
 */
import { useMutation } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'

export const Route = createFileRoute('/rag/kbs/$id/permissions')({
  component: PermissionsPage,
})

type PermResult = {
  visible_count: number
  sample_doc_ids: string[]
  user_id?: string
}

function PermissionsPage() {
  const { id } = Route.useParams()
  const kbId = Number(id)
  const [userId, setUserId] = React.useState('')

  const m = useMutation({
    mutationFn: async (): Promise<PermResult> => {
      const res = await fetch(`${getApiBase()}/api/kbs/${kbId}/permission-test`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', ...(await getAuthHeaders()) },
        body: JSON.stringify({ user_id: userId }),
      })
      if (!res.ok) throw new Error(await res.text())
      return (await res.json()) as PermResult
    },
  })

  return (
    <div className="panel" data-testid="rag-permissions">
      <div className="panel-head">
        <span>Permission test</span>
      </div>
      <div className="panel-body" style={{ padding: 16, display: 'grid', gap: 10, maxWidth: 520 }}>
        <label style={{ fontSize: 12, display: 'grid', gap: 4 }}>
          Target user id
          <input
            className="rag-input"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            data-testid="rag-perm-userid"
          />
        </label>
        <button
          type="button"
          disabled={!userId.trim() || m.isPending}
          onClick={() => m.mutate()}
          data-testid="rag-perm-run"
        >
          {m.isPending ? 'Running…' : 'Test access'}
        </button>
        {m.error && (
          <p style={{ fontSize: 12, color: 'var(--red, #c43c3c)' }}>{(m.error as Error).message}</p>
        )}
        {m.data && (
          <div data-testid="rag-perm-result">
            <p style={{ fontSize: 13, margin: '8px 0 4px' }}>
              Visible documents: <strong>{m.data.visible_count}</strong>
            </p>
            <ul style={{ fontSize: 12, color: 'var(--ink-2)', paddingLeft: 16 }}>
              {(m.data.sample_doc_ids ?? []).slice(0, 10).map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
