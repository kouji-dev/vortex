// Pure helpers for the Gateway Providers page.

import type { ProviderCredential, ProviderKind } from './gateway-types'

/** Display order for the built-in provider catalog. */
export const PROVIDER_CATALOG: { kind: ProviderKind; label: string }[] = [
  { kind: 'anthropic', label: 'Anthropic' },
  { kind: 'openai', label: 'OpenAI' },
  { kind: 'azure_openai', label: 'Azure OpenAI' },
  { kind: 'bedrock', label: 'Amazon Bedrock' },
  { kind: 'vertex', label: 'Google Vertex AI' },
  { kind: 'gemini', label: 'Gemini' },
  { kind: 'mistral', label: 'Mistral' },
  { kind: 'groq', label: 'Groq' },
  { kind: 'together', label: 'Together' },
  { kind: 'fireworks', label: 'Fireworks' },
  { kind: 'ollama', label: 'Ollama' },
  { kind: 'vllm', label: 'vLLM' },
]

/** Health badge state derived from credential row. */
export type HealthBadge = 'healthy' | 'unhealthy' | 'unknown' | 'stale'

const STALE_AFTER_MS = 24 * 60 * 60 * 1000 // 24h

export function healthBadge(
  cred: Pick<ProviderCredential, 'healthy' | 'last_health_at'>,
  now: number = Date.now(),
): HealthBadge {
  if (!cred.last_health_at) return 'unknown'
  const age = now - new Date(cred.last_health_at).getTime()
  if (age > STALE_AFTER_MS) return 'stale'
  return cred.healthy ? 'healthy' : 'unhealthy'
}

export function validateCredentialSecret(secret: string): string | null {
  if (!secret.trim()) return 'Secret required'
  if (secret.length < 8) return 'Secret looks too short'
  return null
}

export function validateCredentialLabel(label: string): string | null {
  if (label.length === 0) return null // optional
  if (label.length > 64) return 'Label too long (max 64)'
  if (!/^[a-zA-Z0-9_-]+$/.test(label)) return 'Label may only use letters, digits, _ and -'
  return null
}

export function providerLabel(kind: ProviderKind | string): string {
  const found = PROVIDER_CATALOG.find((p) => p.kind === kind)
  return found?.label ?? kind
}
