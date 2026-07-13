import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { RevealDirective } from '../../../shared/reveal/reveal.directive';

@Component({
  selector: 'vx-providers',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RevealDirective, RouterLink],
  template: `
    <section id="providers" class="wrap section-pad" style="padding-top:0;">
      <div class="section-head" vxReveal>
        <div class="eyebrow"><span class="tick"></span>EVERY PROVIDER</div>
        <h2 class="h-display">One key in. All of them out.</h2>
        <p class="lede">
          Route to any provider through a single interface — including the enterprise clouds. Or
          bring your own keys and pay the provider directly.
        </p>
      </div>

      <div class="prov-row" vxReveal>
        <div class="prov">
          <span class="prov-mark" style="background:#10a37f;">O</span>
          <div><div class="prov-name">OpenAI</div><div class="prov-kind">GPT · o-series</div></div>
        </div>
        <div class="prov">
          <span class="prov-mark" style="background:#cc785c;">A</span>
          <div><div class="prov-name">Anthropic</div><div class="prov-kind">Claude</div></div>
        </div>
        <div class="prov">
          <span class="prov-mark" style="background:#4285f4;">G</span>
          <div><div class="prov-name">Google</div><div class="prov-kind">Gemini</div></div>
        </div>
      </div>
      <div class="prov-row" style="margin-top:14px;" vxReveal>
        <div class="prov">
          <span class="prov-mark" style="background:#0078d4;">Az</span>
          <div><div class="prov-name">Azure</div><div class="prov-kind">Azure OpenAI</div></div>
        </div>
        <div class="prov">
          <span class="prov-mark" style="background:#ff9900; color:#111;">Bk</span>
          <div><div class="prov-name">Bedrock</div><div class="prov-kind">AWS</div></div>
        </div>
        <div class="prov">
          <span class="prov-mark" style="background:#34a853;">Vx</span>
          <div><div class="prov-name">Vertex</div><div class="prov-kind">Google Cloud</div></div>
        </div>
      </div>

      <p class="byok-note" vxReveal>
        <b>Bring your own keys — 0% markup.</b> Use Vortex-managed capacity, or attach your org's
        provider keys (encrypted per-org) and Vortex governs the traffic without touching the
        bill.
      </p>

      <div style="margin-top:28px;" vxReveal>
        <a class="btn btn-ghost" routerLink="/models">Browse the model catalog →</a>
      </div>
    </section>
  `,
})
export class Providers {}
