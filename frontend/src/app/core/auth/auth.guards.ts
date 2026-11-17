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
 */
export function roleGuard(role: Role): CanMatchFn {
  return () => {
    const auth = inject(AuthService);
    const router = inject(Router);
    return auth.user()?.role === role ? true : router.createUrlTree(['/leave']);
  };
}
