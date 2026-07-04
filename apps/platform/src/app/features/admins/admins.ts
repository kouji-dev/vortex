import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  KjButtonComponent,
  KjBadgeComponent,
  KjFieldComponent,
  KjFieldLabelComponent,
  KjInputComponent,
} from '@kouji-ui/components';
import { PlatformService, type PlatformAdmin } from '../../shared/data/platform-service';

const ROLES = ['platform_owner', 'platform_admin', 'support'];

/** Platform Admins — vendor staff + roles (plan §D2). */
@Component({
  selector: 'app-admins',
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
          <h1>Platform Admins</h1>
          <p>Vendor staff with access to this console, and their roles.</p>
        </div>
      </div>

      @if (error()) {
        <div class="banner err" data-testid="admins-error">{{ error() }}</div>
      }

      <div class="card">
        <div class="card-head"><h2>Add platform admin</h2></div>
        <div class="toolbar">
          <kj-field>
            <kj-field-label>Email address</kj-field-label>
            <kj-input
              type="email"
              data-testid="admin-email"
              placeholder="staff@vortex.dev"
              [(ngModel)]="newEmail"
              (keydown.enter)="onAdd()"
            />
          </kj-field>
          <div class="filter">
            <span class="vx-label">Role</span>
            <select data-testid="admin-role" [(ngModel)]="newRole">
              @for (r of roles; track r) {
                <option [value]="r">{{ r }}</option>
              }
            </select>
          </div>
          <kj-button
            kjSize="sm"
            data-testid="admin-add"
            [kjDisabled]="busy() || !newEmail.trim()"
            (click)="onAdd()"
          >
            Add
          </kj-button>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h2>Platform admins</h2>
          <span class="vx-label">{{ admins().length }} total</span>
        </div>
        @if (loading()) {
          <div class="empty">Loading…</div>
        } @else if (admins().length === 0) {
          <div class="empty" data-testid="admins-empty">No platform admins yet.</div>
        } @else {
          <div class="tbl-wrap">
            <table class="tbl" data-testid="admins-table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Role</th>
                </tr>
              </thead>
              <tbody>
                @for (a of admins(); track a.id ?? a.email) {
                  <tr>
                    <td class="strong">{{ a.email }}</td>
                    <td><kj-badge variant="secondary" size="xs">{{ a.role }}</kj-badge></td>
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
export class Admins {
  private readonly platform = inject(PlatformService);

  readonly admins = signal<PlatformAdmin[]>([]);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly roles = ROLES;
  newEmail = '';
  newRole = 'platform_admin';

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      this.admins.set(await this.platform.admins());
      this.error.set(null);
    } catch {
      this.error.set('Could not load platform admins.');
    } finally {
      this.loading.set(false);
    }
  }

  async onAdd(): Promise<void> {
    const email = this.newEmail.trim();
    if (!email || this.busy()) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.platform.addAdmin(email, this.newRole);
      this.newEmail = '';
      await this.load();
    } catch {
      this.error.set('Could not add platform admin.');
    } finally {
      this.busy.set(false);
    }
  }
}
