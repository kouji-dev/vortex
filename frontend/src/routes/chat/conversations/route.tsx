import { createFileRoute } from '@tanstack/react-router'

import { ConversationsRouteLayout } from '~/components/chat/ConversationsRouteLayout'

export const Route = createFileRoute('/chat/conversations')({
  component: ConversationsRouteLayout,
})
