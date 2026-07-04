import { Component, inject } from '@angular/core';
import { KjBadgeComponent } from '@kouji-ui/components';
import { KjIconDirective } from '@kouji-ui/core';
import { AuthService } from '../../shared/data/auth-service';
import { MetricsService } from '../../shared/data/metrics-service';

/** Admin Overview hub — org-wide spend, traffic and budget health (plan §D1). */
@Component({
  selector: 'app-overview',
  standalone: true,
  imports: [KjBadgeComponent, KjIconDirective],
  styleUrl: './overview.css',
  template: `
    <section class="page">
      <div class="page-head">
        <div>
          <span class="vx-label">Admin Console</span>
          <h1>Overview</h1>
          <p>
            Org-wide spend, traffic and budget health across
            {{ orgName() }}. Current billing month.
          </p>
        </div>
      </div>

      <!-- KPI tiles -->
      <div class="kpi-grid" data-testid="overview-kpis">
        @for (kpi of kpis; track kpi.label) {
          <div class="kpi">
            <span class="kpi-label vx-label">{{ kpi.label }}</span>
            <span class="kpi-value vx-display">{{ kpi.value }}</span>
            <kj-badge
              [variant]="kpi.trend === 'up' ? 'default' : 'secondary'"
              size="xs"
            >
              <span
                class="kpi-delta-icon"
                [kjIcon]="kpi.trend === 'down' ? 'trending-down' : 'trending-up'"
                kjIconSize="xs"
              ></span>
              {{ kpi.delta }}
            </kj-badge>
          </div>
        }
      </div>

      <!-- Secondary panels -->
      <div class="panel-grid">
        <div class="panel">
          <div class="panel-head">
            <h2>Top spenders</h2>
            <span class="vx-label">by team · this month</span>
          </div>
          <div class="bars">
            @for (row of topSpenders; track row.label) {
              <div class="bar-row">
                <span class="bar-label">{{ row.label }}</span>
                <span class="bar-track">
                  <span class="bar-fill" [style.width.%]="row.pct"></span>
                </span>
                <span class="bar-value vx-mono">{{ row.value }}</span>
              </div>
            }
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h2>Providers</h2>
            <span class="vx-label">request share</span>
          </div>
          <div class="legend">
            @for (row of providerShare; track row.label) {
              <div class="legend-row">
                <span class="dot"></span>
                <span class="legend-label">{{ row.label }}</span>
                <span class="legend-value vx-mono">{{ row.value }}</span>
              </div>
            }
          </div>
        </div>
      </div>
    </section>
  `,
})
export class Overview {
  private readonly auth = inject(AuthService);
  private readonly metrics = inject(MetricsService);

  readonly kpis = this.metrics.overviewKpis();
  readonly topSpenders = this.metrics.topSpenders();
  readonly providerShare = this.metrics.providerShare();

  orgName(): string {
    return this.auth.user()?.orgName ?? 'your organisation';
  }
}
