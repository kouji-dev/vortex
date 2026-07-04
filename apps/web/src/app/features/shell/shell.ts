import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { KjAvatarComponent } from '@kouji-ui/components';
import { KjIconDirective } from '@kouji-ui/core';
import { Prism } from '../../shared/prism/prism';
import { AuthService, type OrgRole } from '../../shared/data/auth-service';
import { ThemeToggle } from '../../shared/theme/theme-toggle';

interface NavItem {
  label: string;
  path: string;
  icon: string;
  badge?: string;
}
interface NavGroup {
  group: string;
  items: NavItem[];
}

/** Admin console IA (plan §D1). */
const ADMIN_NAV: NavGroup[] = [
  {
    group: 'Admin Console',
    items: [
      { label: 'Overview', path: '/overview', icon: 'home' },
      { label: 'Usage & Budgets', path: '/usage', icon: 'cpu' },
      { label: 'Teams & Members', path: '/teams', icon: 'users' },
      { label: 'Apps', path: '/apps', icon: 'layers' },
      { label: 'Providers & Models', path: '/providers', icon: 'database' },
      { label: 'Audit & Alerts', path: '/audit', icon: 'shield' },
      { label: 'Billing', path: '/billing', icon: 'credit-card' },
      { label: 'Settings', path: '/settings', icon: 'settings' },
    ],
  },
];

/** Member workspace IA (plan §D1). */
const MEMBER_NAV: NavGroup[] = [
  {
    group: 'Workspace',
    items: [
      { label: 'Home', path: '/me/home', icon: 'home' },
      { label: 'My Usage & Budget', path: '/me/usage', icon: 'cpu' },
      { label: 'My Keys', path: '/me/keys', icon: 'key' },
      { label: 'My Apps', path: '/me/apps', icon: 'layers' },
      { label: 'Profile & Settings', path: '/me/profile', icon: 'settings' },
    ],
  },
];

const ROLE_LABEL: Record<OrgRole, string> = {
  owner: 'Owner',
  admin: 'Admin',
  member: 'Member',
};

/** Authenticated layout: topbar + left sidebar + routed content. */
@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    KjAvatarComponent,
    KjIconDirective,
    ThemeToggle,
    Prism,
  ],
  styleUrl: './shell.css',
  template: `
    <div class="shell">
      <aside class="sidebar">
        <div class="brand">
          <vx-prism [size]="18" gradId="vxWebShell" />
          <span class="brand-word vx-display">Vortex</span>
        </div>

        <nav class="nav">
          @for (grp of nav(); track grp.group) {
            <div class="nav-group-label vx-label">{{ grp.group }}</div>
            @for (item of grp.items; track item.path) {
              <a
                class="nav-item"
                [routerLink]="item.path"
                routerLinkActive="active"
                attr.data-testid="nav-{{ item.path }}"
              >
                <span class="nav-icon" [kjIcon]="item.icon" kjIconSize="sm"></span>
                <span class="nav-label">{{ item.label }}</span>
                @if (item.badge) {
                  <span class="nav-badge">{{ item.badge }}</span>
                }
              </a>
            }
          }
        </nav>

        <div class="sidebar-foot">
          <button
            type="button"
            class="who"
            data-testid="account-menu"
            aria-haspopup="menu"
            [attr.aria-expanded]="menuOpen()"
            (click)="toggleMenu($event)"
          >
            <kj-avatar [content]="initials()" size="sm" />
            <span class="who-meta">
              <span class="who-name" data-testid="sidebar-account">{{ displayName() }}</span>
              <span class="who-role">{{ roleLabel() }}</span>
            </span>
            <span class="who-caret" [kjIcon]="menuOpen() ? 'chevron-down' : 'chevron-up'" kjIconSize="sm"></span>
          </button>
          @if (menuOpen()) {
            <div class="account-menu" role="menu" data-testid="account-menu-panel">
              <div class="account-menu-label">{{ displayName() }} · {{ roleLabel() }}</div>
              <button class="account-menu-item" role="menuitem" (click)="goSettings()">
                <span kjIcon="settings" kjIconSize="sm"></span>
                {{ settingsLabel() }}
              </button>
              <div class="account-menu-sep"></div>
              <button
                class="account-menu-item danger"
                role="menuitem"
                data-testid="logout"
                (click)="onLogout()"
              >
                <span kjIcon="log-out" kjIconSize="sm"></span>
                Sign out
              </button>
            </div>
          }
        </div>
      </aside>

      <div class="content">
        <header class="topbar">
          <div class="org">
            <span class="vx-label">Organisation</span>
            <span class="org-name">{{ orgName() }}</span>
          </div>
          <div class="topbar-actions">
            <vx-theme-toggle />
          </div>
        </header>

        <main class="main">
          <router-outlet />
        </main>
      </div>
    </div>
  `,
})
export class Shell {
  readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly nav = computed(() => (this.auth.isAdmin() ? ADMIN_NAV : MEMBER_NAV));

  readonly displayName = computed(() => {
    const u = this.auth.user();
    return u?.name || u?.email || 'Account';
  });

  readonly initials = computed(() =>
    this.displayName()
      .split(/[\s@.]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase() ?? '')
      .join(''),
  );

  readonly roleLabel = computed(() => {
    const role = this.auth.user()?.role;
    return role ? ROLE_LABEL[role] : '';
  });

  readonly orgName = computed(() => this.auth.user()?.orgName ?? 'Vortex');

  /** Account menu entry — admins go to org Settings, members to their profile
      (mirrors Vortex.dc.html openUserMenu: 'Settings' vs 'Profile & settings'). */
  readonly settingsLabel = computed(() =>
    this.auth.isAdmin() ? 'Settings' : 'Profile & settings',
  );
  private readonly settingsPath = computed(() =>
    this.auth.isAdmin() ? '/settings' : '/me/profile',
  );

  /** Account dropdown — click to open, outside-click + Esc to close. */
  readonly menuOpen = signal(false);

  toggleMenu(event: Event): void {
    event.stopPropagation();
    this.menuOpen.update((v) => !v);
  }

  @HostListener('document:click')
  closeMenu(): void {
    if (this.menuOpen()) this.menuOpen.set(false);
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.menuOpen()) this.menuOpen.set(false);
  }

  async goSettings(): Promise<void> {
    this.menuOpen.set(false);
    await this.router.navigate([this.settingsPath()]);
  }

  async onLogout(): Promise<void> {
    this.menuOpen.set(false);
    await this.auth.signOut();
    await this.router.navigate(['/login']);
  }
}
