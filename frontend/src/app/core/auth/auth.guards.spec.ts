import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  CanMatchFn,
  provideRouter,
  Route,
  RouterStateSnapshot,
  UrlSegment,
  UrlTree,
} from '@angular/router';
import { provideHttpClient } from '@angular/common/http';

import { fakeToken, TEST_ROUTES } from '../../testing/fake-token';
import { authGuard, roleGuard } from './auth.guards';

/** Calls the CanMatch guard the way the router would, for the URL /approvals. */
function matchManager(): ReturnType<CanMatchFn> {
  const guard = roleGuard('manager') as (...args: unknown[]) => ReturnType<CanMatchFn>;
  return guard({} as Route, [new UrlSegment('approvals', {})], {});
}

function configure(token?: string): void {
  sessionStorage.clear();
  if (token) {
    sessionStorage.setItem('leavedesk.token', token);
  }
  TestBed.configureTestingModule({ providers: [provideRouter(TEST_ROUTES), provideHttpClient()] });
}

describe('route guards (UI-6)', () => {
  afterEach(() => sessionStorage.clear());

  it('roleGuard("manager") lets a manager in', () => {
    configure(fakeToken('E-MO', 'manager'));
    const result = TestBed.runInInjectionContext(() => matchManager());
    expect(result).toBe(true);
  });

  it('roleGuard("manager") sends an employee to /leave', () => {
    configure(fakeToken('E-ANA', 'employee'));
    const result = TestBed.runInInjectionContext(() => matchManager());
    expect(result instanceof UrlTree && result.toString()).toBe('/leave');
  });

  it('roleGuard("manager") sends a signed-out visitor to /login, back to /approvals afterwards', () => {
    configure();
    const result = TestBed.runInInjectionContext(() => matchManager());
    expect(result instanceof UrlTree && result.toString()).toBe('/login?returnUrl=%2Fapprovals');
  });

  it('authGuard sends a signed-out user to /login with a returnUrl', () => {
    configure();
    const result = TestBed.runInInjectionContext(() =>
      authGuard({} as ActivatedRouteSnapshot, { url: '/leave' } as RouterStateSnapshot),
    );
    expect(result instanceof UrlTree && result.toString()).toBe('/login?returnUrl=%2Fleave');
  });
});
