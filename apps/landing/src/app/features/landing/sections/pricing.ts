import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RevealDirective } from '../../../shared/reveal/reveal.directive';
import { APP_URL } from '../landing.tokens';

@Component({
  selector: 'vx-pricing',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RevealDirective],
  template: `
    <section id="pricing" class="wrap section-pad" style="padding-top:0;">
      <div class="section-head" style="max-width:640px;" vxReveal>
        <div class="eyebrow"><span class="tick"></span>PRICING</div>
        <h2 class="h-display">Start free. Scale with control.</h2>
        <p class="lede">
          Pay for usage, or bring your own keys and pay nothing extra. Governance is included at
          every tier.
        </p>
      </div>

      <div class="price-grid" vxReveal>
        <div class="plan">
          <div class="plan-name">Free</div>
          <div class="plan-price">$0</div>
          <div class="plan-desc">For individuals and first pilots.</div>
          <ul>
            @for (f of freeFeatures; track f) {
            <li>
              <svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
              {{ f }}
            </li>
            }
          </ul>
          <a class="btn btn-line" [href]="appUrl">Start free</a>
        </div>
        <div class="plan featured">
          <div class="plan-name">Pro</div>
          <div class="plan-price">Usage<small> / or BYOK</small></div>
          <div class="plan-desc">For teams that need attribution and caps.</div>
          <ul>
            @for (f of proFeatures; track f) {
            <li>
              <svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
              {{ f }}
            </li>
            }
          </ul>
          <a class="btn btn-gradient" [href]="appUrl">Start Pro</a>
        </div>
        <div class="plan">
          <div class="plan-name">Enterprise</div>
          <div class="plan-price">Custom</div>
          <div class="plan-desc">Self-host or managed, air-gap, and SSO.</div>
          <ul>
            @for (f of enterpriseFeatures; track f) {
            <li>
              <svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
              {{ f }}
            </li>
            }
          </ul>
          <a class="btn btn-line" href="#">Contact sales</a>
        </div>
      </div>
      <div class="price-note" vxReveal>
        Budget + rate limits included at every tier · BYOK 0% markup · managed keys add a small markup · no per-seat lock-in
      </div>
    </section>
  `,
})
export class Pricing {
  readonly appUrl = APP_URL;

  // Feature bullets mirror the real plan entitlements (see db seed).
  readonly freeFeatures = [
    '2 members · 1 service account each',
    '20 requests/min · $50 team budget',
    'BYOK · 0% markup · one endpoint',
  ];
  readonly proFeatures = [
    '10 members · 3 service accounts each',
    '600 requests/min · custom per-key limits',
    'Teams, apps, RBAC & cost attribution',
  ];
  readonly enterpriseFeatures = [
    'Unlimited members & service accounts',
    'Custom rate limits, budgets & contracts',
    'Self-host or managed keys · SSO · audit',
  ];
}
