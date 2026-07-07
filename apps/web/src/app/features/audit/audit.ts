import { Component, computed, inject, signal } from '@angular/core';
import { KjAvatarComponent, KjBadgeComponent, KjButtonComponent, KjTagComponent } from '@kouji-ui/components';
import { KjIconDirective } from '@kouji-ui/core';
import {
  AuditData,
  type Alert,
  type AlertSeverity,
} from './audit.data';

type Tab = 'audit' | 'alerts';

/**
 * Audit & Alerts admin screen (plan §D6). Two signal-switched sections:
 * a tamper-evident, hash-chained audit log with actor/action filters, and a
 * spend-anomaly / budget alerts feed with client-side acknowledge. Data from
 * {@link AuditData}; filtered and mutated client-side until the audit +
 * anomaly APIs land.
 */
@Component({
  selector: 'app-audit',
  standalone: true,
  imports: [KjAvatarComponent, KjBadgeComponent, KjButtonComponent, KjTagComponent, KjIconDirective],
  styleUrl: './audit.css',
  template: `
    <section class="page">
      <div class="page-head">
        <div>
          <span class="vx-label">Admin Console</span>
          <h1>Audit &amp; Alerts</h1>
          <p>
            A tamper-evident record of every privileged action, and live
            spend-anomaly &amp; budget alerts. Each audit entry is hash-chained
            to the one before it.
          </p>
        </div>
        <div class="head-actions">
          @if (tab() === 'audit') {
            <kj-button kjVariant="ghost" kjSize="sm">
              <span [kjIcon]="'shield'" kjIconSize="xs"></span>
              Verify chain
            </kj-button>
            <kj-button kjVariant="ghost" kjSize="sm">
              <span [kjIcon]="'upload'" kjIconSize="xs"></span>
              Export
            </kj-button>
          } @else {
            <kj-button kjVariant="ghost" kjSize="sm">
              <span [kjIcon]="'settings'" kjIconSize="xs"></span>
              Alert rules
            </kj-button>
          }
        </div>
      </div>

      <!-- ── Tabs ── -->
      <div class="page-tabs" role="tablist" aria-label="Audit sections">
        <button
          type="button"
          class="page-tab"
          role="tab"
          [class.active]="tab() === 'audit'"
          [attr.aria-selected]="tab() === 'audit'"
          (click)="tab.set('audit')"
        >
          <span [kjIcon]="'shield'" kjIconSize="xs"></span>
          Audit log
        </button>
        <button
          type="button"
          class="page-tab"
          role="tab"
          [class.active]="tab() === 'alerts'"
          [attr.aria-selected]="tab() === 'alerts'"
          (click)="tab.set('alerts')"
        >
          <span [kjIcon]="'bell'" kjIconSize="xs"></span>
          Alerts
          @if (openCount() > 0) {
            <span class="tab-count">{{ openCount() }}</span>
          }
        </button>
      </div>

      <!-- ══ AUDIT LOG ══ -->
      @if (tab() === 'audit') {
        <div class="panel">
          <!-- chain verified banner -->
          <div class="chain-bar">
            <span class="chain-verified">
              <span [kjIcon]="'shield'" kjIconSize="sm"></span>
              Hash chain verified · {{ data.chain.entries.toLocaleString() }} entries
            </span>
            <span class="chain-meta vx-mono">
              Last verified {{ data.chain.verifiedAgo }} · {{ data.chain.algo }}
            </span>
          </div>

          <!-- filters -->
          <div class="filters">
            <div class="search">
              <span class="glyph" [kjIcon]="'search'" kjIconSize="xs"></span>
              <input
                type="search"
                placeholder="Search actor, action or target…"
                [value]="query()"
                (input)="query.set($any($event.target).value)"
              />
            </div>
            <label class="filter">
              <span class="filter-label vx-label">Actor</span>
              <select [value]="actor()" (change)="actor.set($any($event.target).value)">
                @for (a of data.actors; track a) {
                  <option [value]="a">{{ a }}</option>
                }
              </select>
            </label>
            <label class="filter">
              <span class="filter-label vx-label">Action</span>
              <select [value]="actionGroup()" (change)="actionGroup.set($any($event.target).value)">
                @for (g of data.actionGroups; track g) {
                  <option [value]="g">{{ g }}</option>
                }
              </select>
            </label>
          </div>

          <div class="table-wrap">
            <table class="vx-table audit">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>Target</th>
                  <th>Hash chain</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                @for (e of filteredEvents(); track e.seq) {
                  <tr>
                    <td class="vx-mono muted nowrap">{{ e.time }}</td>
                    <td>
                      <span class="actor">
                        @if (e.system) {
                          <span class="sys-avatar" [kjIcon]="'cpu'" kjIconSize="xs"></span>
                          <span class="actor-name sys">system</span>
                        } @else {
                          <kj-avatar [content]="initials(e.actor)" size="xs"></kj-avatar>
                          <span class="actor-name">{{ e.actor }}</span>
                        }
                      </span>
                    </td>
                    <td><span class="action vx-mono">{{ e.action }}</span></td>
                    <td class="target">{{ e.target }}</td>
                    <td>
                      <span class="hash-chain" [title]="'prev ' + e.prevHash + ' → ' + e.hash">
                        <span class="hash prev vx-mono">{{ e.prevHash }}</span>
                        <span class="hash-link" [kjIcon]="'shield'" kjIconSize="xs"></span>
                        <span class="hash this vx-mono">{{ e.hash }}</span>
                      </span>
                    </td>
                    <td class="num">
                      <kj-badge variant="default" size="xs">
                        <span [kjIcon]="'check'" kjIconSize="xs"></span> linked
                      </kj-badge>
                    </td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="6" class="empty">No audit entries match your filters.</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <p class="chain-note">
            <span [kjIcon]="'shield'" kjIconSize="xs"></span>
            Each entry hashes its own contents plus the previous entry's hash.
            Any tampering breaks the chain and is detected on verify.
          </p>
        </div>
      }

      <!-- ══ ALERTS ══ -->
      @if (tab() === 'alerts') {
        <div class="panel">
          <div class="alert-summary">
            <kj-badge variant="secondary" size="xs">{{ counts().critical }} critical</kj-badge>
            <kj-badge variant="secondary" size="xs">{{ counts().warn }} warnings</kj-badge>
            <kj-badge variant="default" size="xs">{{ counts().info }} signals</kj-badge>
            <span class="spacer"></span>
            <span class="vx-label">{{ openCount() }} open · {{ ackCount() }} acknowledged</span>
          </div>

          <div class="alert-list">
            @for (a of alerts(); track a.id) {
              <div class="alert-card" [class.acked]="a.status === 'ack'">
                <span class="sev-icon" [class]="'sev-' + a.severity">
                  <span [kjIcon]="sevIcon(a.severity)" kjIconSize="sm"></span>
                </span>
                <div class="alert-body">
                  <div class="alert-title-row">
                    <kj-badge [variant]="a.severity === 'info' ? 'default' : 'secondary'" size="xs">
                      {{ a.kind }}
                    </kj-badge>
                    <span class="alert-title">{{ a.title }}</span>
                  </div>
                  <p class="alert-detail">{{ a.detail }}</p>
                  <div class="alert-foot">
                    <span class="alert-entity">
                      <span class="glyph" [kjIcon]="'user'" kjIconSize="xs"></span>
                      {{ a.entity }}
                    </span>
                    <span class="alert-tags">
                      @for (t of a.tags; track t) {
                        <kj-tag>{{ t }}</kj-tag>
                      }
                    </span>
                  </div>
                </div>
                <div class="alert-side">
                  <span class="alert-when vx-mono">{{ a.when }}</span>
                  @if (a.status === 'ack') {
                    <span class="pill pill-ok">
                      <span [kjIcon]="'check'" kjIconSize="xs"></span> acknowledged
                    </span>
                  } @else {
                    <kj-button kjVariant="ghost" kjSize="sm" (click)="ack(a)">
                      Acknowledge
                    </kj-button>
                  }
                </div>
              </div>
            }
          </div>
        </div>
      }
    </section>
  `,
})
export class Audit {
  protected readonly data = inject(AuditData);

