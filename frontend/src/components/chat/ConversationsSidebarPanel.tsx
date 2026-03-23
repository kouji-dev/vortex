import { Link } from '@tanstack/react-router'

import type { Conversation } from '~/lib/chat-types'

type ConversationsSidebarPanelProps = {
  conversations: Conversation[] | undefined
  conversationsPending: boolean
  conversationsError: Error | null
  onNewConversation: () => void
}

export function ConversationsSidebarPanel({
  conversations,
  conversationsPending,
  conversationsError,
  onNewConversation,
}: ConversationsSidebarPanelProps) {
  return (
    <aside className="flex w-full shrink-0 flex-col gap-2 border-b border-neutral-200 p-3 dark:border-neutral-800 md:h-full md:min-h-0 md:w-64 md:max-w-64 md:overflow-y-auto md:border-b-0 md:border-r md:overscroll-contain">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold">Conversations</span>
        <button
          type="button"
          className="rounded bg-neutral-800 px-2 py-1 text-xs text-white dark:bg-neutral-200 dark:text-neutral-900"
          onClick={onNewConversation}
        >
          New
        </button>
      </div>
      {conversationsPending && <p className="text-sm text-neutral-500">Loading…</p>}
      {conversationsError && (
        <p className="text-sm text-red-600">{conversationsError.message}</p>
      )}
      <ul className="max-h-48 min-h-0 space-y-1 overflow-y-auto md:max-h-none">
        {(conversations ?? []).map((c) => (
          <li key={c.id}>
            <Link
              to="/chat/conversations/$id"
              params={{ id: String(c.id) }}
              className="block w-full truncate rounded px-2 py-1 text-left text-sm hover:bg-neutral-100 dark:hover:bg-neutral-900"
              activeProps={{
                className:
                  'bg-neutral-200 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-800',
              }}
            >
              <span
                className={
                  c.title
                    ? 'block truncate'
                    : 'block truncate text-neutral-600 dark:text-neutral-400'
                }
              >
                {c.title ?? 'New conversation'}
              </span>
              {c.assistant_id != null && (
                <span className="block truncate text-[10px] text-neutral-500">
                  Assistant #{c.assistant_id}
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </aside>
  )
}
