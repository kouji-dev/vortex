import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RevealDirective } from '../../../shared/reveal/reveal.directive';
import { APP_URL } from '../landing.tokens';

/** Mid-page CTA — a quiet conversion beat between governance and deploy. */
@Component({
  selector: 'vx-mid-cta',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RevealDirective],
  template: `
    <section class="wrap" style="padding:0 32px 112px; text-align:center;">
      <div vxReveal style="display:flex; flex-direction:column; align-items:center; gap:18px;">
        <p class="lede" style="margin:0; max-width:520px;">
          Every request governed. Every dollar attributed. See it on your own traffic in minutes.
        </p>
        <a class="btn btn-gradient btn-lg" [href]="appUrl">Start free</a>
      </div>
    </section>
  `,
})
export class MidCta {
  readonly appUrl = APP_URL;
}
