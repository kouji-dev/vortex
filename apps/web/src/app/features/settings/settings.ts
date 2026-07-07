import { Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { KjBadgeComponent, KjButtonComponent, KjToggleComponent } from '@kouji-ui/components';
import { KjIconDirective } from '@kouji-ui/core';
import { AuthService } from '../../shared/data/auth-service';
import { BillingService } from '../../shared/data/billing-service';
import { ThemeService, VxTheme } from '../../shared/theme/theme-service';
import { SESSION_POLICIES, SessionPolicy, SettingsService } from './settings.data';

/**
 * Organisation Settings admin screen (plan §D · `scrSettings`). Org profile,
 * security policy, interface & notification defaults and the lifecycle danger
 * zone. Single-tenant — there is no org switcher. Toggles, inputs and the
 * delete-org confirm are client-side signals; the org API lands in a later
 * pass. Theme is wired live to {@link ThemeService}.
 */
@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [KjBadgeComponent, KjButtonComponent, KjToggleComponent, KjIconDirective],
  styleUrl: './settings.css',
  template: `
    <section class="page">
      @if (auth.isAdmin()) {
      <div class="page-head">
        <div>
          <span class="vx-label">Admin Console</span>
          <h1>Settings</h1>
          <p>
            Organization profile, security and lifecycle. {{ org.name }} is a
            single organization — there is no org switcher.
          </p>
        </div>
      </div>

      <div class="settings-stack">
        <!-- 1 · Organisation profile -->
        <div class="panel">
          <div class="panel-head">
            <h2>Organization profile</h2>
            <span class="vx-label">identity &amp; billing</span>
          </div>

          <div class="org-id">
            <span class="org-logo">{{ org.monogram }}</span>
            <div class="org-id-text">
              <span class="org-name">{{ org.name }}</span>
              <span class="org-meta vx-mono"
                >{{ org.id }} · created {{ org.created }}</span
              >
            </div>
            <kj-button kjVariant="ghost" kjSize="sm">
              <span [kjIcon]="'image'" kjIconSize="sm"></span>
              Change logo
            </kj-button>
          </div>

          <div class="field-row">
            <label class="field">
              <span class="field-label">Organization name</span>
              <input
                class="input"
                [value]="orgName()"
                (input)="orgName.set(val($event))"
              />
            </label>
            <label class="field">
              <span class="field-label">Billing email</span>
              <input
                class="input"
                [value]="billingEmail()"
                (input)="billingEmail.set(val($event))"
              />
            </label>
          </div>

          <div class="stat-grid">
            <div class="stat">
              <span class="stat-k vx-label">Plan</span>
              <span class="stat-v">{{ sub()?.plan?.name ?? org.plan }}</span>
            </div>
            <div class="stat">
              <span class="stat-k vx-label">Region</span>
              <span class="stat-v">{{ org.region }}</span>
            </div>
            <div class="stat">
              <span class="stat-k vx-label">Members</span>
              <span class="stat-v vx-mono">{{ seatsUsed() }} / {{ seatsLimit() }}</span>
            </div>
          </div>

          <div class="panel-foot">
            <kj-button
              kjVariant="accent"
              kjSize="sm"
              [kjLoading]="saving()"
              (click)="saveProfile()"
            >
              Save changes
            </kj-button>
            @if (savedProfile()) {
              <span class="saved-note">
                <span [kjIcon]="'check'" kjIconSize="xs"></span>Saved
              </span>
            }
          </div>
        </div>

        <!-- 2 · Security -->
        <div class="panel">
          <div class="panel-head">
            <h2>Security</h2>
            <span class="vx-label">access &amp; identity</span>
          </div>

          <div class="rules">
            <div class="rule">
              <div class="rule-main">
                <span class="rule-title">Allowed email domains</span>
                <span class="rule-desc">Restrict invites to verified domains.</span>
              </div>
              <input
                class="input rule-input"
                [value]="domains()"
                (input)="domains.set(val($event))"
              />
            </div>

            <div class="rule">
              <div class="rule-main">
                <span class="rule-title">Session timeout</span>
                <span class="rule-desc">Idle logout for the console.</span>
              </div>
              <select
                class="input rule-select"
                [value]="sessionPolicy()"
                (change)="sessionPolicy.set(asPolicy($event))"
              >
                @for (o of policies; track o) {
                  <option [value]="o">{{ o }}</option>
                }
              </select>
            </div>

            <div class="rule">
              <div class="rule-main">
                <span class="rule-title">Enforce 2FA</span>
                <span class="rule-desc">Require two-factor for every member.</span>
              </div>
              <kj-toggle
                appearance="switch"
                ariaLabel="Enforce two-factor authentication"
                [pressed]="enforce2fa()"
                (pressedChange)="enforce2fa.set($event)"
              ></kj-toggle>
            </div>

            <div class="rule">
              <div class="rule-main">
                <span class="rule-title">
                  SSO / SAML
                  <kj-badge variant="secondary" size="xs">Roadmap</kj-badge>
                </span>
                <span class="rule-desc">Single sign-on via your IdP.</span>
              </div>
              <kj-toggle
                appearance="switch"
                ariaLabel="Enable SSO / SAML"
                [pressed]="sso()"
                (pressedChange)="sso.set($event)"
              ></kj-toggle>
            </div>

            <div class="rule">
              <div class="rule-main">
                <span class="rule-title">
                  SCIM provisioning
                  <kj-badge variant="secondary" size="xs">Roadmap</kj-badge>
                </span>
                <span class="rule-desc">Auto-provision &amp; deprovision members.</span>
              </div>
              <kj-toggle
                appearance="switch"
                ariaLabel="Enable SCIM provisioning"
                [pressed]="scim()"
                (pressedChange)="scim.set($event)"
              ></kj-toggle>
            </div>
          </div>
        </div>

        <!-- 3 · Interface & notifications -->
        <div class="panel">
          <div class="panel-head">
            <h2>Interface &amp; notifications</h2>
            <span class="vx-label">appearance &amp; alerts</span>
          </div>

          <div class="rules">
            <div class="rule">
              <div class="rule-main">
                <span class="rule-title">Theme</span>
                <span class="rule-desc">Console appearance for your account.</span>
              </div>
              <div class="seg">
                <button
                  type="button"
                  class="seg-btn"
                  [class.on]="theme() === 'light'"
                  (click)="setTheme('light')"
                >
                  Light
                </button>
                <button
                  type="button"
                  class="seg-btn"
                  [class.on]="theme() === 'dark'"
                  (click)="setTheme('dark')"
                >
                  Dark
                </button>
              </div>
            </div>

            <div class="rule">
              <div class="rule-main">
                <span class="rule-title">Density</span>
                <span class="rule-desc">Row spacing for tables and lists.</span>
              </div>
              <div class="seg">
                <button
                  type="button"
                  class="seg-btn"
                  [class.on]="density() === 'comfortable'"
                  (click)="density.set('comfortable')"
                >
                  Comfortable
                </button>
                <button
                  type="button"
                  class="seg-btn"
                  [class.on]="density() === 'compact'"
                  (click)="density.set('compact')"
                >
                  Compact
                </button>
              </div>
            </div>

            <div class="rule">
              <div class="rule-main">
                <span class="rule-title">Budget-alert emails</span>
                <span class="rule-desc">Email owners when a team nears its cap.</span>
              </div>
              <kj-toggle
                appearance="switch"
                ariaLabel="Budget-alert emails"
                [pressed]="budgetAlerts()"
                (pressedChange)="budgetAlerts.set($event)"
              ></kj-toggle>
            </div>

            <div class="rule">
              <div class="rule-main">
                <span class="rule-title">Weekly digest</span>
                <span class="rule-desc">A Monday summary of spend and traffic.</span>
              </div>
              <kj-toggle
                appearance="switch"
                ariaLabel="Weekly digest email"
                [pressed]="weeklyDigest()"
                (pressedChange)="weeklyDigest.set($event)"
              ></kj-toggle>
            </div>
          </div>
        </div>

        <!-- 4 · Danger zone -->
        <div class="panel danger-panel">
          <div class="danger-head">
            <span [kjIcon]="'alert-triangle'" kjIconSize="sm"></span>
            Danger zone
          </div>
          <div class="danger-body">
            <div class="rule">
              <div class="rule-main">
                <span class="rule-title">Transfer ownership</span>
                <span class="rule-desc">Hand this org to another owner.</span>
              </div>
              <kj-button kjVariant="ghost" kjSize="sm">Transfer</kj-button>
            </div>
            <div class="rule rule-last">
              <div class="rule-main">
                <span class="rule-title danger-title">Delete organization</span>
                <span class="rule-desc"
                  >Permanently remove the org, all teams, apps, keys and logs.</span
                >
              </div>
              <button type="button" class="danger-btn" (click)="openDelete()">
                <span [kjIcon]="'x'" kjIconSize="sm"></span>Delete
              </button>
            </div>
          </div>
        </div>
      </div>
      } @else {
        <!-- ══ MEMBER · Profile & Settings (scrMyProfile) ═════════ -->
        <div class="page-head">
          <div>
            <span class="vx-label">My account</span>
            <h1>Profile &amp; Settings</h1>
            <p>Your profile, password and interface defaults.</p>
          </div>
        </div>

        <div class="settings-stack">
          <!-- 1 · Profile -->
          <div class="panel">
            <div class="panel-head">
              <h2>Profile</h2>
              <span class="vx-label">name &amp; identity</span>
            </div>

            <div class="org-id">
              <span class="org-logo">{{ myMonogram() }}</span>
              <div class="org-id-text">
                <span class="org-name">{{ myName() }}</span>
                <span class="org-meta"
                  >{{ myEmail() }} · {{ myRole() }} · {{ member.team }} team</span
                >
              </div>
              <kj-button kjVariant="ghost" kjSize="sm">
                <span [kjIcon]="'image'" kjIconSize="sm"></span>
                Change photo
              </kj-button>
            </div>

            <div class="field-row">
              <label class="field">
                <span class="field-label">Full name</span>
                <input
                  class="input"
                  [value]="myName()"
                  (input)="myName.set(val($event))"
                />
              </label>
              <label class="field">
                <span class="field-label">Email</span>
                <input
                  class="input"
                  [value]="myEmail()"
                  (input)="myEmail.set(val($event))"
                />
              </label>
            </div>

            <div class="panel-foot">
              <kj-button
                kjVariant="accent"
                kjSize="sm"
                [kjLoading]="saving()"
                (click)="saveProfile()"
              >
                Save profile
              </kj-button>
              @if (savedProfile()) {
                <span class="saved-note">
                  <span [kjIcon]="'check'" kjIconSize="xs"></span>Saved
                </span>
              }
            </div>
          </div>

          <!-- 2 · Password -->
          <div class="panel">
            <div class="panel-head">
              <h2>Password</h2>
              <span class="vx-label">account security</span>
            </div>

            <div class="field-row">
              <label class="field">
                <span class="field-label">Current password</span>
                <input
                  class="input"
                  type="password"
                  [value]="currentPw()"
                  (input)="currentPw.set(val($event))"
                />
              </label>
              <label class="field">
                <span class="field-label">New password</span>
                <input
                  class="input"
                  type="password"
                  placeholder="12+ characters"
                  [value]="newPw()"
                  (input)="newPw.set(val($event))"
                />
              </label>
            </div>

            <div class="rules">
              <div class="rule rule-last">
                <div class="rule-main">
                  <span class="rule-title">Two-factor authentication</span>
                  <span class="rule-desc">Require a second factor at sign-in.</span>
                </div>
                <kj-toggle
                  appearance="switch"
                  ariaLabel="Two-factor authentication"
                  [pressed]="twoFactor()"
                  (pressedChange)="twoFactor.set($event)"
                ></kj-toggle>
              </div>
            </div>

            <div class="panel-foot">
              <kj-button kjVariant="accent" kjSize="sm" (click)="updatePassword()">
                Update password
              </kj-button>
              @if (pwUpdated()) {
                <span class="saved-note">
                  <span [kjIcon]="'check'" kjIconSize="xs"></span>Password updated
                </span>
              }
            </div>
          </div>

          <!-- 3 · Interface & notifications -->
          <div class="panel">
            <div class="panel-head">
              <h2>Interface &amp; notifications</h2>
              <span class="vx-label">appearance &amp; alerts</span>
            </div>

            <div class="rules">
              <div class="rule">
                <div class="rule-main">
                  <span class="rule-title">Theme</span>
                  <span class="rule-desc">Console appearance for your account.</span>
                </div>
                <div class="seg">
                  <button
                    type="button"
                    class="seg-btn"
                    [class.on]="theme() === 'light'"
                    (click)="setTheme('light')"
                  >
                    Light
                  </button>
                  <button
                    type="button"
                    class="seg-btn"
                    [class.on]="theme() === 'dark'"
                    (click)="setTheme('dark')"
                  >
                    Dark
                  </button>
                </div>
              </div>

              <div class="rule">
                <div class="rule-main">
                  <span class="rule-title">Density</span>
                  <span class="rule-desc">Table &amp; control spacing.</span>
                </div>
                <div class="seg">
                  <button
                    type="button"
                    class="seg-btn"
                    [class.on]="density() === 'comfortable'"
                    (click)="density.set('comfortable')"
                  >
                    Comfortable
                  </button>
                  <button
                    type="button"
                    class="seg-btn"
                    [class.on]="density() === 'compact'"
                    (click)="density.set('compact')"
                  >
                    Compact
                  </button>
                </div>
              </div>

              <div class="rule">
                <div class="rule-main">
                  <span class="rule-title">Budget alerts</span>
                  <span class="rule-desc">Email me at 80% and 100% of my budget.</span>
                </div>
                <kj-toggle
                  appearance="switch"
                  ariaLabel="Budget alerts"
                  [pressed]="budgetAlerts()"
                  (pressedChange)="budgetAlerts.set($event)"
                ></kj-toggle>
              </div>

              <div class="rule rule-last">
                <div class="rule-main">
                  <span class="rule-title">Weekly usage digest</span>
                  <span class="rule-desc">A summary of my spend every Monday.</span>
                </div>
                <kj-toggle
                  appearance="switch"
                  ariaLabel="Weekly usage digest"
                  [pressed]="weeklyDigest()"
                  (pressedChange)="weeklyDigest.set($event)"
                ></kj-toggle>
              </div>
            </div>
          </div>
        </div>
      }
    </section>

    <!-- Delete-org confirm modal -->
    @if (deleteOpen()) {
      <div class="scrim" (click)="closeDelete()">
        <div
          class="modal"
          role="dialog"
          aria-label="Delete organization"
          (click)="stop($event)"
        >
          <div class="modal-crumb vx-label danger-crumb">
            <span [kjIcon]="'alert-triangle'" kjIconSize="xs"></span>Danger
          </div>
          <h3 class="modal-title">Delete {{ org.name }}?</h3>
          <p class="modal-sub">
            This deletes <b>{{ org.members }} members</b>, all teams, apps, keys,
            budgets and logs. This cannot be undone.
          </p>
          <label class="field">
            <span class="field-label">Type DELETE to confirm</span>
            <input
              class="input"
              placeholder="DELETE"
              [value]="confirmText()"
              (input)="confirmText.set(val($event))"
            />
          </label>
          <div class="modal-foot">
            <kj-button kjVariant="ghost" kjSize="sm" (click)="closeDelete()"
              >Cancel</kj-button
            >
            <span class="spacer"></span>
            <button
              type="button"
              class="danger-btn"
              [disabled]="!canDelete()"
              (click)="closeDelete()"
            >
              Delete forever
            </button>
          </div>
        </div>
      </div>
    }
  `,
})
export class Settings {
  private readonly svc = inject(SettingsService);
  private readonly themeSvc = inject(ThemeService);
  private readonly billing = inject(BillingService);
  protected readonly auth = inject(AuthService);

