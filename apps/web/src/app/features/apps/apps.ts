import { Component, computed, inject, signal } from '@angular/core';
import {
  KjBadgeComponent,
  KjButtonComponent,
  KjTagComponent,
  KjToggleComponent,
} from '@kouji-ui/components';
import { KjIconDirective } from '@kouji-ui/core';
import { AuthService } from '../../shared/data/auth-service';
import {
  App,
  AppGrant,
  AppKind,
  AppsData,
  PrincipalType,
  RouteProvider,
  ServiceKey,
} from './apps.data';

type DetailTab = 'overview' | 'access' | 'routing' | 'keys' | 'usage';

/** Apps — deployable gateway services (system / service / personal) with a
 *  master-detail panel: list + selected-app config (plan §D3). */
@Component({
  selector: 'app-apps',
  standalone: true,
  imports: [
    KjBadgeComponent,
    KjButtonComponent,
    KjTagComponent,
    KjToggleComponent,
    KjIconDirective,
  ],
  styleUrl: './apps.css',
  template: `
    <section class="page">
      @if (auth.isAdmin()) {
      @if (!selected()) {
        <!-- ══ MASTER · apps list ══════════════════════════════ -->
        <div class="page-head">
          <div>
            <span class="vx-label">Admin Console</span>
            <h1>Apps</h1>
            <p>
              Everything that calls the gateway — the built-in <b>Chat</b>
              (system), org-deployed <b>service</b> apps and members’
              <b>personal</b> apps. Each app has a technical member, a routing
              policy and access grants.
            </p>
          </div>
          <kj-button kjVariant="primary" kjSize="sm" (click)="openDeploy()">
            <span [kjIcon]="'plus'" kjIconSize="sm"></span>
            Deploy app
          </kj-button>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h2>Deployed apps</h2>
            <span class="vx-label">{{ apps().length }} total</span>
          </div>

          <div class="table-wrap">
            <table class="apps-table" data-testid="apps-table">
              <thead>
                <tr>
                  <th>App</th>
                  <th>Technical member</th>
                  <th>Access</th>
                  <th class="num">Requests · MTD</th>
                  <th class="num">Spend · MTD</th>
                  <th>Primary route</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                @for (a of apps(); track a.id) {
                  <tr (click)="open(a)" data-testid="app-row">
                    <td>
                      <span class="app-cell">
                        <span class="app-mark" [class]="'k-' + a.kind">
                          <span [kjIcon]="kindIcon(a.kind)" kjIconSize="sm"></span>
                        </span>
                        <span class="app-id">
                          <span class="app-name">{{ a.name }}</span>
                          <kj-badge [variant]="a.kind === 'system' ? 'default' : 'secondary'" size="xs">
                            {{ kindLabel(a.kind) }}
                          </kj-badge>
                        </span>
                      </span>
                    </td>
                    <td>
                      @if (a.tech === '—') {
                        <span class="muted">—</span>
                      } @else {
                        <span class="svc-chip">
                          <span [kjIcon]="'cpu'" kjIconSize="xs"></span>
                          <span class="vx-mono">{{ a.tech }}</span>
                        </span>
                      }
                    </td>
                    <td><span class="muted-2">{{ a.access }}</span></td>
                    <td class="num vx-mono">{{ compact(a.requests) }}</td>
                    <td class="num vx-mono strong">{{ '$' + money(a.spend) }}</td>
                    <td><span class="route-cell vx-mono">{{ a.policy }}</span></td>
                    <td>
                      <kj-badge
                        [variant]="a.status === 'active' ? 'default' : 'secondary'"
                        size="xs"
                        dot="true"
                        [dotColor]="a.status === 'active' ? 'var(--vx-good)' : 'var(--vx-warn)'"
                      >
                        {{ a.status }}
                      </kj-badge>
                    </td>
                    <td class="chev">
                      <span [kjIcon]="'chevron-right'" kjIconSize="sm"></span>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      } @else {
        <!-- ══ DETAIL · selected app ═══════════════════════════ -->
        @let a = selected()!;
        <button class="crumbs" type="button" (click)="back()" data-testid="apps-back">
          <span [kjIcon]="'chevron-right'" kjIconSize="xs" class="crumb-flip"></span>
          Apps
          <span class="crumb-sep">/</span>
          <b>{{ a.name }}</b>
        </button>

        <div class="page-head">
          <div>
            <span class="vx-label">App</span>
            <h1>{{ a.name }}</h1>
            <p>
              <b>{{ kindLabel(a.kind) }}</b> · owned by {{ a.owner }} ·
              {{ a.tech === '—' ? 'personal — uses owner’s keys' : a.tech }}
            </p>
          </div>
          <kj-badge
            [variant]="a.status === 'active' ? 'default' : 'secondary'"
            size="sm"
            dot="true"
            [dotColor]="a.status === 'active' ? 'var(--vx-good)' : 'var(--vx-warn)'"
          >
            {{ a.status }}
          </kj-badge>
        </div>

        <!-- overview stat tiles -->
        <div class="kpi-grid">
          @for (s of stats(a); track s.label) {
            <div class="kpi">
              <span class="kpi-label vx-label">{{ s.label }}</span>
              <span class="kpi-value vx-display">{{ s.value }}</span>
            </div>
          }
        </div>

        <!-- tabs -->
        <div class="tabs" role="tablist" data-testid="app-tabs">
          @for (t of tabs; track t.id) {
            <button
              type="button"
              role="tab"
              class="tab"
              [class.active]="tab() === t.id"
              [attr.aria-selected]="tab() === t.id"
              (click)="tab.set(t.id)"
            >
              {{ t.label }}
            </button>
          }
        </div>

        @switch (tab()) {
          @case ('overview') {
            <div class="panel">
              <div class="panel-head"><h2>App</h2></div>
              <dl class="defs">
                <div><dt>Kind</dt><dd>{{ kindLabel(a.kind) }}</dd></div>
                <div><dt>Owner</dt><dd>{{ a.owner }}</dd></div>
                <div>
                  <dt>Technical member</dt>
                  <dd>
                    @if (a.tech === '—') {
                      <span class="muted">— (personal, uses owner’s keys)</span>
                    } @else {
                      <span class="svc-chip">
                        <span [kjIcon]="'cpu'" kjIconSize="xs"></span>
                        <span class="vx-mono">{{ a.tech }}</span>
                      </span>
                    }
                  </dd>
                </div>
                <div><dt>Access</dt><dd>{{ a.access }}</dd></div>
                <div><dt>Default routing</dt><dd class="vx-mono">{{ a.policy }}</dd></div>
              </dl>
            </div>
          }

          @case ('access') {
            <div class="panel">
              <div class="panel-head">
                <h2>Access grants</h2>
                <kj-button kjVariant="secondary" kjSize="xs" (click)="openGrant()">
                  <span [kjIcon]="'plus'" kjIconSize="xs"></span>
                  Grant access
                </kj-button>
              </div>
              <div class="table-wrap">
                <table class="apps-table" data-testid="grants-table">
                  <thead>
                    <tr><th>Grantee</th><th>Type</th><th>App role</th><th>Via</th><th></th></tr>
                  </thead>
                  <tbody>
                    @for (g of grantsFor(a); track g.who) {
                      <tr>
                        <td class="strong">{{ g.who }}</td>
                        <td>
                          <kj-tag>
                            <span [kjIcon]="g.principalType === 'team' ? 'users' : 'user'" kjIconSize="xs"></span>
                            {{ g.principalType }}
                          </kj-tag>
                        </td>
                        <td>
                          <kj-badge [variant]="g.role === 'app_admin' ? 'default' : 'secondary'" size="xs">
                            {{ g.role }}
                          </kj-badge>
                        </td>
                        <td><span class="muted-2">{{ g.via }}</span></td>
                        <td class="chev">
                          <kj-button kjVariant="ghost" kjSize="xs" (click)="removeGrant(a, g)" aria-label="Revoke grant">
                            <span [kjIcon]="'x'" kjIconSize="xs"></span>
                          </kj-button>
                        </td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
              <p class="notebar">
                <span [kjIcon]="'info'" kjIconSize="xs"></span>
                Grant whole <b>teams</b> or specific <b>members</b>.
                <b>app_admin</b> configures routing / access / keys; <b>app_member</b> can use the app.
              </p>
            </div>
          }

          @case ('routing') {
            <div class="panel">
              <div class="panel-head">
                <h2>Candidate chain</h2>
                <span class="vx-label">primary → failover</span>
              </div>
              <div class="chain">
                @for (h of a.routing; track h.model; let i = $index) {
                  @if (i > 0) {
                    <div class="hop-arrow">
                      <span [kjIcon]="'arrow-down'" kjIconSize="sm"></span>
                      <span class="hop-note vx-mono">on failure / timeout</span>
                    </div>
                  }
                  <div class="hop">
                    <span class="hop-n vx-mono">{{ i + 1 }}</span>
                    <span class="prov-dot sm" [style.background]="meta(h.prov).color">{{ meta(h.prov).letter }}</span>
                    <span class="hop-id">
                      <span class="hop-model">{{ h.model }}</span>
                      <span class="hop-bind">{{ h.role }} · binds {{ h.binding }}</span>
                    </span>
                  </div>
                }
              </div>
              <div class="route-settings">
                <div class="rset">
                  <div><span class="rset-t">Retry primary</span><span class="rset-d">before falling through</span></div>
                  <span class="vx-mono rset-v">3×</span>
                </div>
                <div class="rset">
                  <div><span class="rset-t">Timeout</span><span class="rset-d">per attempt</span></div>
                  <span class="vx-mono rset-v">30s</span>
                </div>
                <div class="rset">
                  <div><span class="rset-t">Fail on 429</span><span class="rset-d">route to fallback on rate-limit</span></div>
                  <kj-toggle appearance="switch" size="sm" [pressed]="failOn429()" (pressedChange)="failOn429.set($event)" ariaLabel="Fail on 429"></kj-toggle>
                </div>
              </div>
            </div>
          }

          @case ('keys') {
            <div class="panel">
              <div class="panel-head">
                <h2>Service keys</h2>
                <span class="vx-label">owned by {{ a.tech === '—' ? a.owner : a.tech }}</span>
              </div>
              <p class="notebar">
                <span [kjIcon]="'key'" kjIconSize="xs"></span>
                These <b>vtx_</b> keys are member-owned, not app-bound — this app’s traffic routes through them.
              </p>
              <div class="table-wrap">
                <table class="apps-table" data-testid="keys-table">
                  <thead>
                    <tr><th>Key</th><th>Rules</th><th class="num">Rate limit</th><th>Created</th><th>Last used</th><th>Status</th><th></th></tr>
                  </thead>
                  <tbody>
                    @for (k of a.keys; track k.mask) {
                      <tr>
                        <td>
                          <div class="key-id">
                            <span class="strong key-name">
                              {{ k.name }}
                              <kj-tag>{{ k.kind }}</kj-tag>
                            </span>
                            <span class="vx-mono key-mask">{{ k.mask }}</span>
                          </div>
                        </td>
                        <td><span class="muted-2">{{ k.rules }}</span></td>
                        <td class="num vx-mono">{{ k.rate }}</td>
                        <td class="vx-mono muted-2">{{ k.created }}</td>
                        <td class="vx-mono muted-2">{{ k.lastUsed }}</td>
                        <td>
                          <kj-badge
                            [variant]="k.status === 'active' ? 'default' : 'secondary'"
                            size="xs"
                            dot="true"
                            [dotColor]="k.status === 'active' ? 'var(--vx-good)' : 'var(--vx-warn)'"
                          >{{ k.status }}</kj-badge>
                        </td>
                        <td class="chev">
                          <span class="key-actions">
                            <kj-button kjVariant="ghost" kjSize="xs" (click)="rotate(k)">Rotate</kj-button>
                            <kj-button kjVariant="ghost" kjSize="xs" (click)="revoke(k)">Revoke</kj-button>
                          </span>
                        </td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            </div>
          }

          @case ('usage') {
            <div class="panel-grid">
              <div class="panel">
                <div class="panel-head"><h2>Spend by member</h2><span class="vx-label">who used this app</span></div>
                <div class="bars">
                  @for (r of a.usageByMember; track r.label) {
                    <div class="bar-row">
                      <span class="bar-label">{{ r.label }}</span>
                      <span class="bar-track"><span class="bar-fill" [style.width.%]="pct(r.value, a.usageByMember)"></span></span>
                      <span class="bar-value vx-mono">{{ '$' + money(r.value) }}</span>
                    </div>
                  }
                </div>
              </div>
              <div class="panel">
                <div class="panel-head"><h2>Spend by model</h2></div>
                <div class="bars">
                  @for (r of a.usageByModel; track r.label) {
                    <div class="bar-row">
                      <span class="bar-label">
                        @if (r.prov) {
                          <span class="prov-dot xs" [style.background]="meta(r.prov).color">{{ meta(r.prov).letter }}</span>
                        }
                        {{ r.label }}
                      </span>
                      <span class="bar-track"><span class="bar-fill" [style.width.%]="pct(r.value, a.usageByModel)"></span></span>
                      <span class="bar-value vx-mono">{{ '$' + money(r.value) }}</span>
                    </div>
                  }
                </div>
              </div>
            </div>
          }
        }
      }
      } @else {
        <!-- ══ MEMBER · My Apps (scrMyApps) ═══════════════════════ -->
        <div class="page-head">
          <div>
            <span class="vx-label">My workspace</span>
            <h1>My Apps</h1>
            <p>
              Apps you can use — the built-in <b>Chat</b>, <b>service</b> apps
              you’re granted and your own <b>personal</b> apps. Where you’re an
              <b>app_admin</b> you can configure it; elsewhere you have
              read-only access.
            </p>
          </div>
        </div>

        <div class="my-apps-grid" data-testid="my-apps-grid">
          @for (a of myApps(); track a.id) {
            <div class="app-card" data-testid="my-app-card">
              <div class="app-card-head">
                <span class="app-mark" [class]="'k-' + a.kind">
                  <span [kjIcon]="kindIcon(a.kind)" kjIconSize="sm"></span>
                </span>
                <div class="app-card-id">
                  <span class="app-name">{{ a.name }}</span>
                  <span class="app-card-policy vx-mono">{{ a.policy }}</span>
                </div>
                <kj-badge [variant]="a.kind === 'system' ? 'default' : 'secondary'" size="xs">
                  {{ kindLabel(a.kind) }}
                </kj-badge>
              </div>

              <div class="app-card-role">
                <kj-badge [variant]="a.role === 'app_admin' ? 'default' : 'secondary'" size="xs">
                  {{ a.role }}
                </kj-badge>
                <span class="muted-2">{{ a.can }}</span>
              </div>

              <div class="app-card-usage">
                <div class="usage-stat">
                  <span class="vx-label">My requests · MTD</span>
                  <span class="usage-v vx-mono">{{ compact(a.myRequests) }}</span>
                </div>
                <div class="usage-stat">
                  <span class="vx-label">My spend · MTD</span>
                  <span class="usage-v vx-mono strong">{{ '$' + money(a.mySpend) }}</span>
                </div>
              </div>
            </div>
          }
        </div>
      }
    </section>

    <!-- ══ Deploy app modal (client-side) ═══════════════════════ -->
    @if (deployOpen()) {
      <div class="scrim" (click)="closeDeploy()">
        <div
          class="modal"
          role="dialog"
          aria-modal="true"
          aria-label="Deploy service app"
          (click)="$event.stopPropagation()"
          data-testid="deploy-modal"
        >
          <div class="modal-head">
            <span class="vx-label">New app</span>
            <h3>Deploy service app</h3>
            <button class="icon-x" type="button" aria-label="Close" (click)="closeDeploy()">
              <span [kjIcon]="'x'" kjIconSize="sm"></span>
            </button>
          </div>
          <div class="modal-body">
            <label class="field">
              <span class="field-label">App name</span>
              <input placeholder="e.g. Support Copilot" [value]="deployForm.name()" (input)="deployForm.name.set($any($event.target).value)" />
            </label>
            <label class="field">
              <span class="field-label">Owner</span>
              <select [value]="deployForm.owner()" (change)="deployForm.owner.set($any($event.target).value)">
                @for (o of owners; track o) { <option [value]="o">{{ o }}</option> }
              </select>
            </label>
            <label class="field">
              <span class="field-label">Technical member’s team</span>
              <select [value]="deployForm.team()" (change)="deployForm.team.set($any($event.target).value)">
                @for (t of teams; track t) { <option [value]="t">{{ t }}</option> }
              </select>
              <span class="field-hint">A service account is auto-created in this team and inherits its default budget.</span>
            </label>
            <label class="field">
              <span class="field-label">Default routing policy</span>
              <select [value]="deployForm.policy()" (change)="deployForm.policy.set($any($event.target).value)">
                @for (p of policies; track p) { <option [value]="p">{{ p }}</option> }
              </select>
            </label>
          </div>
          <div class="modal-foot">
            <kj-button kjVariant="ghost" kjSize="sm" (click)="closeDeploy()">Cancel</kj-button>
            <kj-button kjVariant="primary" kjSize="sm" (click)="deploy()">
              <span [kjIcon]="'plus'" kjIconSize="sm"></span>
              Deploy app
            </kj-button>
          </div>
        </div>
      </div>
    }

    <!-- ══ Grant access modal (client-side) ═════════════════════ -->
    @if (grantOpen()) {
      <div class="scrim" (click)="closeGrant()">
        <div
          class="modal"
          role="dialog"
          aria-modal="true"
          aria-label="Grant app access"
          (click)="$event.stopPropagation()"
          data-testid="grant-modal"
        >
          <div class="modal-head">
            <span class="vx-label">Grant access</span>
            <h3>Grant app access</h3>
            <button class="icon-x" type="button" aria-label="Close" (click)="closeGrant()">
              <span [kjIcon]="'x'" kjIconSize="sm"></span>
            </button>
          </div>
          <div class="modal-body">
            <div class="field">
              <span class="field-label">Grant to</span>
              <div class="seg">
                @for (p of principalTypes; track p) {
                  <button type="button" class="seg-btn" [class.active]="grantForm.type() === p" (click)="grantForm.type.set(p)">
                    {{ p }}
                  </button>
                }
              </div>
            </div>
            <label class="field">
              <span class="field-label">{{ grantForm.type() === 'team' ? 'Team' : 'Member' }}</span>
              <select [value]="grantForm.who()" (change)="grantForm.who.set($any($event.target).value)">
                @for (o of grantForm.type() === 'team' ? teams : owners; track o) {
                  <option [value]="o">{{ o }}</option>
                }
              </select>
            </label>
            <div class="field">
              <span class="field-label">App role</span>
              <div class="seg">
                @for (r of roles; track r) {
                  <button type="button" class="seg-btn" [class.active]="grantForm.role() === r" (click)="grantForm.role.set(r)">
                    {{ r }}
                  </button>
                }
              </div>
            </div>
          </div>
          <div class="modal-foot">
            <kj-button kjVariant="ghost" kjSize="sm" (click)="closeGrant()">Cancel</kj-button>
            <kj-button kjVariant="primary" kjSize="sm" (click)="grant()">Grant</kj-button>
          </div>
        </div>
      </div>
    }
  `,
})
export class Apps {
  private readonly data = inject(AppsData);
  protected readonly auth = inject(AuthService);

