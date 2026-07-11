import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';
import { CatalogService, type HostModel, type SupportedFeatures } from './catalog.service';
import { Icon } from './icon';
import {
  CAPS,
  fmtCtx,
  isCheapest,
  modelOpenWeights,
  money1M,
  pmark,
} from './catalog.util';

/** /models/:id — one logical model across every host that serves it. */
@Component({
  selector: 'vx-model-detail',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, Icon],
  template: `
    @if (svc.models() === null) {
      <section class="cp-hero"><div class="wrap"><div class="cp-empty">Loading…</div></div></section>
    } @else if (!model()) {
      <section class="cp-hero">
        <div class="wrap">
          <button class="cat-back" routerLink="/models"><vx-icon name="back" />All models</button>
          <div class="cp-empty">Model not found.</div>
        </div>
      </section>
    } @else {
      <section class="cp-hero">
        <div class="wrap">
          <button class="cat-back" routerLink="/models"><vx-icon name="back" />All providers &amp; models</button>
          <h1 class="cp-h1 model-h1">
            {{ model()!.displayName }}
            @if (openWeights()) { <span class="ow-badge">Open weights</span> }
            <span class="modality" [class]="'modality ' + model()!.modality">{{ model()!.modality }}</span>
          </h1>
          @if (description()) { <p class="cp-lede">{{ description() }}</p> }
          <div class="dmeta">
            <div class="dmeta-item"><div class="k">Knowledge cutoff</div><div class="v">{{ knowledge() || '—' }}</div></div>
            <div class="dmeta-item"><div class="k">Released</div><div class="v">{{ released() || '—' }}</div></div>
            <div class="dmeta-item"><div class="k">Input modalities</div><div class="v">{{ inputMods() || '—' }}</div></div>
            <div class="dmeta-item"><div class="k">Hosts</div><div class="v">{{ model()!.hosts.length }} providers</div></div>
            @if (model()!.intelligenceIndex != null) {
              <div class="dmeta-item"><div class="k">Intelligence</div><div class="v">{{ model()!.intelligenceIndex }}</div></div>
            }
            @if (model()!.codingIndex != null) {
              <div class="dmeta-item"><div class="k">Coding</div><div class="v">{{ model()!.codingIndex }}</div></div>
            }
          </div>
        </div>
      </section>

      <section class="cp-body">
        <div class="wrap">
          <div class="cp-kicker">
            <div class="eyebrow"><span class="tick"></span>AVAILABLE ON {{ model()!.hosts.length }} PROVIDERS</div>
          </div>
          <div class="table-scroll">
            <table class="htable">
              <thead>
                <tr>
                  <th>Provider</th><th>Upstream id</th>
                  <th class="num">Input $/1M</th><th class="num">Output $/1M</th>
                  <th class="num">Cached in $/1M</th><th class="num">Cache write $/1M</th>
                  <th class="num">Context</th><th class="num">Max out</th>
                  <th>Regions</th><th>Capabilities</th>
                </tr>
              </thead>
              <tbody>
                @for (h of model()!.hosts; track h.host) {
                  <tr>
                    <td>
                      <a class="prov-cell" [routerLink]="['/providers', h.host]">
                        <span class="pmark" [style.background]="brand(h.host)" [style.width.px]="26" [style.height.px]="26" [style.fontSize.px]="12">{{ mark(h.host) }}</span>
                        <span class="pname">{{ name(h.host) }}</span>
                      </a>
                    </td>
                    <td class="mono">{{ h.upstreamModelId }}</td>
                    <td class="num price" [class.cheap]="cheapest(h)">
                      {{ price(h.inputPer1kMicro) }}
                      @if (cheapest(h)) { <span class="cheap-tag">Cheapest</span> }
                    </td>
                    <td class="num price">{{ price(h.outputPer1kMicro) }}</td>
                    <td class="num price" [class.dim]="h.cachedInputPer1kMicro == null">{{ price(h.cachedInputPer1kMicro) }}</td>
                    <td class="num price" [class.dim]="h.cacheWritePer1kMicro == null">{{ price(h.cacheWritePer1kMicro) }}</td>
                    <td class="num mono">{{ ctx(h.contextWindow) }}</td>
                    <td class="num mono">{{ ctx(h.maxOutput) }}</td>
                    <td>
                      @for (r of h.regions ?? []; track r) { <span class="rg">{{ r }}</span> }
                      @if (!(h.regions?.length)) { <span class="dim">—</span> }
                    </td>
                    <td>
                      @for (c of caps(h); track c.key) {
                        <span class="cap"><vx-icon [name]="c.key" />{{ c.label }}</span>
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      </section>
    }
  `,
})
export class ModelDetail {
  readonly svc = inject(CatalogService);
  private route = inject(ActivatedRoute);
  readonly id = toSignal(this.route.paramMap.pipe(map((p) => p.get('id') ?? '')), {
    initialValue: '',
  });

  constructor() {
    this.svc.load();
  }

  readonly model = computed(() => (this.svc.models() ?? []).find((m) => m.id === this.id()));
  readonly openWeights = computed(() => (this.model() ? modelOpenWeights(this.model()!) : false));
  readonly description = computed(() => this.model()?.hosts.find((h) => h.description)?.description ?? '');
  readonly knowledge = computed(() => this.model()?.hosts.find((h) => h.knowledge)?.knowledge ?? '');
  readonly released = computed(() => this.model()?.hosts.find((h) => h.releaseDate)?.releaseDate ?? '');
  readonly inputMods = computed(() => {
    const m = this.model()?.hosts.find((h) => h.modalities)?.modalities?.input ?? [];
    return m.map((s) => s[0].toUpperCase() + s.slice(1)).join(' · ');
  });

  private providerMap = computed(() => new Map(this.svc.providers().map((p) => [p.id, p])));
  brand(host: string): string {
    return this.providerMap().get(host)?.brandColor ?? '#666';
  }
  name(host: string): string {
    return this.providerMap().get(host)?.name ?? host;
  }
  cheapest(h: HostModel): boolean {
    return this.model() ? isCheapest(this.model()!, h) : false;
  }
  caps(h: HostModel) {
    return CAPS.filter((c) => h.supportedFeatures?.[c.key as keyof SupportedFeatures]);
  }
  mark = pmark;
  price = money1M;
  ctx = fmtCtx;
}
