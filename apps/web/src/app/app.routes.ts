import { Routes } from '@angular/router';
import { authGuard, guestGuard } from './shared/auth/auth-guard';

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
        data: { title: 'Usage & Budgets', sub: 'Cost explorer sliceable by team, member, app, key and model — plus team-default and per-member budgets.' },
        loadComponent: () => import('./features/stub/stub').then((m) => m.Stub),
      },
      {
        path: 'teams',
        data: { title: 'Teams & Members', sub: 'Teams, members and roles — human and technical — with each member’s keys.' },
        loadComponent: () => import('./features/stub/stub').then((m) => m.Stub),
      },
      {
        path: 'apps',
        data: { title: 'Apps', sub: 'Per-app access, routing, service keys, technical member and usage.' },
        loadComponent: () => import('./features/stub/stub').then((m) => m.Stub),
      },
      {
        path: 'providers',
        data: { title: 'Providers & Models', sub: 'Provider credentials and the enabled model catalog.' },
        loadComponent: () => import('./features/stub/stub').then((m) => m.Stub),
      },
      {
        path: 'audit',
        data: { title: 'Audit & Alerts', sub: 'Hash-chained audit log and spend anomaly alerts.' },
        loadComponent: () => import('./features/stub/stub').then((m) => m.Stub),
      },
      {
        path: 'billing',
        data: { title: 'Billing', sub: 'Plan, invoices and payment method via the Stripe customer portal (SaaS only).' },
        loadComponent: () => import('./features/stub/stub').then((m) => m.Stub),
      },
      {
        path: 'settings',
        data: { title: 'Settings', sub: 'Organisation profile, security and console preferences.' },
        loadComponent: () => import('./features/stub/stub').then((m) => m.Stub),
      },

      // ── Member workspace ──
      {
        path: 'me/home',
        data: { title: 'Home', sub: 'Your workspace — usage, budget and quick links.' },
        loadComponent: () => import('./features/stub/stub').then((m) => m.Stub),
      },
      {
        path: 'me/usage',
        data: { title: 'My Usage & Budget', sub: 'Your monthly spend against your effective budget ceiling.' },
        loadComponent: () => import('./features/stub/stub').then((m) => m.Stub),
      },
      {
        path: 'me/keys',
        data: { title: 'My Keys', sub: 'Your default and personal virtual keys.' },
        loadComponent: () => import('./features/stub/stub').then((m) => m.Stub),
      },
      {
        path: 'me/apps',
        data: { title: 'My Apps', sub: 'Apps you can access.' },
        loadComponent: () => import('./features/stub/stub').then((m) => m.Stub),
      },
      {
        path: 'me/profile',
        data: { title: 'Profile & Settings', sub: 'Your profile and personal preferences.' },
        loadComponent: () => import('./features/stub/stub').then((m) => m.Stub),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
