import { RenderMode, ServerRoute } from '@angular/ssr';

/**
 * The landing page is a single route rendered on the server for every request
 * (fresh SSR HTML, no build-time prerender needed for the marketing beta).
 */
export const serverRoutes: ServerRoute[] = [
  {
    path: '**',
    renderMode: RenderMode.Server,
  },
];
