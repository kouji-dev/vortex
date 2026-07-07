import { Component, computed, inject, signal } from '@angular/core';
import { KjAvatarComponent, KjBadgeComponent, KjButtonComponent } from '@kouji-ui/components';
import { KjIconDirective } from '@kouji-ui/core';
import { AuthService } from '../../shared/data/auth-service';
import { MetricsService, type KpiTile } from '../../shared/data/metrics-service';

type CostDim = 'team' | 'member' | 'app' | 'model';
type Range = '7d' | '30d' | 'MTD';

interface AdminKpi extends KpiTile {
  spark: boolean;
  seed: number;
  spk?: { line: string; area: string } | null;
}
interface DimRow {
  label: string;
  v: number;
  prov?: string;
}

/** Admin Overview hub — org-wide spend, traffic and budget health (plan §D1). */
@Component({
  selector: 'app-overview',
  standalone: true,
  imports: [KjAvatarComponent, KjBadgeComponent, KjButtonComponent, KjIconDirective],
  styleUrl: './overview.css',
  template: `
    <section class="page">
      @if (auth.isAdmin()) {
      <div class="page-head">
        <div>
          <span class="vx-label">Admin Console</span>
          <h1>Overview</h1>
          <p>
            Org-wide spend, traffic and budget health across
            {{ orgName() }}. Current billing month.
          </p>
        </div>
        <div class="head-actions">
          <div class="range-toggle" role="tablist" aria-label="Date range">
            @for (r of ranges; track r) {
              <button
                type="button"
                class="seg"
                [class.on]="range() === r"
                (click)="range.set(r)"
              >
                {{ r }}
              </button>
            }
          </div>
          <kj-button kjVariant="accent" kjSize="sm">
            <span [kjIcon]="'cpu'" kjIconSize="xs"></span>
            Usage &amp; budgets
          </kj-button>
        </div>
      </div>

      <!-- ── KPI tiles ── -->
      <div class="kpi-grid" data-testid="overview-kpis">
        @for (k of kpis; track k.label) {
          <div class="kpi">
            <span class="kpi-label vx-label">{{ k.label }}</span>
            <span class="kpi-value vx-display">{{ k.value }}</span>
            <span class="kpi-delta" [class]="'kpi-delta--' + k.trend">
              @if (k.trend !== 'flat') {
                <span
                  class="kpi-delta-icon"
                  [kjIcon]="k.trend === 'down' ? 'trending-down' : 'trending-up'"
                  kjIconSize="xs"
                ></span>
              }
              {{ k.delta }}
            </span>
            @if (k.spk) {
              <svg
                class="kpi-spark"
                [class.up]="k.trend === 'up'"
                [class.down]="k.trend === 'down'"
                viewBox="0 0 80 28"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                <path [attr.d]="k.spk.area" class="spark-area" />
                <path [attr.d]="k.spk.line" class="spark-line" />
              </svg>
            }
          </div>
        }
      </div>

      <!-- ── Spend over time + Budget burn ── -->
      <div class="grid-2-1">
        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>Spend over time</h2>
              <span class="vx-label">hourly rollup · micro-USD</span>
            </div>
            <div class="legend-inline">
              <span class="lg"><i class="sw accent"></i>This month</span>
              <span class="lg"><i class="sw muted"></i>Previous</span>
            </div>
          </div>
          <svg
            class="area-svg"
            [attr.viewBox]="'0 0 ' + area().w + ' ' + area().h"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <defs>
              <linearGradient id="vx-area-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stop-color="var(--vx-accent)" stop-opacity="0.25" />
                <stop offset="1" stop-color="var(--vx-accent)" stop-opacity="0" />
              </linearGradient>
            </defs>
            @for (g of area().grid; track $index) {
              <line
                class="area-grid"
                [attr.x1]="area().pl"
                [attr.y1]="g.y"
                [attr.x2]="area().w - area().pr"
                [attr.y2]="g.y"
              />
              <text class="area-axis" text-anchor="end" [attr.x]="area().pl - 8" [attr.y]="g.y + 3">
                {{ g.label }}
              </text>
            }
            @for (x of area().xl; track $index) {
              <text class="area-axis" text-anchor="middle" [attr.x]="x.x" [attr.y]="area().h - 8">
                {{ x.text }}
              </text>
            }
            <path [attr.d]="area().spendArea" fill="url(#vx-area-grad)" />
            <path class="area-line muted" [attr.d]="area().prevLine" />
            <path class="area-line accent" [attr.d]="area().spendLine" />
          </svg>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>Budget burn</h2>
              <span class="vx-label">org spend vs Σ member budgets</span>
            </div>
          </div>
          <div class="gauge-wrap">
            <svg
              class="gauge-svg"
              [attr.width]="gauge().size"
              [attr.height]="gauge().size"
              [attr.viewBox]="'0 0 ' + gauge().size + ' ' + gauge().size"
              aria-hidden="true"
            >
              <circle
                fill="none"
                stroke="var(--vx-bg-2)"
                stroke-width="9"
                stroke-linecap="round"
                [attr.cx]="gauge().cx"
                [attr.cy]="gauge().cy"
                [attr.r]="gauge().r"
                [attr.stroke-dasharray]="gauge().full + ' ' + gauge().C"
                [attr.transform]="'rotate(135 ' + gauge().cx + ' ' + gauge().cy + ')'"
              />
              <circle
                fill="none"
                stroke-width="9"
                stroke-linecap="round"
                [attr.stroke]="gauge().col"
                [attr.cx]="gauge().cx"
                [attr.cy]="gauge().cy"
                [attr.r]="gauge().r"
                [attr.stroke-dasharray]="gauge().len + ' ' + gauge().C"
                [attr.transform]="'rotate(135 ' + gauge().cx + ' ' + gauge().cy + ')'"
              />
              <text class="gauge-val" text-anchor="middle" [attr.x]="gauge().cx" [attr.y]="gauge().cy">
                {{ gauge().pct }}%
              </text>
              <text
                class="gauge-lbl"
                text-anchor="middle"
                [attr.x]="gauge().cx"
                [attr.y]="gauge().cy + 16"
              >
                OF BUDGETS
              </text>
            </svg>
            <div class="gauge-meta">
              <span class="vx-display gauge-left">{{ money(budgets - spent) }} left</span>
              <span class="vx-label">of {{ money(budgets) }} · resets in 12 days</span>
            </div>
            <div class="warnbar warn">
              <span class="warn-ico" [kjIcon]="'lock'" kjIconSize="sm"></span>
              <span>
                <b>Marcus Reed</b> is at 95% of his override budget. Platform team
                enforces <b>hard</b> caps.
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Top spenders + Providers ── -->
      <div class="grid-14-1">
        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>Top spenders</h2>
              <span class="vx-label">this month</span>
            </div>
            <div class="dim-toggle">
              @for (d of dims; track d) {
                <button
                  type="button"
                  class="dim-chip"
                  [class.on]="costDim() === d"
                  (click)="costDim.set(d)"
                >
                  {{ dimLabels[d] }}
                </button>
              }
            </div>
          </div>
          <div class="bars">
            @for (row of topDim(); track row.label; let i = $index) {
              <div class="bar-row">
                <span class="bar-label">
                  @if (row.prov) {
                    <span class="pmark" [style.background]="provColor(row.prov)">
                      {{ provLetter(row.prov) }}
                    </span>
                  }
                  {{ row.label }}
                </span>
                <span class="bar-track">
                  <span
                    class="bar-fill"
                    [style.width.%]="barPct(row)"
                    [style.background]="barColor(row, i)"
                  ></span>
                </span>
                <span class="bar-value vx-mono">{{ money(row.v) }}</span>
              </div>
            }
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>Providers</h2>
              <span class="vx-label">request share</span>
            </div>
          </div>
          <div class="donut-wrap">
            <svg
              class="donut-svg"
              [attr.width]="donut().size"
              [attr.height]="donut().size"
              [attr.viewBox]="'0 0 ' + donut().size + ' ' + donut().size"
              aria-hidden="true"
            >
              @for (a of donut().arcs; track $index) {
                <circle
                  fill="none"
                  stroke-width="16"
                  [attr.stroke]="a.color"
                  [attr.cx]="donut().cx"
                  [attr.cy]="donut().cy"
                  [attr.r]="donut().r"
                  [attr.stroke-dasharray]="a.dash"
                  [attr.stroke-dashoffset]="a.offset"
                  [attr.transform]="'rotate(-90 ' + donut().cx + ' ' + donut().cy + ')'"
                />
              }
              <text class="donut-tot" text-anchor="middle" [attr.x]="donut().cx" [attr.y]="donut().cy - 2">
                100
              </text>
              <text class="donut-lbl" text-anchor="middle" [attr.x]="donut().cx" [attr.y]="donut().cy + 14">
                SHARE
              </text>
            </svg>
            <div class="legend">
              @for (p of providers; track p.label) {
                <div class="legend-row">
                  <span class="dot" [style.background]="p.color"></span>
                  <span class="legend-label">{{ p.label }}</span>
                  <span class="legend-value vx-mono">{{ p.v }}%</span>
                </div>
              }
            </div>
          </div>
        </div>
      </div>

      <!-- ── Open alerts + Recent activity ── -->
      <div class="grid-1-1">
        <div class="panel">
          <div class="panel-head">
            <div><h2>Open alerts</h2></div>
            <kj-button kjVariant="ghost" kjSize="sm">Inbox</kj-button>
          </div>
          <div class="feed">
            @for (a of alerts; track $index) {
              <div class="feed-row">
                <span class="feed-dot" [class]="'dot-' + a.tone"></span>
                <span class="feed-text">{{ a.text }}</span>
                <span class="feed-time vx-mono">{{ a.time }}</span>
              </div>
            }
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div><h2>Recent activity</h2></div>
            <kj-button kjVariant="ghost" kjSize="sm">Audit log</kj-button>
          </div>
          <div class="feed">
            @for (a of activity; track $index) {
              <div class="feed-row">
                @if (a.actor === 'system') {
                  <span class="feed-sys">S</span>
                } @else {
                  <kj-avatar [content]="initials(a.actor)" size="xs"></kj-avatar>
                }
                <span class="feed-act">
                  <span class="vx-mono act-verb">{{ a.action }}</span>
                  <span class="act-target">{{ a.target }}</span>
                </span>
                <span class="feed-time vx-mono">{{ a.time }}</span>
              </div>
            }
          </div>
        </div>
      </div>
      } @else {
      <!-- ── Member: Home (scrMyHome) ── -->
      <div class="page-head">
        <div>
          <span class="vx-label">My Console</span>
          <h1>Home</h1>
          <p>
            Welcome back, {{ firstName() }}. Your spend, budget, apps and
            keys — scoped to you. Current billing month.
          </p>
        </div>
      </div>

      <!-- personal KPI tiles with sparklines -->
      <div class="kpi-grid" data-testid="myhome-kpis">
        @for (k of myKpis; track k.label) {
          <div class="kpi">
            <span class="kpi-label vx-label">{{ k.label }}</span>
            <span class="kpi-value vx-display">{{ k.value }}</span>
            <span class="kpi-delta" [class]="'kpi-delta--' + k.trend">
              @if (k.trend !== 'flat') {
                <span
                  class="kpi-delta-icon"
                  [kjIcon]="k.trend === 'down' ? 'trending-down' : 'trending-up'"
                  kjIconSize="xs"
                ></span>
              }
              {{ k.delta }}
            </span>
            @if (k.spk) {
              <svg
                class="kpi-spark"
                [class.up]="k.trend === 'up'"
                [class.down]="k.trend === 'down'"
                viewBox="0 0 80 28"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                <path [attr.d]="k.spk.area" class="spark-area" />
                <path [attr.d]="k.spk.line" class="spark-line" />
              </svg>
            }
          </div>
        }
      </div>

      <!-- ── My budget gauge + My spend area ── -->
      <div class="grid-1-1">
        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>My monthly budget</h2>
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
              <span class="vx-label">of {{ money(myBudget.ceiling) }}/mo · resets in 12 days</span>
            </div>
            <div class="warnbar warn">
              <span class="warn-ico" [kjIcon]="'lock'" kjIconSize="sm"></span>
              <span>
                You’re at <b>{{ myGauge().pct }}%</b>. At 100% new requests are
                blocked (402) — {{ myBudget.team }} enforces <b>hard</b> caps.
              </span>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>My spend</h2>
              <span class="vx-label">last 14 days · micro-USD</span>
            </div>
          </div>
          <svg
            class="area-svg"
            [attr.viewBox]="'0 0 ' + myArea().w + ' ' + myArea().h"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <defs>
              <linearGradient id="vx-area-grad-me" x1="0" y1="0" x2="0" y2="1">
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
            <path [attr.d]="myArea().areaPath" fill="url(#vx-area-grad-me)" />
            <path class="area-line accent" [attr.d]="myArea().line" />
          </svg>
        </div>
      </div>

      <!-- ── My apps + My keys ── -->
      <div class="grid-1-1">
        <div class="panel">
          <div class="panel-head">
            <div><h2>My apps</h2><span class="vx-label">apps scoped to you</span></div>
            <kj-button kjVariant="ghost" kjSize="sm">All</kj-button>
          </div>
          <div class="obj-list">
            @for (a of myApps; track a.name) {
              <div class="obj-row">
                <span class="obj-icon" [class]="'kind-' + a.kind" [kjIcon]="a.icon" kjIconSize="sm"></span>
                <span class="obj-meta">
                  <span class="obj-name">{{ a.name }}</span>
                  <span class="obj-sub">{{ a.access }}</span>
                </span>
                <kj-badge [variant]="a.kind === 'system' ? 'default' : 'secondary'" size="xs">
                  {{ appKindLabel(a.kind) }}
                </kj-badge>
              </div>
            }
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div><h2>My keys</h2><span class="vx-label">default + personal</span></div>
            <kj-button kjVariant="ghost" kjSize="sm">Manage</kj-button>
          </div>
          <div class="obj-list">
            @for (k of myKeys; track k.name) {
              <div class="obj-row">
                <span class="obj-icon key" [kjIcon]="'key'" kjIconSize="sm"></span>
                <span class="obj-meta">
                  <span class="obj-name">
                    {{ k.name }}
                    <kj-badge [variant]="k.kind === 'default' ? 'default' : 'secondary'" size="xs">
                      {{ k.kind }}
                    </kj-badge>
                  </span>
                  <span class="obj-sub vx-mono">{{ k.mask }}</span>
                </span>
                <span class="status-pill"><span class="status-dot"></span>{{ k.status }}</span>
              </div>
            }
          </div>
        </div>
      </div>
      }
    </section>
  `,
})
export class Overview {
  protected readonly auth = inject(AuthService);
  private readonly metrics = inject(MetricsService);

