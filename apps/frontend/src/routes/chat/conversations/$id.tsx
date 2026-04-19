import { createFileRoute } from '@tanstack/react-router'

import { ConversationThreadPage } from '~/components/chat/ConversationThreadPage'

export const Route = createFileRoute('/chat/conversations/$id')({
  component: ConversationThreadPageRoute,
})

function ConversationThreadPageRoute() {
  const { id } = Route.useParams()
  return <ConversationThreadPage conversationId={Number(id)} />
}
