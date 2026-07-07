import { Injectable, signal } from '@angular/core';

export type KeyKind = 'default' | 'personal';
export type KeyStatus = 'active' | 'stale' | 'revoked';

/**
 * A member-owned virtual key. Keys cap models / providers / IP + a rate limit,
 * but never a budget — spend counts against the owner's monthly budget.
 */
export interface VirtualKey {
  id: string;
  name: string;
  kind: KeyKind;
  /** Masked secret prefix — the full secret is only revealed once, at create/rotate. */
  mask: string;
  status: KeyStatus;
  /** Human summary of attached rules (models / providers / IP). */
  rules: string;
  /** Rate limit, e.g. "600 RPM". */
  rate: string;
  created: string;
  used: string;
}

/**
 * My Keys demo data. Mirrors the design mockup (scrMyKeys) — the signed-in
 * member owns exactly one default key plus any personal keys they create.
 * Wired to the gateway's key API in a later pass.
 */
@Injectable({ providedIn: 'root' })
export class KeysService {
  /** The signed-in member this workspace belongs to (demo). */
  readonly memberName = 'Sara Okafor';
  /** The member's monthly budget spend counts against (demo, USD). */
  readonly monthlyBudget = 1500;
  readonly spent = 620;

  private readonly _keys = signal<VirtualKey[]>([
    {
      id: 'k_default',
      name: 'default',
      kind: 'default',
      mask: 'vtx_live_••••4a9f',
      status: 'active',
      rules: 'All models',
      rate: '600 RPM',
      created: 'Mar 2, 2026',
      used: '2m ago',
    },
    {
      id: 'k_ci',
      name: 'ci-pipeline',
      kind: 'personal',
      mask: 'vtx_live_••••7c21',
      status: 'active',
      rules: '3 models · IP allowlist',
      rate: '300 RPM',
      created: 'Apr 18, 2026',
      used: '18m ago',
    },
    {
      id: 'k_mobile',
      name: 'mobile-tests',
      kind: 'personal',
      mask: 'vtx_test_••••9be3',
      status: 'active',
      rules: 'gpt-4o-mini only',
      rate: '120 RPM',
      created: 'May 6, 2026',
      used: '6h ago',
    },
    {
      id: 'k_legacy',
      name: 'legacy-notebook',
      kind: 'personal',
      mask: 'vtx_live_••••99ab',
      status: 'stale',
      rules: 'gemini',
      rate: '1,000 RPM',
      created: 'Jan 11, 2026',
      used: '3mo ago',
    },
  ]);

  keys() {
    return this._keys;
  }

  /** Add a client-side personal key (demo — the create modal calls this). */
  add(name: string, rules: string, rate: string): void {
    const suffix = Math.random().toString(16).slice(2, 6);
    this._keys.update((ks) => [
      ...ks,
      {
        id: 'k_' + suffix,
        name: name.trim() || 'new-key',
        kind: 'personal',
        mask: 'vtx_live_••••' + suffix,
        status: 'active',
        rules: rules || 'All models',
        rate: rate.trim() ? rate.trim() + ' RPM' : '600 RPM',
        created: 'Just now',
        used: 'never',
      },
    ]);
  }

  /** Rotate — swap the masked prefix (a new secret would be revealed once). */
  rotate(id: string): void {
    const suffix = Math.random().toString(16).slice(2, 6);
    this._keys.update((ks) =>
      ks.map((k) =>
        k.id === id
          ? { ...k, mask: k.mask.slice(0, k.mask.length - 4) + suffix, used: 'never', status: 'active' }
          : k,
      ),
    );
  }

  /** Revoke a personal key (default keys can't be revoked). */
  revoke(id: string): void {
    this._keys.update((ks) =>
      ks.map((k) => (k.id === id && k.kind === 'personal' ? { ...k, status: 'revoked' } : k)),
    );
  }
}
