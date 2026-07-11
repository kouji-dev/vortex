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
  {
    path: 'models',
    loadComponent: () => import('./features/catalog/catalog').then((m) => m.Catalog),
  },
  {
    path: 'models/:id',
    loadComponent: () => import('./features/catalog/model-detail').then((m) => m.ModelDetail),
  },
  {
    path: 'providers/:id',
    loadComponent: () => import('./features/catalog/provider-detail').then((m) => m.ProviderDetail),
  },
  { path: '**', redirectTo: '' },
];
