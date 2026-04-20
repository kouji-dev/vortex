import * as React from 'react'

type EmptyConversationStateProps = {
  setComposeDraft: React.Dispatch<React.SetStateAction<string>>
}

export function EmptyConversationState({ setComposeDraft: _setComposeDraft }: EmptyConversationStateProps) {
  return (
    <div className="flex min-h-[min(56dvh,26rem)] w-full flex-col items-center justify-center px-4 py-8 sm:px-8 sm:py-12">
      <div className="w-full max-w-2xl space-y-8">
        <header className="text-center">
          <h2 className="text-xl font-semibold tracking-tight sm:text-2xl text-ink">
            Start the conversation
          </h2>
          <p className="mx-auto mt-3 max-w-lg text-sm leading-relaxed text-ink-2">
            Use the composer below to send your first message.
          </p>
        </header>
      </div>
    </div>
  )
}
