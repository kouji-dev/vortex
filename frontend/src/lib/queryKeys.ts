export const queryKeys = {
  health: (apiBase: string) => ['health', apiBase] as const,
  me: (apiBase: string) => ['me', apiBase] as const,
  conversations: () => ['conversations'] as const,
  chatStarters: () => ['chat-starters'] as const,
  conversation: (id: number) => ['conversation', id] as const,
  conversationMessagesTail: (id: number) =>
    ['conversation-messages', id, 'recent-tail'] as const,
}
