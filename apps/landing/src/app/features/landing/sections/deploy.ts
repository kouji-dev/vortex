import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RevealDirective } from '../../../shared/reveal/reveal.directive';

@Component({
  selector: 'vx-deploy',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RevealDirective],
  template: `
    <section class="wrap section-pad" style="padding-top:0;">
      <div class="section-head" vxReveal>
        <div class="eyebrow"><span class="tick"></span>DEPLOY YOUR WAY</div>
        <h2 class="h-display">Your infra. Your data.</h2>
        <p class="lede">
          Run Vortex as managed SaaS or bring it fully inside your perimeter. Same gateway, same
          governance — different blast radius.
        </p>
      </div>

      <div class="deploy-grid" vxReveal>
        <div class="deploy">
          <div
            class="glow"
            style="background:radial-gradient(ellipse 400px 300px at 100% 0%, rgba(96,165,250,0.10), transparent 60%);"
          ></div>
          <div class="tagline">MANAGED</div>
          <h3>SaaS</h3>
          <ul>
            <li>
              <svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
              <span><b>Multi-tenant, managed</b> — we run and update the gateway; you onboard in minutes.</span>
            </li>
            <li>
              <svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
              <span>Hard tenant isolation with <b>Postgres row-level security</b>.</span>
            </li>
            <li>
              <svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
              <span>Per-org <b>encrypted keys</b>; capacity managed or BYOK.</span>
            </li>
            <li>
              <svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
              <span>Rolling updates, no maintenance windows to own.</span>
            </li>
          </ul>
        </div>
        <div class="deploy">
          <div
            class="glow"
            style="background:radial-gradient(ellipse 400px 300px at 100% 0%, rgba(167,139,250,0.12), transparent 60%);"
          ></div>
          <div class="tagline">ON YOUR TERMS</div>
          <h3>Self-host</h3>
          <ul>
            <li>
              <svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
              <span><b>On-prem or air-gapped</b> — the gateway runs entirely inside your network.</span>
            </li>
            <li>
              <svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
              <span>Your provider keys, your database, <b>your data never leaves</b>.</span>
            </li>
            <li>
              <svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
              <span>Same <b>RLS tenant isolation</b> and hash-chained audit.</span>
            </li>
            <li>
              <svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
              <span>Deploy from a single image; upgrade on your schedule.</span>
            </li>
          </ul>
        </div>
      </div>
    </section>
  `,
})
export class Deploy {}
