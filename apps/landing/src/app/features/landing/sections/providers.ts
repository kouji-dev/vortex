import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { RevealDirective } from '../../../shared/reveal/reveal.directive';
import { providerDisplayName } from '../../catalog/catalog.util';

/** Marquee pill data — the 12 hosts, design-exact marks + brand colours. */
interface ProviderPill {
  name: string;
  mark: string;
  color: string;
  ink: string;
}

/** (id, mark, colour) per host — names come from the shared short-name map. */
const PILL_DEFS: { id: string; mark: string; color: string; ink?: string }[] = [
  { id: 'openai', mark: 'O', color: '#10a37f' },
  { id: 'anthropic', mark: 'A', color: '#cc785c' },
  { id: 'google', mark: 'G', color: '#4285f4' },
  { id: 'azure', mark: 'Az', color: '#0078d4' },
  { id: 'bedrock', mark: 'Bk', color: '#ff9900' },
  { id: 'vertex', mark: 'Vx', color: '#34a853' },
  { id: 'groq', mark: 'G', color: '#f55036' },
  { id: 'mistral', mark: 'M', color: '#ff7000' },
  { id: 'deepseek', mark: 'Ds', color: '#4d6bfe' },
  { id: 'xai', mark: 'x', color: '#a7adba', ink: '#111' },
  { id: 'together', mark: 'Tg', color: '#1668ff' },
  { id: 'fireworks', mark: 'Fw', color: '#ff5b2e' },
];

const PILLS: ProviderPill[] = PILL_DEFS.map((d) => ({
  name: providerDisplayName(d.id),
  mark: d.mark,
  color: d.color,
  ink: d.ink ?? '#fff',
}));

/** Models & Providers teaser — compact band + provider marquee → /models. */
@Component({
  selector: 'vx-providers',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, RevealDirective],
  template: `
    <section id="catalog" class="wrap section-pad" style="padding-top:0;">
      <div class="ct2" id="providers" vxReveal>
        <span class="vx-orbit" aria-hidden="true"></span>
        <div class="ct2-top">
          <div style="min-width:250px;">
            <div class="eyebrow"><span class="tick"></span>MODELS &amp; PROVIDERS</div>
            <h2 class="ct2-title">
              One logical model.<br /><span class="grad-text">Every host it runs on.</span>
            </h2>
          </div>
          <div class="ct2-stats">
            <div class="ct2-stat"><b>16</b><span>models</span></div>
            <div class="ct2-stat"><b>12</b><span>providers</span></div>
            <div class="ct2-stat"><b>1</b><span>endpoint</span></div>
          </div>
          <a class="btn btn-gradient" routerLink="/models"
            >Browse the catalog
            <svg
              viewBox="0 0 24 24"
              width="16"
              height="16"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </a>
        </div>
        <div class="ct2-marquee">
          <div class="ct2-track">
            @for (half of halves; track half) {
              <span class="ct2-half">
                @for (p of pills; track p.name) {
                  <span class="ct2-pill">
                    <span class="mk2" [style.background]="p.color" [style.color]="p.ink">{{
                      p.mark
                    }}</span>
                    {{ p.name }}
                  </span>
                }
              </span>
            }
          </div>
        </div>
        <div class="ct2-byok">
          <b>One key in. All of them out.</b> Bring your own keys — 0% markup, encrypted per-org —
          or use Vortex-managed capacity. Either way, Vortex governs the traffic.
        </div>
      </div>
    </section>
  `,
})
export class Providers {
  readonly pills = PILLS;
  /** Two copies of the pill run → seamless -50% marquee loop. */
  readonly halves = [0, 1];
}