  // ── Admin (scrOverview) ──────────────────────────────────────────
  readonly spent = 18_240;
  readonly budgets = 26_500;

  readonly ranges: Range[] = ['7d', '30d', 'MTD'];
  readonly range = signal<Range>('MTD');

  /** KPI tiles with pre-computed sparkline paths for the spark tiles. */
  readonly kpis: AdminKpi[] = [
    { label: 'Org spend · MTD', value: '$18,240', delta: '12.4%', trend: 'up', spark: true, seed: 3 },
    { label: 'Sum of member budgets', value: '$26,500', delta: 'ceiling', trend: 'flat', spark: false, seed: 5 },
    { label: 'Requests', value: '2.84M', delta: '12.4%', trend: 'up', spark: true, seed: 8 },
    { label: 'Tokens', value: '1.92B', delta: '9.1%', trend: 'up', spark: true, seed: 11 },
    { label: 'Active members', value: '38 / 42', delta: '+4', trend: 'up', spark: false, seed: 2 },
    { label: 'Open alerts', value: '3', delta: '1 critical', trend: 'up', spark: false, seed: 7 },
  ].map((k) => ({ ...k, spk: k.spark ? this.spark(k.seed) : null }) as AdminKpi);

  // spend-over-time series (this month vs previous)
  private readonly spendThis = [820, 910, 760, 1180, 990, 1290, 1120, 1480, 1310, 1620, 1440, 1710, 1590, 1284];
  private readonly spendPrev = [700, 760, 820, 910, 880, 1010, 970, 1120, 1080, 1210, 1160, 1290, 1240, 1180];
  private readonly xLabels = ['00', '', '', '06', '', '', '12', '', '', '18', '', '', '', 'now'];

