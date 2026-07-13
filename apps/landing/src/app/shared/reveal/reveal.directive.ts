import {
  Directive,
  ElementRef,
  afterNextRender,
  inject,
} from '@angular/core';

/**
 * Entrance-reveal directive (DS motion discipline): content animates *from*
 * hidden via the `.reveal` → `.reveal.in` transition. Uses a SHARED
 * IntersectionObserver in the browser only, so elements entering the viewport
 * in the same batch stagger by 80ms (design's reveal cadence). On the server
 * (and when reduced motion is requested) the element is revealed immediately
 * so nothing is ever stuck invisible.
 */

let sharedIo: IntersectionObserver | null = null;

function observe(el: HTMLElement): void {
  sharedIo ??= new IntersectionObserver(
    (entries) => {
      let d = 0;
      for (const entry of entries) {
        if (entry.isIntersecting) {
          (entry.target as HTMLElement).style.transitionDelay = `${d}ms`;
          d += 80;
          entry.target.classList.add('in');
          sharedIo!.unobserve(entry.target);
        }
      }
    },
    { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
  );
  sharedIo.observe(el);
}

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
      observe(el);
    });
  }
}
