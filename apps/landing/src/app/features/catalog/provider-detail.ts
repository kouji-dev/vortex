import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';
import { CatalogService, type HostModel, type SupportedFeatures } from './catalog.service';
import { FilterBar } from './filter-bar';
import { Icon } from './icon';
import {
  CAPS,
  emptyFilter,
  fmtCtx,
  matchesFilters,
  money1M,
  pmark,
  pmarkInk,
  providerDisplayName,
  sortRows,
  type FilterState,
  type SortKey,
} from './catalog.util';

/** Provider blurbs — design-exact marketing copy (not in /v1/catalog). */
const PROVIDER_DESC: Record<string, string> = {
  openai: 'GPT and o-series models, served directly from OpenAI.',
  anthropic: 'The Claude family, direct from Anthropic.',
  google: 'Gemini models on Google AI.',
  azure: 'OpenAI models on Microsoft Azure, with regional deployments and enterprise controls.',
  bedrock: 'Frontier and open-weights models through AWS Bedrock.',
  vertex: 'Claude and Gemini on Google Cloud Vertex AI.',
  groq: 'Open-weights models at very low latency on Groq LPUs.',
  mistral: 'Mistral’s own hosted models, from the source.',
  deepseek: 'DeepSeek’s chat and reasoning models, direct.',
  xai: 'Grok models from xAI, with live search grounding.',
  together: 'Open-weights models hosted on Together AI.',
  fireworks: 'Open-weights models hosted on Fireworks AI.',
};

/** /providers/:id — provider header + filter bar + its models as a table. */
@Component({
  selector: 'vx-provider-detail',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, FilterBar, Icon],
  template: `
    @if (svc.models() === null) {
      <section class="cp-hero"><div class="wrap"><div class="cp-empty">Loading…</div></div></section>
    } @else if (!provider()) {
      <section class="cp-hero">
        <div class="wrap">
          <button class="cat-back" routerLink="/models"><vx-icon name="back" />All providers</button>
          <div class="cp-empty">Provider not found.</div>
        </div>
      </section>
    } @else {
      <section class="cp-hero cp-hero-prov" [style.--pc]="provider()!.brandColor">
        <div class="wrap">
          <button class="cat-back" routerLink="/models"><vx-icon name="back" />All providers</button>
          <div class="prov-id">
            <span
              class="pmark"
              [style.background]="provider()!.brandColor"
              [style.color]="ink(provider()!.id)"
              [style.width.px]="58"
              [style.height.px]="58"
              [style.fontSize.px]="24"
              >{{ mark(provider()!.id) }}</span
            >
            <div>
              <h1 class="cp-h1 prov-id-name">{{ displayName() }}</h1>
              <div class="prov-id-sub">
                <span class="prov-id-fam">{{ provider()!.defaultFamily }} wire format</span>
                <span class="dotsep">·</span><span>{{ allCount() }} models</span>
              </div>
            </div>
          </div>
          @if (desc()) {
            <p class="cp-lede">{{ desc() }}</p>
          }
        </div>
      </section>

      <vx-filterbar
        [(filter)]="filter"
        [(sort)]="sort"
        [sortable]="true"
        [count]="rows().length"
        placeholder="Search these models…"
      />

      <section class="cp-body">
        <div class="wrap">
          @if (rows().length === 0) {
            <div class="cp-empty">No models match these filters.</div>
          } @else {
            <div class="table-scroll">
              <table class="htable">
                <thead>
                  <tr>
                    <th>Model</th><th>Upstream id</th>
                    <th class="num">Input $/1M</th><th class="num">Output $/1M</th>
                    <th class="num">Cached in $/1M</th><th class="num">Cache write $/1M</th>
                    <th class="num">Context</th><th class="num">Max out</th>
                    <th class="num">Intel</th><th>Capabilities</th>
                  </tr>
                </thead>
                <tbody>
                  @for (r of rows(); track r.id) {
                    <tr>
                      <td>
                        <a class="mlink" [routerLink]="['/models', r.id]">{{ r.name }}</a>
                        <span class="mlink-mod">{{ r.modality }}</span>
                      </td>
                      <td class="mono">{{ r.h.upstreamModelId }}</td>
                      <td class="num price">{{ price(r.h.inputPer1kMicro) }}</td>
                      <td class="num price">{{ price(r.h.outputPer1kMicro) }}</td>
                      <td class="num price" [class.dim]="r.h.cachedInputPer1kMicro == null">{{ price(r.h.cachedInputPer1kMicro) }}</td>
                      <td class="num price" [class.dim]="r.h.cacheWritePer1kMicro == null">{{ price(r.h.cacheWritePer1kMicro) }}</td>
                      <td class="num mono">{{ ctx(r.h.contextWindow) }}</td>
                      <td class="num mono">{{ ctx(r.h.maxOutput) }}</td>
                      <td class="num mono" [class.dim]="r.intel == null">{{ r.intel ?? '—' }}</td>
                      <td>
                        @for (c of caps(r.h); track c.key) {
                          <span class="cap"><vx-icon [name]="c.key" />{{ c.label }}</span>
                        }
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </div>
      </section>
    }
  `,
})
export class ProviderDetail {
  readonly svc = inject(CatalogService);
  private route = inject(ActivatedRoute);
  readonly filter = signal<FilterState>(emptyFilter());
  readonly sort = signal<SortKey>('newest');
  readonly id = toSignal(this.route.paramMap.pipe(map((p) => p.get('id') ?? '')), {
    initialValue: '',
  });

  constructor() {
    this.svc.load();
  }

  readonly provider = computed(() => this.svc.providers().find((p) => p.id === this.id()));
  readonly displayName = computed(() => {
    const p = this.provider();
    return p ? providerDisplayName(p.id, p.name) : '';
  });
  readonly desc = computed(() => PROVIDER_DESC[this.id()] ?? '');
  readonly allCount = computed(
    () => (this.svc.models() ?? []).filter((m) => m.hosts.some((h) => h.host === this.id())).length,
  );

  readonly rows = computed(() => {
    const id = this.id();
    const f = this.filter();
    const list = (this.svc.models() ?? [])
      .filter((m) => m.hosts.some((h) => h.host === id) && matchesFilters(m, f))
      .map((m) => ({
        id: m.id,
        name: m.displayName,
        modality: m.modality,
        intel: m.intelligenceIndex ?? null,
        h: m.hosts.find((h) => h.host === id)!,
      }));
    return sortRows(list, this.sort());
  });

  caps(h: HostModel) {
    return CAPS.filter((c) => h.supportedFeatures?.[c.key as keyof SupportedFeatures]);
  }
  mark = pmark;
  ink = pmarkInk;
  price = money1M;
  ctx = fmtCtx;
}
