import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';
import { Icon } from './icon';
import { CAPS, SORTS, emptyFilter, type FilterState, type SortKey } from './catalog.util';
import type { SupportedFeatures } from './catalog.service';

const MODS: { key: FilterState['mod']; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'text', label: 'Text' },
  { key: 'multimodal', label: 'Multimodal' },
  { key: 'embedding', label: 'Embedding' },
];

/** Shared search + modality + capability + open-weights filter bar. */
@Component({
  selector: 'vx-filterbar',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  template: `
    <div class="cp-filterbar">
      <div class="wrap cp-filterbar-inner">
        <label class="f-search">
          <vx-icon name="search" />
          <input
            type="search"
            [placeholder]="placeholder()"
            [value]="filter().q"
            (input)="patch({ q: $any($event.target).value })"
          />
        </label>

        <div class="f-chips">
          @for (m of mods; track m.key) {
            <button class="fchip" [class.on]="filter().mod === m.key" (click)="patch({ mod: m.key })">
              {{ m.label }}
            </button>
          }
        </div>

        <div class="f-chips">
          @for (c of caps; track c.key) {
            <button class="fchip" [class.on]="hasCap(c.key)" (click)="toggleCap(c.key)">
              <vx-icon [name]="c.key" />{{ c.label }}
            </button>
          }
        </div>

        @if (sortable()) {
          <label class="f-sort">
            Sort
            <select [value]="sort()" (change)="sort.set($any($event.target).value)">
              @for (s of sorts; track s.key) {
                <option [value]="s.key">{{ s.label }}</option>
              }
            </select>
          </label>
        }

        <span class="fb-count"><b>{{ count() }}</b> models</span>
        @if (dirty()) { <button class="f-reset" (click)="reset()">Reset</button> }
      </div>
    </div>
  `,
})
export class FilterBar {
  readonly filter = model.required<FilterState>();
  readonly count = input(0);
  readonly placeholder = input('Search models, ids…');
  /** Show the sort dropdown (only where a model list is rendered). */
  readonly sortable = input(false);
  readonly sort = model<SortKey>('newest');

  readonly mods = MODS;
  readonly caps = CAPS;
  readonly sorts = SORTS;

  patch(p: Partial<FilterState>): void {
    this.filter.set({ ...this.filter(), ...p });
  }
  hasCap(k: keyof SupportedFeatures): boolean {
    return this.filter().caps.includes(k);
  }
  toggleCap(k: keyof SupportedFeatures): void {
    const caps = this.hasCap(k)
      ? this.filter().caps.filter((c) => c !== k)
      : [...this.filter().caps, k];
    this.patch({ caps });
  }
  dirty(): boolean {
    const f = this.filter();
    return !!f.q || f.mod !== 'all' || f.caps.length > 0;
  }
  reset(): void {
    this.filter.set(emptyFilter());
  }
}
