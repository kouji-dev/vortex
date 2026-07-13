import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CatalogService } from './catalog.service';
import { money1M, pmark, pmarkInk, providerDisplayName } from './catalog.util';

/** /models — catalog hero + provider cards (each → provider detail). */
@Component({
  selector: 'vx-catalog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <section class="cp-hero">
      <div class="wrap">
        <div class="eyebrow"><span class="tick"></span>THE CATALOG</div>
        <h1 class="cp-h1">Every provider,<br /><span class="grad-text">one interface.</span></h1>
        <p class="cp-lede">
          Vortex routes to twelve providers behind a single endpoint. Choose one to explore the
          models it serves — with live pricing, context windows and capabilities.
        </p>
      </div>
    </section>

    <section class="cp-body">
      <div class="wrap">
        @if (svc.models() === null) {
          <div class="cp-empty">Loading catalog…</div>
        } @else if (svc.error()) {
          <div class="cp-empty">Catalog unavailable — {{ svc.error() }}</div>
        } @else {
          <div class="cat-prov-grid">
            @for (c of cards(); track c.p.id) {
              <button
                class="pcard"
                [routerLink]="['/providers', c.p.id]"
                [style.--pc]="c.p.brandColor"
              >
                <span class="pcard-bar"></span>
                <span class="pcard-body">
                  <span class="pcard-head">
                    <span
                      class="pmark"
                      [style.background]="c.p.brandColor"
                      [style.color]="ink(c.p.id)"
                      [style.width.px]="42"
                      [style.height.px]="42"
                      [style.fontSize.px]="17"
                      >{{ mark(c.p.id) }}</span
                    >
                    <span>
                      <span class="pcard-name" style="display:block;">{{ c.name }}</span>
                      <span class="pcard-fam">{{ c.p.defaultFamily }} family</span>
                    </span>
                  </span>
                  <span class="pm-chips">
                    @for (n of c.chips; track n) { <span class="pm-chip">{{ n }}</span> }
                    @if (c.more > 0) { <span class="pm-chip more">+{{ c.more }} more</span> }
                  </span>
                  <span class="pcard-meta">
                    <span>{{ c.count }} model{{ c.count === 1 ? '' : 's' }}</span>
                    @if (c.from !== null) {
                      <span class="pm-from">from {{ price(c.from) }} / 1M</span>
                    }
                  </span>
                </span>
              </button>
            }
          </div>
        }
      </div>
    </section>
  `,
})
export class Catalog {
  readonly svc = inject(CatalogService);

  constructor() {
    this.svc.load();
  }

  readonly cards = computed(() => {
    const models = this.svc.models() ?? [];
    return this.svc.providers().map((p) => {
      const served = models.filter((m) => m.hosts.some((h) => h.host === p.id));
      const prices = served.flatMap((m) =>
        m.hosts.filter((h) => h.host === p.id).map((h) => h.inputPer1kMicro),
      );
      const from = prices.length ? Math.min(...prices) : null;
      return {
        p,
        name: providerDisplayName(p.id, p.name),
        count: served.length,
        chips: served.slice(0, 3).map((m) => m.displayName),
        more: Math.max(0, served.length - 3),
        from,
      };
    });
  });

  mark = pmark;
  ink = pmarkInk;
  price = money1M;
}
