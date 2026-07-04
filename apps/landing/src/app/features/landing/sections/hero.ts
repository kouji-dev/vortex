import { ChangeDetectionStrategy, Component } from '@angular/core';
import { Prism } from '../../../shared/prism/prism';
import { APP_URL } from '../landing.tokens';

@Component({
  selector: 'vx-hero',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Prism],
  template: `
    <section class="wrap" style="padding:104px 32px 84px; text-align:center;">
      <!-- Animated Prism (PrismLogo, idle state) -->
      <div
        class="reveal in"
        style="display:flex; justify-content:center; margin-bottom:34px;"
      >
        <span
          class="vx-prism"
          style="display:inline-block; filter:drop-shadow(0 0 40px rgba(167,139,250,0.35));"
        >
          <vx-prism [size]="88" [animated]="true" gradId="pmHero" />
        </span>
      </div>

      <div
        class="reveal in eyebrow"
        style="justify-content:center; margin-bottom:26px;"
      >
        <span class="tick"></span>AI GATEWAY · BUILT FOR ENTERPRISES
      </div>

      <h1 class="h-display hero-h1 reveal in" style="font-size:74px; margin-bottom:26px;">
        <span style="display:block;">Every model.</span>
        <span class="grad-text" style="display:block;">One gateway.</span>
        <span style="display:block; color:var(--vx-ink-3); font-weight:500;">Total control.</span>
      </h1>

      <p class="lede reveal in" style="max-width:588px; margin:0 auto 34px;">
        One OpenAI- and Anthropic-compatible endpoint in front of every provider — with the
        budgets, RBAC, and audit enterprises actually need. Change one line and you're on.
      </p>

      <div
        class="reveal in"
        style="display:flex; gap:12px; justify-content:center; flex-wrap:wrap;"
      >
        <a class="btn btn-gradient btn-lg" [href]="appUrl">Start free</a>
        <a class="btn btn-line btn-lg" href="#product">Read the docs</a>
      </div>

      <!-- trust strip -->
      <div class="trust reveal in">
        <span class="chip"><span class="dot"></span><b>40+</b> models</span>
        <span class="chip"><span class="dot"></span><b>6</b> providers</span>
        <span class="chip"><span class="dot"></span><b>0%</b> markup with BYOK</span>
        <span class="chip"><span class="dot"></span><b>&lt;1s</b> first byte</span>
      </div>
    </section>
  `,
})
export class Hero {
  readonly appUrl = APP_URL;
}
