import { Component, computed, inject, signal } from '@angular/core';
import {
  KjBadgeComponent,
  KjButtonComponent,
  KjCardComponent,
  KjCellTemplateDirective,
  KjTableComponent,
  KjTagComponent,
  KjToggleComponent,
} from '@kouji-ui/components';
import { KjIconDirective, kjColumn, type KjColumnDef } from '@kouji-ui/core';
import {
  CatalogModel,
  ProviderCredential,
  ProviderKey,
  ProvidersData,
} from './providers.data';

/** Providers & Models — BYOK credentials + the gateway model catalog (plan §D5). */
@Component({
  selector: 'app-providers',
  standalone: true,
  imports: [
    KjBadgeComponent,
    KjButtonComponent,
    KjCardComponent,
    KjCellTemplateDirective,
    KjTableComponent,
    KjTagComponent,
    KjToggleComponent,
    KjIconDirective,
  ],
  styleUrl: './providers.css',
  template: `
    <section class="page">
      <div class="page-tabs" role="tablist">
        <button
          class="page-tab"
          [class.active]="tab() === 'credentials'"
          (click)="tab.set('credentials')"
          data-testid="tab-credentials"
        >
          Credentials
        </button>
        <button
          class="page-tab"
          [class.active]="tab() === 'models'"
          (click)="tab.set('models')"
          data-testid="tab-models"
        >
          Models
        </button>
      </div>

      @switch (tab()) {
        @case ('credentials') {
          <!-- ── Provider credentials ─────────────────────────── -->
          <div class="page-head">
            <div>
              <span class="vx-label">Admin Console</span>
              <h1>Provider Credentials</h1>
              <p>
                BYO provider keys — encrypted at rest and scoped org / team /
                app. {{ credentials.length }} connected.
              </p>
            </div>
            <kj-button kjVariant="primary" kjSize="sm" (click)="openModal()">
              <span [kjIcon]="'plus'" kjIconSize="sm"></span>
              Add provider credential
            </kj-button>
          </div>

          <div class="cred-grid" data-testid="provider-cards">
          @for (c of credentials; track c.name) {
            <kj-card class="cred-card" [class.is-invalid]="c.status === 'invalid'">
              <!-- brand dot · name / scope · edit -->
              <div class="cred-top">
                <span class="prov-dot" [style.background]="meta(c.prov).color">{{
                  meta(c.prov).letter
                }}</span>
                <div class="cred-id">
                  <span class="cred-name">{{ c.name }}</span>
                  <span class="cred-scope">{{ c.scope }}</span>
                </div>
                <button
                  class="icon-btn"
                  type="button"
                  aria-label="Edit credential"
                  (click)="edit(c)"
                >
                  <span [kjIcon]="'wrench'" kjIconSize="sm"></span>
                </button>
              </div>

              <!-- status pill · encrypted / scope tags · updated -->
              <div class="cred-tags">
                <kj-badge
                  [variant]="c.status === 'valid' ? 'default' : 'destructive'"
                  size="xs"
                  dot="true"
                  [dotColor]="c.status === 'valid' ? 'var(--vx-good)' : 'var(--vx-err)'"
                >
                  {{ c.status === 'valid' ? 'valid' : 'invalid' }}
                </kj-badge>
                <kj-tag>
                  <span [kjIcon]="'lock'" kjIconSize="xs"></span>
                  encrypted
                </kj-tag>
                <kj-tag>
                  <span [kjIcon]="c.managed ? 'sparkle' : 'key'" kjIconSize="xs"></span>
                  {{ c.managed ? 'Managed' : 'BYOK' }}
                </kj-tag>
                <span class="cred-updated vx-mono">updated {{ c.updated }}</span>
              </div>

              <!-- masked key -->
              <div class="cred-key">
                <span class="key-mask vx-mono">{{ c.keyMask }}</span>
              </div>

              @if (c.status === 'invalid') {
                <p class="cred-warn">
                  <span [kjIcon]="'lock'" kjIconSize="sm"></span>
                  Credential rejected on last check. Requests are failing over.
                </p>
              }

              <!-- actions -->
              <div class="cred-foot">
                <kj-button kjVariant="ghost" kjSize="xs" (click)="test(c)">Test</kj-button>
                <kj-button kjVariant="ghost" kjSize="xs" (click)="rotate(c)">Rotate</kj-button>
                <kj-button kjVariant="ghost" kjSize="xs" (click)="edit(c)">Edit</kj-button>
              </div>
            </kj-card>
          }
          </div>
        }

        @case ('models') {
          <!-- ── Model catalog ────────────────────────────────── -->
          <div class="page-head">
            <div>
              <span class="vx-label">Admin Console</span>
              <h1>Model Catalog</h1>
              <p>
                Every model available through the gateway — price, context
                window and per-model enablement.
                {{ enabledCount() }} enabled · {{ models.length }} total.
              </p>
            </div>
          </div>

          <div class="catalog-toolbar">
          <label class="search">
            <span [kjIcon]="'search'" kjIconSize="sm"></span>
            <input
              type="search"
              placeholder="Search models…"
              [value]="search()"
              (input)="onSearch($event)"
              data-testid="model-search"
            />
          </label>
          <select
            class="prov-select"
            [value]="providerFilter()"
            (change)="onFilter($event)"
            data-testid="model-provider-filter"
          >
            @for (f of providerFilters; track f.value) {
              <option [value]="f.value">{{ f.label }}</option>
            }
          </select>
        </div>

        <kj-table
          class="models-table"
          data-testid="model-table"
          [kjData]="filteredModels()"
          [kjColumns]="modelCols"
          [kjGetRowId]="rowId"
          kjVariant="clean"
        >
          <!-- provider dot + model name / alias -->
          <ng-template kjCellTemplate="model" let-row>
            <span class="model-cell">
              <span class="prov-dot sm" [style.background]="meta(row.prov).color">{{
                meta(row.prov).letter
              }}</span>
              <span class="model-id">
                <span class="model-name">{{ row.name }}</span>
                <span class="model-alias vx-mono">{{ row.alias }}</span>
              </span>
            </span>
          </ng-template>

          <ng-template kjCellTemplate="prov" let-row>
            <kj-tag>{{ meta(row.prov).label }}</kj-tag>
          </ng-template>

          <ng-template kjCellTemplate="ctx" let-row>
            <span class="cell-num vx-mono">{{ row.ctx }}</span>
          </ng-template>

          <ng-template kjCellTemplate="in" let-row>
            <span class="cell-num vx-mono">\${{ row.in.toFixed(2) }}</span>
          </ng-template>

          <ng-template kjCellTemplate="out" let-row>
            <span class="cell-num vx-mono">\${{ row.out.toFixed(2) }}</span>
          </ng-template>

          <!-- enabled switch -->
          <ng-template kjCellTemplate="on" let-row>
            <kj-toggle
              appearance="switch"
              size="sm"
              [pressed]="row.on"
              (pressedChange)="toggle(row, $event)"
              [ariaLabel]="'Toggle ' + row.alias"
            ></kj-toggle>
          </ng-template>

          <div kjEmpty class="empty">No models match your filters.</div>
        </kj-table>
        }
      }
    </section>

    <!-- ── Add credential modal (client-side) ─────────────────── -->
    @if (modalOpen()) {
      <div class="scrim" (click)="closeModal()">
        <div
          class="modal"
          role="dialog"
          aria-modal="true"
          aria-label="Add provider credential"
          (click)="$event.stopPropagation()"
          data-testid="credential-modal"
        >
          <div class="modal-head">
            <span class="vx-label">New credential</span>
            <h3>Add provider credential</h3>
            <button class="icon-x" type="button" aria-label="Close" (click)="closeModal()">
              <span [kjIcon]="'x'" kjIconSize="sm"></span>
            </button>
          </div>

          <div class="modal-body">
            <label class="field">
              <span class="field-label">Provider</span>
              <select [value]="form.prov()" (change)="form.prov.set($any($event.target).value)">
                @for (o of providerOptions; track o.value) {
                  <option [value]="o.value">{{ o.label }}</option>
                }
              </select>
            </label>

            <label class="field">
              <span class="field-label">API key</span>
              <input
                type="password"
                class="vx-mono"
                placeholder="sk-…"
                [value]="form.key()"
                (input)="form.key.set($any($event.target).value)"
              />
              <span class="field-hint">Encrypted with AES-256 before storage.</span>
            </label>

            <div class="field">
              <span class="field-label">Scope</span>
              <div class="seg">
                @for (s of scopes; track s) {
                  <button
                    type="button"
                    class="seg-btn"
                    [class.active]="form.scope() === s"
                    (click)="form.scope.set(s)"
                  >
                    {{ s }}
                  </button>
                }
              </div>
              <span class="field-hint"
                >Org-scoped credentials apply everywhere unless overridden by team or app.</span
              >
            </div>

            <div class="test-row">
              <div>
                <span class="field-label">Test connection</span>
                <span class="field-hint">Verify the key before saving.</span>
              </div>
              <kj-button kjVariant="secondary" kjSize="sm" (click)="testForm()">
                <span [kjIcon]="'sparkle'" kjIconSize="sm"></span>
                Test
              </kj-button>
            </div>

            @if (toast()) {
              <p class="toast">{{ toast() }}</p>
            }
          </div>

          <div class="modal-foot">
            <kj-button kjVariant="ghost" kjSize="sm" (click)="closeModal()">Cancel</kj-button>
            <kj-button kjVariant="primary" kjSize="sm" (click)="save()">
              <span [kjIcon]="'lock'" kjIconSize="sm"></span>
              Save credential
            </kj-button>
          </div>
        </div>
      </div>
    }
  `,
})
export class Providers {
  private readonly data = inject(ProvidersData);

