import { inject } from '@angular/core';
import { CanActivateFn, CanMatchFn, Router } from '@angular/router';

import { Role } from '../api.types';
import { AuthService } from './auth.service';

/**
 * Route guards decide whether a route may open (UI-6). They only improve the experience:
 * the API still rejects anything the user isn't allowed to do.
 */

/** Signed-in users only; others go to /login and come back afterwards. */
export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.isLoggedIn()
    ? true
    : router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
};

/** The login page is for signed-out users; signed-in users go to My leave. */
export const guestGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.isLoggedIn() ? router.createUrlTree(['/leave']) : true;
};

/**
 * Only users with this role may enter. It is a CanMatch guard, so for anyone else the route
 * doesn't match at all and its lazy code is never downloaded.
 * CanMatch runs before the parent's authGuard, so a signed-out visitor is sent to /login here,
 * with the page they wanted as returnUrl (otherwise they would come back to /leave).
 */
export function roleGuard(role: Role): CanMatchFn {
  return (_route, segments) => {
    const auth = inject(AuthService);
    const router = inject(Router);
    const user = auth.user();
    if (!user) {
      const returnUrl = '/' + segments.map((s) => s.path).join('/');
      return router.createUrlTree(['/login'], { queryParams: { returnUrl } });
    }
    return user.role === role ? true : router.createUrlTree(['/leave']);
  };
}
