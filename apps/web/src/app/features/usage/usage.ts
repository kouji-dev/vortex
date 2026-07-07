import { Component, computed, inject, signal } from '@angular/core';
import { KjBadgeComponent, KjButtonComponent } from '@kouji-ui/components';
import { KjIconDirective } from '@kouji-ui/core';
import { AuthService } from '../../shared/data/auth-service';
import {
  UsageData,
  type BreakdownRow,
  type CostDim,
  type DateRange,
  type LogStatus,
  type MemberBudget,
} from './usage.data';

/**
 * Usage & Budgets admin screen (plan §D2) — cost explorer, per-member
 * budgets and a live request log. Data from {@link UsageData}; sliced
 * client-side via signals until the analytics API lands.
 */
@Component({
  selector: 'app-usage',
  standalone: true,
  imports: [KjBadgeComponent, KjButtonComponent, KjIconDirective],
  styleUrl: './usage.css',
  template: `
    <section class="page">
      @if (auth.isAdmin()) {
      <div class="page-tabs">
        <button class="page-tab" [class.active]="tab() === 'usage'" (click)="tab.set('usage')">Usage</button>
        <button class="page-tab" [class.active]="tab() === 'budgets'" (click)="tab.set('budgets')">Budgets</button>
        <button class="page-tab" [class.active]="tab() === 'logs'" (click)="tab.set('logs')">Logs</button>
      </div>

      @switch (tab()) {
        @case ('usage') {
      <div class="page-head">
        <div>
          <span class="vx-label">Admin Console</span>
          <h1>Usage</h1>
          <p>
            Attribute every dollar along any dimension — team, member, app,
            API key or model — then drill down and flag spikes.
            Current billing month.
          </p>
        </div>
        <div class="head-actions">
          <kj-button kjVariant="ghost" kjSize="sm">
            <span [kjIcon]="'upload'" kjIconSize="xs"></span>
            Export CSV
          </kj-button>
          <kj-button kjVariant="ghost" kjSize="sm">
            <span [kjIcon]="'bell'" kjIconSize="xs"></span>
            Schedule
          </kj-button>
        </div>
      </div>

      <!-- ── Cost explorer ── -->
      <div class="panel">
        <div class="panel-head">
          <h2>Cost explorer</h2>
          <div class="range-toggle" role="tablist" aria-label="Date range">
            @for (r of data.ranges; track r.id) {
              <button
                type="button"
                class="seg"
                [class.on]="range() === r.id"
                (click)="range.set(r.id)"
              >
                {{ r.label }}
              </button>
            }
          </div>
        </div>

        <!-- dimension slicer -->
        <div class="dim-tabs" role="tablist" aria-label="Slice by dimension">
          @for (d of data.dimensions; track d.id) {
            <button
              type="button"
              class="dim-tab"
              [class.on]="dim() === d.id"
              (click)="dim.set(d.id)"
            >
              {{ d.label }}
            </button>
          }
        </div>

        <!-- KPI tiles -->
        <div class="kpi-grid">
          @for (kpi of kpis(); track kpi.label) {
            <div class="kpi">
              <span class="kpi-label vx-label">{{ kpi.label }}</span>
              <span class="kpi-value vx-display">{{ kpi.value }}</span>
            </div>
          }
        </div>

        <!-- spend chart -->
        <div class="chart-wrap">
          <span class="vx-label">Spend over time · {{ rangeLabel() }}</span>
          <div class="chart">
            @for (p of spendSeries(); track $index) {
              <div class="chart-col" [title]="money(p.value)">
                <span class="chart-bar" [style.height.%]="spendBarPct(p.value)"></span>
                <span class="chart-tick">{{ p.label }}</span>
              </div>
            }
          </div>
        </div>

        <!-- breakdown table -->
        <div class="table-wrap">
          <table class="vx-table">
            <thead>
              <tr>
                <th>{{ dimLabel() }}</th>
                <th class="num">Requests</th>
                <th class="num">Tokens</th>
                <th class="num">Cost</th>
                <th class="num">% share</th>
                <th class="num">Trend</th>
              </tr>
            </thead>
            <tbody>
              @for (row of rows(); track row.label) {
                <tr>
                  <td>
                    <span class="cell-main">
                      @if (row.technical) {
                        <span class="glyph" [kjIcon]="'cpu'" kjIconSize="xs"></span>
                      }
                      <span class="cell-label">{{ row.label }}</span>
                      @if (row.spike) {
                        <kj-badge variant="secondary" size="xs">
                          <span [kjIcon]="'trending-up'" kjIconSize="xs"></span> spike
                        </kj-badge>
                      }
                    </span>
                    @if (row.sub) {
                      <span class="cell-sub">{{ row.sub }}</span>
                    }
                  </td>
                  <td class="num vx-mono">{{ compact(row.requests) }}</td>
                  <td class="num vx-mono">{{ compact(row.tokens) }}</td>
                  <td class="num vx-mono strong">{{ money(row.cost) }}</td>
                  <td class="num">
                    <span class="share">
                      <span class="share-track">
                        <span class="share-fill" [style.width.%]="sharePct(row)"></span>
                      </span>
                      <span class="vx-mono">{{ sharePct(row).toFixed(1) }}%</span>
                    </span>
                  </td>
                  <td class="num">
                    <kj-badge [variant]="row.trend >= 0 ? 'default' : 'secondary'" size="xs">
                      <span
                        [kjIcon]="row.trend >= 0 ? 'trending-up' : 'trending-down'"
                        kjIconSize="xs"
                      ></span>
                      {{ row.trend >= 0 ? '+' : '' }}{{ row.trend.toFixed(1) }}%
                    </kj-badge>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

        }
        @case ('budgets') {
      <div class="page-head">
        <div>
          <span class="vx-label">Admin Console</span>
          <h1>Budgets</h1>
          <p>
            Every budget is per member, per month — the team default, or a
            per-member override. It applies across all apps.
          </p>
        </div>
      </div>

      <!-- ── Budgets ── -->
      <div class="panel">
        <div class="panel-head">
          <h2>Budgets</h2>
          <span class="vx-label">per member · per month</span>
        </div>

        <!-- org rollup -->
        <div class="org-budget">
          <div class="org-budget-head">
            <span class="vx-label">Org spend vs. sum of ceilings</span>
            <span class="vx-mono strong">
              {{ money(data.orgBudget.spent) }} / {{ money(data.orgBudget.ceiling) }}
            </span>
          </div>
          <span class="budget-track lg">
            <span
              class="budget-fill"
              [class]="toneClass(orgFrac())"
              [style.width.%]="pct(orgFrac())"
            ></span>
          </span>
        </div>

        <!-- team defaults -->
        <span class="vx-label section-label">Team defaults</span>
        <div class="team-grid">
          @for (t of data.teamBudgets; track t.name) {
            <div class="team-card">
              <div class="team-card-head">
                <span class="team-avatar">{{ t.name.charAt(0) }}</span>
                <div class="team-meta">
                  <span class="team-name">{{ t.name }}</span>
                  <span class="team-sub">{{ t.members }} members</span>
                </div>
                <kj-badge [variant]="t.enforce === 'hard' ? 'secondary' : 'default'" size="xs">
                  {{ t.enforce }}
                </kj-badge>
              </div>
              <div class="team-figure">
                <span class="vx-display">{{ money(t.def) }}</span>
                <span class="team-sub">default / member</span>
              </div>
              <span class="budget-track">
                <span
                  class="budget-fill"
                  [class]="toneClass(teamFrac(t))"
                  [style.width.%]="pct(teamFrac(t))"
                ></span>
              </span>
              <div class="team-foot">
                <span class="team-sub">
                  {{ t.overrides }} override{{ t.overrides === 1 ? '' : 's' }}
                </span>
                <kj-button kjVariant="ghost" kjSize="sm">Edit default</kj-button>
              </div>
            </div>
          }
        </div>

        <!-- per-member overrides -->
        <span class="vx-label section-label">Per-member budgets &amp; burn</span>
        <div class="table-wrap">
          <table class="vx-table">
            <thead>
              <tr>
                <th>Member</th>
                <th>Source</th>
                <th class="num">Ceiling</th>
                <th>Burn</th>
                <th>Enforce</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (m of data.memberBudgets; track m.name) {
                <tr>
                  <td>
                    <span class="cell-main">
                      @if (m.technical) {
                        <span class="glyph" [kjIcon]="'cpu'" kjIconSize="xs"></span>
                      }
                      <span class="cell-label">{{ m.name }}</span>
                    </span>
                    <span class="cell-sub">{{ m.team }} team</span>
                  </td>
                  <td>
                    <kj-badge [variant]="m.source === 'override' ? 'default' : 'secondary'" size="xs">
                      {{ m.source === 'override' ? 'Override' : 'Team default' }}
                    </kj-badge>
                  </td>
                  <td class="num vx-mono strong">{{ money(m.ceiling) }}</td>
                  <td>
                    <div class="burn">
                      <div class="burn-head">
                        <span class="vx-mono" [class.over]="memberFrac(m) >= 1">
                          {{ money(m.spent) }}
                        </span>
                        <span class="vx-mono muted">{{ (memberFrac(m) * 100).toFixed(0) }}%</span>
                      </div>
                      <span class="budget-track">
                        <span
                          class="budget-fill"
                          [class]="toneClass(memberFrac(m))"
                          [style.width.%]="pct(memberFrac(m))"
                        ></span>
                      </span>
                    </div>
                  </td>
                  <td>
                    <span class="pill" [class]="'pill-' + (m.enforce === 'hard' ? 'err' : 'neutral')">
                      {{ m.enforce }}
                    </span>
                  </td>
                  <td class="num">
                    <kj-button kjVariant="ghost" kjSize="sm">Override</kj-button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

        }
        @case ('logs') {
      <div class="page-head">
        <div>
          <span class="vx-label">Admin Console</span>
          <h1>Request logs</h1>
          <p>
            Recent gateway requests across the org — search by member, app
            or model. Live tail of the last requests.
          </p>
        </div>
      </div>

      <!-- ── Request logs ── -->
      <div class="panel">
        <div class="panel-head">
          <h2>Request logs</h2>
          <div class="search">
            <span class="glyph" [kjIcon]="'search'" kjIconSize="xs"></span>
            <input
              type="search"
              placeholder="Search member, app or model…"
              [value]="logQuery()"
              (input)="logQuery.set($any($event.target).value)"
            />
          </div>
        </div>
        <div class="table-wrap">
          <table class="vx-table logs">
            <thead>
              <tr>
                <th>Time</th>
                <th>Member</th>
                <th>App</th>
                <th>Model</th>
                <th class="num">Tokens in</th>
                <th class="num">Tokens out</th>
                <th class="num">Cost</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              @for (log of filteredLogs(); track $index) {
                <tr>
                  <td class="vx-mono muted">{{ log.time }}</td>
                  <td class="cell-label">{{ log.member }}</td>
                  <td>{{ log.app }}</td>
                  <td class="vx-mono">{{ log.model }}</td>
                  <td class="num vx-mono">{{ compact(log.tokensIn) }}</td>
                  <td class="num vx-mono">{{ compact(log.tokensOut) }}</td>
                  <td class="num vx-mono strong">{{ money(log.cost, 4) }}</td>
                  <td>
                    <span class="pill" [class]="'pill-' + statusTone(log.status)">
                      {{ statusLabel(log.status) }}
                    </span>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="8" class="empty">No requests match “{{ logQuery() }}”.</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>
        }
      }
      } @else {
      <!-- ── Member: My Usage & Budget (scrMyUsage) ── -->
      <div class="page-head">
        <div>
          <span class="vx-label">My Console</span>
          <h1>My Usage &amp; Budget</h1>
          <p>
            Your spend sliced by app and model, and your monthly ceiling.
            Your budget is read-only — it's set by your team default or an
            admin override.
          </p>
        </div>
      </div>

      <!-- ── My spend over time + budget gauge ── -->
      <div class="my-grid">
        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>My spend over time</h2>
              <span class="vx-label">daily · Apr 2026 · micro-USD</span>
            </div>
          </div>
          <svg
            class="area-svg"
            [attr.viewBox]="'0 0 ' + myArea().w + ' ' + myArea().h"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <defs>
              <linearGradient id="vx-my-area-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stop-color="var(--vx-accent)" stop-opacity="0.25" />
                <stop offset="1" stop-color="var(--vx-accent)" stop-opacity="0" />
              </linearGradient>
            </defs>
            @for (g of myArea().grid; track $index) {
              <line
                class="area-grid"
                [attr.x1]="myArea().pl"
                [attr.y1]="g.y"
                [attr.x2]="myArea().w - myArea().pr"
                [attr.y2]="g.y"
              />
              <text class="area-axis" text-anchor="end" [attr.x]="myArea().pl - 8" [attr.y]="g.y + 3">
                {{ g.label }}
              </text>
            }
            @for (x of myArea().xl; track $index) {
              <text class="area-axis" text-anchor="middle" [attr.x]="x.x" [attr.y]="myArea().h - 6">
                {{ x.text }}
              </text>
            }
            <path [attr.d]="myArea().areaPath" fill="url(#vx-my-area-grad)" />
            <path class="area-line accent" [attr.d]="myArea().line" />
          </svg>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>Budget</h2>
              <span class="vx-label">{{ myBudget.team }} team · {{ myBudget.enforce }} cap</span>
            </div>
          </div>
          <div class="gauge-wrap">
            <svg
              class="gauge-svg"
              [attr.width]="myGauge().size"
              [attr.height]="myGauge().size"
              [attr.viewBox]="'0 0 ' + myGauge().size + ' ' + myGauge().size"
              aria-hidden="true"
            >
              <circle
                fill="none"
                stroke="var(--vx-bg-2)"
                stroke-width="9"
                stroke-linecap="round"
                [attr.cx]="myGauge().cx"
                [attr.cy]="myGauge().cy"
                [attr.r]="myGauge().r"
                [attr.stroke-dasharray]="myGauge().full + ' ' + myGauge().C"
                [attr.transform]="'rotate(135 ' + myGauge().cx + ' ' + myGauge().cy + ')'"
              />
              <circle
                fill="none"
                stroke-width="9"
                stroke-linecap="round"
                [attr.stroke]="myGauge().col"
                [attr.cx]="myGauge().cx"
                [attr.cy]="myGauge().cy"
                [attr.r]="myGauge().r"
                [attr.stroke-dasharray]="myGauge().len + ' ' + myGauge().C"
                [attr.transform]="'rotate(135 ' + myGauge().cx + ' ' + myGauge().cy + ')'"
              />
              <text class="gauge-val" text-anchor="middle" [attr.x]="myGauge().cx" [attr.y]="myGauge().cy">
                {{ myGauge().pct }}%
              </text>
              <text class="gauge-lbl" text-anchor="middle" [attr.x]="myGauge().cx" [attr.y]="myGauge().cy + 16">
                OF BUDGET
              </text>
            </svg>
            <div class="gauge-meta">
              <span class="vx-display gauge-left">{{ money(myBudget.ceiling - myBudget.spent) }} left</span>
              <span class="vx-label">of {{ money(myBudget.ceiling) }}/mo</span>
            </div>
            <div class="warnbar info">
              <span class="warn-ico" [kjIcon]="'info'" kjIconSize="sm"></span>
              <span>
                Set by
                <b>{{ myBudget.source === 'override' ? 'an admin override' : myBudget.team + ' team default' }}</b>.
                Contact your team admin to change it.
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- ── My spend by model / app ── -->
      <div class="panel">
        <div class="panel-head">
          <h2>My spend by model &amp; app</h2>
          <span class="vx-label">this month</span>
        </div>
        <span class="vx-label section-label">By model</span>
        <div class="table-wrap">
          <table class="vx-table">
            <thead>
              <tr>
                <th>Model</th>
                <th class="num">Cost</th>
                <th class="num">Share</th>
              </tr>
            </thead>
            <tbody>
              @for (row of mySpendByModel; track row.label) {
                <tr>
                  <td>
                    <span class="cell-main">
                      <span class="glyph" [kjIcon]="'cpu'" kjIconSize="xs"></span>
                      <span class="cell-label">{{ row.label }}</span>
                    </span>
                    <span class="cell-sub">{{ row.sub }}</span>
                  </td>
                  <td class="num vx-mono strong">{{ money(row.cost) }}</td>
                  <td class="num">
                    <span class="share">
                      <span class="share-track">
                        <span class="share-fill" [style.width.%]="mySharePct(row.cost, mySpendByModel)"></span>
                      </span>
                      <span class="vx-mono">{{ mySharePct(row.cost, mySpendByModel).toFixed(0) }}%</span>
                    </span>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>

        <span class="vx-label section-label">By app</span>
        <div class="table-wrap">
          <table class="vx-table">
            <thead>
              <tr>
                <th>App</th>
                <th class="num">Cost</th>
                <th class="num">Share</th>
              </tr>
            </thead>
            <tbody>
              @for (row of mySpendByApp; track row.label) {
                <tr>
                  <td><span class="cell-label">{{ row.label }}</span></td>
                  <td class="num vx-mono strong">{{ money(row.cost) }}</td>
                  <td class="num">
                    <span class="share">
                      <span class="share-track">
                        <span class="share-fill" [style.width.%]="mySharePct(row.cost, mySpendByApp)"></span>
                      </span>
                      <span class="vx-mono">{{ mySharePct(row.cost, mySpendByApp).toFixed(0) }}%</span>
                    </span>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

      <!-- ── My recent request history ── -->
      <div class="panel">
        <div class="panel-head">
          <h2>My recent requests</h2>
          <span class="vx-label">live tail · scoped to you</span>
        </div>
        <div class="table-wrap">
          <table class="vx-table logs">
            <thead>
              <tr>
                <th>Time</th>
                <th>App</th>
                <th>Model</th>
                <th class="num">Tokens in</th>
                <th class="num">Tokens out</th>
                <th class="num">Cost</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              @for (log of myLogs(); track $index) {
                <tr>
                  <td class="vx-mono muted">{{ log.time }}</td>
                  <td>{{ log.app }}</td>
                  <td class="vx-mono">{{ log.model }}</td>
                  <td class="num vx-mono">{{ compact(log.tokensIn) }}</td>
                  <td class="num vx-mono">{{ compact(log.tokensOut) }}</td>
                  <td class="num vx-mono strong">{{ money(log.cost, 4) }}</td>
                  <td>
                    <span class="pill" [class]="'pill-' + statusTone(log.status)">
                      {{ statusLabel(log.status) }}
                    </span>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="7" class="empty">No requests yet this month.</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>
      }
    </section>
  `,
})
export class Usage {
  protected readonly data = inject(UsageData);
  protected readonly auth = inject(AuthService);

