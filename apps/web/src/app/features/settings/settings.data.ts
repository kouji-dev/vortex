import { Injectable } from '@angular/core';

/** Organisation profile — single-tenant; there is no org switcher. */
export interface OrgProfile {
  name: string;
  id: string;
  plan: string;
  region: string;
  members: number;
  seats: number;
  created: string;
  billingEmail: string;
  /** Single-letter monogram for the gradient logo tile. */
  monogram: string;
}

/** Idle-logout options for the console session policy. */
export const SESSION_POLICIES = ['1 hour', '8 hours', '24 hours'] as const;
export type SessionPolicy = (typeof SESSION_POLICIES)[number];

/**
 * Settings demo data — org profile, security and interface defaults. Mirrors
 * the design mockup (Northwind AI, `scrSettings`). Wired to the gateway's org
 * API in a later pass; serves realistic values so the console renders like the
 * design source today.
 */
@Injectable({ providedIn: 'root' })
export class SettingsService {
  readonly org: OrgProfile = {
    name: 'Northwind AI',
    id: 'org_4kf9x2',
    plan: 'Enterprise',
    region: 'US-East · aws',
    members: 142,
    seats: 200,
    created: 'Jan 2025',
    billingEmail: 'billing@northwind.ai',
    monogram: 'N',
  };

  /**
   * Signed-in member's own profile (member "Profile & Settings" screen). Name /
   * email / role are overridden live from the session where available; team &
   * monogram are demo values until the member API lands.
   */
  readonly member = {
    name: 'Aisha Khan',
    email: 'aisha@northwind.ai',
    role: 'member',
    team: 'Mobile',
  };

  /** Verified domains invites are restricted to. */
  readonly allowedDomains = 'northwind.ai';

  /** Default idle-logout policy. */
  readonly sessionPolicy: SessionPolicy = '8 hours';
}
