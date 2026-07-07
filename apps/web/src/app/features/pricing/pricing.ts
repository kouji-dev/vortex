import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { PricingTable } from './pricing-table';
import { BillingService } from '../../shared/data/billing-service';

/**
 * Public pricing page (no auth) — the landing pricing table. Registered outside
 * the authGuard shell so prospects can view plans before signing up.
 */
@Component({
  selector: 'app-pricing',
  standalone: true,
  imports: [PricingTable, RouterLink],
  styleUrl: './pricing.css',
  template: `
    <div class="pricing-page">
      <div class="pricing-hero">
        <h1>Plans that scale with you</h1>
        <p>From a single builder to a whole enterprise — pay for what you use.</p>
      </div>

      @if (data(); as d) {
        <app-pricing-table [plans]="d.plans" />
      } @else {
        <p style="text-align:center">Loading plans…</p>
      }

      <div class="pricing-hero" style="margin-top:32px">
        <a routerLink="/signup"><b>Start free</b></a>
        · no credit card required
      </div>
    </div>
  `,
})
export class Pricing {
  private readonly billing = inject(BillingService);
  protected readonly data = toSignal(this.billing.getPricing());
}
