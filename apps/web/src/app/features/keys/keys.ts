import { Component, computed, inject, signal } from '@angular/core';
import { KjButtonComponent } from '@kouji-ui/components';
import { KjIconDirective } from '@kouji-ui/core';
import { KeysService, VirtualKey } from './keys.data';

/**
 * My Keys — the member workspace screen (plan §D1, design scrMyKeys). Shows the
 * member's virtual keys: exactly one default key plus any personal keys. Each
 * key caps models / providers / IP + a rate limit, but has NO budget — every
 * request through any of these keys counts against the member's monthly budget.
 * Create / rotate / revoke are client-side signals; the key API lands later.
 */
@Component({
  selector: 'app-keys',
  standalone: true,
  imports: [KjButtonComponent, KjIconDirective],
  styleUrl: './keys.css',
  template: `
    <section class="page">
      <div class="page-head">
        <div>
          <span class="vx-label">Member Workspace</span>
          <h1>My Keys</h1>
          <p>
            Your <b>default</b> key plus any <b>personal</b> keys. Each has its
            own rules (models / providers / IP) and rate limit — but no budget.
            Requests through any of these keys count against your
            <b>monthly budget</b>.
          </p>
        </div>
        <div class="head-actions">
          <kj-button kjVariant="accent" kjSize="sm" (click)="openCreate()">
            <span [kjIcon]="'plus'" kjIconSize="sm"></span>
            Create key
          </kj-button>
        </div>
      </div>

      <!-- Budget context strip -->
      <div class="budget-strip" data-testid="keys-budget">
        <div class="budget-copy">
          <span [kjIcon]="'wallet'" kjIconSize="sm"></span>
          <span>
            Spend across all your keys counts against your monthly budget —
            <span class="vx-mono">{{ money(svc.spent) }}</span> of
            <span class="vx-mono">{{ money(svc.monthlyBudget) }}</span> used.
          </span>
        </div>
        <span class="bar-track">
          <span
            class="bar-fill"
            [class.bar-warn]="frac() >= 0.8"
            [class.bar-err]="frac() >= 1"
            [style.width.%]="pct()"
          ></span>
        </span>
      </div>

      <div class="table-wrap">
        <table class="tbl" data-testid="keys-table">
          <thead>
            <tr>
              <th>Key</th>
              <th>Rules</th>
              <th>Rate limit</th>
              <th>Status</th>
              <th class="ar">Created</th>
              <th class="ar">Last used</th>
              <th aria-label="Actions"></th>
            </tr>
          </thead>
          <tbody>
            @for (k of keys(); track k.id) {
              <tr [class.is-revoked]="k.status === 'revoked'">
                <td>
                  <span class="key-id">
                    <span class="key-name">
                      {{ k.name }}
                      <span class="tag" [class.tag-accent]="k.kind === 'default'">
                        {{ k.kind }}
                      </span>
                    </span>
                    <span class="key-mask vx-mono">{{ k.mask }}</span>
                  </span>
                </td>
                <td class="rules">{{ k.rules }}</td>
                <td class="vx-mono rate">{{ k.rate }}</td>
                <td>
                  <span class="pill" [class]="'pill pill-' + k.status">
                    <span class="dot"></span>{{ cap(k.status) }}
                  </span>
                </td>
                <td class="ar vx-mono meta">{{ k.created }}</td>
                <td class="ar vx-mono meta">{{ k.used }}</td>
                <td class="ar kebab-cell">
                  <button
                    class="kebab"
                    type="button"
                    aria-label="Key actions"
                    [disabled]="k.status === 'revoked'"
                    (click)="toggleMenu(k.id)"
                  >
                    <span [kjIcon]="'more'" kjIconSize="sm"></span>
                  </button>
                  @if (menuFor() === k.id) {
                    <div class="menu" role="menu">
                      <button class="menu-item" (click)="rotate(k)">
                        <span [kjIcon]="'loader'" kjIconSize="xs"></span>Rotate key
                      </button>
                      <div class="menu-sep"></div>
                      @if (k.kind === 'personal') {
                        <button class="menu-item danger" (click)="revoke(k)">
                          <span [kjIcon]="'x'" kjIconSize="xs"></span>Revoke key
                        </button>
                      } @else {
                        <button class="menu-item disabled" disabled>
                          <span [kjIcon]="'lock'" kjIconSize="xs"></span>Default
                          key — can't revoke
                        </button>
                      }
                    </div>
                  }
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>

    <!-- Create personal key modal (client-side) -->
    @if (createOpen()) {
      <div class="scrim" (click)="closeAll()">
        <div
          class="modal"
          role="dialog"
          aria-label="Create personal key"
          (click)="stop($event)"
        >
          <div class="modal-crumb vx-label">
            <span [kjIcon]="'key'" kjIconSize="xs"></span>New personal key
          </div>
          <h3 class="modal-title">Create personal key</h3>
          <p class="modal-sub">
            Keys are member-owned. Rules cap models / providers / IP + rate limit
            — never budget.
          </p>
          <label class="field">
            <span class="field-label">Key name</span>
            <input
              class="input"
              placeholder="e.g. ci-pipeline"
              [value]="ckName()"
              (input)="ckName.set(val($event))"
            />
          </label>
          <label class="field">
            <span class="field-label">Allowed models</span>
            <select class="input" [value]="ckRules()" (change)="ckRules.set(val($event))">
              <option value="All models">All models</option>
              <option value="claude-sonnet-4.5, gpt-4o">claude-sonnet-4.5, gpt-4o</option>
              <option value="gpt-4o-mini only">gpt-4o-mini only</option>
              <option value="gemini">gemini</option>
            </select>
          </label>
          <label class="field">
            <span class="field-label">Requests / min (RPM)</span>
            <input
              class="input vx-mono"
              placeholder="600"
              [value]="ckRate()"
              (input)="ckRate.set(val($event))"
            />
          </label>
          <div class="note">
            No per-key budget. Spend is governed by <b>your monthly budget</b>
            across all your keys and apps.
          </div>
          <div class="modal-foot">
            <kj-button kjVariant="ghost" kjSize="sm" (click)="closeAll()">Cancel</kj-button>
            <span class="spacer"></span>
            <kj-button kjVariant="accent" kjSize="sm" (click)="create()">Create key</kj-button>
          </div>
        </div>
      </div>
    }
  `,
})
export class Keys {
  protected readonly svc = inject(KeysService);

