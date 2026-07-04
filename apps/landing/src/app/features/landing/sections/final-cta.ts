import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RevealDirective } from '../../../shared/reveal/reveal.directive';
import { APP_URL } from '../landing.tokens';

@Component({
  selector: 'vx-final-cta',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RevealDirective],
  template: `
    <section class="cta-band wrap">
      <div class="glow"></div>
      <div vxReveal>
        <h2 class="h-display">
          <span style="display:block;">Every model.</span>
          <span class="grad-text" style="display:block;">One gateway.</span>
          <span style="display:block; color:var(--vx-ink-3); font-weight:500;">Total control.</span>
        </h2>
        <a class="btn btn-gradient btn-lg" [href]="appUrl">Start free</a>
      </div>
    </section>
  `,
})
export class FinalCta {
  readonly appUrl = APP_URL;
}