  /** Area-chart geometry (two series, gridlines, axis labels). */
  readonly area = computed(() => {
    const w = 760, h = 210, pl = 44, pr = 12, pt = 14, pb = 26;
    const iw = w - pl - pr, ih = h - pt - pb;
    const n = this.spendThis.length;
    const max = Math.max(...this.spendThis, ...this.spendPrev) * 1.1;
    const X = (i: number) => pl + (i / (n - 1)) * iw;
    const Y = (v: number) => pt + ih - (v / max) * ih;
    const path = (d: number[]) =>
      d.map((v, i) => (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1)).join(' ');
    const spendLine = path(this.spendThis);
    const spendArea = `${spendLine}L${X(n - 1).toFixed(1)} ${pt + ih}L${X(0).toFixed(1)} ${pt + ih}Z`;
    const grid = [];
    for (let g = 0; g <= 4; g++) grid.push({ y: pt + ih - (g / 4) * ih, label: '$' + this.compact((max * g) / 4) });
    const xl = this.xLabels.map((text, i) => ({ x: X(i), text })).filter((o) => o.text);
    return { w, h, pl, pr, spendLine, spendArea, prevLine: path(this.spendPrev), grid, xl };
  });

  /** Radial gauge geometry for org burn (spend / Σ budgets). */
  readonly gauge = computed(() => {
    const size = 132, r = size / 2 - 9, cx = size / 2, cy = size / 2, C = 2 * Math.PI * r;
    const frac = this.spent / this.budgets;
    const col = frac >= 0.95 ? 'var(--vx-err)' : frac >= 0.8 ? 'var(--vx-warn)' : 'var(--vx-good)';
    return { size, r, cx, cy, C, full: C * 0.75, len: Math.min(frac, 1) * C * 0.75, col, pct: Math.round(frac * 100) };
  });

