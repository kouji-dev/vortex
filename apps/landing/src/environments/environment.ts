/**
 * Development environment. `ng build`/`ng serve` (no `--configuration=production`)
 * use this file; the production build swaps it for environment.prod.ts via the
 * angular.json fileReplacements. Point `apiUrl` at the gateway that serves the
 * public GET /v1/catalog.
 */
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8080',
};
