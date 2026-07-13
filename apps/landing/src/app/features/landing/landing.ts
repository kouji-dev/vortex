import { ChangeDetectionStrategy, Component, afterNextRender } from '@angular/core';
import { Hero } from './sections/hero';
import { Dropin } from './sections/dropin';
import { Providers } from './sections/providers';
import { Governance } from './sections/governance';
import { HowItWorks } from './sections/how-it-works';
import { MidCta } from './sections/mid-cta';
import { Deploy } from './sections/deploy';
import { Pricing } from './sections/pricing';
import { FinalCta } from './sections/final-cta';

/**
 * Vortex marketing landing — the dark brand stage. Composes every section from
 * the design (nav → hero → drop-in → how-it-works → models & providers teaser →
 * governance → mid-page CTA → deploy → pricing → final CTA → footer) over the
 * atmosphere + masked-grid background. Rendered server-side (SSR) for a fast,
 * crawlable first paint; interactive reveals + smooth scroll hydrate in the browser.
 */
@Component({
  selector: 'vx-landing',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Hero, Dropin, HowItWorks, Providers, Governance, MidCta, Deploy, Pricing, FinalCta],
  template: `
    <vx-hero />
    <vx-dropin />
    <vx-how-it-works />
    <vx-providers />
    <vx-governance />
    <vx-mid-cta />
    <vx-deploy />
    <vx-pricing />
    <vx-final-cta />
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