  /** Apps the signed-in member can use (member "My Apps" view). */
  readonly myApps = signal(this.data.myApps());

  readonly owners = this.data.ownerOptions();
  readonly teams = this.data.teamOptions();
  readonly policies = this.data.policyOptions();
  readonly principalTypes: PrincipalType[] = ['team', 'member'];
  readonly roles = ['app_member', 'app_admin'] as const;
  readonly tabs: { id: DetailTab; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'access', label: 'Access' },
    { id: 'routing', label: 'Routing' },
    { id: 'keys', label: 'Keys' },
    { id: 'usage', label: 'Usage' },
  ];

  /** Live app list (mutable copy so client-side deploy/grant reflect). */
  private readonly rows = signal<App[]>(this.data.apps());
  readonly apps = computed(() => this.rows());

  readonly selectedId = signal<string | null>(null);
  readonly selected = computed(() => this.rows().find((a) => a.id === this.selectedId()) ?? null);

  readonly tab = signal<DetailTab>('overview');
  readonly failOn429 = signal(true);

  readonly deployOpen = signal(false);
  readonly grantOpen = signal(false);

  readonly deployForm = {
    name: signal(''),
    owner: signal(this.owners[0]),
    team: signal(this.teams[0]),
    policy: signal(this.policies[0]),
  };
  readonly grantForm = {
    type: signal<PrincipalType>('team'),
    who: signal(this.teams[0]),
    role: signal<(typeof this.roles)[number]>('app_member'),
  };

  meta(prov: RouteProvider) {
    return this.data.meta(prov);
  }

  open(a: App): void {
    this.selectedId.set(a.id);
    this.tab.set('overview');
  }
  back(): void {
    this.selectedId.set(null);
  }

  grantsFor(a: App): AppGrant[] {
    return a.grants;
  }

  stats(a: App): { label: string; value: string }[] {
    return [
      { label: 'Spend · MTD', value: '$' + this.money(a.spend) },
      { label: 'Requests', value: this.compact(a.requests) },
      { label: 'p50 latency', value: a.latency + 'ms' },
      { label: 'Error rate', value: a.errRate.toFixed(2) + '%' },
      { label: 'Access grants', value: String(a.grants.length) },
      { label: 'Service keys', value: String(a.keys.length) },
    ];
  }

  kindLabel(k: AppKind): string {
    return k === 'system' ? 'System' : k === 'service' ? 'Service' : 'Personal';
  }
  kindIcon(k: AppKind): string {
    return k === 'system' ? 'message-square' : k === 'service' ? 'cpu' : 'book';
  }

  pct(value: number, rows: { value: number }[]): number {
    const max = Math.max(...rows.map((r) => r.value), 1);
    return Math.round((value / max) * 100);
  }

  money(n: number): string {
    return n.toLocaleString('en-US');
  }
  compact(n: number): string {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k';
    return String(n);
  }

  // ── Deploy modal ──
  openDeploy(): void {
    this.deployForm.name.set('');
    this.deployOpen.set(true);
  }
  closeDeploy(): void {
    this.deployOpen.set(false);
  }
  deploy(): void {
    const name = this.deployForm.name().trim() || 'New service';
    const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    const app: App = {
      id: 'app_' + slug + '_' + Date.now(),
      name,
      kind: 'service',
      owner: this.deployForm.owner(),
      tech: 'svc-' + (slug.split('-')[0] || 'new'),
      access: this.deployForm.team(),
      status: 'active',
      spend: 0,
      requests: 0,
      latency: 0,
      errRate: 0,
      policy: this.deployForm.policy(),
      grants: [
        { who: this.deployForm.team(), principalType: 'team', role: 'app_member', via: 'team grant' },
        { who: this.deployForm.owner(), principalType: 'member', role: 'app_admin', via: 'direct' },
      ],
      keys: [
        {
          name: 'default',
          kind: 'default',
          mask: 'vtx_live_••••' + Math.random().toString(16).slice(2, 6),
          status: 'active',
          rules: 'All models',
          rate: '600 RPM',
          created: 'just now',
          lastUsed: '—',
        },
      ],
      routing: [
        { model: this.deployForm.policy().split(' ')[0], prov: 'anthropic', role: 'Primary', binding: 'app cred' },
      ],
      usageByMember: [],
      usageByModel: [],
    };
    this.rows.update((r) => [...r, app]);
    this.closeDeploy();
    this.open(app);
  }

  // ── Grant modal ──
  openGrant(): void {
    this.grantForm.type.set('team');
    this.grantForm.who.set(this.teams[0]);
    this.grantForm.role.set('app_member');
    this.grantOpen.set(true);
  }
  closeGrant(): void {
    this.grantOpen.set(false);
  }
  grant(): void {
    const a = this.selected();
    if (!a) return;
    const g: AppGrant = {
      who: this.grantForm.who(),
      principalType: this.grantForm.type(),
      role: this.grantForm.role(),
      via: this.grantForm.type() === 'team' ? 'team grant' : 'direct',
    };
    this.rows.update((rows) =>
      rows.map((x) => (x.id === a.id ? { ...x, grants: [...x.grants, g] } : x)),
    );
    this.closeGrant();
  }
  removeGrant(a: App, g: AppGrant): void {
    this.rows.update((rows) =>
      rows.map((x) => (x.id === a.id ? { ...x, grants: x.grants.filter((y) => y !== g) } : x)),
    );
  }

  // ── Key actions (client-side stubs) ──
  rotate(k: ServiceKey): void {
    void k;
  }
  revoke(k: ServiceKey): void {
    void k;
  }
}
