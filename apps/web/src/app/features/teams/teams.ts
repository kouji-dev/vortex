import { Component, computed, inject, signal } from '@angular/core';
import {
  KjAvatarComponent,
  KjButtonComponent,
  KjCellTemplateDirective,
  KjTableComponent,
} from '@kouji-ui/components';
import { KjIconDirective, kjColumn, type KjColumnDef } from '@kouji-ui/core';
import {
  Member,
  OrgRole,
  Team,
  TeamsService,
} from './teams.data';

/**
 * Teams & Members admin screen (plan §3a/3b). A team groups people and sets a
 * default per-member monthly budget; members carry an effective budget (team
 * default or a per-member override), an org role and a status. Create-team /
 * invite-member / budget-override are client-side signals — the org API lands
 * in a later pass.
 */
@Component({
  selector: 'app-teams',
  standalone: true,
  imports: [
    KjAvatarComponent,
    KjButtonComponent,
    KjIconDirective,
    KjTableComponent,
    KjCellTemplateDirective,
  ],
  styleUrl: './teams.css',
  template: `
    <section class="page">
      <div class="page-tabs">
        <button
          class="page-tab"
          [class.active]="tab() === 'teams'"
          (click)="tab.set('teams')"
        >
          Teams
        </button>
        <button
          class="page-tab"
          [class.active]="tab() === 'members'"
          (click)="tab.set('members')"
        >
          Members &amp; Roles
        </button>
      </div>

      @switch (tab()) {
        @case ('teams') {
          <div class="page-head">
            <div>
              <span class="vx-label">Admin Console</span>
              <h1>Teams</h1>
              <p>
                A team groups people and sets a
                <b>default monthly budget per member</b>. A team admin manages
                membership and the team default; each member belongs to exactly
                one team.
              </p>
            </div>
            <div class="head-actions">
              <kj-button kjVariant="accent" kjSize="sm" (click)="openCreateTeam()">
                <span [kjIcon]="'plus'" kjIconSize="sm"></span>
                Create team
              </kj-button>
            </div>
          </div>

          <div class="table-wrap" data-testid="teams-table">
            <kj-table
              [kjData]="teams"
              [kjColumns]="teamCols"
              [kjGetRowId]="teamRowId"
              [kjPageSize]="'all'"
              kjVariant="clean"
            >
              <ng-template kjCellTemplate="name" let-t="row">
                <span class="team-cell-name">
                  <span class="team-chip team-chip-sm">{{ t.name[0] }}</span>
                  <span class="team-name">{{ t.name }}</span>
                </span>
              </ng-template>
              <ng-template kjCellTemplate="def" let-t="row">
                <span class="cell-r vx-mono cell-strong">{{ money(t.def) }}/mo</span>
              </ng-template>
              <ng-template kjCellTemplate="enf" let-t="row">
                <span class="tag" [class.tag-err]="t.enf === 'hard'">{{
                  t.enf === 'hard' ? 'hard' : 'soft'
                }}</span>
              </ng-template>
              <ng-template kjCellTemplate="members" let-t="row">
                <span class="cell-r vx-mono">{{ t.members }}</span>
              </ng-template>
              <ng-template kjCellTemplate="spend" let-t="row">
                <span class="cell-r vx-mono cell-strong">{{ money(t.spend) }}</span>
              </ng-template>
              <ng-template kjCellTemplate="admin" let-t="row">
                <span class="admin-cell">
                  <kj-avatar [content]="initials(t.admin)" size="sm"></kj-avatar>
                  {{ t.admin }}
                </span>
              </ng-template>
              <ng-template kjCellTemplate="chevron">
                <span
                  class="chevron"
                  [kjIcon]="'chevron-right'"
                  kjIconSize="sm"
                ></span>
              </ng-template>
            </kj-table>
          </div>
        }

        @case ('members') {
          <div class="page-head">
            <div>
              <span class="vx-label">Admin Console</span>
              <h1>Members &amp; Roles</h1>
              <p>
                Everyone in {{ svc.orgName }} — humans and per-app service
                accounts. Org role, their one team, effective budget and status.
              </p>
            </div>
            <div class="head-actions">
              <kj-button kjVariant="accent" kjSize="sm" (click)="openInvite()">
                <span [kjIcon]="'send'" kjIconSize="sm"></span>
                Invite member
              </kj-button>
            </div>
          </div>

          <div class="legend">
          <span class="legend-k vx-label">Legend</span>
          <span class="legend-item"
            ><span class="tag">Human</span> a person</span
          >
          <span class="legend-item"
            ><span class="tag tag-accent"
              ><span [kjIcon]="'cpu'" kjIconSize="xs"></span>Service acct</span
            >
            auto-created per app</span
          >
          <span class="legend-sep">|</span>
          <span class="legend-item"
            ><span class="role role-owner">Owner</span> full control</span
          >
          <span class="legend-item"
            ><span class="role role-admin">Admin</span> manage everything</span
          >
          <span class="legend-item"
            ><span class="role role-member">Member</span> use keys</span
          >
        </div>

        <div class="table-wrap" data-testid="members-table">
          <kj-table
            [kjData]="members"
            [kjColumns]="memberCols"
            [kjGetRowId]="memberRowId"
            [kjPageSize]="'all'"
            kjVariant="clean"
          >
            <ng-template kjCellTemplate="name" let-m="row">
              <span class="member">
                @if (m.type === 'technical') {
                  <span class="svc-chip"
                    ><span [kjIcon]="'cpu'" kjIconSize="sm"></span
                  ></span>
                } @else {
                  <kj-avatar [content]="initials(m.name)" size="sm"></kj-avatar>
                }
                <span class="member-id">
                  <span class="member-name">{{ m.name }}</span>
                  <span class="member-sub">{{
                    m.type === 'technical'
                      ? 'service acct · ' + (m.app ?? '')
                      : m.email
                  }}</span>
                </span>
              </span>
            </ng-template>
            <ng-template kjCellTemplate="type" let-m="row">
              <span class="tag" [class.tag-accent]="m.type === 'technical'">
                @if (m.type === 'technical') {
                  <span [kjIcon]="'cpu'" kjIconSize="xs"></span>Service acct
                } @else {
                  Human
                }
              </span>
            </ng-template>
            <ng-template kjCellTemplate="role" let-m="row">
              <span class="role" [class]="'role role-' + m.role">{{
                cap(m.role)
              }}</span>
            </ng-template>
            <ng-template kjCellTemplate="team" let-m="row">
              <span class="team-cell">
                <span>{{ m.team }}</span>
                @if (m.teamRole === 'team_admin') {
                  <span class="tag tag-accent">admin</span>
                }
              </span>
            </ng-template>
            <ng-template kjCellTemplate="budget" let-m="row">
              <span class="cell-r">
                <span class="budget">
                  <span class="vx-mono budget-v">{{ money(m.budget) }}</span>
                  <span
                    class="budget-src"
                    [class.is-override]="m.bsrc === 'override'"
                    >{{ m.bsrc === 'override' ? 'override' : 'default' }}</span
                  >
                </span>
              </span>
            </ng-template>
            <ng-template kjCellTemplate="status" let-m="row">
              <span class="pill" [class]="'pill pill-' + m.status">
                <span class="dot"></span>{{ cap(m.status) }}
              </span>
            </ng-template>
            <ng-template kjCellTemplate="seen" let-m="row">
              <span class="cell-r vx-mono seen">{{ m.seen }}</span>
            </ng-template>
            <ng-template kjCellTemplate="actions" let-m="row">
              <span class="kebab-cell">
                <button
                  class="kebab"
                  type="button"
                  aria-label="Row actions"
                  (click)="toggleMenu(m.email)"
                >
                  <span [kjIcon]="'more'" kjIconSize="sm"></span>
                </button>
                @if (menuFor() === m.email) {
                  <div class="menu" role="menu">
                    <button class="menu-item" (click)="editRole(m)">
                      <span [kjIcon]="'user'" kjIconSize="xs"></span>Edit role
                    </button>
                    <button class="menu-item" (click)="openOverride(m)">
                      <span [kjIcon]="'settings'" kjIconSize="xs"></span>Set
                      budget override
                    </button>
                    <div class="menu-sep"></div>
                    <button class="menu-item danger" (click)="remove(m)">
                      <span [kjIcon]="'trash'" kjIconSize="xs"></span>Remove
                    </button>
                  </div>
                }
              </span>
            </ng-template>
          </kj-table>
        </div>
        }
      }
    </section>

    <!-- Create team modal -->
    @if (createTeamOpen()) {
      <div class="scrim" (click)="closeAll()">
        <div class="modal" role="dialog" aria-label="Create team" (click)="stop($event)">
          <div class="modal-crumb vx-label">
            <span [kjIcon]="'users'" kjIconSize="xs"></span>New team
          </div>
          <h3 class="modal-title">Create team</h3>
          <label class="field">
            <span class="field-label">Team name</span>
            <input class="input" placeholder="e.g. Platform" [value]="ctName()"
              (input)="ctName.set(val($event))" />
          </label>
          <label class="field">
            <span class="field-label">Team admin</span>
            <select class="input" [value]="ctAdmin()" (change)="ctAdmin.set(val($event))">
              @for (h of svc.activeHumans(); track h.email) {
                <option [value]="h.name">{{ h.name }}</option>
              }
            </select>
          </label>
          <div class="field-row">
            <label class="field">
              <span class="field-label">Default budget / member</span>
              <span class="money-input">
                <span class="money-cur">$</span>
                <input class="input" [value]="ctBudget()" (input)="ctBudget.set(val($event))" />
              </span>
            </label>
            <div class="field">
              <span class="field-label">Enforcement</span>
              <div class="seg">
                <button type="button" class="seg-btn" [class.on]="ctEnf() === 'hard'"
                  (click)="ctEnf.set('hard')">Hard</button>
                <button type="button" class="seg-btn" [class.on]="ctEnf() === 'soft'"
                  (click)="ctEnf.set('soft')">Soft</button>
              </div>
            </div>
          </div>
          <div class="modal-foot">
            <kj-button kjVariant="ghost" kjSize="sm" (click)="closeAll()">Cancel</kj-button>
            <span class="spacer"></span>
            <kj-button kjVariant="accent" kjSize="sm" (click)="closeAll()">Create team</kj-button>
          </div>
        </div>
      </div>
    }

    <!-- Invite member modal -->
    @if (inviteOpen()) {
      <div class="scrim" (click)="closeAll()">
        <div class="modal" role="dialog" aria-label="Invite members" (click)="stop($event)">
          <div class="modal-crumb vx-label">
            <span [kjIcon]="'send'" kjIconSize="xs"></span>Invite
          </div>
          <h3 class="modal-title">Invite members</h3>
          <p class="modal-sub">They'll get an email link to join {{ svc.orgName }}.</p>
          <label class="field">
            <span class="field-label">Email addresses</span>
            <textarea class="input" rows="3" placeholder="alice@company.com, bob@company.com"
              [value]="invEmails()" (input)="invEmails.set(val($event))"></textarea>
          </label>
          <div class="field-row">
            <label class="field">
              <span class="field-label">Org role</span>
              <select class="input" [value]="invRole()" (change)="invRole.set(val($event))">
                <option value="member">member</option>
                <option value="admin">admin</option>
                <option value="owner">owner</option>
              </select>
            </label>
            <label class="field">
              <span class="field-label">Team</span>
              <select class="input" [value]="invTeam()" (change)="invTeam.set(val($event))">
                @for (name of svc.teamNames(); track name) {
                  <option [value]="name">{{ name }}</option>
                }
              </select>
            </label>
          </div>
          <div class="note">
            Each new member joins one team and inherits its default budget.
          </div>
          <div class="modal-foot">
            <kj-button kjVariant="ghost" kjSize="sm" (click)="closeAll()">Cancel</kj-button>
            <span class="spacer"></span>
            <kj-button kjVariant="accent" kjSize="sm" (click)="closeAll()">Send invites</kj-button>
          </div>
        </div>
      </div>
    }

    <!-- Budget override editor -->
    @if (overrideMember(); as m) {
      <div class="scrim" (click)="closeAll()">
        <div class="modal" role="dialog" aria-label="Budget override" (click)="stop($event)">
          <div class="modal-crumb vx-label">
            <span [kjIcon]="'settings'" kjIconSize="xs"></span>Budget override
          </div>
          <h3 class="modal-title">{{ m.name }}</h3>
          <p class="modal-sub">
            {{ m.team }} team · default {{ money(ovTeamDefault()) }}/mo
          </p>
          <div class="field">
            <span class="field-label">Budget source</span>
            <div class="seg">
              <button type="button" class="seg-btn" [class.on]="ovSource() === 'default'"
                (click)="ovSource.set('default')">Team default</button>
              <button type="button" class="seg-btn" [class.on]="ovSource() === 'override'"
                (click)="ovSource.set('override')">Override</button>
            </div>
          </div>
          <label class="field">
            <span class="field-label">Monthly budget (override)</span>
            <span class="money-input" [class.disabled]="ovSource() === 'default'">
              <span class="money-cur">$</span>
              <input class="input" [value]="ovValue()" [disabled]="ovSource() === 'default'"
                (input)="ovValue.set(val($event))" />
            </span>
            <span class="field-hint"
              >Overrides the {{ money(ovTeamDefault()) }} team default for this
              member only.</span
            >
          </label>
          <div class="burn-card">
            <div class="burn-row">
              <span class="vx-mono">{{ money(m.spent) }} spent</span>
              <span class="vx-mono burn-cap">{{ Math.round(memberFrac(m) * 100) }}%</span>
            </div>
            <span class="bar-track">
              <span class="bar-fill"
                [class.bar-warn]="memberFrac(m) >= 0.8"
                [class.bar-err]="memberFrac(m) >= 1"
                [style.width.%]="pct(memberFrac(m))"></span>
            </span>
          </div>
          <div class="modal-foot">
            <kj-button kjVariant="ghost" kjSize="sm" (click)="closeAll()">Revert to default</kj-button>
            <span class="spacer"></span>
            <kj-button kjVariant="accent" kjSize="sm" (click)="closeAll()">Save override</kj-button>
          </div>
        </div>
      </div>
    }
  `,
})
export class Teams {
  protected readonly svc = inject(TeamsService);
  protected readonly Math = Math;

