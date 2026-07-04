import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  PlatformService,
  formatUsd,
  formatCount,
  type UsageRow,
} from '../../shared/data/platform-service';

/** Usage — cross-tenant table sliceable by tenant / provider / model (plan §D2). */
@Component({
  selector: 'app-usage',
  standalone: true,
  imports: [FormsModule],
  styleUrls: ['../_shared/console.css'],
  template: `
    <section class="page">
      <div class="page-head">
        <div>
          <span class="vx-label">Super-admin</span>
          <h1>Usage</h1>
          <p>Cross-tenant requests, tokens and cost — slice by tenant, provider or model.</p>
        </div>
      </div>

      @if (error()) {
        <div class="banner err" data-testid="usage-error">{{ error() }}</div>
      }

      <div class="card">
        <div class="toolbar">
          <div class="filter">
            <span class="vx-label">Tenant</span>
            <select data-testid="filter-tenant" [ngModel]="tenant()" (ngModelChange)="tenant.set($event)">
              <option value="">All tenants</option>
              @for (o of tenantOptions(); track o) {
                <option [value]="o">{{ o }}</option>
              }
            </select>
          </div>
          <div class="filter">
            <span class="vx-label">Provider</span>
            <select data-testid="filter-provider" [ngModel]="provider()" (ngModelChange)="provider.set($event)">
              <option value="">All providers</option>
              @for (o of providerOptions(); track o) {
                <option [value]="o">{{ o }}</option>
              }
            </select>
          </div>
          <div class="filter">
            <span class="vx-label">Model</span>
            <select data-testid="filter-model" [ngModel]="model()" (ngModelChange)="model.set($event)">
              <option value="">All models</option>
              @for (o of modelOptions(); track o) {
                <option [value]="o">{{ o }}</option>
              }
            </select>
          </div>
          <div class="spacer"></div>
          <div class="filter">
            <span class="vx-label">Total cost</span>
            <span class="kpi-value vx-display" data-testid="usage-total">{{ totalCost() }}</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h2>Usage records</h2>
          <span class="vx-label">{{ filtered().length }} rows</span>
        </div>
        @if (loading()) {
          <div class="empty">Loading…</div>
        } @else if (filtered().length === 0) {
          <div class="empty" data-testid="usage-empty">No usage for the current filters.</div>
        } @else {
          <div class="tbl-wrap">
            <table class="tbl" data-testid="usage-table">
              <thead>
                <tr>
                  <th>Tenant</th>
                  <th>Provider</th>
                  <th>Model</th>
                  <th class="num">Requests</th>
                  <th class="num">Tokens</th>
                  <th class="num">Cost</th>
                </tr>
              </thead>
              <tbody>
                @for (r of filtered(); track $index) {
                  <tr>
                    <td class="strong mono">{{ r.orgId }}</td>
                    <td>{{ r.provider }}</td>
                    <td class="mono">{{ r.model }}</td>
                    <td class="num">{{ count(r.requests) }}</td>
                    <td class="num">{{ count(r.totalTokens) }}</td>
                    <td class="num">{{ usd(r.costMicro) }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      </div>
    </section>
  `,
})
export class Usage {
  private readonly platform = inject(PlatformService);

  readonly rows = signal<UsageRow[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  tenant = signal('');
  provider = signal('');
  model = signal('');

  readonly tenantOptions = computed(() => this.distinct((r) => r.orgId));
  readonly providerOptions = computed(() => this.distinct((r) => r.provider));
  readonly modelOptions = computed(() => this.distinct((r) => r.model));

  readonly filtered = computed(() =>
    this.rows().filter(
      (r) =>
        (!this.tenant() || r.orgId === this.tenant()) &&
        (!this.provider() || r.provider === this.provider()) &&
        (!this.model() || r.model === this.model()),
    ),
  );

  readonly totalCost = computed(() =>
    formatUsd(this.filtered().reduce((s, r) => s + (r.costMicro ?? 0), 0)),
  );

  usd = formatUsd;
  count = formatCount;

  constructor() {
    void this.load();
  }

  private distinct(pick: (r: UsageRow) => string): string[] {
    return [...new Set(this.rows().map(pick))].filter(Boolean).sort();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      this.rows.set(await this.platform.usage());
      this.error.set(null);
    } catch {
      this.error.set('Could not load usage.');
    } finally {
      this.loading.set(false);
    }
  }
}
