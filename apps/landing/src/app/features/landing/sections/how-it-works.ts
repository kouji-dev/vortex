import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RevealDirective } from '../../../shared/reveal/reveal.directive';

@Component({
  selector: 'vx-how-it-works',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RevealDirective],
  template: `
    <section class="wrap section-pad" style="padding-top:0;">
      <div class="section-head" vxReveal>
        <div class="eyebrow"><span class="tick"></span>HOW IT WORKS</div>
        <h2 class="h-display">Three steps to shipped.</h2>
      </div>
      <div class="steps" vxReveal>
        <div class="step">
          <div class="step-num">01 · CONNECT</div>
          <h3>Point the base URL</h3>
          <p>
            Swap one environment variable. Your existing SDK, agent, or IDE talks to Vortex with
            zero code changes.
          </p>
        </div>
        <div class="step">
          <div class="step-num">02 · GOVERN</div>
          <h3>Set budgets &amp; roles</h3>
          <p>
            Add teams and apps, assign budgets and caps, and enable audit. Policy applies to
            every request from that moment.
          </p>
        </div>
        <div class="step">
          <div class="step-num">03 · SHIP</div>
          <h3>Route to any model</h3>
          <p>
            Send traffic to any of 40+ models across six providers, with fallback, attribution,
            and live cost in one place.
          </p>
        </div>
      </div>
    </section>
  `,
})
export class HowItWorks {}