  // ── Providers (donut) ──
  readonly providers = [
    { label: 'Anthropic', v: 46, color: 'var(--vx-prov-anthropic)' },
    { label: 'OpenAI', v: 32, color: 'var(--vx-prov-openai)' },
    { label: 'Google', v: 15, color: 'var(--vx-prov-google)' },
    { label: 'Other', v: 7, color: 'var(--vx-ink-4)' },
  ];

  readonly donut = computed(() => {
    const size = 148, r = size / 2 - 14, cx = size / 2, cy = size / 2, C = 2 * Math.PI * r;
    const tot = this.providers.reduce((a, s) => a + s.v, 0);
    let off = 0;
    const arcs = this.providers.map((s) => {
      const len = (s.v / tot) * C;
      const a = { color: s.color, dash: `${len.toFixed(2)} ${(C - len).toFixed(2)}`, offset: -off };
      off += len;
      return a;
    });
    return { size, r, cx, cy, arcs };
  });

  // ── Top spenders (grid-bars, per-dimension) ──
  readonly dims: CostDim[] = ['team', 'member', 'app', 'model'];
  readonly dimLabels: Record<CostDim, string> = { team: 'Team', member: 'Member', app: 'App', model: 'Model' };
  readonly costDim = signal<CostDim>('team');
  private readonly costDims: Record<CostDim, DimRow[]> = {
    team: [
      { label: 'Platform', v: 6120 },
      { label: 'Growth', v: 4880 },
      { label: 'Support', v: 3410 },
      { label: 'Data Science', v: 2240 },
      { label: 'Sandbox', v: 1590 },
    ],
    member: [
      { label: 'Marcus Reed', v: 2380 },
      { label: 'Priya Nair', v: 2140 },
      { label: 'Dana Lopez', v: 1760 },
      { label: 'svc-support', v: 1520 },
      { label: 'Kai Tanaka', v: 1180 },
      { label: 'Ana Costa', v: 960 },
    ],
    app: [
      { label: 'Chat', v: 7420 },
      { label: 'Support Copilot', v: 6240 },
      { label: 'Analytics ETL', v: 4100 },
      { label: 'Research Notebook', v: 2410 },
      { label: 'Playground', v: 820 },
    ],
    model: [
      { label: 'claude-sonnet-4.5', v: 8120, prov: 'anthropic' },
      { label: 'gpt-4o', v: 5240, prov: 'openai' },
      { label: 'gemini-2.5-pro', v: 2610, prov: 'google' },
      { label: 'claude-haiku-4', v: 1920, prov: 'anthropic' },
      { label: 'mistral-large', v: 640, prov: 'mistral' },
    ],
  };
  private readonly palette = ['#7c8cf8', '#5b8def', '#4aa3c7', '#6b6f8f', '#5f9ea0', '#8b7cf0'];
  readonly topDim = computed(() =>
    this.costDims[this.costDim()].slice().sort((a, b) => b.v - a.v).slice(0, 6),
  );