  /** Member (scrMyUsage) — the signed-in member's own budget & spend. */
  readonly myBudget = {
    team: 'Platform',
    enforce: 'hard',
    source: 'override' as 'override' | 'default',
    spent: 2_380,
    ceiling: 2_500,
  };
  readonly mySpendByModel = [
    { label: 'claude-sonnet-4.5', sub: 'Anthropic', cost: 1_280 },
    { label: 'gpt-4o', sub: 'OpenAI', cost: 640 },
    { label: 'claude-haiku-4', sub: 'Anthropic', cost: 320 },
    { label: 'gemini-2.5-pro', sub: 'Google', cost: 140 },
  ];
  readonly mySpendByApp = [
    { label: 'Chat', cost: 1_540 },
    { label: 'Support Copilot', cost: 560 },
    { label: 'Research Notebook', cost: 220 },
    { label: "My Playground", cost: 60 },
  ];

  /** My daily spend series (micro-USD) — Apr 2026, 30 days. */
  private readonly mySpend30 = Array.from({ length: 30 }, (_, i) =>
    18 + Math.round(Math.sin(i / 3) * 7 + i * 0.4 + (i % 7 < 2 ? -6 : 3)),
  );

  /** Big area chart of my daily spend (accent gradient, gridlines, day ticks). */
  readonly myArea = computed(() => {
    const data = this.mySpend30;
    const w = 760, h = 220, pl = 40, pr = 12, pt = 14, pb = 24;
    const iw = w - pl - pr, ih = h - pt - pb, n = data.length;
    const max = Math.max(...data) * 1.15;
    const X = (i: number) => pl + (i / (n - 1)) * iw;
    const Y = (v: number) => pt + ih - (v / max) * ih;
    const line = data.map((v, i) => (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1)).join(' ');
    const areaPath = `${line}L${X(n - 1).toFixed(1)} ${pt + ih}L${X(0).toFixed(1)} ${pt + ih}Z`;
    const grid = [];
    for (let g = 0; g <= 4; g++) grid.push({ y: pt + ih - (g / 4) * ih, label: '$' + this.compact((max * g) / 4) });
    const xl = data
      .map((_, i) => ({ x: X(i), text: i % 4 === 0 ? String(i + 1) : '' }))
      .filter((o) => o.text);
    return { w, h, pl, pr, line, areaPath, grid, xl };
  });

