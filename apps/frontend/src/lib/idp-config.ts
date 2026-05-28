/**
 * Per-IdP-kind config field definitions for the create/edit form.
 * Server side stores config as JSON; frontend renders one input per field.
 */
import type { IdpKind } from './admin-types'

export interface IdpConfigField {
  key: string
  label: string
  type: 'text' | 'url' | 'password' | 'textarea'
  required: boolean
  placeholder?: string
}

const OIDC_FIELDS: IdpConfigField[] = [
  { key: 'issuer', label: 'Issuer URL', type: 'url', required: true, placeholder: 'https://idp.example.com' },
  { key: 'client_id', label: 'Client ID', type: 'text', required: true },
  { key: 'client_secret', label: 'Client Secret', type: 'password', required: true },
  { key: 'scopes', label: 'Scopes', type: 'text', required: false, placeholder: 'openid email profile' },
]

const SAML_FIELDS: IdpConfigField[] = [
  { key: 'entity_id', label: 'IdP Entity ID', type: 'text', required: true },
  { key: 'sso_url', label: 'SSO URL', type: 'url', required: true },
  { key: 'x509_cert', label: 'X.509 Certificate', type: 'textarea', required: true, placeholder: '-----BEGIN CERTIFICATE-----' },
]

const ENTRA_FIELDS: IdpConfigField[] = [
  { key: 'tenant_id', label: 'Tenant ID', type: 'text', required: true },
  { key: 'client_id', label: 'Client ID', type: 'text', required: true },
  { key: 'client_secret', label: 'Client Secret', type: 'password', required: true },
]

const OKTA_FIELDS: IdpConfigField[] = [
  { key: 'okta_domain', label: 'Okta Domain', type: 'text', required: true, placeholder: 'acme.okta.com' },
  { key: 'client_id', label: 'Client ID', type: 'text', required: true },
  { key: 'client_secret', label: 'Client Secret', type: 'password', required: true },
]

const GOOGLE_FIELDS: IdpConfigField[] = [
  { key: 'client_id', label: 'Client ID', type: 'text', required: true },
  { key: 'client_secret', label: 'Client Secret', type: 'password', required: true },
  { key: 'hosted_domain', label: 'Hosted Domain (optional)', type: 'text', required: false, placeholder: 'acme.com' },
]

const FIELDS_BY_KIND: Record<IdpKind, IdpConfigField[]> = {
  oidc: OIDC_FIELDS,
  saml: SAML_FIELDS,
  entra: ENTRA_FIELDS,
  okta: OKTA_FIELDS,
  google: GOOGLE_FIELDS,
}

export function getIdpFields(kind: IdpKind): IdpConfigField[] {
  return FIELDS_BY_KIND[kind]
}

/**
 * Validate that all required fields are present in the supplied config.
 * Returns array of missing field keys. Empty array means valid.
 */
export function validateIdpConfig(
  kind: IdpKind,
  config: Record<string, string>,
): string[] {
  const missing: string[] = []
  for (const f of getIdpFields(kind)) {
    if (!f.required) continue
    const v = config[f.key]
    if (v == null || v.trim() === '') missing.push(f.key)
  }
  return missing
}
