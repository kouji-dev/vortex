import { Component, computed, inject, signal } from '@angular/core';
import {
  PlatformService,
  formatUsd,
  formatCount,
  type Tenant,
  type UsageRow,
} from '../../shared/data/platform-service';

/** Platform Overview — cross-tenant KPIs (plan §D2). */
@Component({
  selector: 'app-overview',
  standalone: true,
  imports: [],
  styleUrls: ['../_shared/console.css', './overview.css'],
  template: `
    <section class="page">
      <div class="page-head">
        <div>
          <span class="vx-label">Super-admin</span>
          <h1>Overview</h1>
          <p>Tenant, spend and traffic health across the Vortex SaaS. Current billing month.</p>
        </div>
      </div>

      @if (error()) {
        <div class="banner err" data-testid="overview-error">{{ error() }}</div>
      }

      <div class="kpi-grid" data-testid="overview-kpis">
        <div class="kpi">
          <span class="vx-label">Total tenants</span>
          <span class="kpi-value vx-display">{{ tenants().length }}</span>
          <span class="kpi-sub">{{ activeCount() }} active · {{ suspendedCount() }} suspended</span>
        </div>
        <div class="kpi">
          <span class="vx-label">Total spend · MTD</span>
          <span class="kpi-value vx-display">{{ totalSpend() }}</span>
          <span class="kpi-sub">across all tenants</span>
        </div>
        <div class="kpi">
          <span class="vx-label">Requests</span>
          <span class="kpi-value vx-display">{{ totalRequests() }}</span>
          <span class="kpi-sub">{{ totalTokens() }} tokens</span>
        </div>
        <div class="kpi">
          <span class="vx-label">New tenants · 30d</span>
          <span class="kpi-value vx-display">{{ newTenants() }}</span>
          <span class="kpi-sub">recently provisioned</span>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h2>Top tenants</h2>
          <span class="vx-label">by spend · this month</span>
        </div>
        @if (loading()) {
          <div class="empty">Loading…</div>
        } @else if (topTenants().length === 0) {
          <div class="empty">No tenants yet.</div>
        } @else {
          <div class="tbl-wrap">
            <table class="tbl">
              <thead>
                <tr>
                  <th>Tenant</th>
                  <th>Status</th>
                  <th class="num">Members</th>
                  <th class="num">Apps</th>
                  <th class="num">Spend</th>
                </tr>
              </thead>
              <tbody>
                @for (t of topTenants(); track t.id) {
                  <tr>
                    <td class="strong">{{ t.name }}</td>
                    <td>{{ t.status }}</td>
                    <td class="num">{{ t.members }}</td>
                    <td class="num">{{ t.apps }}</td>
                    <td class="num">{{ usd(t.spendMicro) }}</td>
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
export class Overview {
  private readonly platform = inject(PlatformService);

  readonly tenants = signal<Tenant[]>([]);
  readonly usageRows = signal<UsageRow[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  readonly activeCount = computed(
    () => this.tenants().filter((t) => t.status === 'active').length,
  );
  readonly suspendedCount = computed(
    () => this.tenants().filter((t) => t.status === 'suspended').length,
  );
  readonly totalSpend = computed(() =>
    formatUsd(this.tenants().reduce((s, t) => s + (t.spendMicro ?? 0), 0)),
  );
  readonly totalRequests = computed(() =>
    formatCount(this.usageRows().reduce((s, r) => s + (r.requests ?? 0), 0)),
  );
  readonly totalTokens = computed(() =>
    formatCount(this.usageRows().reduce((s, r) => s + (r.totalTokens ?? 0), 0)),
  );
  readonly newTenants = computed(() => {
    const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;
    return this.tenants().filter((t) => {
      const ts = Date.parse(t.createdAt ?? '');
      return !Number.isNaN(ts) && ts >= cutoff;
    }).length;
  });
  readonly topTenants = computed(() =>
    [...this.tenants()].sort((a, b) => (b.spendMicro ?? 0) - (a.spendMicro ?? 0)).slice(0, 8),
  );

  usd = formatUsd;

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const [tenants, usage] = await Promise.all([
        this.platform.tenants(),
        this.platform.usage(),
      ]);
      this.tenants.set(tenants);
      this.usageRows.set(usage);
    } catch {
      this.error.set('Could not load platform metrics.');
    } finally {
      this.loading.set(false);
    }
  }
}
