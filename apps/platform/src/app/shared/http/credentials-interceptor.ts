import { HttpInterceptorFn } from '@angular/common/http';

/** Ensures same-origin /api and /platform calls send the session cookie. */
export const credentialsInterceptor: HttpInterceptorFn = (req, next) => {
  if (req.url.startsWith('/api') || req.url.startsWith('/platform')) {
    return next(req.clone({ withCredentials: true }));
  }
  return next(req);
};
