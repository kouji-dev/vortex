import { Injectable } from '@angular/core';

/** Provider identity keys used across credentials + catalog. */
export type ProviderKey =
  | 'openai'
  | 'anthropic'
  | 'google'
  | 'azure'
  | 'bedrock'
  | 'vertex';

export interface ProviderMeta {
  key: ProviderKey;
  label: string;
  /** Brand dot colour — token where defined, brand hex fallback otherwise. */
  color: string;
  letter: string;
}

/** A stored, encrypted provider credential (BYOK) or a managed connection. */
export interface ProviderCredential {
  prov: ProviderKey;
  name: string;
  /** Resolution scope — org-wide unless overridden by team / app. */
  scope: string;
  status: 'valid' | 'invalid';
  /** BYOK = customer key, encrypted at rest. Managed = Vortex-provided. */
  managed: boolean;
  /** Masked key preview (last-4 only). */
  keyMask: string;
  updated: string;
}

/** A model exposed through the gateway. Prices are USD per 1M tokens. */
export interface CatalogModel {
  alias: string;
  prov: ProviderKey;
  name: string;
  /** Input price, USD / 1M tokens. */
  in: number;
  /** Output price, USD / 1M tokens. */
  out: number;
  ctx: string;
  on: boolean;
  share: number;
}

/** Brand marks — anthropic/openai/google/mistral live as `--vx-prov-*`
 *  tokens; azure/bedrock/vertex fall back to their brand hex. */
export const PROVIDER_META: Record<ProviderKey, ProviderMeta> = {
  anthropic: { key: 'anthropic', label: 'Anthropic', color: 'var(--vx-prov-anthropic)', letter: 'A' },
  openai: { key: 'openai', label: 'OpenAI', color: 'var(--vx-prov-openai)', letter: 'O' },
  google: { key: 'google', label: 'Google', color: 'var(--vx-prov-google)', letter: 'G' },
  azure: { key: 'azure', label: 'Azure OpenAI', color: '#0a7bd4', letter: 'Z' },
  bedrock: { key: 'bedrock', label: 'AWS Bedrock', color: '#ff9900', letter: 'B' },
  vertex: { key: 'vertex', label: 'Google Vertex AI', color: '#4285f4', letter: 'V' },
};

export interface ProviderFilterOption {
  value: 'all' | ProviderKey;
  label: string;
}

/**
 * Providers & Models mock. Mirrors the design source (`scrProviders` /
 * `scrModels`) plus the seeded model catalog. Swapped for the gateway
 * admin API in a later pass.
 */
@Injectable({ providedIn: 'root' })
export class ProvidersData {
  meta(prov: ProviderKey): ProviderMeta {
    return PROVIDER_META[prov];
  }

  credentials(): ProviderCredential[] {
    return [
      {
        prov: 'openai',
        name: 'OpenAI',
        scope: 'Organization',
        status: 'valid',
        managed: false,
        keyMask: 'sk-••••••1c40',
        updated: '1w ago',
      },
      {
        prov: 'anthropic',
        name: 'Anthropic',
        scope: 'Organization',
        status: 'valid',
        managed: false,
        keyMask: 'sk-ant-•••8f2a',
        updated: '3d ago',
      },
      {
        prov: 'google',
        name: 'Google AI',
        scope: 'Team · Data Science',
        status: 'valid',
        managed: false,
        keyMask: 'AIza••••b91d',
        updated: '2w ago',
      },
      {
        prov: 'azure',
        name: 'Azure OpenAI',
        scope: 'App · Support Copilot',
        status: 'valid',
        managed: false,
        keyMask: '••••••4e7c',
        updated: '5d ago',
      },
      {
        prov: 'bedrock',
        name: 'AWS Bedrock',
        scope: 'Organization',
        status: 'invalid',
        managed: false,
        keyMask: 'AKIA••••0a3f',
        updated: '5d ago',
      },
      {
        prov: 'vertex',
        name: 'Google Vertex AI',
        scope: 'App · Analytics ETL',
        status: 'valid',
        managed: true,
        keyMask: 'svc-•••••acct',
        updated: '2w ago',
      },
    ];
  }

  providerFilters(): ProviderFilterOption[] {
    return [
      { value: 'all', label: 'All providers' },
      { value: 'anthropic', label: 'Anthropic' },
      { value: 'openai', label: 'OpenAI' },
      { value: 'google', label: 'Google' },
      { value: 'azure', label: 'Azure OpenAI' },
      { value: 'bedrock', label: 'AWS Bedrock' },
      { value: 'vertex', label: 'Google Vertex AI' },
    ];
  }

  /** Provider options for the "Add credential" modal. */
  providerOptions(): { value: ProviderKey; label: string }[] {
    return [
      { value: 'anthropic', label: 'Anthropic' },
      { value: 'openai', label: 'OpenAI' },
      { value: 'google', label: 'Google AI' },
      { value: 'azure', label: 'Azure OpenAI' },
      { value: 'bedrock', label: 'AWS Bedrock' },
      { value: 'vertex', label: 'Google Vertex AI' },
    ];
  }

  models(): CatalogModel[] {
    return [
      { alias: 'claude-sonnet-4-5', prov: 'anthropic', name: 'Claude Sonnet 4.5', in: 3.0, out: 15.0, ctx: '200k', on: true, share: 34 },
      { alias: 'gpt-4o', prov: 'openai', name: 'GPT-4o', in: 2.5, out: 10.0, ctx: '128k', on: true, share: 23 },
      { alias: 'gemini-2.5-pro', prov: 'google', name: 'Gemini 2.5 Pro', in: 1.25, out: 5.0, ctx: '1M', on: true, share: 15 },
      { alias: 'claude-haiku-4-5', prov: 'anthropic', name: 'Claude Haiku 4.5', in: 0.8, out: 4.0, ctx: '200k', on: true, share: 12 },
      { alias: 'gpt-4o-mini', prov: 'openai', name: 'GPT-4o mini', in: 0.15, out: 0.6, ctx: '128k', on: true, share: 9 },
      { alias: 'claude-opus-4-1', prov: 'anthropic', name: 'Claude Opus 4.1', in: 15.0, out: 75.0, ctx: '200k', on: false, share: 4 },
      { alias: 'gemini-2.5-flash', prov: 'google', name: 'Gemini 2.5 Flash', in: 0.3, out: 2.5, ctx: '1M', on: false, share: 3 },
    ];
  }
}
