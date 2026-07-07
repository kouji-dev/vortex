import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

/** A plan's entitlements as returned by the public catalog. */
export interface PlanEntitlements {
  seatsPerOrg: number | null;
  servicePerMember: number | null;
  teamBudgetMicro: number | null;
  rpm: number | null;
  tpm: number | null;
  concurrency: number | null;
  flags: Record<string, unknown>;
}

export interface PricingTier {
  meter: string;
  upToQty: number | null;
  unitPriceMicro: number;
}

export interface PlanCatalogEntry {
  planId: string;
  name: string;
  priceMicro: number | null;
  entitlements: PlanEntitlements;
  tiers: PricingTier[];
}

export interface SubscriptionInfo {
  plan: { id: string; name: string | null };
  entitlements: PlanEntitlements;
  usage: {
    period: string;
    requests: number;
    inputTokens: number;
    outputTokens: number;
    costMicro: number;
    seats: number;
    serviceAccounts: number;
  };
  seats: { used: number; limit: number | null };
  services: { used: number; limitPerMember: number | null };
  stripe: boolean;
}

/** Reads the pricing catalog + current subscription from the gateway API. */
@Injectable({ providedIn: 'root' })
export class BillingService {
  private readonly http = inject(HttpClient);

  /** Public pricing catalog (no auth). */
  getPricing(): Observable<{ plans: PlanCatalogEntry[] }> {
    return this.http.get<{ plans: PlanCatalogEntry[] }>('/api/pricing');
  }

  /** Current org plan + entitlements + usage (auth required). */
  getSubscription(): Observable<SubscriptionInfo> {
    return this.http.get<SubscriptionInfo>('/api/billing/subscription');
  }
}
