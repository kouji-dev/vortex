import { HttpInterceptorFn } from '@angular/common/http';

/** Ensures same-origin /api and /v1 calls send the session cookie. */
export const credentialsInterceptor: HttpInterceptorFn = (req, next) => {
  if (req.url.startsWith('/api') || req.url.startsWith('/v1')) {
    return next(req.clone({ withCredentials: true }));
  }
  return next(req);
};
