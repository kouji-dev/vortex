import { Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { KjBadgeComponent } from '@kouji-ui/components';
import { PricingTable } from '../pricing/pricing-table';
import { BillingService } from '../../shared/data/billing-service';

/**
 * In-console billing screen (owner/admin). Shows the current plan + usage and
 * the upgrade pricing table. Actual checkout runs through Stripe (managed only).
 */
@Component({
  selector: 'app-billing',
  standalone: true,
  imports: [PricingTable, KjBadgeComponent],
  styleUrl: '../pricing/pricing.css',
  template: `
    <section class="page">
      <div class="page-head">
        <div>
          <span class="vx-label">Admin Console</span>
          <h1>Billing &amp; Plan</h1>
          <p>Your current plan, usage this period, and upgrade options.</p>
        </div>
      </div>

      @if (sub(); as s) {
        <div class="panel" style="max-width:960px;margin-bottom:20px">
          <div class="panel-head">
            <h2>Current plan</h2>
            <kj-badge variant="default" size="xs">{{ s.plan.name }}</kj-badge>
          </div>
          <div class="plan-summary">
            <div class="metric">
              <span class="vx-label">Seats</span>
              <b>{{ s.seats.used }}{{ s.seats.limit === null ? '' : ' / ' + s.seats.limit }}</b>
            </div>
            <div class="metric">
              <span class="vx-label">Service accounts</span>
              <b>{{ s.usage.serviceAccounts }}</b>
            </div>
            <div class="metric">
              <span class="vx-label">Requests (mo)</span>
              <b>{{ s.usage.requests }}</b>
            </div>
            <div class="metric">
              <span class="vx-label">Spend (mo)</span>
              <b>{{ dollars(s.usage.costMicro) }}</b>
            </div>
          </div>
        </div>
      }

      @if (plans(); as p) {
        <h2 style="max-width:960px">Upgrade</h2>
        <app-pricing-table [plans]="p.plans" [currentPlanId]="currentPlanId()" />
      }
    </section>
  `,
})
export class Billing {
  private readonly billing = inject(BillingService);
  protected readonly sub = toSignal(this.billing.getSubscription());
  protected readonly plans = toSignal(this.billing.getPricing());
  protected readonly currentPlanId = computed(() => this.sub()?.plan.id ?? null);

  dollars(micro: number): string {
    return `$${(micro / 1_000_000).toFixed(2)}`;
  }
}
