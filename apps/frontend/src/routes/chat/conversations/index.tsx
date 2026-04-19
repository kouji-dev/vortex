import { createFileRoute } from '@tanstack/react-router'

import { ConversationThreadPage } from '~/components/chat/ConversationThreadPage'

export const Route = createFileRoute('/chat/conversations/')({
  component: ConversationsComposerIndex,
})

function ConversationsComposerIndex() {
  return <ConversationThreadPage conversationId={null} />
}