  barPct(row: DimRow): number {
    const max = Math.max(...this.topDim().map((r) => r.v), 1);
    return (row.v / max) * 100;
  }
  barColor(row: DimRow, i: number): string {
    return row.prov ? this.provColor(row.prov) : this.palette[i % this.palette.length];
  }

  // ── Open alerts + recent activity ──
  readonly alerts = [
    { tone: 'err', text: 'Marcus Reed — 402 hard cap hit', time: '12m ago' },
    { tone: 'warn', text: 'svc-support spend +340% vs baseline', time: '1h ago' },
    { tone: 'warn', text: 'Marcus Reed budget crossed 95%', time: 'Yesterday' },
  ];
  readonly activity = [
    { actor: 'system', action: 'budget.enforce', target: 'Marcus Reed', time: '12m ago' },
    { actor: 'Priya Nair', action: 'key.rotate', target: 'svc-chat · default', time: '34m ago' },
    { actor: 'Dana Lopez', action: 'app.deploy', target: 'Analytics ETL', time: '1h ago' },
    { actor: 'Marcus Reed', action: 'model.enable', target: 'gemini-2.5-pro', time: '2h ago' },
  ];

  private readonly provColors: Record<string, string> = {
    anthropic: 'var(--vx-prov-anthropic)',
    openai: 'var(--vx-prov-openai)',
    google: 'var(--vx-prov-google)',
    mistral: 'var(--vx-prov-mistral)',
  };
  provColor(p: string): string {
    return this.provColors[p] ?? 'var(--vx-ink-4)';
  }
  provLetter(p: string): string {
    return ({ anthropic: 'A', openai: 'O', google: 'G', mistral: 'M' } as Record<string, string>)[p] ?? '?';
  }

