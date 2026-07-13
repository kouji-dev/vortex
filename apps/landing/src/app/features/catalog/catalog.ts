import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CatalogService } from './catalog.service';
import { FilterBar } from './filter-bar';
import { money1M, pmark, matchesFilters, emptyFilter, type FilterState } from './catalog.util';

/** /models — filter bar + provider cards (each → provider detail). */
@Component({
  selector: 'vx-catalog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, FilterBar],
  template: `
    <section class="cp-hero">
      <div class="wrap">
        <div class="eyebrow"><span class="tick"></span>MODELS &amp; PROVIDERS</div>
        <h1 class="cp-h1">Every provider,<br /><span class="grad-text">one interface.</span></h1>
        <p class="cp-lede">
          One logical model is often served by several providers. Browse the live catalog — Vortex
          shows the price, context, and capabilities of each, so you route to the right one.
        </p>
      </div>
    </section>

    <vx-filterbar [(filter)]="filter" [count]="totalMatched()" />

    <section class="cp-body">
      <div class="wrap">
        <div class="section-head" style="margin-bottom:18px;">
          <div class="eyebrow"><span class="tick"></span>PROVIDERS</div>
        </div>

        @if (svc.models() === null) {
          <div class="cp-empty">Loading catalog…</div>
        } @else if (svc.error()) {
          <div class="cp-empty">Catalog unavailable — {{ svc.error() }}</div>
        } @else {
          <div class="cat-prov-grid">
            @for (c of cards(); track c.p.id) {
              <button class="pcard" [routerLink]="['/providers', c.p.id]">
                <span class="pcard-bar" [style.background]="c.p.brandColor"></span>
                <span class="pcard-body">
                  <span class="pcard-head">
                    <span
                      class="pmark"
                      [style.background]="c.p.brandColor"
                      [style.width.px]="42"
                      [style.height.px]="42"
                      [style.fontSize.px]="17"
                      >{{ mark(c.p.id) }}</span
                    >
                    <span>
                      <span class="pcard-name" style="display:block;">{{ c.p.name }}</span>
                      <span class="pcard-fam">{{ c.p.defaultFamily }} family</span>
                    </span>
                  </span>
                  <span class="pm-chips">
                    @for (n of c.chips; track n) { <span class="pm-chip">{{ n }}</span> }
                    @if (c.more > 0) { <span class="pm-chip more">+{{ c.more }} more</span> }
                  </span>
                  <span class="pcard-meta">
                    <span><b>{{ c.count }}</b> models</span>
                    @if (c.from !== null) {
                      <span class="pm-from">from <b>{{ price(c.from) }}</b> / 1M</span>
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
  readonly filter = signal<FilterState>(emptyFilter());

  constructor() {
    this.svc.load();
  }

  private matched = computed(() => {
    const f = this.filter();
    return (this.svc.models() ?? []).filter((m) => matchesFilters(m, f));
  });

  readonly totalMatched = computed(() => this.matched().length);

  readonly cards = computed(() => {
    const matched = this.matched();
    return this.svc.providers().map((p) => {
      const models = matched.filter((m) => m.hosts.some((h) => h.host === p.id));
      const prices = models.flatMap((m) =>
        m.hosts.filter((h) => h.host === p.id).map((h) => h.inputPer1kMicro),
      );
      const from = prices.length ? Math.min(...prices) : null;
      return {
        p,
        count: models.length,
        chips: models.slice(0, 3).map((m) => m.displayName),
        more: Math.max(0, models.length - 3),
        from,
      };
    });
  });

  mark = pmark;
  price = money1M;
}
