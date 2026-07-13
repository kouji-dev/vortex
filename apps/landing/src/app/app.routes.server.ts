import { RenderMode, ServerRoute } from '@angular/ssr';

/**
 * The landing page is a single route rendered on the server for every request
 * (fresh SSR HTML, no build-time prerender needed for the marketing beta).
 */
export const serverRoutes: ServerRoute[] = [
  // Catalog pages fetch the live /v1/catalog in the browser → client render
  // (no SSR-time coupling to the API).
  { path: 'models', renderMode: RenderMode.Client },
  { path: 'models/:id', renderMode: RenderMode.Client },
  { path: 'providers/:id', renderMode: RenderMode.Client },
  {
    path: '**',
    renderMode: RenderMode.Server,
  },
];
