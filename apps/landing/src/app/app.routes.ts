import { Routes } from '@angular/router';

/**
 * The marketing site is a single long-scroll landing page. All navigation
 * is in-page (anchor sections). Product CTAs (Sign in / Start free) leave
 * to the tenant console app.
 */
export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./features/landing/landing').then((m) => m.Landing),
  },
  { path: '**', redirectTo: '' },
];
