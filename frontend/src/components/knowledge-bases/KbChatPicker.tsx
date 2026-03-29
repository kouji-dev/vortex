import * as Popover from '@radix-ui/react-popover'
import * as React from 'react'

import { KbPickerPanel } from '~/components/knowledge-bases/KbPickerPanel'

export type KbChatPickerProps = {
  conversationId: number
  activeCount: number
}

export function KbChatPicker({ conversationId, activeCount }: KbChatPickerProps) {
  const [open, setOpen] = React.useState(false)
  const isActive = activeCount > 0

  return (
    <Popover.Root open={open} onOpenChange={setOpen} modal={false}>
      <Popover.Trigger asChild>
        <button
          type="button"
          data-testid="chat-kb-picker-trigger"
          className={[
            'flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs transition-colors',
            isActive
              ? 'border-blue-500 text-blue-400 hover:bg-blue-500/10'
              : 'border-neutral-600 text-neutral-400 hover:border-neutral-500 hover:text-neutral-300',
          ].join(' ')}
          aria-label={
            isActive
              ? `${activeCount} knowledge base${activeCount !== 1 ? 's' : ''} active`
              : 'Knowledge bases'
          }
          aria-expanded={open}
        >
          <span>📚</span>
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
            open={open}
            onRequestClose={() => setOpen(false)}
          />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
