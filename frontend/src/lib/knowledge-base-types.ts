/** Mirrors authenticated knowledge-base API responses. */

export type KnowledgeBaseSummary = {
  id: number
  name: string
  description: string
  owner_user_id: number
  created_at: string
}

export type KnowledgeBaseDocument = {
  id: number
  knowledge_base_id: number
  filename: string
  status: string
  created_at: string
}