  readonly credentials = this.data.credentials();
  readonly models = this.data.models();
  readonly providerFilters = this.data.providerFilters();
  readonly providerOptions = this.data.providerOptions();
  readonly scopes = ['Organization', 'Team', 'App'] as const;

  /** kj-table column defs — cells are rendered via `kjCellTemplate` slots. */
  readonly modelCols: KjColumnDef<CatalogModel>[] = [
    kjColumn<CatalogModel>({ id: 'model', accessorKey: 'name', header: 'Model' }),
    kjColumn<CatalogModel>({ id: 'prov', accessorKey: 'prov', header: 'Provider' }),
    kjColumn<CatalogModel>({ id: 'ctx', accessorKey: 'ctx', header: 'Context' }),
    kjColumn<CatalogModel>({ id: 'in', accessorKey: 'in', header: 'Input / 1M' }),
    kjColumn<CatalogModel>({ id: 'out', accessorKey: 'out', header: 'Output / 1M' }),
    kjColumn<CatalogModel>({ id: 'on', accessorKey: 'on', header: 'Enabled' }),
  ];

  readonly rowId = (m: CatalogModel): string => m.alias;

  /** Local switch overrides so toggling in the table is reflected live. */
  private readonly modelState = signal<Record<string, boolean>>(
    Object.fromEntries(this.models.map((m) => [m.alias, m.on])),
  );

