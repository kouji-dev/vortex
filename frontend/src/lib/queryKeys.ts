export const queryKeys = {
  health: (apiBase: string) => ['health', apiBase] as const,
  me: (apiBase: string) => ['me', apiBase] as const,
  conversations: () => ['conversations'] as const,
  chatStarters: () => ['chat-starters'] as const,
  conversation: (id: number) => ['conversation', id] as const,
  conversationMessagesTail: (id: number) =>
    ['conversation-messages', id, 'recent-tail'] as const,
  knowledgeBases: () => ['knowledge-bases'] as const,
  knowledgeBase: (id: number) => ['knowledge-base', id] as const,
  knowledgeBaseDocuments: (id: number) => ['knowledge-base-documents', id] as const,
  knowledgeBaseConnectors: (id: number) => ['knowledge-base-connectors', id] as const,
  knowledgeBaseConnectorJobs: (id: number) =>
    ['knowledge-base-connector-jobs', id] as const,
}
