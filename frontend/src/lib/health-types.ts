/** GET /health JSON (fields may be absent on older API builds). */
export type HealthResponse = {
  status: string
  auth_mode?: 'dev' | 'entra'
  api?: { post_knowledge_bases?: boolean }
}
