import { Component, input } from '@angular/core';
import { KjBadgeComponent, KjButtonComponent } from '@kouji-ui/components';
import type { PlanCatalogEntry } from '../../shared/data/billing-service';

/**
 * Reusable 3-tier pricing table. Shared by the public /pricing page and the
 * in-console billing screen. Pure presentational — data comes from the caller.
 */
@Component({
  selector: 'app-pricing-table',
  standalone: true,
  imports: [KjBadgeComponent, KjButtonComponent],
  styleUrl: './pricing.css',
  template: `
    <div class="tiers">
      @for (p of plans(); track p.planId) {
        <div class="tier" [class.current]="p.planId === currentPlanId()">
          <div class="tier-head">
            <span class="tier-name">{{ p.name }}</span>
            @if (p.planId === currentPlanId()) {
              <kj-badge variant="default" size="xs">Current</kj-badge>
            } @else if (recommended() === p.planId) {
              <kj-badge variant="secondary" size="xs">Popular</kj-badge>
            }
          </div>

          <div class="tier-price">
            <span class="price-amt">{{ price(p) }}</span>
            @if (p.priceMicro !== null && p.priceMicro > 0) {
              <span class="price-per">/ month</span>
            }
          </div>

          <ul class="tier-feats">
            <li><b>{{ seats(p) }}</b> members</li>
            <li><b>{{ services(p) }}</b> service accounts / member</li>
            <li><b>{{ rpm(p) }}</b> requests / min</li>
            <li><b>{{ tpm(p) }}</b> tokens / min</li>
            <li>{{ budget(p) }} team budget</li>
            @if (p.entitlements.flags['allowCustomRateLimit']) {
              <li>Custom per-key rate limits</li>
            }
          </ul>

          <kj-button
            [kjVariant]="p.planId === currentPlanId() ? 'ghost' : 'accent'"
            kjSize="sm"
            [kjDisabled]="p.planId === currentPlanId()"
          >
            {{ cta(p) }}
          </kj-button>
        </div>
      }
    </div>
  `,
})
export class PricingTable {
  readonly plans = input.required<PlanCatalogEntry[]>();
  readonly currentPlanId = input<string | null>(null);
  readonly recommended = input<string | null>('plan_pro');

  price(p: PlanCatalogEntry): string {
    if (p.priceMicro === null) return 'Custom';
    if (p.priceMicro === 0) return 'Free';
    return `$${Math.round(p.priceMicro / 1_000_000)}`;
  }
  private lim(v: number | null): string {
    return v === null ? 'Unlimited' : `${v}`;
  }
  seats(p: PlanCatalogEntry): string {
    return this.lim(p.entitlements.seatsPerOrg);
  }
  services(p: PlanCatalogEntry): string {
    return this.lim(p.entitlements.servicePerMember);
  }
  rpm(p: PlanCatalogEntry): string {
    return this.lim(p.entitlements.rpm);
  }
  tpm(p: PlanCatalogEntry): string {
    const t = p.entitlements.tpm;
    return t === null ? 'Unlimited' : `${(t / 1000).toLocaleString()}k`;
  }
  budget(p: PlanCatalogEntry): string {
    const b = p.entitlements.teamBudgetMicro;
    return b === null ? 'Unlimited' : `$${Math.round(b / 1_000_000)}`;
  }
  cta(p: PlanCatalogEntry): string {
    if (p.planId === this.currentPlanId()) return 'Current plan';
    if (p.priceMicro === null) return 'Contact sales';
    if (p.priceMicro === 0) return 'Start free';
    return 'Upgrade';
  }
}