  /** Radial gauge — my spend vs. my monthly ceiling. */
  readonly myGauge = computed(() => {
    const size = 128, r = size / 2 - 9, cx = size / 2, cy = size / 2, C = 2 * Math.PI * r;
    const frac = this.myFrac();
    const col = frac >= 0.95 ? 'var(--vx-err)' : frac >= 0.8 ? 'var(--vx-warn)' : 'var(--vx-good)';
    return { size, r, cx, cy, C, full: C * 0.75, len: Math.min(frac, 1) * C * 0.75, col, pct: Math.round(frac * 100) };
  });

  myFrac(): number {
    return this.myBudget.ceiling ? this.myBudget.spent / this.myBudget.ceiling : 0;
  }
  mySharePct(cost: number, rows: { cost: number }[]): number {
    const max = Math.max(...rows.map((r) => r.cost), 1);
    return (cost / max) * 100;
  }

  readonly tab = signal<'usage' | 'budgets' | 'logs'>('usage');
  readonly range = signal<DateRange>('mtd');
  readonly dim = signal<CostDim>('team');
  readonly logQuery = signal('');

  readonly rows = computed(() => this.data.rows(this.dim()));
  private readonly total = computed(() =>
    this.rows().reduce((sum, r) => sum + r.cost, 0),
  );