  /** Seeded, deterministic sparkline — mirrors the DS Sparkline. */
  private spark(seed: number): { line: string; area: string } {
    const n = 24, w = 80, h = 28;
    const pts: number[] = [];
    let v = 0.5;
    for (let i = 0; i < n; i++) {
      const r = Math.sin((seed + i) * 12.9898) * 43758.5453;
      v = Math.max(0.05, Math.min(0.95, v + (r - Math.floor(r) - 0.5) * 0.3));
      pts.push(v);
    }
    const line = pts
      .map((p, i) => `${i ? 'L' : 'M'} ${((i / (n - 1)) * w).toFixed(1)} ${(h - p * h).toFixed(1)}`)
      .join(' ');
    return { line, area: `${line} L ${w} ${h} L 0 ${h} Z` };
  }

  initials(name: string): string {
    return name.split(/\s+/).map((p) => p.charAt(0)).join('').slice(0, 2).toUpperCase();
  }

  // ── Member (scrMyHome) demo data — scoped to the signed-in member ──
  readonly myKpis: AdminKpi[] = [
    { label: 'My spend · MTD', value: '$2,380', delta: '6.1%', trend: 'up', spark: true, seed: 4 },
    { label: 'My budget', value: '$2,500', delta: 'override', trend: 'flat', spark: false, seed: 1 },
    { label: 'My requests', value: '184K', delta: '8.0%', trend: 'up', spark: true, seed: 6 },
    { label: 'My keys', value: '2', delta: 'active', trend: 'flat', spark: false, seed: 2 },
  ].map((k) => ({ ...k, spk: k.spark ? this.spark(k.seed) : null }) as AdminKpi);

