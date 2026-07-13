import { environment } from '../../../environments/environment';

/** Where product CTAs (Sign in / Start free) lead — the tenant console app. */
export const APP_URL = 'http://localhost:4200';

/**
 * Gateway API base — serves the public GET /v1/catalog for the models pages.
 * Driven by the Angular environment (dev → localhost:8080, prod → same-origin);
 * override per deployment in src/environments/environment*.ts.
 */
export const API_URL = environment.apiUrl;
