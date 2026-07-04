import {
  Directive,
  ElementRef,
  afterNextRender,
  inject,
} from '@angular/core';

/**
 * Entrance-reveal directive (DS motion discipline): content animates *from*
 * hidden via the `.reveal` → `.reveal.in` transition. Uses IntersectionObserver
 * in the browser only; on the server (and when reduced motion is requested) the
 * element is revealed immediately so nothing is ever stuck invisible.
 */
@Directive({
  selector: '[vxReveal]',
  standalone: true,
  host: { class: 'reveal' },
})
export class RevealDirective {
  private readonly host = inject(ElementRef<HTMLElement>);

  constructor() {
    // afterNextRender only runs in the browser, so this is SSR-safe.
    afterNextRender(() => {
      const el = this.host.nativeElement as HTMLElement;
      const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      if (reduced || !('IntersectionObserver' in window)) {
        el.classList.add('in');
        return;
      }

      const io = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              entry.target.classList.add('in');
              io.unobserve(entry.target);
            }
          }
        },
        { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
      );
      io.observe(el);
    });
  }
}