  protected readonly org = this.svc.org;
  protected readonly member = this.svc.member;
  protected readonly policies = SESSION_POLICIES;

  // Live plan + seat usage (falls back to demo values before the call resolves).
  protected readonly sub = toSignal(this.billing.getSubscription());
  protected readonly seatsUsed = computed(() => this.sub()?.seats.used ?? this.org.members);
  protected readonly seatsLimit = computed(
    () => this.sub()?.seats.limit ?? this.org.seats,
  );

  // Member profile (name / email / role prefer the live session).
  readonly myName = signal(this.auth.user()?.name ?? this.svc.member.name);
  readonly myEmail = signal(this.auth.user()?.email ?? this.svc.member.email);
  readonly myRole = computed(() => this.auth.user()?.role ?? this.svc.member.role);
  readonly myMonogram = computed(() =>
    this.myName()
      .split(' ')
      .map((s) => s[0])
      .slice(0, 2)
      .join('')
      .toUpperCase(),
  );

  // Member password panel (client-side stub).
  readonly currentPw = signal('');
  readonly newPw = signal('');
  readonly pwUpdated = signal(false);
  readonly twoFactor = signal(true);

  // Org profile
  readonly orgName = signal(this.org.name);
  readonly billingEmail = signal(this.org.billingEmail);
  readonly saving = signal(false);
  readonly savedProfile = signal(false);

