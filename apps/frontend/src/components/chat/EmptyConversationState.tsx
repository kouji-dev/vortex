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
          <h2 className="text-xl font-semibold tracking-tight sm:text-2xl" style={{ color: 'var(--ink)' }}>
            Start the conversation
          </h2>
          <p className="mx-auto mt-3 max-w-lg text-sm leading-relaxed" style={{ color: 'var(--ink-2)' }}>
            Use the composer below to send your first message. You can write freely or choose a
            suggestion—it only fills the input; nothing is sent until you press Send.
          </p>
        </header>

        {!startersFetched && <PrismLogo state="loading" size={16} className="mx-auto" />}

        {startersFetched && starters?.sections && starters.sections.length > 0 && (
          <div
            data-testid="chat-starters-suggested"
            className="rounded-md px-5 py-6 sm:px-8 sm:py-8"
            style={{
              background: 'var(--panel)',
              border: '1px solid var(--line)',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <p
              className="mb-5 text-center font-mono text-[10px] font-semibold uppercase tracking-[0.08em]"
              style={{ color: 'var(--ink-3)' }}
            >
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