  readonly rangeLabel = computed(
    () => this.data.ranges.find((r) => r.id === this.range())?.label ?? '',
  );
  readonly dimLabel = computed(
    () => this.data.dimensions.find((d) => d.id === this.dim())?.label ?? '',
  );

  /** Explorer KPI tiles derived from the active slice. */
  readonly kpis = computed(() => {
    const rows = this.rows();
    const total = this.total();
    const top = rows[0];
    const spikes = rows.filter((r) => r.spike).length;
    return [
      { label: 'Total spend · MTD', value: this.money(total) },
      { label: 'Segments', value: String(rows.length) },
      {
        label: `Top ${this.dimLabel().toLowerCase()}`,
        value: top ? `${top.label} · ${((top.cost / total) * 100).toFixed(0)}%` : '—',
      },
      { label: 'Anomalies', value: spikes ? `${spikes} spike` : '0' },
    ];
  });

  /** Daily-spend series (CSS column chart) for the active range. */
  readonly spendSeries = computed(() => this.data.spendSeries(this.range()));
  private readonly spendMax = computed(() =>
    Math.max(...this.spendSeries().map((p) => p.value), 1),
  );

  /** Column height as a % of the peak day in the active range. */
  spendBarPct(value: number): number {
    return (value / this.spendMax()) * 100;
  }