  readonly keys = this.svc.keys();

  readonly menuFor = signal<string | null>(null);
  readonly createOpen = signal(false);

  // Create-key form
  readonly ckName = signal('');
  readonly ckRules = signal('All models');
  readonly ckRate = signal('600');

  readonly frac = computed(() =>
    this.svc.monthlyBudget ? this.svc.spent / this.svc.monthlyBudget : 0,
  );

  money(n: number): string {
    return '$' + n.toLocaleString('en-US');
  }
  pct(): number {
    return Math.min(this.frac() * 100, 100);
  }
  cap(s: string): string {
    return s[0].toUpperCase() + s.slice(1);
  }
  val(e: Event): string {
    return (e.target as HTMLInputElement | HTMLSelectElement).value;
  }
  stop(e: Event): void {
    e.stopPropagation();
  }

  toggleMenu(id: string): void {
    this.menuFor.update((cur) => (cur === id ? null : id));
  }
  openCreate(): void {
    this.closeAll();
    this.ckName.set('');
    this.ckRules.set('All models');
    this.ckRate.set('600');
    this.createOpen.set(true);
  }
  create(): void {
    this.svc.add(this.ckName(), this.ckRules(), this.ckRate());
    this.closeAll();
  }
  rotate(k: VirtualKey): void {
    this.svc.rotate(k.id);
    this.menuFor.set(null);
  }
  revoke(k: VirtualKey): void {
    this.svc.revoke(k.id);
    this.menuFor.set(null);
  }
  closeAll(): void {
    this.menuFor.set(null);
    this.createOpen.set(false);
  }
}