  readonly tab = signal<'credentials' | 'models'>('credentials');
  readonly search = signal('');
  readonly providerFilter = signal<'all' | ProviderKey>('all');
  readonly modalOpen = signal(false);
  readonly toast = signal('');

  readonly form = {
    prov: signal<ProviderKey>('anthropic'),
    key: signal(''),
    scope: signal<string>('Organization'),
  };

  readonly filteredModels = computed(() => {
    const q = this.search().trim().toLowerCase();
    const prov = this.providerFilter();
    return this.models
      .map((m) => ({ ...m, on: this.modelState()[m.alias] }))
      .filter((m) => prov === 'all' || m.prov === prov)
      .filter(
        (m) => !q || m.name.toLowerCase().includes(q) || m.alias.toLowerCase().includes(q),
      );
  });

  readonly enabledCount = computed(
    () => Object.values(this.modelState()).filter(Boolean).length,
  );

  meta(prov: ProviderKey) {
    return this.data.meta(prov);
  }

  onSearch(e: Event): void {
    this.search.set((e.target as HTMLInputElement).value);
  }

  onFilter(e: Event): void {
    this.providerFilter.set((e.target as HTMLSelectElement).value as 'all' | ProviderKey);
  }

  toggle(m: CatalogModel, pressed: boolean): void {
    this.modelState.update((s) => ({ ...s, [m.alias]: pressed }));
  }

  // Credential actions (client-side stubs until the admin API lands).
  test(c: ProviderCredential): void {
    void c;
  }
  rotate(c: ProviderCredential): void {
    void c;
  }
  edit(c: ProviderCredential): void {
    this.openModal();
  }

  openModal(): void {
    this.toast.set('');
    this.modalOpen.set(true);
  }
  closeModal(): void {
    this.modalOpen.set(false);
  }
  testForm(): void {
    this.toast.set('Connection OK ✓');
  }
  save(): void {
    this.closeModal();
  }
}
