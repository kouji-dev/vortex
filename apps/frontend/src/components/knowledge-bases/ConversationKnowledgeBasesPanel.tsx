import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import * as React from 'react'
import { PrismLogo } from '~/components/brand'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import {
  type KnowledgeBaseSummary,
  knowledgeBaseListFromResponse,
  parseKnowledgeBasesListJson,
} from '~/lib/knowledge-base-types'
import { queryKeys } from '~/lib/queryKeys'
import type { Conversation } from '~/lib/chat-types'

type ConversationKnowledgeBasesPanelProps = {
  conversationId: number
  conversation: Conversation | undefined
  disabled?: boolean
}

export function ConversationKnowledgeBasesPanel({
  conversationId,
  conversation,
  disabled,
}: ConversationKnowledgeBasesPanelProps) {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  const attachedKey = React.useMemo(
    () =>
      [...(conversation?.knowledge_base_ids ?? [])].sort((a, b) => a - b).join(','),
    [conversation?.knowledge_base_ids],
  )

  const listQ = useQuery({
    queryKey: queryKeys.knowledgeBases(),
    queryFn: async () => {
      const res = await fetch(`${apiBase}/api/knowledge-bases`, {
        headers: await getAuthHeaders(),
      })
      const text = await res.text()
      return knowledgeBaseListFromResponse(res, text, parseKnowledgeBasesListJson)
    },
  })

  const [draftIds, setDraftIds] = React.useState<number[]>([])
  React.useEffect(() => {
    setDraftIds([...(conversation?.knowledge_base_ids ?? [])])
  }, [conversationId, attachedKey])

  const saveMut = useMutation({
    mutationFn: async (ids: number[]) => {
      const res = await fetch(
        `${apiBase}/api/chat/conversations/${conversationId}/knowledge-bases`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            ...(await getAuthHeaders()),
          },
          body: JSON.stringify({ knowledge_base_ids: ids }),
        },
      )
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<Conversation>
    },
    onSuccess: (data) => {
      void qc.setQueryData(queryKeys.conversation(conversationId), data)
      void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
    },
  })

  const toggle = (id: number) => {
    setDraftIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  const sortedDraft = [...draftIds].sort((a, b) => a - b).join(',')
  const sortedAttached = attachedKey
  const dirty = sortedDraft !== sortedAttached

  return (
    <details className="rounded-lg border border-neutral-200 bg-neutral-50/90 px-3 py-2 text-sm dark:border-neutral-800 dark:bg-neutral-900/50">
      <summary className="cursor-pointer font-medium text-neutral-800 dark:text-neutral-200">
        Knowledge bases for this chat
      </summary>
      <div className="mt-2 space-y-2 text-neutral-600 dark:text-neutral-400">
        <p className="text-xs">
          RAG uses chunks from the bases you attach. Manage corpora under{' '}
          <Link
            to="/knowledge-bases"
            className="text-blue-600 underline dark:text-blue-400"
          >
            Knowledge bases
          </Link>
          .
        </p>
        {listQ.isPending && <PrismLogo state="loading" size={16} className="my-2" />}
        {listQ.isError && (
          <p className="text-xs text-red-600">{(listQ.error as Error).message}</p>
        )}
        {listQ.data && listQ.data.length === 0 && (
          <p className="text-xs">You have no knowledge bases yet.</p>
        )}
        {listQ.data && listQ.data.length > 0 && (
          <ul className="max-h-40 space-y-1.5 overflow-y-auto">
            {listQ.data.map((kb) => (
              <li key={kb.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id={`kb-${conversationId}-${kb.id}`}
                  className="rounded border-neutral-400"
                  checked={draftIds.includes(kb.id)}
                  disabled={disabled || saveMut.isPending}
                  onChange={() => toggle(kb.id)}
                />
                <label
                  htmlFor={`kb-${conversationId}-${kb.id}`}
                  className="min-w-0 flex-1 cursor-pointer truncate text-neutral-900 dark:text-neutral-100"
                >
                  {kb.name}
                </label>
              </li>
            ))}
          </ul>
        )}
        {saveMut.isError && (
          <p className="text-xs text-red-600">{(saveMut.error as Error).message}</p>
        )}
        <div className="flex flex-wrap gap-2 pt-1">
          <button
            type="button"
            disabled={disabled || saveMut.isPending || !dirty}
            className="rounded-md bg-neutral-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
            onClick={() => saveMut.mutate(draftIds)}
          >
            {saveMut.isPending ? 'Saving…' : 'Save attachment'}
          </button>
        </div>
      </div>
    </details>
  )
}
