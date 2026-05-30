/**
 * Pure helpers for adaptive auth UI.
 *
 * The login/signup pages render only the strategies the deployment enables,
 * driven by the public `GET /v1/auth/config` bootstrap. These helpers turn the
 * raw config into render decisions, with a safe default when the config has not
 * loaded yet (password-only, so the form is never blocked).
 */
import type { AuthConfig } from './admin-types'

export interface SocialButton {
  provider: string
  label: string
  startUrl: string
}

const SOCIAL_LABELS: Record<string, string> = {
  google: 'Google',
  github: 'GitHub',
  gitlab: 'GitLab',
}

export const DEFAULT_AUTH_CONFIG: AuthConfig = {
  password: true,
  social: [],
  directory: false,
  enterprise: true,
}

/** Label for a social provider key (falls back to a capitalized name). */
export function socialLabel(provider: string): string {
  return SOCIAL_LABELS[provider] ?? provider.charAt(0).toUpperCase() + provider.slice(1)
}

/** Build the ordered social buttons to render, with their start URLs. */
export function socialButtons(cfg: AuthConfig | undefined, apiBase = ''): SocialButton[] {
  const list = cfg?.social ?? []
  return list.map((provider) => ({
    provider,
    label: socialLabel(provider),
    startUrl: `${apiBase}/api/v1/auth/social/${provider}/start`,
  }))
}

/** Whether the password email/password form should render. */
export function showPasswordForm(cfg: AuthConfig | undefined): boolean {
  // Default to true when config absent so users are never locked out by a
  // failed bootstrap fetch.
  return cfg?.password ?? DEFAULT_AUTH_CONFIG.password
}

/** Whether the enterprise SSO row should render. */
export function showEnterpriseSso(cfg: AuthConfig | undefined): boolean {
  return cfg?.enterprise ?? DEFAULT_AUTH_CONFIG.enterprise
}

/** Whether the directory (LDAP) login option should render. */
export function showDirectoryLogin(cfg: AuthConfig | undefined): boolean {
  return cfg?.directory ?? DEFAULT_AUTH_CONFIG.directory
}

/** True when at least one strategy is renderable (sanity for empty configs). */
export function hasAnyStrategy(cfg: AuthConfig | undefined): boolean {
  return (
    showPasswordForm(cfg) ||
    showEnterpriseSso(cfg) ||
    showDirectoryLogin(cfg) ||
    (cfg?.social?.length ?? 0) > 0
  )
}
