import { Injectable, signal } from '@angular/core';
import { API_URL } from '../landing/landing.tokens';

// Catalog shapes are the single source of truth in @vortex/core. These are
// TYPE-ONLY re-exports — erased at build, so no server code (env/redis) is
// pulled into the marketing bundle. Data is fetched from GET /v1/catalog.
export type {
  SupportedFeatures,
  Modalities,
  HostModel,
  CatalogModel,
  HostMeta,
} from '@vortex/core/catalog';

import type { CatalogModel, HostMeta } from '@vortex/core/catalog';

/** Shape of the public /v1/catalog response (landing-specific). */
export interface CatalogData {
  models: CatalogModel[];
  providers: HostMeta[];
}

@Injectable({ providedIn: 'root' })
export class CatalogService {
  /** null = not loaded yet, [] resolved. Signals drive the components. */
  readonly models = signal<CatalogModel[] | null>(null);
  readonly providers = signal<HostMeta[]>([]);
  readonly error = signal<string | null>(null);

  private started = false;

  /** Fetch the catalog once (browser only — avoids SSR coupling to the API). */
  load(): void {
    if (this.started || typeof fetch === 'undefined') return;
    this.started = true;
    fetch(`${API_URL}/v1/catalog`)
      .then((r) => {
        if (!r.ok) throw new Error(`catalog ${r.status}`);
        return r.json() as Promise<CatalogData>;
      })
      .then((d) => {
        this.providers.set(d.providers ?? []);
        this.models.set(d.models ?? []);
      })
      .catch((e) => this.error.set(String(e?.message ?? e)));
  }

  meta(providers: HostMeta[], id: string): HostMeta | undefined {
    return providers.find((p) => p.id === id);
  }
}
