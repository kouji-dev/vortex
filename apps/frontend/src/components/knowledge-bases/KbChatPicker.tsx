import * as Popover from '@radix-ui/react-popover'
import * as React from 'react'
import { Library } from 'lucide-react'

import { KbPickerPanel } from '~/components/knowledge-bases/KbPickerPanel'

export type KbChatPickerProps = {
  conversationId: number | null
  activeCount: number
  draftKnowledgeBaseIds?: number[]
  onDraftKnowledgeBaseIdsChange?: (ids: number[]) => void
}

export function KbChatPicker({
  conversationId,
  activeCount,
  draftKnowledgeBaseIds,
  onDraftKnowledgeBaseIdsChange,
}: KbChatPickerProps) {
  const [open, setOpen] = React.useState(false)
  const isActive = activeCount > 0

  return (
    <Popover.Root open={open} onOpenChange={setOpen} modal={false}>
      <Popover.Trigger asChild>
        <button
          type="button"
          data-testid="chat-kb-picker-trigger"
          className={[
            'inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-xs transition-colors',
            isActive
              ? 'border-blue-500/70 bg-blue-50 text-blue-700 hover:bg-blue-100 dark:border-blue-500/70 dark:bg-blue-500/10 dark:text-blue-300 dark:hover:bg-blue-500/20'
              : 'border-neutral-200 bg-white text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-200 dark:hover:bg-neutral-900',
          ].join(' ')}
          aria-label={
            isActive
              ? `${activeCount} knowledge base${activeCount !== 1 ? 's' : ''} active`
              : 'Knowledge bases'
          }
          aria-expanded={open}
        >
          <Library className="size-3.5 shrink-0" aria-hidden />
          <span>{isActive ? `${activeCount} KBs active` : 'KBs'}</span>
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top"
          align="center"
          sideOffset={8}
          collisionPadding={12}
          data-testid="kb-picker-popover"
          className="z-100 w-[min(22rem,calc(100vw-1.5rem))] outline-none"
          onCloseAutoFocus={(e) => e.preventDefault()}
        >
          <KbPickerPanel
            conversationId={conversationId}
            draftKnowledgeBaseIds={draftKnowledgeBaseIds}
            onDraftKnowledgeBaseIdsChange={onDraftKnowledgeBaseIdsChange}
            open={open}
            onRequestClose={() => setOpen(false)}
          />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