  readonly myBudget = { team: 'Platform', enforce: 'hard', spent: 2_380, ceiling: 2_500 };

  /** My spend, last 14 days (micro-USD). */
  private readonly mySpend14 = [120, 140, 110, 180, 160, 200, 190, 220, 210, 240, 220, 260, 240, 280].map(
    (v) => v * 2.3,
  );

  /** Single-series area chart for my recent spend. */
  readonly myArea = computed(() => {
    const data = this.mySpend14;
    const w = 760, h = 200, pl = 44, pr = 12, pt = 14, pb = 22;
    const iw = w - pl - pr, ih = h - pt - pb, n = data.length;
    const max = Math.max(...data) * 1.1;
    const X = (i: number) => pl + (i / (n - 1)) * iw;
    const Y = (v: number) => pt + ih - (v / max) * ih;
    const line = data.map((v, i) => (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1)).join(' ');
    const areaPath = `${line}L${X(n - 1).toFixed(1)} ${pt + ih}L${X(0).toFixed(1)} ${pt + ih}Z`;
    const grid = [];
    for (let g = 0; g <= 4; g++) grid.push({ y: pt + ih - (g / 4) * ih, label: '$' + this.compact((max * g) / 4) });
    return { w, h, pl, pr, line, areaPath, grid };
  });

  /** Radial gauge for my budget burn (my spend / my ceiling). */
  readonly myGauge = computed(() => {
    const size = 132, r = size / 2 - 9, cx = size / 2, cy = size / 2, C = 2 * Math.PI * r;
    const frac = this.myBudget.spent / this.myBudget.ceiling;
    const col = frac >= 0.95 ? 'var(--vx-err)' : frac >= 0.8 ? 'var(--vx-warn)' : 'var(--vx-good)';
    return { size, r, cx, cy, C, full: C * 0.75, len: Math.min(frac, 1) * C * 0.75, col, pct: Math.round(frac * 100) };
  });

  /** My apps — built-in Chat, granted service apps, personal apps. */
  readonly myApps = [
    { name: 'Chat', kind: 'system', access: 'Built-in', icon: 'chat' },
    { name: 'Support Copilot', kind: 'service', access: 'Shared', icon: 'cpu' },
    { name: 'Research Notebook', kind: 'service', access: 'Shared', icon: 'book' },
    { name: 'My Playground', kind: 'personal', access: 'Personal', icon: 'cpu' },
  ];

  /** My keys — the default key plus any personal keys. */
  readonly myKeys = [
    { name: 'default', kind: 'default', mask: 'sk-vor-••••-9f2a', status: 'active' },
    { name: 'laptop-cli', kind: 'personal', mask: 'sk-vor-••••-c71d', status: 'active' },
  ];

  appKindLabel(kind: string): string {
    return ({ system: 'System', service: 'Service', personal: 'Personal' } as Record<string, string>)[kind] ?? kind;
  }

  orgName(): string {
    return this.auth.user()?.orgName ?? 'your organisation';
  }
  firstName(): string {
    return (this.auth.user()?.name ?? 'there').split(' ')[0];
  }
  budgetPct(): number {
    return Math.min((this.myBudget.spent / this.myBudget.ceiling) * 100, 100);
  }

  money(v: number, dp = 0): string {
    return `$${v.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;
  }
  compact(n: number): string {
    if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
    if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
    return `${Math.round(n)}`;
  }
}
