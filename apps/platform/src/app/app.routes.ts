import { Routes } from '@angular/router';
import { authGuard, guestGuard } from './shared/auth/auth-guard';

/**
 * Platform super-admin console routes (plan §D2). A separate surface for
 * vendor staff (platform_admins), above all tenant orgs. v1 essentials:
 * Overview, Tenants, Usage, Plans, Platform Admins, Audit.
 */
export const routes: Routes = [
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/login/login').then((m) => m.Login),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./features/shell/shell').then((m) => m.Shell),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'overview' },
      {
        path: 'overview',
        loadComponent: () => import('./features/overview/overview').then((m) => m.Overview),
      },
      {
        path: 'tenants',
        loadComponent: () => import('./features/tenants/tenants').then((m) => m.Tenants),
      },
      {
        path: 'usage',
        loadComponent: () => import('./features/usage/usage').then((m) => m.Usage),
      },
      {
        path: 'plans',
        loadComponent: () => import('./features/plans/plans').then((m) => m.Plans),
      },
      {
        path: 'admins',
        loadComponent: () => import('./features/admins/admins').then((m) => m.Admins),
      },
      {
        path: 'audit',
        loadComponent: () => import('./features/audit/audit').then((m) => m.Audit),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