  readonly teams = this.svc.teams();
  readonly members = this.svc.members();

  // ---- kj-table column defs (custom cells rendered via kjCellTemplate) ----
  readonly teamCols: KjColumnDef<Team>[] = [
    kjColumn<Team>({ id: 'name', accessorKey: 'name', header: 'Team' }),
    kjColumn<Team>({ id: 'def', accessorKey: 'def', header: 'Default / member' }),
    kjColumn<Team>({ id: 'enf', accessorKey: 'enf', header: 'Enforce' }),
    kjColumn<Team>({ id: 'members', accessorKey: 'members', header: 'Members' }),
    kjColumn<Team>({ id: 'spend', accessorKey: 'spend', header: 'Spend · MTD' }),
    kjColumn<Team>({ id: 'admin', accessorKey: 'admin', header: 'Team admin' }),
    kjColumn<Team>({ id: 'chevron', header: '' }),
  ];
  readonly teamRowId = (t: Team): string => t.id;

  readonly memberCols: KjColumnDef<Member>[] = [
    kjColumn<Member>({ id: 'name', accessorKey: 'name', header: 'Member' }),
    kjColumn<Member>({ id: 'type', accessorKey: 'type', header: 'Type' }),
    kjColumn<Member>({ id: 'role', accessorKey: 'role', header: 'Org role' }),
    kjColumn<Member>({ id: 'team', accessorKey: 'team', header: 'Team' }),
    kjColumn<Member>({ id: 'budget', accessorKey: 'budget', header: 'Budget' }),
    kjColumn<Member>({ id: 'status', accessorKey: 'status', header: 'Status' }),
    kjColumn<Member>({ id: 'seen', accessorKey: 'seen', header: 'Last active' }),
    kjColumn<Member>({ id: 'actions', header: '' }),
  ];
  readonly memberRowId = (m: Member): string => m.email;