  // Security
  readonly domains = signal(this.svc.allowedDomains);
  readonly sessionPolicy = signal<SessionPolicy>(this.svc.sessionPolicy);
  readonly enforce2fa = signal(true);
  readonly sso = signal(false);
  readonly scim = signal(false);

  // Interface & notifications
  readonly theme = this.themeSvc.theme;
  readonly density = signal<'comfortable' | 'compact'>('comfortable');
  readonly budgetAlerts = signal(true);
  readonly weeklyDigest = signal(true);

  // Danger zone
  readonly deleteOpen = signal(false);
  readonly confirmText = signal('');
  readonly canDelete = computed(() => this.confirmText().trim() === 'DELETE');

  // ---- actions ----
  setTheme(t: VxTheme): void {
    if (this.theme() !== t) this.themeSvc.toggle();
  }
  saveProfile(): void {
    // Placeholder: org API persistence lands in a later pass.
    this.saving.set(true);
    this.savedProfile.set(false);
    setTimeout(() => {
      this.saving.set(false);
      this.savedProfile.set(true);
    }, 400);
  }
  updatePassword(): void {
    // Placeholder: password API persistence lands in a later pass.
    this.pwUpdated.set(true);
    this.currentPw.set('');
    this.newPw.set('');
  }
  openDelete(): void {
    this.confirmText.set('');
    this.deleteOpen.set(true);
  }
  closeDelete(): void {
    this.deleteOpen.set(false);
  }

  // ---- template helpers ----
  val(e: Event): string {
    return (e.target as HTMLInputElement | HTMLSelectElement).value;
  }
  asPolicy(e: Event): SessionPolicy {
    return (e.target as HTMLSelectElement).value as SessionPolicy;
  }
  stop(e: Event): void {
    e.stopPropagation();
  }
}
