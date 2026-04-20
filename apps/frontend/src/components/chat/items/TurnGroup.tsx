import * as React from 'react'
import { Copy } from 'lucide-react'
import { PrismLogo } from '~/components/brand'
import { ThinkingBlock } from '~/components/chat/ThinkingBlock'
import { UserMessageItem } from './UserMessageItem'
import { AssistantTextItem } from './AssistantTextItem'
import { LlmCallBadge } from './LlmCallBadge'
import { ToolCallItem } from './ToolCallItem'
import type { StreamThreadItem, ThreadItem } from '~/lib/chat-types'

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

  const thinkingItems = assistantItems.filter((i) => i.kind === 'thinking') as
    (ThreadItem & { kind: 'thinking' })[]
  const textItems = assistantItems.filter(
    (i) => i.kind === 'assistant_text',
  ) as (ThreadItem & { kind: 'assistant_text' })[]
  const toolItems = assistantItems.filter(
    (i) => i.kind === 'tool_call' || i.kind === 'server_tool_use',
  ) as (ThreadItem & { kind: 'tool_call' | 'server_tool_use' })[]
  const llmItem = assistantItems.find((i) => i.kind === 'llm_call') as
    | (ThreadItem & { kind: 'llm_call' })
    | undefined
  const errorItem = assistantItems.find((i) => i.kind === 'error') as
    | (ThreadItem & { kind: 'error' })
    | undefined

  const latestText = textItems.at(-1)
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
          onClick={() =>
            llmItem
              ? onSetActive(llmItem)
              : latestText
              ? onSetActive(latestText)
              : undefined
          }
        >
          <header className="msg-head">
            <span className="avatar-sm avatar-asst mono">VX</span>
            <span className="who-name">Assistant</span>
          </header>

          {thinkingItems.length > 0 && (
            <div className="mb-2">
              <ThinkingBlock
                items={thinkingItems as unknown as StreamThreadItem[]}
                running={isStreaming ?? false}
                defaultOpen={isStreaming ?? false}
              />
            </div>
          )}

          {toolItems.length > 0 && (
            <div className="mb-1 flex flex-col gap-0.5">
              {toolItems.map((t) => (
                <ToolCallItem key={t.id} item={t} />
              ))}
            </div>
          )}

          {latestText && (
            <AssistantTextItem
              item={latestText}
              streaming={isStreaming && latestText.status === 'streaming'}
            />
          )}

          {errorItem && (
            <div className="msg-body md text-red-800 dark:text-red-200">
              {errorItem.data.message || 'Error'}
            </div>
          )}

          {llmItem && !isStreaming && <LlmCallBadge item={llmItem} />}

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
                onClick={() =>
                  latestText &&
                  void navigator.clipboard
                    .writeText(latestText.data.text)
                    .catch(() => {})
                }
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
