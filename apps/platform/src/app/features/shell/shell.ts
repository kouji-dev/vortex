import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { KjAvatarComponent } from '@kouji-ui/components';
import { KjIconDirective } from '@kouji-ui/core';
import { Prism } from '../../shared/prism/prism';
import { PlatformAuthService } from '../../shared/data/platform-auth-service';
import { ThemeToggle } from '../../shared/theme/theme-toggle';

interface NavItem {
  label: string;
  path: string;
  icon: string;
}

/** Platform super-admin IA (plan §D2 essentials). */
const NAV: NavItem[] = [
  { label: 'Overview', path: '/overview', icon: 'home' },
  { label: 'Tenants', path: '/tenants', icon: 'building' },
  { label: 'Usage', path: '/usage', icon: 'cpu' },
  { label: 'Plans', path: '/plans', icon: 'layers' },
  { label: 'Platform Admins', path: '/admins', icon: 'shield' },
  { label: 'Audit', path: '/audit', icon: 'scroll-text' },
];

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
          <vx-prism [size]="18" gradId="vxPlatformShell" />
          <span class="brand-word vx-display">Vortex</span>
          <span class="platform-tag vx-label" data-testid="platform-badge">Platform</span>
        </div>

        <nav class="nav">
          @for (item of nav; track item.path) {
            <a
              class="nav-item"
              [routerLink]="item.path"
              routerLinkActive="active"
              attr.data-testid="nav-{{ item.path }}"
            >
              <span class="nav-icon" [kjIcon]="item.icon" kjIconSize="sm"></span>
              <span class="nav-label">{{ item.label }}</span>
            </a>
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
              <span class="who-role">Platform admin</span>
            </span>
            <span class="who-caret" [kjIcon]="menuOpen() ? 'chevron-down' : 'chevron-up'" kjIconSize="sm"></span>
          </button>
          @if (menuOpen()) {
            <div class="account-menu" role="menu" data-testid="account-menu-panel">
              <div class="account-menu-label">{{ displayName() }} · Platform admin</div>
              <button class="account-menu-item" role="menuitem" (click)="goAudit()">
                <span kjIcon="scroll-text" kjIconSize="sm"></span>
                Platform audit
              </button>
              <div class="account-menu-sep"></div>
              <button
                class="account-menu-item danger"
                role="menuitem"
                data-testid="menu-signout"
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
            <span class="vx-label">Super-admin</span>
            <span class="org-name">Platform console</span>
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
  readonly auth = inject(PlatformAuthService);
  private readonly router = inject(Router);

  readonly nav = NAV;

  readonly displayName = computed(() => this.auth.email() || 'Platform admin');

  readonly initials = computed(() =>
    this.displayName()
      .split(/[\s@.]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase() ?? '')
      .join(''),
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

  async goAudit(): Promise<void> {
    this.menuOpen.set(false);
    await this.router.navigate(['/audit']);
  }

  async onLogout(): Promise<void> {
    this.menuOpen.set(false);
    await this.auth.signOut();
    await this.router.navigate(['/login']);
  }
}
