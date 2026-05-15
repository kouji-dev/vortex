import * as React from 'react'
import { Copy } from 'lucide-react'
import { PrismLogo } from '~/components/brand'
import { ProcessBlock } from '~/components/chat/ProcessBlock'
import { UserMessageItem } from './UserMessageItem'
import { AssistantTextItem } from './AssistantTextItem'
import { LlmCallBadge } from './LlmCallBadge'
import type { ThreadItem } from '~/lib/chat-types'

type Props = {
  turnId: string
  items: ThreadItem[]
  isStreaming?: boolean
  onSetActive: (item: ThreadItem) => void
  userInitials: string
  userDisplayName: string
  onRegenerate?: (turnId: string) => void
  regenerateDisabled?: boolean
  isLastTurn?: boolean
}

export function TurnGroup({
  turnId,
  items,
  isStreaming,
  onSetActive,
  userInitials,
  userDisplayName,
  onRegenerate,
  regenerateDisabled,
  isLastTurn,
}: Props) {
  const userItem = items.find((i) => i.kind === 'user_message') as
    | (ThreadItem & { kind: 'user_message' })
    | undefined
  const assistantItems = items.filter(
    (i) => i.kind !== 'user_message' && i.kind !== 'turn_end',
  )

  const textItems = assistantItems.filter(
    (i) => i.kind === 'assistant_text',
  ) as (ThreadItem & { kind: 'assistant_text' })[]
  // Everything that goes inside the collapsed Process block — thinking,
  // memory pills, tool calls, server tool uses, and citations — kept in
  // chronological (id) order so the timeline reads top→bottom.
  const processItems = assistantItems
    .filter(
      (i) =>
        i.kind === 'thinking' ||
        i.kind === 'memory_pill' ||
        i.kind === 'tool_call' ||
        i.kind === 'server_tool_use' ||
        i.kind === 'kb_search' ||
        i.kind === 'citation',
    )
    .slice()
    .sort((a, b) => a.id - b.id) as Parameters<typeof ProcessBlock>[0]['items']
  const processIsStreaming =
    isStreaming && processItems.some((i) => i.status === 'streaming')
  const llmItems = (assistantItems.filter((i) => i.kind === 'llm_call') as
    (ThreadItem & { kind: 'llm_call' })[]).slice().sort((a, b) => a.id - b.id)
  const errorItem = assistantItems.find((i) => i.kind === 'error') as
    | (ThreadItem & { kind: 'error' })
    | undefined

  const latestText = textItems.at(-1)
  const combinedAssistantText = textItems.map((t) => t.data.text).filter(Boolean).join('\n\n')
  const hasAssistantContent = assistantItems.length > 0

  return (
    <React.Fragment key={turnId}>
      {userItem && (
        <li
          key={`${turnId}-user`}
          data-testid="chat-message-user"
          data-turn-id={turnId}
          className="msg msg-user"
          onClick={() => onSetActive(userItem)}
        >
          <UserMessageItem
            item={userItem}
            userInitials={userInitials}
            displayName={userDisplayName}
          />
          <div className="msg-actions">
            <button
              type="button"
              className="btn btn-sm"
              aria-label="Copy message"
              onClick={(e) => {
                e.stopPropagation()
                void navigator.clipboard.writeText(userItem.data.text ?? '').catch(() => {})
              }}
            >
              <Copy className="size-3.5" strokeWidth={2} />
              <span>Copy</span>
            </button>
          </div>
        </li>
      )}

      {(hasAssistantContent || isStreaming) && (
        <li
          key={`${turnId}-asst`}
          data-testid="chat-message-assistant"
          data-turn-id={turnId}
          className="msg msg-asst"
          onClick={() => {
            const lastLlm = llmItems.at(-1)
            if (lastLlm) onSetActive(lastLlm)
            else if (latestText) onSetActive(latestText)
          }}
        >
          <header className="msg-head">
            <span className="avatar-sm avatar-asst mono">VX</span>
            <span className="who-name">Assistant</span>
          </header>

          {processItems.length > 0 && (
            <div className="mb-2">
              <ProcessBlock
                items={processItems}
                isStreaming={processIsStreaming}
                defaultOpen={processIsStreaming}
              />
            </div>
          )}

          {textItems.map((t, idx) => {
            const isLastText = idx === textItems.length - 1
            return (
              <AssistantTextItem
                key={t.id}
                item={t}
                streaming={isLastText && isStreaming && t.status === 'streaming'}
              />
            )
          })}

          {errorItem && (
            <div className="msg-body md text-red-800 dark:text-red-200">
              {errorItem.data.message || 'Error'}
            </div>
          )}

          {!isStreaming && llmItems.length > 0 && (
            <div className="mt-1 flex flex-col gap-0.5">
              {llmItems.map((it) => (
                <LlmCallBadge
                  key={it.id}
                  item={it}
                  iterationLabel={llmItems.length > 1 ? `iter ${(it.data as { iteration_index: number }).iteration_index}` : null}
                />
              ))}
            </div>
          )}

          {isStreaming && (
            <div className="mt-2 flex items-center gap-2">
              <PrismLogo state="streaming" size={20} />
            </div>
          )}

          {!isStreaming && (
            <div className="msg-actions">
              <button
                type="button"
                className="btn btn-sm"
                aria-label="Copy message"
                disabled={!combinedAssistantText}
                onClick={() => {
                  if (!combinedAssistantText) return
                  void navigator.clipboard.writeText(combinedAssistantText).catch(() => {})
                }}
              >
                <Copy className="size-3.5" strokeWidth={2} />
                <span>Copy</span>
              </button>
              {isLastTurn && onRegenerate && (
                <button
                  type="button"
                  data-testid="chat-regenerate"
                  className="btn btn-sm"
                  disabled={regenerateDisabled}
                  onClick={() => onRegenerate(turnId)}
                >
                  Regenerate
                </button>
              )}
            </div>
          )}
        </li>
      )}
    </React.Fragment>
  )
}
