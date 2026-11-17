import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { AuthService } from './auth.service';

const LOGIN_URL = '/api/auth/login';

/**
 * Runs on every HttpClient request (UI-4, UI-5).
 * 1. Adds "Authorization: Bearer <token>" to /api/ calls, except the login call itself.
 * 2. If the API answers 401 (token missing, expired or invalid), signs the user out.
 * Only /api/ URLs get the token, so it can never leak to another site.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const isApi = req.url.startsWith('/api/');
  const isLogin = req.url === LOGIN_URL;
  const token = auth.token();

  const request =
    isApi && !isLogin && token
      ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
      : req;

  return next(request).pipe(
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse && err.status === 401 && isApi && !isLogin) {
        auth.logout('expired');
      }
      return throwError(() => err);
    }),
  );
};