  readonly tab = signal<Tab>('audit');

  // ── Audit filters ──
  readonly query = signal('');
  readonly actor = signal('Any');
  readonly actionGroup = signal('Any');

  readonly filteredEvents = computed(() => {
    const q = this.query().trim().toLowerCase();
    const actor = this.actor();
    const group = this.actionGroup();
    return this.data.events.filter((e) => {
      if (actor !== 'Any' && e.actor !== actor) return false;
      if (group !== 'Any' && e.action.split('.')[0] !== group) return false;
      if (q && !`${e.actor} ${e.action} ${e.target}`.toLowerCase().includes(q)) return false;
      return true;
    });
  });

  // ── Alerts (client-side ack) ──
  readonly alerts = signal<Alert[]>(this.data.alerts.map((a) => ({ ...a })));

  readonly counts = computed(() => {
    const list = this.alerts();
    return {
      critical: list.filter((a) => a.severity === 'critical').length,
      warn: list.filter((a) => a.severity === 'warn').length,
      info: list.filter((a) => a.severity === 'info').length,
    };
  });
  readonly openCount = computed(() => this.alerts().filter((a) => a.status === 'open').length);
  readonly ackCount = computed(() => this.alerts().filter((a) => a.status === 'ack').length);

  ack(alert: Alert): void {
    this.alerts.update((list) =>
      list.map((a) => (a.id === alert.id ? { ...a, status: 'ack' } : a)),
    );
  }

  initials(name: string): string {
    return name
      .split(/\s+/)
      .map((p) => p.charAt(0))
      .join('')
      .slice(0, 2)
      .toUpperCase();
  }

  sevIcon(sev: AlertSeverity): string {
    return sev === 'critical' ? 'alert-triangle' : sev === 'warn' ? 'bell' : 'sparkle';
  }
}
