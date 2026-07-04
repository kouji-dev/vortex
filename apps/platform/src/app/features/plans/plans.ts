import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  KjButtonComponent,
  KjFieldComponent,
  KjFieldLabelComponent,
  KjInputComponent,
} from '@kouji-ui/components';
import { PlatformService, type Plan } from '../../shared/data/platform-service';

/** Plans — list tiers + create (plan §D2). */
@Component({
  selector: 'app-plans',
  standalone: true,
  imports: [
    FormsModule,
    KjButtonComponent,
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
          <h1>Plans</h1>
          <p>Billing tiers and entitlements assigned to tenant organisations.</p>
        </div>
      </div>

      @if (error()) {
        <div class="banner err" data-testid="plans-error">{{ error() }}</div>
      }

      <div class="card">
        <div class="card-head"><h2>Create plan</h2></div>
        <div class="toolbar">
          <kj-field>
            <kj-field-label>Plan name</kj-field-label>
            <kj-input data-testid="plan-name" placeholder="Growth" [(ngModel)]="newName" />
          </kj-field>
          <kj-field>
            <kj-field-label>Monthly price (USD)</kj-field-label>
            <kj-input data-testid="plan-price" type="number" placeholder="99" [(ngModel)]="newPrice" />
          </kj-field>
          <kj-button
            kjSize="sm"
            data-testid="plan-create"
            [kjDisabled]="busy() || !newName.trim()"
            (click)="onCreate()"
          >
            Create
          </kj-button>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h2>Plans</h2>
          <span class="vx-label">{{ plans().length }} total</span>
        </div>
        @if (loading()) {
          <div class="empty">Loading…</div>
        } @else if (plans().length === 0) {
          <div class="empty" data-testid="plans-empty">No plans defined yet.</div>
        } @else {
          <div class="tbl-wrap">
            <table class="tbl" data-testid="plans-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th class="num">Price · mo</th>
                  <th>Stripe price</th>
                </tr>
              </thead>
              <tbody>
                @for (p of plans(); track p.id) {
                  <tr>
                    <td class="strong">{{ p.name }}</td>
                    <td class="num">{{ p.price != null ? price(p.price) : '—' }}</td>
                    <td class="mono">{{ p.stripePriceId ?? '—' }}</td>
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
export class Plans {
  private readonly platform = inject(PlatformService);

  readonly plans = signal<Plan[]>([]);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  newName = '';
  newPrice: number | null = null;

  constructor() {
    void this.load();
  }

  /** Plan price is stored/displayed in whole USD. */
  price(usd: number): string {
    return usd.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      this.plans.set(await this.platform.plans());
      this.error.set(null);
    } catch {
      this.error.set('Could not load plans.');
    } finally {
      this.loading.set(false);
    }
  }

  async onCreate(): Promise<void> {
    const name = this.newName.trim();
    if (!name || this.busy()) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.platform.createPlan(name, this.newPrice ?? undefined);
      this.newName = '';
      this.newPrice = null;
      await this.load();
    } catch {
      this.error.set('Could not create plan.');
    } finally {
      this.busy.set(false);
    }
  }
}
