import * as React from 'react'
import { PrismLogo } from '~/components/brand'

import { StartersPanel } from '~/components/chat/StartersPanel'
import type { ChatStartersPayload } from '~/hooks/useChatStartersQuery'

type EmptyConversationStateProps = {
  starters: ChatStartersPayload | undefined
  startersFetched: boolean
  setComposeDraft: React.Dispatch<React.SetStateAction<string>>
}

export function EmptyConversationState({
  starters,
  startersFetched,
  setComposeDraft,
}: EmptyConversationStateProps) {
  return (
    <div className="flex min-h-[min(56dvh,26rem)] w-full flex-col items-center justify-center px-4 py-8 sm:px-8 sm:py-12">
      <div className="w-full max-w-2xl space-y-8">
        <header className="text-center">
          <h2 className="text-xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50 sm:text-2xl">
            Start the conversation
          </h2>
          <p className="mx-auto mt-3 max-w-lg text-sm leading-relaxed text-neutral-600 dark:text-neutral-400">
            Use the composer below to send your first message. You can write freely or choose a
            suggestion—it only fills the input; nothing is sent until you press Send.
          </p>
        </header>

        {!startersFetched && <PrismLogo state="loading" size={16} className="mx-auto" />}

        {startersFetched && starters?.sections && starters.sections.length > 0 && (
          <div
            data-testid="chat-starters-suggested"
            className="rounded-2xl border border-neutral-200/90 bg-neutral-50/80 px-5 py-6 shadow-[0_1px_0_rgba(15,23,42,0.04)] dark:border-neutral-800 dark:bg-neutral-900/40 dark:shadow-none sm:px-8 sm:py-8"
          >
            <p className="mb-5 text-center text-[11px] font-semibold uppercase tracking-[0.12em] text-neutral-500 dark:text-neutral-500">
              Suggested prompts
            </p>
            <StartersPanel
              variant="featured"
              sections={starters.sections}
              setComposeDraft={setComposeDraft}
            />
          </div>
        )}
      </div>
    </div>
  )
}