  // Top tab: teams | members
  readonly tab = signal<'teams' | 'members'>('teams');

  // Row kebab menu
  readonly menuFor = signal<string | null>(null);

  // Modals
  readonly createTeamOpen = signal(false);
  readonly inviteOpen = signal(false);
  readonly overrideMember = signal<Member | null>(null);

  // Create-team form
  readonly ctName = signal('');
  readonly ctAdmin = signal('');
  readonly ctBudget = signal('1,000');
  readonly ctEnf = signal<'hard' | 'soft'>('soft');

  // Invite form
  readonly invEmails = signal('');
  readonly invRole = signal('member');
  readonly invTeam = signal('');

  // Override editor
  readonly ovValue = signal('');
  readonly ovSource = signal<'default' | 'override'>('default');
  readonly ovTeamDefault = computed(() => {
    const m = this.overrideMember();
    return m ? this.svc.teamOf(m.team)?.def ?? 0 : 0;
  });

  // ---- money & progress helpers ----
  money(n: number): string {
    return '$' + n.toLocaleString('en-US');
  }
  teamFrac(t: { spend: number; def: number; members: number }): number {
    const cap = t.def * t.members;
    return cap ? t.spend / cap : 0;
  }
  memberFrac(m: Member): number {
    return m.budget ? m.spent / m.budget : 0;
  }
  pct(frac: number): number {
    return Math.min(frac * 100, 100);
  }
  cap(s: string): string {
    return s[0].toUpperCase() + s.slice(1);
  }
  initials(name: string): string {
    return name
      .split(' ')
      .map((p) => p[0])
      .slice(0, 2)
      .join('')
      .toUpperCase();
  }
  val(e: Event): string {
    return (e.target as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement).value;
  }
  stop(e: Event): void {
    e.stopPropagation();
  }

  // ---- actions ----
  toggleMenu(email: string): void {
    this.menuFor.update((cur) => (cur === email ? null : email));
  }
  openCreateTeam(): void {
    this.closeAll();
    this.ctAdmin.set(this.svc.activeHumans()[0]?.name ?? '');
    this.createTeamOpen.set(true);
  }
  openInvite(): void {
    this.closeAll();
    this.invTeam.set(this.svc.teamNames()[0] ?? '');
    this.inviteOpen.set(true);
  }
  openOverride(m: Member): void {
    this.closeAll();
    this.ovSource.set(m.bsrc);
    this.ovValue.set(m.budget.toLocaleString('en-US'));
    this.overrideMember.set(m);
  }
  editRole(m: Member): void {
    // Placeholder: role editing lands with the org API pass.
    this.menuFor.set(null);
    void (m.role as OrgRole);
  }
  remove(m: Member): void {
    // Placeholder: removal lands with the org API pass.
    this.menuFor.set(null);
    void m;
  }
  closeAll(): void {
    this.menuFor.set(null);
    this.createTeamOpen.set(false);
    this.inviteOpen.set(false);
    this.overrideMember.set(null);
  }
}
