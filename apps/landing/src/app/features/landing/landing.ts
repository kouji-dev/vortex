import { ChangeDetectionStrategy, Component, afterNextRender } from '@angular/core';
import { SiteNav } from './sections/site-nav';
import { Hero } from './sections/hero';
import { Dropin } from './sections/dropin';
import { Providers } from './sections/providers';
import { Governance } from './sections/governance';
import { HowItWorks } from './sections/how-it-works';
import { Deploy } from './sections/deploy';
import { Pricing } from './sections/pricing';
import { FinalCta } from './sections/final-cta';
import { SiteFooter } from './sections/site-footer';

/**
 * Vortex marketing landing — the dark brand stage. Composes every section from
 * the design (announce + nav → hero → drop-in → providers → governance →
 * how-it-works → deploy → pricing → final CTA → footer) over the atmosphere +
 * masked-grid background. Rendered server-side (SSR) for a fast, crawlable
 * first paint; interactive reveals + smooth scroll hydrate in the browser.
 */
@Component({
  selector: 'vx-landing',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    SiteNav,
    Hero,
    Dropin,
    Providers,
    Governance,
    HowItWorks,
    Deploy,
    Pricing,
    FinalCta,
    SiteFooter,
  ],
  template: `
    <div class="vx-atmosphere"></div>
    <div class="vx-grid"></div>

    <div class="page">
      <vx-site-nav />
      <vx-hero />
      <vx-dropin />
      <vx-providers />
      <vx-governance />
      <vx-how-it-works />
      <vx-deploy />
      <vx-pricing />
      <vx-final-cta />
      <vx-site-footer />
    </div>
  `,
})
export class Landing {
  constructor() {
    // Smooth in-page anchor scrolling (browser-only; SSR-safe via afterNextRender).
    afterNextRender(() => {
      const anchors = document.querySelectorAll<HTMLAnchorElement>('a[href^="#"]');
      anchors.forEach((a) => {
        a.addEventListener('click', (ev) => {
          const id = a.getAttribute('href');
          if (!id || id.length < 2) return;
          const target = document.querySelector(id);
          if (!target) return;
          ev.preventDefault();
          const y = target.getBoundingClientRect().top + window.pageYOffset - 72;
          window.scrollTo({ top: y, behavior: 'smooth' });
        });
      });
    });
  }
}
