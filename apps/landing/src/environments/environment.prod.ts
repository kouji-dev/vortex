/**
 * Production environment (swapped in by angular.json fileReplacements on the
 * production build). `apiUrl` is empty → the catalog is fetched same-origin
 * (`/v1/catalog`), i.e. the landing is served behind the same host as the
 * gateway. Set an absolute URL here if the API lives on a different origin.
 */
export const environment = {
  production: true,
  apiUrl: '',
};
