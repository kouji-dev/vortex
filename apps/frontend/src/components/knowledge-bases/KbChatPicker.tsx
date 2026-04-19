import * as Popover from '@radix-ui/react-popover'
import * as React from 'react'
import { ChevronsUpDown, Library } from 'lucide-react'

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
          className={`composer-pill ${isActive ? 'on' : ''}`}
          aria-label={
            isActive
              ? `${activeCount} knowledge base${activeCount !== 1 ? 's' : ''} active`
              : 'Add knowledge'
          }
          aria-expanded={open}
        >
          <Library className="size-3 shrink-0" strokeWidth={2} aria-hidden />
          <span className="pill-label-full">
            {isActive
              ? `${activeCount} knowledge base${activeCount !== 1 ? 's' : ''}`
              : 'Add knowledge'}
          </span>
          <ChevronsUpDown className="size-3" strokeWidth={2} aria-hidden />
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
