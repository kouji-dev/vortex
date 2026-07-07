import { Routes } from '@angular/router';
import { authGuard, guestGuard } from './shared/auth/auth-guard';
import { adminGuard } from './shared/auth/admin-guard';

/**
 * Route table for the tenant console. IA follows plan §D1: an admin
 * console (owner/admin) and a member workspace, both under the shell.
 * Non-trivial screens are stubs today (data wiring follows per feature).
 */
export const routes: Routes = [
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/login/login').then((m) => m.Login),
  },
  {
    path: 'signup',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/signup/signup').then((m) => m.Signup),
  },
  {
    path: 'forgot-password',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/forgot/forgot').then((m) => m.Forgot),
  },
  {
    path: 'reset-password',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/reset/reset').then((m) => m.Reset),
  },
  {
    // Public pricing (no auth) — the landing pricing table.
    path: 'pricing',
    loadComponent: () => import('./features/pricing/pricing').then((m) => m.Pricing),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./features/shell/shell').then((m) => m.Shell),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'overview' },

      // ── Admin console (owner/admin) ──
      {
        path: 'overview',
        loadComponent: () => import('./features/overview/overview').then((m) => m.Overview),
      },
      {
        path: 'usage',
        loadComponent: () => import('./features/usage/usage').then((m) => m.Usage),
      },
      {
        path: 'teams',
        canActivate: [adminGuard],
        loadComponent: () => import('./features/teams/teams').then((m) => m.Teams),
      },
      {
        path: 'apps',
        loadComponent: () => import('./features/apps/apps').then((m) => m.Apps),
      },
      {
        path: 'providers',
        canActivate: [adminGuard],
        loadComponent: () => import('./features/providers/providers').then((m) => m.Providers),
      },
      {
        path: 'audit',
        canActivate: [adminGuard],
        loadComponent: () => import('./features/audit/audit').then((m) => m.Audit),
      },
      {
        path: 'billing',
        canActivate: [adminGuard],
        loadComponent: () => import('./features/billing/billing').then((m) => m.Billing),
      },
      {
        path: 'settings',
        loadComponent: () => import('./features/settings/settings').then((m) => m.Settings),
      },

      // ── Member workspace ──
      // Member workspace shares the flat admin paths — each screen branches by
      // role (a member at /usage sees "My Usage & Budget", at /overview sees
      // "Home", at /settings sees "Profile"). Keys is member-specific.
      {
        path: 'keys',
        loadComponent: () => import('./features/keys/keys').then((m) => m.Keys),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
