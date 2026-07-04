import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  KjButtonComponent,
  KjBadgeComponent,
  KjFieldComponent,
  KjFieldLabelComponent,
  KjInputComponent,
} from '@kouji-ui/components';
import {
  PlatformService,
  formatUsd,
  type Tenant,
} from '../../shared/data/platform-service';

/** Tenants — list all orgs + provision / suspend / reactivate / delete (plan §D2). */
@Component({
  selector: 'app-tenants',
  standalone: true,
  imports: [
    FormsModule,
    KjButtonComponent,
    KjBadgeComponent,
    KjFieldComponent,
    KjFieldLabelComponent,
    KjInputComponent,
  ],
  styleUrls: ['../_shared/console.css'],
  template: `
    <section class="page">
      <div class="page-head">
        <div>
          <span class="vx-label">Super-admin</span>
          <h1>Tenants</h1>
          <p>Every tenant organisation across the SaaS — provision, suspend, reactivate or delete.</p>
        </div>
      </div>

      @if (error()) {
        <div class="banner err" data-testid="tenants-error">{{ error() }}</div>
      }

      <div class="card">
        <div class="card-head">
          <h2>Provision tenant</h2>
        </div>
        <div class="toolbar">
          <kj-field>
            <kj-field-label>Organisation name</kj-field-label>
            <kj-input
              data-testid="tenant-name"
              placeholder="Acme Inc."
              [(ngModel)]="newName"
              (keydown.enter)="onProvision()"
            />
          </kj-field>
          <kj-button
            kjSize="sm"
            data-testid="tenant-provision"
            [kjDisabled]="busy() || !newName.trim()"
            (click)="onProvision()"
          >
            Provision
          </kj-button>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h2>All tenants</h2>
          <span class="vx-label">{{ tenants().length }} total</span>
        </div>

        @if (loading()) {
          <div class="empty">Loading…</div>
        } @else if (tenants().length === 0) {
          <div class="empty" data-testid="tenants-empty">No tenants provisioned yet.</div>
        } @else {
          <div class="tbl-wrap">
            <table class="tbl" data-testid="tenants-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Plan</th>
                  <th class="num">Members</th>
                  <th class="num">Apps</th>
                  <th class="num">Spend · MTD</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                @for (t of tenants(); track t.id) {
                  <tr attr.data-testid="tenant-row-{{ t.id }}">
                    <td class="strong">{{ t.name }}</td>
                    <td>
                      <kj-badge [variant]="t.status === 'active' ? 'default' : 'destructive'" size="xs">
                        {{ t.status }}
                      </kj-badge>
                    </td>
                    <td class="mono">{{ t.planId ?? '—' }}</td>
                    <td class="num">{{ t.members }}</td>
                    <td class="num">{{ t.apps }}</td>
                    <td class="num">{{ usd(t.spendMicro) }}</td>
                    <td>
                      <div class="row-actions">
                        @if (t.status === 'active') {
                          <kj-button
                            kjVariant="ghost"
                            kjSize="sm"
                            [kjDisabled]="busy()"
                            attr.data-testid="tenant-suspend-{{ t.id }}"
                            (click)="onSuspend(t)"
                          >
                            Suspend
                          </kj-button>
                        } @else {
                          <kj-button
                            kjVariant="ghost"
                            kjSize="sm"
                            [kjDisabled]="busy()"
                            attr.data-testid="tenant-reactivate-{{ t.id }}"
                            (click)="onReactivate(t)"
                          >
                            Reactivate
                          </kj-button>
                        }
                        <kj-button
                          kjVariant="destructive"
                          kjSize="sm"
                          [kjDisabled]="busy()"
                          attr.data-testid="tenant-delete-{{ t.id }}"
                          (click)="onDelete(t)"
                        >
                          Delete
                        </kj-button>
                      </div>
                    </td>
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
export class Tenants {
  private readonly platform = inject(PlatformService);

  readonly tenants = signal<Tenant[]>([]);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  newName = '';

  usd = formatUsd;

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      this.tenants.set(await this.platform.tenants());
      this.error.set(null);
    } catch {
      this.error.set('Could not load tenants.');
    } finally {
      this.loading.set(false);
    }
  }

  async onProvision(): Promise<void> {
    const name = this.newName.trim();
    if (!name || this.busy()) return;
    await this.run(() => this.platform.provisionTenant(name), 'Could not provision tenant.');
    this.newName = '';
  }

  async onSuspend(t: Tenant): Promise<void> {
    await this.run(() => this.platform.suspendTenant(t.id), 'Could not suspend tenant.');
  }

  async onReactivate(t: Tenant): Promise<void> {
    await this.run(() => this.platform.reactivateTenant(t.id), 'Could not reactivate tenant.');
  }

  async onDelete(t: Tenant): Promise<void> {
    await this.run(() => this.platform.deleteTenant(t.id), 'Could not delete tenant.');
  }

  private async run(op: () => Promise<void>, failMsg: string): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await op();
      await this.load();
    } catch {
      this.error.set(failMsg);
    } finally {
      this.busy.set(false);
    }
  }
}