  readonly filteredLogs = computed(() => {
    const q = this.logQuery().trim().toLowerCase();
    if (!q) return this.data.logs;
    return this.data.logs.filter((l) =>
      `${l.member} ${l.app} ${l.model}`.toLowerCase().includes(q),
    );
  });

  /** Member (scrMyUsage) — only the signed-in member's own requests. */
  readonly myLogs = computed(() =>
    this.data.logs.filter((l) => l.member === this.myMember),
  );
  private readonly myMember = 'Marcus Reed';

  private readonly orgB = this.data.orgBudget;
  orgFrac(): number {
    return this.orgB.spent / this.orgB.ceiling;
  }

  sharePct(row: BreakdownRow): number {
    const total = this.total();
    return total ? (row.cost / total) * 100 : 0;
  }
  teamFrac(t: { spent: number; def: number; members: number }): number {
    const ceiling = t.def * t.members || 1;
    return t.spent / ceiling;
  }
  memberFrac(m: MemberBudget): number {
    return m.ceiling ? m.spent / m.ceiling : 0;
  }

  pct(frac: number): number {
    return Math.min(frac * 100, 100);
  }
  toneClass(frac: number): string {
    return frac >= 0.9 ? 'fill-err' : frac >= 0.8 ? 'fill-warn' : 'fill-ok';
  }

  statusTone(s: LogStatus): string {
    return s === 'ok' ? 'ok' : s === 'throttled' ? 'warn' : 'err';
  }
  statusLabel(s: LogStatus): string {
    return { ok: 'success', error: 'error', blocked: 'blocked', throttled: 'throttled' }[s];
  }

  money(v: number, dp = 0): string {
    return `$${v.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;
  }
  compact(v: number): string {
    if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(2)}B`;
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
    if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
    return String(v);
  }
}
