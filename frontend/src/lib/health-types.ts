/** GET /health JSON (fields may be absent on older API builds). */
export type HealthResponse = {
  status: string
  auth_mode?: 'dev' | 'entra'
  deployment_mode?: 'dev' | 'saas' | 'selfhosted'
  api?: { post_knowledge_bases?: boolean }
}
